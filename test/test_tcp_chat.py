"""
Test TCP Chat & Multi-peer Messaging (đề bài mục 3.3, 4.1, 4.2, 5.1, 5.3).

Kiểm tra:
- Khởi tạo kết nối TCP và gửi IDENT nhận diện danh tính.
- Gửi và nhận tin nhắn văn bản hai chiều theo thời gian thực.
- Hỗ trợ đầy đủ bộ ký tự tiếng Việt Unicode và Emoji.
- Quản lý tin nhắn chưa đọc (unread count) và thông báo khi tin nhắn đến từ peer khác.
- Chuyển đổi qua lại giữa các phòng chat (/chat) và xem lại tin nhắn chưa đọc.
- Rời phòng chat an toàn bằng /leave (gửi gói BYE|).
- Xử lý khi peer ngắt kết nối đột ngột (crash/tắt app): phát hiện và thông báo.
- Hoạt động ổn định khi nhiều peer kết nối đồng thời.
"""

import socket
import time
import unittest

import helpers
from helpers import Output, Peer, connect_peers, wait_until


class TCPChatTests(unittest.TestCase):
    requirement = "TCP Chat - Phiên chat P2P, Unread Count & Multi-peer (3.3, 4.1, 4.2)"

    def setUp(self):
        self.peers = []

    def tearDown(self):
        for p in self.peers:
            p.stop()

    def make_peer(self, name):
        p = Peer(name=name)
        p.start()
        self.peers.append(p)
        return p

    def test_connect_and_ident_handshake(self):
        """Alice kết nối TCP tới Bob; Bob nhận gói tin IDENT và biết danh tính Alice."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        alice.add_contact(bob)

        success = alice.open_chat("Bob")
        self.assertTrue(success, "Alice phải kết nối thành công tới Bob")
        self.assertTrue(alice.out.wait_for("Connected to Bob"))

        # Kiểm tra Bob đã nhận diện kết nối từ Alice trong chat_conns
        self.assertTrue(
            wait_until(lambda: "Alice" in bob.node.chat_conns, timeout=2.0),
            "Bob phải nhận diện Alice qua gói IDENT",
        )

    def test_send_and_receive_message(self):
        """Alice gửi tin nhắn trong phiên chat; Bob nhận và hiển thị ngay lập tức."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        msg_text = "Xin chao Bob!"
        alice.send_message(msg_text)

        # Alice hiển thị tin mình vừa gửi
        self.assertTrue(alice.out.has(f"[Alice] {msg_text}"))

        # Bob nhận được và hiển thị
        self.assertTrue(
            bob.out.wait_for(f"[Alice] {msg_text}", timeout=2.0),
            "Bob phải nhận và hiển thị tin nhắn từ Alice",
        )

    def test_two_way_messaging(self):
        """Hai peer trò chuyện qua lại hai chiều liên tục."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        alice.send_message("Cau 1")
        self.assertTrue(bob.out.wait_for("[Alice] Cau 1"))

        bob.send_message("Tra loi 1")
        self.assertTrue(alice.out.wait_for("[Bob] Tra loi 1"))

        alice.send_message("Cau 2")
        self.assertTrue(bob.out.wait_for("[Alice] Cau 2"))

    def test_unicode_and_vietnamese_characters(self):
        """Tin nhắn tiếng Việt có dấu và Emoji UTF-8 được truyền toàn vẹn."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        special_msg = "Chào bạn! Đây là đồ án Lập Trình Mạng: 🌟🔥🎉"
        alice.send_message(special_msg)
        self.assertTrue(bob.out.wait_for(f"[Alice] {special_msg}", timeout=2.0))

    def test_unread_notification_when_partner_mismatch(self):
        """
        Đề bài mục 3.3:
        Nếu nhận tin từ peer không phải current_partner:
        - Tin nhắn được lưu vào bộ nhớ.
        - Hiển thị thông báo kèm bộ đếm chưa đọc (unread count).
        """
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        charlie = self.make_peer("Charlie")

        alice.add_contact(bob)
        bob.add_contact(charlie)
        bob.add_contact(alice)

        # Bob đang mở chat với Charlie
        bob.open_chat("Charlie")

        # Alice kết nối tới Bob và gửi tin
        alice.open_chat("Bob")
        wait_until(lambda: "Alice" in bob.node.chat_conns, timeout=2.0)
        alice.send_message("Hello Bob from Alice!")

        # Bob không hiển thị trực tiếp nội dung tin nhắn của Alice trong khung chat
        # mà hiển thị thông báo tin nhắn chưa đọc
        self.assertTrue(
            bob.out.wait_for("New message from Alice (1 unread)", timeout=2.0),
            "Bob phải thông báo có 1 tin chưa đọc từ Alice",
        )

        # Alice gửi tiếp tin thứ 2
        alice.send_message("Are you there?")
        self.assertTrue(
            bob.out.wait_for("New message from Alice (2 unread)", timeout=2.0),
            "Bob phải thông báo có 2 tin chưa đọc từ Alice",
        )

    def test_switch_chat_partner_displays_unread_history(self):
        """Khi chuyển sang chat với peer có tin nhắn chờ (/chat <name>), hiển thị lại lịch sử unread."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        charlie = self.make_peer("Charlie")

        alice.add_contact(bob)
        bob.add_contact(alice)
        bob.add_contact(charlie)

        # Bob đang bận với Charlie
        bob.open_chat("Charlie")

        # Alice gửi 2 tin nhắn tới Bob
        alice.open_chat("Bob")
        wait_until(lambda: "Alice" in bob.node.chat_conns, timeout=2.0)
        alice.send_message("Tin cho 1")
        alice.send_message("Tin cho 2")

        self.assertTrue(bob.out.wait_for("New message from Alice (2 unread)"))

        # Bob chuyển khung chat sang Alice
        bob.open_chat("Alice")

        # Bob phải hiển thị thông báo chuyển đổi kèm số lượng tin chưa đọc
        self.assertTrue(bob.out.wait_for("Switched to Alice — 2 unread:"))
        self.assertTrue(bob.out.has("[Alice] Tin cho 1"))
        self.assertTrue(bob.out.has("[Alice] Tin cho 2"))

        # Bộ đếm unread của Alice được xóa về 0
        self.assertEqual(bob.node.unread_counts.get("Alice", 0), 0)

    def test_leave_chat_sends_bye_and_resets_partner(self):
        """Lệnh /leave đóng phiên chat hiện tại, gửi gói tin BYE| và dọn dẹp state."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        # Alice rời chat
        alice.leave_chat()

        self.assertTrue(alice.out.has("Left chat with Bob."))
        self.assertIsNone(alice.node.current_partner)

        # Bob nhận được BYE và thông báo Alice closed the chat
        self.assertTrue(
            bob.out.wait_for("Alice closed the chat", timeout=2.0),
            "Bob phải nhận được thông báo khi Alice rời phiên chat",
        )

    def test_abrupt_disconnect_detected(self):
        """
        Đề bài mục 5.3:
        Khi peer ngắt kết nối đột ngột (crash/mất mạng không gửi BYE),
        bên còn lại phát hiện và in thông báo ngắt kết nối.
        """
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        # Đóng đột ngột socket của Alice với shutdown SHUT_WR để tạo sự kiện EOF
        with alice.node._state_lock:
            conn = alice.node.chat_conns.get("Bob")
        self.assertIsNotNone(conn)
        try:
            conn.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        conn.close()

        # Bob phải phát hiện ngắt kết nối
        self.assertTrue(
            wait_until(
                lambda: bob.out.has("disconnected (connection closed)")
                or bob.out.has("Connection with Alice lost"),
                timeout=3.0,
            ),
            "Bob phải phát hiện ngắt kết nối đột ngột từ Alice",
        )

    def test_multiple_peers_concurrent_connections(self):
        """Một node có thể duy trì nhiều kết nối TCP đồng thời với các peer khác nhau."""
        hub = self.make_peer("Hub")
        p1 = self.make_peer("Client1")
        p2 = self.make_peer("Client2")

        p1.add_contact(hub)
        p2.add_contact(hub)
        hub.add_contact(p1)
        hub.add_contact(p2)

        p1.open_chat("Hub")
        p2.open_chat("Hub")

        self.assertTrue(
            wait_until(lambda: len(hub.node.chat_conns) == 2, timeout=2.0),
            "Hub phải duy trì kết nối đồng thời với cả 2 client",
        )

        p1.send_message("Msg from 1")
        p2.send_message("Msg from 2")

        self.assertTrue(hub.out.wait_for("Client1"))
        self.assertTrue(hub.out.wait_for("Client2"))


if __name__ == "__main__":
    unittest.main()
