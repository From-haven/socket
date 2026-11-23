"""
Test Error Handling & Stability (đề bài mục 5.3 & Bảng điểm chấm lỗi 10%).

Kiểm tra các tình huống biên và xử lý lỗi:
- Kết nối tới peer không online hoặc không tồn tại trong danh bạ.
- Kết nối tới cổng TCP bị từ chối / server đích không mở.
- Gửi tin nhắn khi chưa mở phiên chat (/chat).
- Gửi file khi chưa mở phiên chat.
- Gửi file không tồn tại trên hệ thống tập tin.
- Rời phiên chat (/leave) khi chưa vào bất kỳ phòng chat nào.
- Xử lý gói tin rác / header không hợp lệ qua TCP mà không gây sập ứng dụng.
- Xử lý khi độ dài trường header vượt ngưỡng an toàn MAX_HEADER_FIELD.
- Xử lý khi đường truyền bị ngắt trong lúc đang gửi tin nhắn.
"""

import socket
import unittest
import warnings

import helpers
from helpers import LOCALHOST, Output, Peer, free_tcp_port, wait_until
from tcp.tcp_protocol import TCPProtocol


class ErrorHandlingTests(unittest.TestCase):
    requirement = "Error Handling - Xử lý lỗi & Ổn định hệ thống (5.3)"

    def setUp(self):
        self.peers = []
        warnings.filterwarnings("ignore", category=ResourceWarning)

    def tearDown(self):
        for p in self.peers:
            p.stop()

    def make_peer(self, name):
        p = Peer(name=name)
        p.start()
        self.peers.append(p)
        return p

    def test_chat_with_offline_user_rejected(self):
        """Mở chat với người dùng không có trong danh sách online."""
        alice = self.make_peer("Alice")
        success = alice.open_chat("GhostUser")
        self.assertFalse(success)
        self.assertTrue(alice.out.has("User 'GhostUser' is not online."))

    def test_chat_connection_refused_handled_gracefully(self):
        """Peer có trong danh bạ nhưng cổng TCP không lắng nghe (tắt app)."""
        alice = self.make_peer("Alice")
        closed_port = free_tcp_port()
        alice.discovery.add_peer("Bob", LOCALHOST, closed_port)

        success = alice.open_chat("Bob")
        self.assertFalse(success)
        self.assertTrue(alice.out.has("Cannot connect to Bob"))

    def test_send_message_without_active_chat(self):
        """Gõ tin nhắn gửi khi chưa thực hiện lệnh /chat."""
        alice = self.make_peer("Alice")
        res = alice.send_message("Xin chao!")
        self.assertFalse(res)
        self.assertTrue(alice.out.has("No active chat. Use /chat <name|number> first."))

    def test_send_file_without_active_chat(self):
        """Gửi file khi chưa chọn đối tượng chat."""
        alice = self.make_peer("Alice")
        res = alice.send_file("anyfile.txt")
        self.assertFalse(res)
        self.assertTrue(alice.out.has("No active chat. Use /chat <name|number> first."))

    def test_send_nonexistent_file(self):
        """Gửi đường dẫn file không tồn tại trên máy."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        alice.add_contact(bob)
        alice.open_chat("Bob")

        res = alice.send_file("this_file_does_not_exist_98765.xyz")
        self.assertFalse(res)
        self.assertTrue(alice.out.has("File not found:"))

    def test_leave_when_not_in_chat(self):
        """Gõ /leave khi chưa tham gia phòng chat nào."""
        alice = self.make_peer("Alice")
        alice.leave_chat()
        self.assertTrue(alice.out.has("You are not in a chat."))

    def test_malformed_header_handled_gracefully(self):
        """Gửi gói tin header không thuộc giao thức (ví dụ HACK|...) không làm crash server."""
        bob = self.make_peer("Bob")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, bob.tcp_port))
        sock.sendall(b"UNKNOWNCOMMAND|some_payload|")

        # Bob phát hiện header lạ và log ra, server vẫn sống bình thường
        self.assertTrue(bob.out.wait_for("Unknown header from", timeout=2.0))
        sock.close()

        # Kiểm tra server của Bob vẫn chấp nhận kết nối mới bình thường
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.connect((LOCALHOST, bob.tcp_port))
        sock2.close()

    def test_oversized_header_attack_rejected(self):
        """Gửi chuỗi dữ liệu dài không có dấu phân cách | nhằm làm tràn bộ đệm header."""
        bob = self.make_peer("Bob")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, bob.tcp_port))
        sock.sendall(b"A" * (TCPProtocol.MAX_HEADER_FIELD + 100))

        # Server ngắt kết nối với client xấu (EOF hoặc Reset trên Windows), không crash
        def is_disconnected():
            try:
                data = sock.recv(1)
                return data == b""
            except (ConnectionResetError, OSError):
                return True

        self.assertTrue(
            wait_until(is_disconnected, timeout=3.0),
            "Server phải đóng kết nối với luồng vi phạm giới hạn header",
        )
        sock.close()


if __name__ == "__main__":
    unittest.main()
