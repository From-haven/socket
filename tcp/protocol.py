"""Giao thức dạng văn bản: HELLO, MSG, FILE, BYE và ACK."""

from urllib.parse import quote, unquote


CHUNK = 4096
MAX_HEADER = 4096

MAX_MESSAGE = 1024 * 1024          # 1 MiB
MAX_FILE = 1024 * 1024 * 1024     # 1 GiB


def recv_exact(sock, num_bytes):
    """
    Đọc chính xác num_bytes từ TCP stream.
    Không đọc lấn sang bản tin tiếp theo.
    """
    chunks = []
    bytes_received = 0

    while bytes_received < num_bytes:
        chunk = sock.recv(
            min(CHUNK, num_bytes - bytes_received)
        )

        if not chunk:
            raise ConnectionError(
                "Kết nối bị ngắt khi chưa nhận đủ dữ liệu"
            )

        chunks.append(chunk)
        bytes_received += len(chunk)

    return b"".join(chunks)


def recv_line_header(sock):
    """Đọc một trường header kết thúc bằng dấu |."""
    buf = bytearray()

    while True:
        ch = sock.recv(1)

        if not ch:
            raise ConnectionError(
                "Mất kết nối khi đang đọc header"
            )

        if ch == b"|":
            return buf.decode("utf-8")

        buf.extend(ch)

        if len(buf) > MAX_HEADER:
            raise ValueError("Trường header quá dài")


def send_header(sock, header):
    """
    Gửi header theo loại bản tin.

    MSG/FILE có HELLO đứng trước để bên nhận
    biết tên người gửi.
    """
    kind = header["type"]

    if kind in ("ACK", "BYE"):
        raw = f"{kind}|"

    elif kind in ("MSG", "FILE"):
        sender = quote(header["sender"], safe="")

        raw = f"HELLO|{sender}|{kind}|"

        if kind == "FILE":
            filename = quote(
                header["filename"],
                safe="",
            )
            raw += filename + "|"

        raw += str(header["size"]) + "|"

    else:
        raise ValueError("Loại bản tin không hợp lệ")

    # Giới hạn từng trường để phía nhận không đọc header vô hạn.
    if any(
        len(field.encode("utf-8")) > MAX_HEADER
        for field in raw.split("|")
    ):
        raise ValueError("Trường header quá dài")

    sock.sendall(raw.encode("utf-8"))


def recv_header(sock):
    """Đọc header và chuyển thành dictionary."""
    kind = recv_line_header(sock)

    if kind in ("ACK", "BYE"):
        return {"type": kind}

    if kind != "HELLO":
        raise ValueError("Thiếu HELLO trước bản tin")

    sender = unquote(recv_line_header(sock))
    kind = recv_line_header(sock)

    if kind not in ("MSG", "FILE"):
        raise ValueError(
            "Chỉ chấp nhận MSG hoặc FILE sau HELLO"
        )

    header = {
        "type": kind,
        "sender": sender,
    }

    if kind == "FILE":
        header["filename"] = unquote(
            recv_line_header(sock)
        )

    size_text = recv_line_header(sock)

    if not size_text.isascii() or not size_text.isdecimal():
        raise ValueError(
            "Kích thước phải là số nguyên không âm"
        )

    header["size"] = int(size_text)

    return header