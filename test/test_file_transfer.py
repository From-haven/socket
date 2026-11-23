"""
Test TCP File Transfer & Concurrent Progress (đề bài mục 3.4, 4.1, 5.1).

Kiểm tra:
- Gửi và nhận file văn bản và file nhị phân qua kết nối TCP riêng.
- Toàn vẹn dữ liệu 100% (so khớp băm SHA256 trước và sau khi gửi).
- Hiển thị tiến độ truyền file (%) cho cả bên gửi và bên nhận.
- Tự động lưu vào thư mục downloads/ được chỉ định.
- Cơ chế chống ghi đè: tự động đổi tên thêm hậu tố _1, _2... khi file đã tồn tại.
- Chuẩn hóa tên file: chống path traversal (../../) và loại bỏ ký tự '|'.
- Dọn dẹp file tạm (.part) khi đường truyền bị ngắt giữa chừng.
- Đa luồng: chat vẫn hoạt động bình thường trong khi file đang được truyền ngầm.
"""

import os
import socket
import tempfile
import threading
import time
import unittest

import helpers
from helpers import (
    LOCALHOST,
    Output,
    Peer,
    connect_peers,
    create_dummy_file,
    file_sha256,
    free_tcp_port,
    wait_until,
)
from tcp.tcp_protocol import TCPProtocol


