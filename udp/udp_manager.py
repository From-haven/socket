import socket
import threading
import time


class UDPDiscovery:
    """
    Module UDP Peer Discovery:
    - Quét và phát hiện các Peer trong mạng LAN qua cổng UDP cố định (mặc định 9999).
    - Broadcast gói tin hiện diện (Presence message) mỗi 3 giây: HELLO|<name>|<tcp_port>|<status>.
    - Quản lý danh sách online_users: tự động xóa user nếu không nhận được tin trong 10 giây (timeout).
    - Cập nhật và đồng bộ trạng thái (online/away).
    - Thread-safe với Lock.
    """

    def __init__(self, username, tcp_port, udp_port=9999, bcast_ip="255.255.255.255", on_notify=None):
        self.username = username
        self.tcp_port = int(tcp_port)
        self.udp_port = int(udp_port)
        self.bcast_ip = bcast_ip
        self.status = "online"

        # Callback hiển thị thông báo (truyền print hoặc show_message từ UI)
        self.on_notify = on_notify if on_notify is not None else print

        # online_users = {name: {"ip": str, "tcp_port": int, "status": str, "last_seen": float}}
        self.online_users = {}
        self.lock = threading.Lock()
        self.running = False
        self.sock = self._create_socket()

    def _create_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Cho phép nhiều tiến trình trên cùng 1 máy bind chung cổng UDP 9999
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", self.udp_port))
        s.settimeout(1.0)
        return s

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()
        self.send_presence()

    def send_presence(self):
        """Gửi ngay một gói tin HELLO broadcast."""
        msg = f"HELLO|{self.username}|{self.tcp_port}|{self.status}".encode("utf-8")
        try:
            self.sock.sendto(msg, (self.bcast_ip, self.udp_port))
        except Exception:
            pass

    def _broadcast_loop(self):
        while self.running:
            self.send_presence()
            self._check_timeouts()

            # Ngủ ngắn từng bước để có thể dừng ngay khi stop() được gọi
            for _ in range(6):
                if not self.running:
                    break
                time.sleep(0.5)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                msg = data.decode("utf-8", errors="replace")
                parts = msg.split("|")

                if len(parts) == 4 and parts[0] == "HELLO":
                    _, sender_name, sender_tcp_port, sender_status = parts

                    # Bỏ qua gói tin của chính mình
                    if sender_name == self.username:
                        continue

                    sender_tcp_port = int(sender_tcp_port)
                    is_new = False
                    status_changed = False
                    old_status = None

                    with self.lock:
                        if sender_name not in self.online_users:
                            is_new = True
                        else:
                            old_status = self.online_users[sender_name]["status"]
                            if old_status != sender_status:
                                status_changed = True

                        self.online_users[sender_name] = {
                            "ip": addr[0],
                            "tcp_port": sender_tcp_port,
                            "status": sender_status,
                            "last_seen": time.time(),
                        }

                    if is_new:
                        self.on_notify(f"[*] {sender_name} ({addr[0]}) is {sender_status}")
                    elif status_changed:
                        self.on_notify(f"[*] {sender_name} changed status to {sender_status}")

            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    pass

    def _check_timeouts(self):
        """Kiểm tra và xóa peer không gửi tin trong 10s."""
        now = time.time()
        offline_list = []
        with self.lock:
            for name, info in list(self.online_users.items()):
                if now - info["last_seen"] > 10.0:
                    offline_list.append(name)
                    del self.online_users[name]

        for name in offline_list:
            self.on_notify(f"[*] {name} went offline")

    def set_status(self, new_status):
        """Cập nhật trạng thái bản thân (online hoặc away) và phát broadcast tức thì."""
        if new_status in ("online", "away"):
            self.status = new_status
            self.send_presence()

    def get_online_users(self):
        """Trả về bản sao thread-safe của danh sách người dùng online."""
        with self.lock:
            return dict(self.online_users)

    def get_peer(self, target):
        """
        Tra cứu thông tin peer theo Tên hoặc Số thứ tự hiển thị trong /list.
        Trả về: (name, ip, tcp_port) hoặc None nếu không tìm thấy.
        """
        target = str(target).strip()
        with self.lock:
            # Danh sách có thứ tự nhất quán để tra cứu bằng STT
            user_list = list(self.online_users.items())

            # Tra cứu theo số thứ tự (1-based index)
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(user_list):
                    name, info = user_list[idx]
                    return name, info["ip"], info["tcp_port"]
                return None

            # Tra cứu theo tên trực tiếp
            if target in self.online_users:
                info = self.online_users[target]
                return target, info["ip"], info["tcp_port"]

            return None

    def stop(self):
        """Dừng các luồng và đóng socket."""
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
