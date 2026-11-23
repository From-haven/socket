"""
Tiện ích dùng chung cho toàn bộ bộ test.

- Tự thêm thư mục gốc project vào sys.path để import `udp`, `tcp`.
- Cấp cổng TCP/UDP ngẫu nhiên (không đụng cổng 9999 nếu bạn đang chạy app thật).
- Output: thay cho print, ghi lại các dòng chương trình in ra để test kiểm tra.
- FakeDiscovery: giả lập danh sách peer để test riêng phần TCP.
- Peer: một "người dùng" TCP hoàn chỉnh (TCPChatNode + Output + FakeDiscovery).
"""

import hashlib
import os
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tcp.tcp_chat import TCPChatNode  # noqa: E402

LOCALHOST = "127.0.0.1"
SLOW = os.environ.get("LANCHAT_TEST_SLOW") == "1"


# --------------------------------------------------------------------------- #
# Cổng mạng & địa chỉ broadcast
# --------------------------------------------------------------------------- #
def free_tcp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((LOCALHOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def udp_socket(port, timeout=1.0):
    """Socket UDP thô dùng làm "máy ngoài" để gửi/nghe gói tin (bind chung cổng với app)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("", port))
    s.settimeout(timeout)
    return s


def _probe_bcast():
    """Chọn địa chỉ broadcast loopback hoạt động được trên máy đang test."""
    port = free_udp_port()
    rx = udp_socket(port, timeout=0.5)
    tx = udp_socket(port)
    try:
        tx.sendto(b"probe", ("127.255.255.255", port))
        rx.recvfrom(16)
        return "127.255.255.255"
    except OSError:
        return LOCALHOST
    finally:
        rx.close()
        tx.close()


BCAST = _probe_bcast()


# --------------------------------------------------------------------------- #
# Chờ điều kiện & thu output
# --------------------------------------------------------------------------- #
def wait_until(predicate, timeout=5.0, interval=0.02):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    try:
        return bool(predicate())
    except Exception:
        return False


class Output:
    """Bộ thu thập tin nhắn in ra (thay thế print) an toàn trong môi trường đa luồng."""

    def __init__(self):
        self._lines = []
        self._lock = threading.Lock()

    def __call__(self, text):
        with self._lock:
            self._lines.append(str(text))

    @property
    def lines(self):
        with self._lock:
            return list(self._lines)

    def text(self):
        with self._lock:
            return "\n".join(self._lines)

    def has(self, pattern):
        with self._lock:
            return any(pattern in line for line in self._lines)

    def count(self, pattern):
        with self._lock:
            return sum(1 for line in self._lines if pattern in line)

    def wait_for(self, pattern, timeout=5.0, interval=0.02):
        return wait_until(lambda: self.has(pattern), timeout=timeout, interval=interval)

    def clear(self):
        with self._lock:
            self._lines.clear()


# --------------------------------------------------------------------------- #
# Giả lập Discovery & Peer hoàn chỉnh cho TCP
# --------------------------------------------------------------------------- #
class FakeDiscovery:
    """Giả lập UDPDiscovery phục vụ kiểm thử độc lập cho module TCP."""

    def __init__(self):
        self.peers = {}  # {name: {"ip": str, "tcp_port": int, "status": str}}
        self._lock = threading.Lock()

    def add_peer(self, name, ip=LOCALHOST, port=5000, status="online"):
        with self._lock:
            self.peers[name] = {
                "ip": ip,
                "tcp_port": int(port),
                "status": status,
                "last_seen": time.time(),
            }

    def remove_peer(self, name):
        with self._lock:
            self.peers.pop(name, None)

    def get_online_users(self):
        with self._lock:
            return dict(self.peers)

    def get_peer(self, target):
        target = str(target).strip()
        with self._lock:
            user_list = list(self.peers.items())
            if target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(user_list):
                    name, info = user_list[idx]
                    return name, info["ip"], info["tcp_port"]
                return None

            if target in self.peers:
                info = self.peers[target]
                return target, info["ip"], info["tcp_port"]
            return None


class Peer:
    """Một đối tượng Peer hoàn chỉnh gói TCPChatNode, Output và FakeDiscovery."""

    def __init__(self, name="Alice", tcp_port=None, downloads_dir=None):
        self.name = name
        self.tcp_port = tcp_port or free_tcp_port()
        self.out = Output()
        self.discovery = FakeDiscovery()
        self.temp_dir = None
        if downloads_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix=f"test_dl_{name}_")
            self.downloads_dir = self.temp_dir
        else:
            self.downloads_dir = downloads_dir
            os.makedirs(self.downloads_dir, exist_ok=True)

        self.node = TCPChatNode(
            username=self.name,
            tcp_port=self.tcp_port,
            udp_discovery=self.discovery,
            downloads_dir=self.downloads_dir,
            host=LOCALHOST,
            on_output=self.out,
        )

    def start(self):
        self.node.start()
        return self

    def stop(self):
        try:
            self.node.stop()
        except Exception:
            pass
        if self.temp_dir and os.path.isdir(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception:
                pass

    def add_contact(self, other_peer, ip=LOCALHOST, port=None):
        """Thêm một peer khác vào danh bạ discovery của peer này."""
        if hasattr(other_peer, "name") and hasattr(other_peer, "tcp_port"):
            self.discovery.add_peer(other_peer.name, ip, other_peer.tcp_port)
        else:
            self.discovery.add_peer(str(other_peer), ip, port or 5000)

    def open_chat(self, target):
        return self.node.open_chat(target)

    def send_message(self, text):
        return self.node.send_message(text)

    def send_file(self, filepath):
        return self.node.send_file(filepath)

    def leave_chat(self):
        return self.node.leave_chat()


def connect_peers(p1, p2):
    """
    Thiết lập kết nối 2 chiều giữa 2 peer:
    p1 mở kết nối tới p2, chờ p2 nhận diện danh tính IDENT,
    sau đó p2 chuyển khung chat tới p1.
    """
    p1.add_contact(p2)
    p2.add_contact(p1)
    p1.open_chat(p2.name)
    wait_until(lambda: p1.name in p2.node.chat_conns, timeout=3.0)
    p2.open_chat(p1.name)
    wait_until(lambda: p2.node.current_partner == p1.name, timeout=3.0)


# --------------------------------------------------------------------------- #
# Tiện ích file & băm kiểm tra toàn vẹn
# --------------------------------------------------------------------------- #
def create_dummy_file(dir_path, filename, size_bytes, pattern=b"A"):
    """Tạo file dữ liệu mẫu cho bài test truyền file."""
    os.makedirs(dir_path, exist_ok=True)
    filepath = os.path.join(dir_path, filename)
    with open(filepath, "wb") as f:
        if len(pattern) == 1:
            f.write(pattern * size_bytes)
        else:
            written = 0
            while written < size_bytes:
                chunk = pattern[: min(len(pattern), size_bytes - written)]
                f.write(chunk)
                written += len(chunk)
    return filepath


def file_sha256(filepath):
    """Tính mã băm SHA256 để so sánh chính xác 100% nội dung giữa 2 file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
