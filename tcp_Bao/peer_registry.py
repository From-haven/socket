import threading
import time

class PeerRegistry:
    """
    Quản lý online_peers dùng chung giữa UDP và TCP.
    Giữ đúng 4 trường: ip, tcp_port, status, last_seen.
    """

    def __init__(self, shared_peers=None, lock=None):
        self.online_peers = shared_peers if shared_peers is not None else {}
        self.lock = lock if lock is not None else threading.Lock()

    def upsert_peer(self, username, ip, tcp_port, status="online"):
        with self.lock:
            self.online_peers[username] = {
                "ip": str(ip),
                "tcp_port": int(tcp_port),
                "status": str(status),
                "last_seen": time.time(),
            }

    def get_peer(self, username):
        with self.lock:
            info = self.online_peers.get(username)
            return dict(info) if info is not None else None

    def find_username_by_ip(self, ip):
        with self.lock:
            for username, info in self.online_peers.items():
                if info.get("ip") == ip:
                    return username
            return None

    def list_peers(self):
        with self.lock:
            return [(name, dict(info)) for name, info in self.online_peers.items()]