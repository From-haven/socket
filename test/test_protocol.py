"""
Test đóng gói / bóc tách khung dữ liệu TCP (đề bài mục 5.2).
Kiểm tra tcp/tcp_protocol.py: MSG, FILE, BYE, IDENT, recv_until, recv_exact.
"""

import socket
import threading
import time
import unittest

import helpers  # noqa: F401  (thiết lập sys.path)
from tcp.tcp_protocol import TCPProtocol


class EncodeTests(unittest.TestCase):
    requirement = "Protocol - Đóng gói tin TCP (5.2)"

    def test_msg_format_header_length_payload(self):
        self.assertEqual(TCPProtocol.encode_msg("hello"), b"MSG|5|hello")

    def test_msg_length_is_in_bytes_not_characters(self):
        text = "xin chào 🙂"
        frame = TCPProtocol.encode_msg(text)
        payload = text.encode("utf-8")
        self.assertGreater(len(payload), len(text))
        self.assertEqual(frame, f"MSG|{len(payload)}|".encode() + payload)

    def test_msg_text_containing_pipe_is_kept(self):
        self.assertEqual(TCPProtocol.encode_msg("a|b|c"), b"MSG|5|a|b|c")

    def test_msg_empty_text(self):
        self.assertEqual(TCPProtocol.encode_msg(""), b"MSG|0|")

    def test_bye_frame(self):
        self.assertEqual(TCPProtocol.encode_bye(), b"BYE|")

    def test_ident_frame(self):
        self.assertEqual(TCPProtocol.encode_ident("Alice"), b"IDENT|5|Alice")

    def test_ident_pipe_in_name_is_sanitized(self):
        self.assertEqual(TCPProtocol.encode_ident("A|B"), b"IDENT|3|A_B")

    def test_file_header_without_sender(self):
        self.assertEqual(TCPProtocol.encode_file_header("a.txt", 12), b"FILE|a.txt|12|")

    def test_file_header_with_sender(self):
        self.assertEqual(
            TCPProtocol.encode_file_header("a.txt", 12, sender="Alice"), b"FILE|Alice|a.txt|12|"
        )

    def test_file_header_pipe_in_filename_is_replaced(self):
        self.assertEqual(TCPProtocol.encode_file_header("we|ird.txt", 1), b"FILE|we_ird.txt|1|")

    def test_file_header_strips_directory_part(self):
        self.assertEqual(TCPProtocol.encode_file_header("/home/u/docs/a.txt", 3), b"FILE|a.txt|3|")
        self.assertEqual(TCPProtocol.encode_file_header("C:\\Users\\u\\a.txt", 3), b"FILE|a.txt|3|")


class DecodeTests(unittest.TestCase):
    requirement = "Protocol - Đọc đúng số byte, chống dính/rách gói (5.2)"

    def setUp(self):
        self.a, self.b = socket.socketpair()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)
        self.b.settimeout(5)

    def test_recv_until_returns_field_without_delimiter(self):
        self.a.sendall(b"MSG|5|hello")
        self.assertEqual(TCPProtocol.recv_until(self.b), b"MSG")
        self.assertEqual(TCPProtocol.recv_until(self.b), b"5")
        self.assertEqual(TCPProtocol.recv_exact(self.b, 5), b"hello")

    def test_recv_until_eof_returns_none(self):
        self.a.close()
        self.assertIsNone(TCPProtocol.recv_until(self.b))

    def test_recv_until_rejects_oversized_header(self):
        self.a.sendall(b"X" * (TCPProtocol.MAX_HEADER_FIELD + 10))
        with self.assertRaises(ValueError):
            TCPProtocol.recv_until(self.b)

    def test_recv_exact_reassembles_fragmented_data(self):
        """Mô phỏng hiện tượng rách gói (fragmentation): dữ liệu đến từng mẩu nhỏ."""
        expected = b"Hello, this is fragmented data stream!"

        def send_fragmented():
            for byte in expected:
                self.a.sendall(bytes([byte]))
                time.sleep(0.005)

        t = threading.Thread(target=send_fragmented)
        t.start()
        received = TCPProtocol.recv_exact(self.b, len(expected))
        t.join()
        self.assertEqual(received, expected)

    def test_recv_exact_raises_on_early_eof(self):
        """Bên gửi ngắt kết nối giữa chừng khi chưa gửi đủ byte."""
        self.a.sendall(b"abc")
        self.a.close()
        with self.assertRaises(ConnectionResetError):
            TCPProtocol.recv_exact(self.b, 10)

    def test_framing_multiple_messages_back_to_back(self):
        """Mô phỏng hiện tượng dính gói (sticky packets): nhiều gói gửi dồn trong một buffer."""
        f1 = TCPProtocol.encode_msg("tin nhan 1")
        f2 = TCPProtocol.encode_msg("tin nhan 2")
        f3 = TCPProtocol.encode_bye()
        self.a.sendall(f1 + f2 + f3)

        # Đọc gói 1
        cmd1 = TCPProtocol.recv_until(self.b)
        len1 = int(TCPProtocol.recv_until(self.b))
        data1 = TCPProtocol.recv_exact(self.b, len1)
        self.assertEqual(cmd1, b"MSG")
        self.assertEqual(data1, b"tin nhan 1")

        # Đọc gói 2
        cmd2 = TCPProtocol.recv_until(self.b)
        len2 = int(TCPProtocol.recv_until(self.b))
        data2 = TCPProtocol.recv_exact(self.b, len2)
        self.assertEqual(cmd2, b"MSG")
        self.assertEqual(data2, b"tin nhan 2")

        # Đọc gói 3 (BYE|)
        cmd3 = TCPProtocol.recv_until(self.b)
        self.assertEqual(cmd3, b"BYE")

    def test_framing_pipe_inside_message_payload(self):
        """Nội dung chứa ký tự | không làm vỡ các trường tiếp theo."""
        payload = "A|B|C|1234|xyz"
        frame = TCPProtocol.encode_msg(payload)
        self.a.sendall(frame)

        cmd = TCPProtocol.recv_until(self.b)
        length = int(TCPProtocol.recv_until(self.b))
        data = TCPProtocol.recv_exact(self.b, length).decode("utf-8")
        self.assertEqual(cmd, b"MSG")
        self.assertEqual(data, payload)

    def test_recv_exact_large_payload(self):
        """Nhận payload lớn hơn buffer CHUNK_SIZE (4096)."""
        large_data = b"X" * 15000
        self.a.sendall(large_data)
        received = TCPProtocol.recv_exact(self.b, len(large_data))
        self.assertEqual(received, large_data)


if __name__ == "__main__":
    unittest.main()
