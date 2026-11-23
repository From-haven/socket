import os


class TCPProtocol:
    """
    Đóng gói và phân tách khung dữ liệu (Framing) trên TCP Byte Stream:
    - IDENT|<length>|<utf-8 username>
    - MSG|<length>|<utf-8 text>
    - FILE|[<sender>|]<filename>|<size_in_bytes>|<raw file bytes>
    - BYE|

    Xử lý hiện tượng dính gói / rách gói bằng việc đọc chính xác số byte (recv_exact).
    """

    CHUNK_SIZE = 4096
    MAX_HEADER_FIELD = 4096

    @staticmethod
    def encode_ident(username):
        """Header nhận diện danh tính khi vừa kết nối TCP."""
        safe_username = username.replace("|", "_")
        payload = safe_username.encode("utf-8")
        return f"IDENT|{len(payload)}|".encode("utf-8") + payload

    @staticmethod
    def encode_msg(text):
        """Header và nội dung tin nhắn chat."""
        payload = text.encode("utf-8")
        return f"MSG|{len(payload)}|".encode("utf-8") + payload

    @staticmethod
    def encode_bye():
        """Bản tin đóng phiên chat."""
        return b"BYE|"

    @staticmethod
    def encode_file_header(filename, size_in_bytes, sender=None):
        """
        Header báo chuẩn bị gửi file.
        Thay thế ký tự '|' trong tên file và sender bằng '_' để tránh vỡ framing.
        Hỗ trợ kèm sender: FILE|<sender>|<filename>|<size>|
        """
        safe_name = os.path.basename(filename.replace("\\", "/")).replace("|", "_")
        if sender:
            safe_sender = str(sender).replace("|", "_")
            return f"FILE|{safe_sender}|{safe_name}|{size_in_bytes}|".encode("utf-8")
        return f"FILE|{safe_name}|{size_in_bytes}|".encode("utf-8")

    @staticmethod
    def recv_until(sock, delimiter=b"|"):
        """Đọc từ socket cho đến khi gặp ký tự phân cách delimiter (mặc định '|')."""
        buf = bytearray()
        while True:
            chunk = sock.recv(1)
            if not chunk:
                return None if len(buf) == 0 else bytes(buf)
            if chunk == delimiter:
                return bytes(buf)
            buf.extend(chunk)
            if len(buf) > TCPProtocol.MAX_HEADER_FIELD:
                raise ValueError("Trường header vượt quá giới hạn an toàn.")

    @staticmethod
    def recv_exact(sock, num_bytes):
        """Đọc chính xác num_bytes từ TCP stream để không đọc lấn sang bản tin kế tiếp."""
        fragments = []
        remaining = num_bytes
        while remaining > 0:
            chunk = sock.recv(min(TCPProtocol.CHUNK_SIZE, remaining))
            if not chunk:
                raise ConnectionResetError("Kết nối bị đóng trước khi nhận đủ dữ liệu.")
            fragments.append(chunk)
            remaining -= len(chunk)
        return b"".join(fragments)
