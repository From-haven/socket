"""
Test UDP Discovery & Online Status (đề bài mục 3.1, 3.2, 5.1).

Kiểm tra:
- Phát (broadcast) gói tin hiện diện HELLO|<name>|<tcp_port>|<status>.
- Tần suất phát gói tin (ngay khi start, định kỳ mỗi 3s, tức thì khi đổi status).
- Nhận diện người dùng online mới qua UDP datagram.
- Bỏ qua gói tin phát ra từ chính bản thân mình (self-ignore).
- Đồng bộ và phát hiện thay đổi trạng thái (online <-> away).
- Cơ chế timeout: tự động phát hiện và xóa người dùng rớt mạng sau 10s không có gói tin.
- Tra cứu danh bạ peer theo tên hoặc số thứ tự (phục vụ lệnh /list và /chat).
"""

import time
import unittest

import helpers
from helpers import BCAST, LOCALHOST, SLOW, Output, free_udp_port, udp_socket, wait_until
from udp.udp_manager import UDPDiscovery


class UDPBase(unittest.TestCase):
    def setUp(self):
        self.port = free_udp_port()
        self.out = Output()
        self._discs = []
        self._socks = []

    def tearDown(self):
        for d in self._discs:
            d.stop()
        for s in self._socks:
            try:
                s.close()
            except Exception:
                pass

    def make_disc(self, name="Alice", tcp_port=5000, start=False, out=None):
        d = UDPDiscovery(
            username=name,
            tcp_port=tcp_port,
            udp_port=self.port,
            bcast_ip=BCAST,
            on_notify=out or self.out,
        )
        self._discs.append(d)
        if start:
            d.start()
        return d

    def raw(self):
        s = udp_socket(self.port)
        self._socks.append(s)
        return s

    def inject(self, payload, sock=None):
        """Gửi một datagram broadcast như thể từ một máy khác trên mạng."""
        s = sock or self.raw()
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        s.sendto(payload, (BCAST, self.port))


class UDPSendTests(UDPBase):
    requirement = "UDP - Phát gói tin hiện diện HELLO (3.1, 3.2)"

    def test_presence_packet_format(self):
        """Gói tin đúng định dạng HELLO|<name>|<tcp_port>|<status>."""
        listener = self.raw()
        d = self.make_disc("Alice", 5000)
        d.send_presence()
        data, _ = listener.recvfrom(1024)
        self.assertEqual(data, b"HELLO|Alice|5000|online")

    def test_presence_has_four_fields(self):
        listener = self.raw()
        self.make_disc("Quan", 6001).send_presence()
        data, _ = listener.recvfrom(1024)
        parts = data.decode("utf-8").split("|")
        self.assertEqual(parts, ["HELLO", "Quan", "6001", "online"])

    def test_broadcast_sent_immediately_on_start(self):
        """Khi gọi start(), phải phát ngay gói tin HELLO đầu tiên mà không cần chờ 3s."""
        listener = self.raw()
        self.make_disc("Alice", 5000, start=True)
        data, _ = listener.recvfrom(1024)
        self.assertTrue(data.startswith(b"HELLO|Alice|5000|"))

    def test_broadcast_repeats_every_3_seconds(self):
        """Đề bài: mỗi 3 giây phát 1 lần."""
        listener = self.raw()
        listener.settimeout(0.5)
        self.make_disc("Alice", 5000, start=True)

        stamps = []
        end = time.time() + 4.2
        while time.time() < end:
            try:
                data, _ = listener.recvfrom(1024)
            except OSError:
                continue
            if data.startswith(b"HELLO|Alice|"):
                now = time.time()
                # Bỏ qua gói gửi ngay khi start() nếu sát vòng lặp đầu tiên
                if not stamps or now - stamps[-1] > 1.0:
                    stamps.append(now)

        self.assertGreaterEqual(
            len(stamps),
            2,
            f"Cần nhận ít nhất 2 đợt phát định kỳ trong ~4s, nhận được {len(stamps)}",
        )
        interval = stamps[1] - stamps[0]
        self.assertTrue(
            2.3 <= interval <= 3.8,
            f"Khoảng cách giữa 2 lần phát phải xấp xỉ 3s (nhận được {interval:.2f}s)",
        )

    def test_set_status_sends_immediate_broadcast(self):
        """Khi đổi trạng thái qua /status, phát ngay gói HELLO mới với trạng thái mới."""
        listener = self.raw()
        d = self.make_disc("Alice", 5000)
        # Hút hết các gói tin cũ nếu có
        listener.settimeout(0.1)
        try:
            while True:
                listener.recvfrom(1024)
        except OSError:
            pass

        d.set_status("away")
        listener.settimeout(1.0)
        data, _ = listener.recvfrom(1024)
        self.assertEqual(data, b"HELLO|Alice|5000|away")
        self.assertEqual(d.status, "away")


