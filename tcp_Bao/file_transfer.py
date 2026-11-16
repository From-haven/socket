import os
import socket
import threading

from tcp_protocol import TCPProtocol


class TCPFileHandler:
    """
    Xử lý riêng tác vụ gửi và nhận file qua TCP:
    - Gửi file trên một kết nối TCP và một luồng riêng (không chặn chat).
    - Nhận file và lưu vào thư mục downloads/, xóa file dở nếu bị ngắt kết nối.
    """

    def __init__(self, downloads_dir="downloads", on_output=None):
        self.downloads_dir = downloads_dir
        self.on_output = on_output if on_output is not None else print
        os.makedirs(self.downloads_dir, exist_ok=True)

    def _emit(self, text):
        self.on_output(text)

    def send_file_async(self, partner, peer_info, filepath):
        if not os.path.isfile(filepath):
            self._emit(f"[!] File not found: {filepath}")
            return None

        t = threading.Thread(
            target=self._send_worker,
            args=(partner, peer_info["ip"], peer_info["tcp_port"], filepath),
            daemon=True,
        )
        t.start()
        return t

    def _send_worker(self, partner, ip, tcp_port, filepath):
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(5.0)
            sock.connect((ip, tcp_port))
            sock.settimeout(None)
            sock.sendall(TCPProtocol.encode_file_header(filename, file_size))

            sent = 0
            last_step = -1
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(TCPProtocol.CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent += len(chunk)
                    if file_size > 0:
                        pct = int(sent * 100 / file_size)
                        if pct // 20 != last_step or pct == 100:
                            last_step = pct // 20
                            self._emit(f"[*] Sending {filename} to {partner}: {pct}%")
            self._emit(f"[*] Sent {filename} ({file_size} bytes) ... 100% Done.")
        except OSError as exc:
            self._emit(f"[!] File transfer interrupted ({filename}): {exc}")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def receive_file(self, conn, sender_label, raw_filename, file_size):
        if file_size < 0:
            raise ValueError("Invalid negative file size.")
        safe_name = os.path.basename(raw_filename.replace("\\", "/")) or "received_file"
        dest_path = self._unique_download_path(safe_name)
        received = 0
        last_step = -1
        try:
            with open(dest_path, "wb") as f:
                while received < file_size:
                    to_read = min(TCPProtocol.CHUNK_SIZE, file_size - received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        raise ConnectionResetError("Truyền file bị gián đoạn giữa chừng.")
                    f.write(chunk)
                    received += len(chunk)
                    if file_size > 0:
                        pct = int(received * 100 / file_size)
                        if pct // 20 != last_step or pct == 100:
                            last_step = pct // 20
                            self._emit(f"[*] Receiving {safe_name} from {sender_label}: {pct}%")
            self._emit(f"[*] Saved file to {dest_path} ({file_size} bytes)")
        except Exception as exc:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            self._emit(f"[!] File transfer failed ({safe_name}): {exc}")

    def _unique_download_path(self, filename):
        base, ext = os.path.splitext(filename)
        candidate = os.path.join(self.downloads_dir, filename)
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(self.downloads_dir, f"{base}_{counter}{ext}")
            counter += 1
        return candidate