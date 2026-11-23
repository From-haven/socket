import os
import socket
import threading

from .tcp_protocol import TCPProtocol


def format_bytes(num_bytes):
    """Format dung lượng file thành đơn vị B, KB, MB, GB dễ đọc."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


class TCPFileHandler:
    """
    Xử lý tác vụ gửi và nhận file qua kết nối TCP:
    - Gửi file trên một kết nối TCP riêng biệt và Thread riêng (không làm nghẽn chat).
    - Hiển thị tiến độ truyền file (percentage).
    - Lưu file vào thư mục downloads/, xóa file dở dang (.part) nếu quá trình truyền bị gián đoạn.
    """

    def __init__(self, downloads_dir="downloads", on_output=None):
        self.downloads_dir = downloads_dir
        self.on_output = on_output if on_output is not None else print
        os.makedirs(self.downloads_dir, exist_ok=True)

    def _emit(self, text):
        self.on_output(text)

    def send_file_async(self, partner, ip, tcp_port, filepath, sender_username=None):
        """Khởi động luồng gửi file nền (background thread)."""
        if not os.path.isfile(filepath):
            self._emit(f"[!] File not found: {filepath}")
            return None

        t = threading.Thread(
            target=self._send_worker,
            args=(partner, ip, tcp_port, filepath, sender_username),
            daemon=True,
        )
        t.start()
        return t

    def _send_worker(self, partner, ip, tcp_port, filepath, sender_username=None):
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        size_str = format_bytes(file_size)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            sock.settimeout(5.0)
            sock.connect((ip, tcp_port))
            sock.settimeout(30.0)

            # Gửi header FILE (đính kèm sender_username để phân biệt khi test localhost)
            sock.sendall(TCPProtocol.encode_file_header(filename, file_size, sender=sender_username))

            sent = 0
            last_pct_bucket = -1

            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(TCPProtocol.CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent += len(chunk)

                    if file_size > 0:
                        pct = int(sent * 100 / file_size)
                        bucket = pct // 20  # Thông báo mỗi 20%
                        if bucket != last_pct_bucket and pct < 100:
                            last_pct_bucket = bucket
                            self._emit(f"[*] Sending {filename} ({size_str}) to {partner} ... {pct}%")

            self._emit(f"[*] Sending {filename} ({size_str}) ... 100% Done.")

        except OSError as exc:
            self._emit(f"[!] File transfer interrupted ({filename}): {exc}")
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def receive_file(self, conn, sender_label, raw_filename, file_size):
        """Nhận file từ socket TCP và lưu vào downloads/."""
        if file_size < 0:
            raise ValueError("Dung lượng file không hợp lệ (âm).")

        safe_name = os.path.basename(raw_filename.replace("\\", "/")).replace("|", "_") or "received_file"
        dest_path = self._unique_download_path(safe_name)
        part_path = dest_path + ".part"
        size_str = format_bytes(file_size)

        received = 0
        last_pct_bucket = -1

        try:
            with open(part_path, "wb") as f:
                while received < file_size:
                    to_read = min(TCPProtocol.CHUNK_SIZE, file_size - received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        raise ConnectionResetError("Truyền file bị ngắt quãng giữa chừng.")
                    f.write(chunk)
                    received += len(chunk)

                    if file_size > 0:
                        pct = int(received * 100 / file_size)
                        bucket = pct // 20
                        if bucket != last_pct_bucket and pct < 100:
                            last_pct_bucket = bucket
                            self._emit(f"[*] Receiving {safe_name} from {sender_label}: {pct}%")

            # Đổi tên file từ .part sang file chính thức sau khi nhận trọn vẹn
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.replace(part_path, dest_path)
            self._emit(f"[*] Received {safe_name} ({size_str}) from {sender_label} -> Saved to {dest_path}")

        except Exception as exc:
            # Xóa file dở dang nếu xảy ra lỗi
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            self._emit(f"[!] File transfer failed ({safe_name}): {exc}")

    def _unique_download_path(self, filename):
        """Đảm bảo không ghi đè file có sẵn bằng cách thêm hậu tố số thứ tự _1, _2..."""
        base, ext = os.path.splitext(filename)
        candidate = os.path.join(self.downloads_dir, filename)
        counter = 1
        while os.path.exists(candidate) or os.path.exists(candidate + ".part"):
            candidate = os.path.join(self.downloads_dir, f"{base}_{counter}{ext}")
            counter += 1
        return candidate
