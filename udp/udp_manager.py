import socket
import threading
import time

class UDPDiscovery:
    def __init__(self, username, tcp_port, udp_port=9999, bcast_ip="255.255.255.255", on_notify=None):
        self.username = username
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.bcast_ip = bcast_ip
        self.status = "online"
            
        # Callback in thông báo (sau này ghép với show_message của UI rất tiện)
        self.on_notify = on_notify if on_notify else print 
        
        self.online_users = {} # {name: {"ip": ..., "tcp_port": ..., "status": ..., "last_seen": ...}}
        self.lock = threading.Lock()
        self.running = False
        self.sock = self._create_socket()

    def _create_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", self.udp_port))
        s.settimeout(1.0) # Đặt timeout để vòng lặp recvfrom không bị kẹt vĩnh viễn khi tắt app
        return s

    def start(self):
        self.running = True
        threading.Thread(target=self._broadcast_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _broadcast_loop(self):
        while self.running:
            msg = f"HELLO|{self.username}|{self.tcp_port}|{self.status}".encode("utf-8")
            try:
                self.sock.sendto(msg, (self.bcast_ip, self.udp_port))
            except Exception as e:
                pass
            
            self._check_timeouts()
            time.sleep(3)

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
                        
                    with self.lock:
                        is_new = sender_name not in self.online_users
                        self.online_users[sender_name] = {
                            "ip": addr[0],
                            "tcp_port": int(sender_tcp_port),
                            "status": sender_status,
                            "last_seen": time.time()
                        }
                    if is_new:
                        self.on_notify(f"[*] {sender_name} ({addr[0]}) is {sender_status}")
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    pass

    def _check_timeouts(self):
        now = time.time()
        offline_list = []
        with self.lock:
            for name, info in list(self.online_users.items()):
                if now - info["last_seen"] > 10.0:
                    offline_list.append(name)
                    del self.online_users[name]
                    
        for name in offline_list:
            self.on_notify(f"[*] {name} went offline")

    # --- CÁC HÀM ĐỂ NHÓM GỌI KHI MERGE ---
    def set_status(self, new_status):
        if new_status in ("online", "away"):
            self.status = new_status

    def get_online_users(self):
        with self.lock:
            # Trả về dict copy để bên ngoài đọc an toàn
            return dict(self.online_users)

    def stop(self):
        self.running = False
        self.sock.close()