class TCPFileTransferTests(unittest.TestCase):
    requirement = "TCP File Transfer - Truyền file, Tiến độ & Đa luồng (3.4, 5.1)"

    def setUp(self):
        self.peers = []
        self.temp_src_dir = tempfile.mkdtemp(prefix="test_files_src_")

    def tearDown(self):
        for p in self.peers:
            p.stop()
        if os.path.isdir(self.temp_src_dir):
            import shutil

            shutil.rmtree(self.temp_src_dir, ignore_errors=True)

    def make_peer(self, name):
        p = Peer(name=name)
        p.start()
        self.peers.append(p)
        return p

    def test_send_and_receive_text_file(self):
        """Gửi và nhận file văn bản thông thường, kiểm tra nội dung toàn vẹn."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        test_content = b"Xin chao, day la noi dung file test truyen qua socket TCP!"
        src_file = os.path.join(self.temp_src_dir, "hello.txt")
        with open(src_file, "wb") as f:
            f.write(test_content)

        alice.send_file(src_file)

        # Chờ Bob nhận xong file
        self.assertTrue(
            bob.out.wait_for("Received hello.txt", timeout=4.0),
            "Bob phải nhận được file hello.txt",
        )

        expected_dest = os.path.join(bob.downloads_dir, "hello.txt")
        self.assertTrue(os.path.isfile(expected_dest))
        with open(expected_dest, "rb") as f:
            self.assertEqual(f.read(), test_content)

    def test_send_and_receive_binary_file_integrity(self):
        """Gửi file nhị phân lớn (50 KB) và kiểm tra toàn vẹn băm SHA256."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        binary_pattern = bytes([i % 256 for i in range(1024)])
        src_file = create_dummy_file(self.temp_src_dir, "data.bin", 50 * 1024, pattern=binary_pattern)
        src_hash = file_sha256(src_file)

        alice.send_file(src_file)

        self.assertTrue(
            bob.out.wait_for("Received data.bin", timeout=5.0),
            "Bob phải nhận được data.bin",
        )

        dest_file = os.path.join(bob.downloads_dir, "data.bin")
        self.assertTrue(os.path.isfile(dest_file))
        dest_hash = file_sha256(dest_file)
        self.assertEqual(src_hash, dest_hash, "Mã băm SHA256 phải khớp 100%")

    def test_transfer_progress_emitted(self):
        """Tiến độ phần trăm (%) được thông báo cho cả bên gửi và bên nhận."""
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        src_file = create_dummy_file(self.temp_src_dir, "progress.bin", 30 * 1024)
        alice.send_file(src_file)

        self.assertTrue(bob.out.wait_for("Received progress.bin", timeout=5.0))

        # Kiểm tra bên gửi có thông báo tiến độ và 100% Done
        self.assertTrue(alice.out.has("100% Done."))
        # Kiểm tra bên nhận có thông báo nhận thành công
        self.assertTrue(bob.out.has("Saved to"))

    def test_duplicate_filename_numbered_avoiding_overwrite(self):
        """
        Nếu file đã tồn tại trong downloads/, file nhận mới được tự động đổi tên
        thành <tên>_1.<ext>, <tên>_2.<ext> để không ghi đè dữ liệu cũ.
        """
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        # Tạo sẵn file report.txt trong thư mục download của Bob
        existing_file = os.path.join(bob.downloads_dir, "report.txt")
        with open(existing_file, "wb") as f:
            f.write(b"OLD REPORT CONTENT")

        # Alice gửi file report.txt với nội dung mới
        src_file = os.path.join(self.temp_src_dir, "report.txt")
        with open(src_file, "wb") as f:
            f.write(b"NEW REPORT CONTENT FROM ALICE")

        alice.send_file(src_file)

        self.assertTrue(bob.out.wait_for("report", timeout=4.0))

        # File cũ vẫn nguyên vẹn
        with open(existing_file, "rb") as f:
            self.assertEqual(f.read(), b"OLD REPORT CONTENT")

        # File mới được lưu với tên report_1.txt
        new_file = os.path.join(bob.downloads_dir, "report_1.txt")
        self.assertTrue(os.path.isfile(new_file), "File mới phải được đổi tên thành report_1.txt")
        with open(new_file, "rb") as f:
            self.assertEqual(f.read(), b"NEW REPORT CONTENT FROM ALICE")

    def test_interrupted_transfer_cleans_up_part_file(self):
        """Nếu quá trình truyền file bị ngắt giữa chừng, file tạm .part phải bị xóa bỏ."""
        bob = self.make_peer("Bob")

        # Dùng raw socket kết nối trực tiếp đến Bob và gửi header file 5000 bytes
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, bob.tcp_port))
        sock.sendall(TCPProtocol.encode_file_header("broken.dat", 5000, sender="Tester"))

        # Chỉ gửi 200 bytes rồi ngắt kết nối đột ngột
        sock.sendall(b"A" * 200)
        sock.close()

        # Chờ Bob phát hiện lỗi ngắt truyền file
        self.assertTrue(
            bob.out.wait_for("File transfer failed (broken.dat)", timeout=3.0),
            "Bob phải thông báo truyền file thất bại",
        )

        part_file = os.path.join(bob.downloads_dir, "broken.dat.part")
        dest_file = os.path.join(bob.downloads_dir, "broken.dat")
        self.assertFalse(os.path.exists(part_file), "File .part phải được dọn dẹp sạch sẽ")
        self.assertFalse(os.path.exists(dest_file), "File đích không được tạo ra khi hỏng")

    def test_filename_sanitization_against_traversal_and_pipe(self):
        """Tên file chứa đường dẫn nguy hiểm ../ hoặc ký tự | được chuẩn hóa an toàn."""
        bob = self.make_peer("Bob")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((LOCALHOST, bob.tcp_port))

        # Gửi header với đường dẫn '../../malicious.txt'
        payload = b"SAFE DATA"
        header = f"FILE|Tester|../../malicious.txt|{len(payload)}|".encode("utf-8")
        sock.sendall(header + payload)
        sock.close()

        self.assertTrue(bob.out.wait_for("malicious.txt", timeout=3.0))

        # File phải được lưu trong downloads/, không bị thoát ra ngoài
        expected_safe = os.path.join(bob.downloads_dir, "malicious.txt")
        self.assertTrue(os.path.isfile(expected_safe))

    def test_concurrent_chat_during_file_transfer(self):
        """
        Đề bài mục 3.4:
        Chatting must keep working while a file is being transferred (run the transfer in its own thread).
        Trong khi đang gửi file nền, 2 peer vẫn gửi và nhận tin nhắn chat bình thường.
        """
        alice = self.make_peer("Alice")
        bob = self.make_peer("Bob")
        connect_peers(alice, bob)

        # Tạo file 150 KB
        src_file = create_dummy_file(self.temp_src_dir, "large.dat", 150 * 1024)

        # Bắt đầu gửi file (chạy bất đồng bộ trong Thread riêng)
        alice.send_file(src_file)

        # Ngay lập tức gửi tin nhắn chat trong khi file đang được truyền
        alice.send_message("Dang gui file, ban van nhan duoc tin chu?")

        # Bob phải nhận được tin nhắn chat ngay lập tức
        self.assertTrue(
            bob.out.wait_for("[Alice] Dang gui file, ban van nhan duoc tin chu?", timeout=2.0),
            "Tin nhắn chat phải được nhận ngay mà không bị chặn bởi truyền file",
        )

        # Bob trả lời lại
        bob.send_message("Nhan duoc tin nhan binh thuong!")
        self.assertTrue(
            alice.out.wait_for("[Bob] Nhan duoc tin nhan binh thuong!", timeout=2.0),
            "Alice phải nhận được tin nhắn phản hồi của Bob",
        )

        # File cũng truyền xong trọn vẹn
        self.assertTrue(bob.out.wait_for("Received large.dat", timeout=5.0))


if __name__ == "__main__":
    unittest.main()
