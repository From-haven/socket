import os


class TCPProtocol:
    """
    Đóng gói và tách khung dữ liệu trên TCP byte stream:
    - IDENT|<length>|<utf-8 username>
    - MSG|<length>|<utf-8 text>
    - FILE|<filename>|<size_in_bytes>|<raw file bytes>
    - BYE|
    """

    CHUNK_SIZE = 4096

    @staticmethod
    def encode_ident(username):
        payload = username.encode("utf-8")
        return f"IDENT|{len(payload)}|".encode("utf-8") + payload

    @staticmethod
    def encode_msg(text):
        payload = text.encode("utf-8")
        return f"MSG|{len(payload)}|".encode("utf-8") + payload

    @staticmethod
    def encode_bye():
        return b"BYE|"

    @staticmethod
    def encode_file_header(filename, size_in_bytes):
        safe_name = os.path.basename(filename.replace("\\", "/"))
        return f"FILE|{safe_name}|{size_in_bytes}|".encode("utf-8")

    @staticmethod
    def recv_until(sock, delimiter=b"|"):
        buf = bytearray()
        while True:
            chunk = sock.recv(1)
            if not chunk:
                return None if len(buf) == 0 else bytes(buf)
            if chunk == delimiter:
                return bytes(buf)
            buf.extend(chunk)

    @staticmethod
    def recv_exact(sock, num_bytes):
        fragments = []
        remaining = num_bytes
        while remaining > 0:
            chunk = sock.recv(min(TCPProtocol.CHUNK_SIZE, remaining))
            if not chunk:
                raise ConnectionResetError("Kết nối bị đóng trước khi nhận đủ dữ liệu.")
            fragments.append(chunk)
            remaining -= len(chunk)
        return b"".join(fragments)