class UDPReceiveTests(UDPBase):
    requirement = "UDP - Tiếp nhận và quản lý danh sách Online (3.1, 3.2)"

    def test_receive_peer_adds_to_online_users(self):
        """Nhận gói HELLO từ peer khác -> ghi nhận vào danh sách online_users."""
        d = self.make_disc("Alice", 5000, start=True)
        self.inject("HELLO|Bob|5002|online")

        self.assertTrue(
            wait_until(lambda: "Bob" in d.get_online_users(), timeout=2.0),
            "Bob phải được thêm vào online_users",
        )
        bob = d.get_online_users()["Bob"]
        self.assertEqual(bob["tcp_port"], 5002)
        self.assertEqual(bob["status"], "online")
        self.assertTrue(self.out.wait_for("Bob"))

    def test_ignore_own_broadcast(self):
        """Bản thân mình gửi broadcast thì phải tự bỏ qua, không đưa chính mình vào online_users."""
        d = self.make_disc("Alice", 5000, start=True)
        self.inject("HELLO|Alice|5000|online")
        time.sleep(0.3)

        self.assertNotIn("Alice", d.get_online_users())
        self.assertFalse(self.out.has("Alice"))

    def test_peer_status_change_reflected(self):
        """Peer đổi trạng thái từ online sang away -> cập nhật và thông báo."""
        d = self.make_disc("Alice", 5000, start=True)
        self.inject("HELLO|Bob|5002|online")
        self.assertTrue(wait_until(lambda: "Bob" in d.get_online_users(), timeout=2.0))

        # Bob đổi sang away
        self.inject("HELLO|Bob|5002|away")
        self.assertTrue(
            wait_until(lambda: d.get_online_users()["Bob"]["status"] == "away", timeout=2.0)
        )
        self.assertTrue(self.out.wait_for("Bob changed status to away"))

    def test_lookup_peer_by_name_and_index(self):
        """Tra cứu peer theo tên hoặc số thứ tự 1-based (dùng cho lệnh /chat)."""
        d = self.make_disc("Alice", 5000, start=True)
        self.inject("HELLO|Minh|6001|online")
        self.inject("HELLO|Lan|6002|away")

        self.assertTrue(
            wait_until(lambda: len(d.get_online_users()) >= 2, timeout=2.0)
        )

        # Tra cứu theo tên
        minh = d.get_peer("Minh")
        self.assertIsNotNone(minh)
        self.assertEqual(minh[0], "Minh")
        self.assertEqual(minh[2], 6001)

        # Tra cứu theo số thứ tự (1 hoặc 2)
        p1 = d.get_peer("1")
        self.assertIsNotNone(p1)
        self.assertIn(p1[0], ["Minh", "Lan"])

        # Tra cứu không tồn tại
        self.assertIsNone(d.get_peer("UnknownUser"))
        self.assertIsNone(d.get_peer("99"))

    def test_timeout_removes_inactive_peer(self):
        """Sau 10s không nhận được tin, peer bị xóa khỏi danh sách và có thông báo offline."""
        d = self.make_disc("Alice", 5000, start=True)
        self.inject("HELLO|Bob|5002|online")
        self.assertTrue(wait_until(lambda: "Bob" in d.get_online_users(), timeout=2.0))

        # Giả lập thời gian trôi qua quá 10 giây cho Bob
        with d.lock:
            d.online_users["Bob"]["last_seen"] = time.time() - 11.0

        # Kích hoạt kiểm tra timeout
        d._check_timeouts()

        self.assertNotIn("Bob", d.get_online_users())
        self.assertTrue(self.out.wait_for("Bob went offline"))

    def test_two_nodes_discover_each_other(self):
        """Hai thực thể UDPDiscovery hoạt động song song phát hiện lẫn nhau."""
        p1 = free_udp_port()
        d1 = UDPDiscovery("Alice", 5001, udp_port=p1, bcast_ip=BCAST)
        d2 = UDPDiscovery("Bob", 5002, udp_port=p1, bcast_ip=BCAST)
        self._discs.extend([d1, d2])

        d1.start()
        d2.start()

        self.assertTrue(
            wait_until(lambda: "Bob" in d1.get_online_users(), timeout=3.0),
            "Alice phải phát hiện ra Bob",
        )
        self.assertTrue(
            wait_until(lambda: "Alice" in d2.get_online_users(), timeout=3.0),
            "Bob phải phát hiện ra Alice",
        )


if __name__ == "__main__":
    unittest.main()
