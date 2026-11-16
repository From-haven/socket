import os
import socket
import threading
import uuid
from pathlib import Path

from .protocol import (
    CHUNK,
    MAX_FILE,
    MAX_MESSAGE,
    recv_exact,
    recv_header,
    send_header,
)


class TCPManager:
    def __init__(
        self,
        username,
        tcp_port,
        download_dir,
        on_notify=print,
    ):
        self.username = username
        self.tcp_port = tcp_port

        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Callback hiển thị thông báo.
        self.notify = on_notify

        # Quản lý trạng thái và các kết nối đang hoạt động.
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.connections = set()

        self.server = None

    # ---------- KHỞI TẠO SERVER ----------

    def start(self):
        self.server = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        try:
            self.server.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )

            self.server.bind(
                ("0.0.0.0", self.tcp_port)
            )

            self.server.listen(20)
            self.server.settimeout(0.5)

        except OSError:
            self.server.close()
            raise

        threading.Thread(
            target=self._accept_loop,
            daemon=True,
        ).start()

    def _track(self, conn):
        """Lưu kết nối để có thể đóng khi thoát ứng dụng."""
        with self.lock:
            if self.stopping.is_set():
                conn.close()
                raise ConnectionError("TCP đã dừng")

            self.connections.add(conn)

    def _close(self, conn):
        with self.lock:
            self.connections.discard(conn)

        conn.close()

    def _accept_loop(self):
        """Mỗi kết nối mới được xử lý bằng một luồng riêng."""
        while not self.stopping.is_set():
            try:
                conn, _ = self.server.accept()

                conn.settimeout(30)
                self._track(conn)

            except socket.timeout:
                continue

            except OSError:
                break

            threading.Thread(
                target=self._receive,
                args=(conn,),
                daemon=True,
            ).start()

    # ---------- NHẬN TIN NHẮN / FILE ----------

    def _receive(self, conn):
        temp = None

        try:
            header = recv_header(conn)

            kind = header.get("type")
            size = header.get("size")
            sender = header.get("sender")

            if kind not in ("MSG", "FILE"):
                raise ValueError(
                    "Loại bản tin không hợp lệ"
                )

            limit = (
                MAX_MESSAGE
                if kind == "MSG"
                else MAX_FILE
            )

            if type(size) is not int or not 0 <= size <= limit:
                raise ValueError(
                    "Kích thước không hợp lệ"
                )

            if not isinstance(sender, str) or not sender:
                raise ValueError(
                    "Thiếu tên người gửi"
                )

            if kind == "MSG":
                payload = recv_exact(conn, size)
                message = payload.decode("utf-8")

                self.notify(
                    f"[{sender}] {message}"
                )

            else:
                name = header.get("filename")

                if not isinstance(name, str) or not name:
                    raise ValueError(
                        "Thiếu tên file"
                    )

                # Chỉ lấy tên file, bỏ đường dẫn từ bên gửi.
                name = name.replace("\\", "/")
                name = name.rsplit("/", 1)[-1]

                # Giữ lại các ký tự phù hợp cho tên file.
                name = "".join(
                    c for c in name
                    if c.isalnum() or c in " ._-"
                )

                name = name.strip(" .")[:100] or "file.bin"

                # Thêm mã riêng để tránh ghi đè file trùng tên.
                target = self.download_dir / (
                    f"{uuid.uuid4().hex}_{name}"
                )

                # File tải dở có đuôi .part.
                temp = target.with_name(
                    target.name + ".part"
                )

                with temp.open("xb") as output:
                    remaining = size

                    while remaining:
                        block = recv_exact(
                            conn,
                            min(CHUNK, remaining),
                        )

                        output.write(block)
                        remaining -= len(block)

                # Chỉ đổi tên sau khi nhận đủ dữ liệu.
                os.replace(temp, target)
                temp = None

                self.notify(
                    f"[FILE từ {sender}] Đã lưu: {target}"
                )

            # Xác nhận đã xử lý xong payload.
            send_header(
                conn,
                {"type": "ACK"},
            )

            # Bên gửi kết thúc lượt truyền bằng BYE.
            if recv_header(conn).get("type") != "BYE":
                raise ValueError(
                    "Thiếu BYE kết thúc lượt truyền"
                )

        except (OSError, ValueError) as exc:
            if not self.stopping.is_set():
                self.notify(
                    f"[Lỗi nhận] {exc}"
                )

        finally:
            # Xóa file chưa hoàn chỉnh nếu có lỗi.
            if temp is not None:
                temp.unlink(missing_ok=True)

            self._close(conn)

    # ---------- GỬI TIN NHẮN / FILE ----------

    def send_message(self, ip, port, text):
        payload = text.encode("utf-8")

        if len(payload) > MAX_MESSAGE:
            raise ValueError(
                "Tin nhắn vượt quá 1 MiB"
            )

        self._send(
            ip,
            port,
            "MSG",
            payload=payload,
        )

    def send_file(self, ip, port, filename):
        self._send(
            ip,
            port,
            "FILE",
            filename=filename,
        )

    def _send(
        self,
        ip,
        port,
        kind,
        payload=b"",
        filename=None,
    ):
        source = None
        conn = None

        try:
            header = {
                "type": kind,
                "sender": self.username,
                "size": len(payload),
            }

            if kind == "FILE":
                source = Path(filename).open("rb")

                header.update(
                    filename=Path(filename).name,
                    size=os.fstat(
                        source.fileno()
                    ).st_size,
                )

                if header["size"] > MAX_FILE:
                    raise ValueError(
                        "File vượt quá 1 GiB"
                    )

            # Timeout kết nối: 5 giây.
            conn = socket.create_connection(
                (ip, port),
                timeout=5,
            )

            # Timeout cho thao tác gửi/nhận tiếp theo.
            conn.settimeout(30)

            self._track(conn)
            send_header(conn, header)

            if source is None:
                conn.sendall(payload)

            else:
                remaining = header["size"]
                last_percent = -10

                while remaining:
                    block = source.read(
                        min(CHUNK, remaining)
                    )

                    if not block:
                        raise OSError(
                            "File nguồn bị thay đổi "
                            "trong lúc gửi"
                        )

                    conn.sendall(block)
                    remaining -= len(block)

                    percent = int(
                        (header["size"] - remaining)
                        * 100
                        / header["size"]
                    )

                    # Giảm số dòng thông báo trên console.
                    if (
                        percent >= last_percent + 10
                        or remaining == 0
                    ):
                        self.notify(
                            f"[*] Đang gửi "
                            f"{Path(filename).name}: "
                            f"{percent}%"
                        )
                        last_percent = percent

                if header["size"] == 0:
                    self.notify(
                        "[*] Đang gửi file rỗng: 100%"
                    )

            # Chờ bên nhận xác nhận đã xử lý xong.
            response = recv_header(conn)

            if response.get("type") != "ACK":
                raise ValueError(
                    "Không nhận được ACK hợp lệ"
                )

            send_header(
                conn,
                {"type": "BYE"},
            )

            self.notify(
                f"[Đã gửi {kind}] {ip}:{port}"
            )

        finally:
            if source is not None:
                source.close()

            if conn is not None:
                self._close(conn)

    # ---------- DỌN DẸP KHI THOÁT ----------

    def stop(self):
        self.stopping.set()

        if self.server is not None:
            self.server.close()

        with self.lock:
            connections = list(self.connections)

        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

            conn.close()