import socket
import threading

from .file_transfer import TCPFileHandler
from .tcp_protocol import TCPProtocol


class TCPChatNode:
    """
    Quản lý các kết nối TCP:
    - TCP Server (lắng nghe kết nối đến bằng accept loop).
    - Quản lý phiên chat P2P (mỗi kết nối chat duy trì 1 Receiver Thread riêng).
    - Lưu trữ lịch sử hội thoại và bộ đếm tin nhắn chưa đọc (unread counters).
    - Quản lý kết nối gửi/nhận file độc lập với luồng chat.
    - Thread-safe đối với trạng thái kết nối và lịch sử chat.
    """

    def __init__(
        self,
        username,
        tcp_port,
        udp_discovery,
        downloads_dir="downloads",
        host="0.0.0.0",
        on_output=None,
    ):
        self.username = username
        self.host = host
        self.tcp_port = int(tcp_port)
        self.udp_discovery = udp_discovery
        self.on_output = on_output if on_output is not None else print

        self.file_handler = TCPFileHandler(
            downloads_dir=downloads_dir,
            on_output=self.on_output,
        )

        self._running = False
        self._server_sock = None
        self._accept_thread = None

        self._state_lock = threading.Lock()
        self.current_partner = None      # Tên peer đang mở khung chat
        self.chat_conns = {}            # {peer_name: socket}
        self.chat_histories = {}        # {peer_name: [list các tin nhắn]}
        self.unread_counts = {}         # {peer_name: số tin chưa đọc}

    def _emit(self, text):
        self.on_output(text)

    def start(self):
        """Khởi động TCP server lắng nghe kết nối đến."""
        if self._running:
            return
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.tcp_port))
        self._server_sock.listen(15)
        self._server_sock.settimeout(1.0)

        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self._emit(f"[*] Listening on TCP port {self.tcp_port}")

    def stop(self):
        """Dừng server và đóng tất cả các kết nối TCP đang mở."""
        self._running = False
        with self._state_lock:
            conns = list(self.chat_conns.items())
            self.chat_conns.clear()
            self.current_partner = None

        for _, sock in conns:
            try:
                sock.sendall(TCPProtocol.encode_bye())
            except OSError:
                pass
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    def _accept_loop(self):
        """Luồng tiếp nhận các kết nối TCP mới đến."""
        while self._running and self._server_sock is not None:
            try:
                conn, addr = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=self._handle_connection,
                args=(conn, addr, None),
                daemon=True,
            ).start()

    def _register_chat_conn(self, peer_name, conn):
        with self._state_lock:
            old = self.chat_conns.get(peer_name)
            self.chat_conns[peer_name] = conn
            if old is not None and old is not conn:
                try:
                    old.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    old.close()
                except OSError:
                    pass

    def _remove_chat_conn(self, peer_name, conn):
        if peer_name is None:
            return
        with self._state_lock:
            if self.chat_conns.get(peer_name) is conn:
                del self.chat_conns[peer_name]
                if self.current_partner == peer_name:
                    self.current_partner = None

    def _handle_connection(self, conn, addr, known_peer):
        """Xử lý đọc stream từ một kết nối socket."""
        peer_name = known_peer
        remote_ip, remote_port = addr[0], addr[1]
        clean_bye = False

        try:
            while self._running:
                cmd_bytes = TCPProtocol.recv_until(conn, b"|")
                if cmd_bytes is None:
                    # Bên kia đóng socket (EOF)
                    break
                cmd = cmd_bytes.decode("utf-8", errors="replace").strip().upper()

                if cmd == "IDENT":
                    len_bytes = TCPProtocol.recv_until(conn, b"|")
                    if len_bytes is None:
                        break
                    length = int(len_bytes.decode("utf-8"))
                    peer_name = TCPProtocol.recv_exact(conn, length).decode("utf-8", errors="replace")
                    self._register_chat_conn(peer_name, conn)

                elif cmd == "MSG":
                    len_bytes = TCPProtocol.recv_until(conn, b"|")
                    if len_bytes is None:
                        break
                    length = int(len_bytes.decode("utf-8"))
                    text = TCPProtocol.recv_exact(conn, length).decode("utf-8", errors="replace")

                    if peer_name is None:
                        peer_name = self._resolve_ip(remote_ip) or f"{remote_ip}:{remote_port}"
                        self._register_chat_conn(peer_name, conn)

                    self._on_incoming_message(peer_name, text)

                elif cmd == "FILE":
                    # Hỗ trợ cả 2 định dạng:
                    # 1) FILE|<filename>|<size>|
                    # 2) FILE|<sender>|<filename>|<size>|
                    f1_bytes = TCPProtocol.recv_until(conn, b"|")
                    f2_bytes = TCPProtocol.recv_until(conn, b"|")
                    if f1_bytes is None or f2_bytes is None:
                        break

                    f1_str = f1_bytes.decode("utf-8", errors="replace")
                    f2_str = f2_bytes.decode("utf-8", errors="replace")

                    if f2_str.isdigit():
                        # Định dạng chuẩn 2 trường: FILE|<filename>|<size>|
                        raw_name = f1_str
                        file_size = int(f2_str)
                        sender_label = (
                            peer_name
                            or self._resolve_ip(remote_ip)
                            or f"{remote_ip}:{remote_port}"
                        )
                    else:
                        # Định dạng mở rộng 3 trường: FILE|<sender>|<filename>|<size>|
                        f3_bytes = TCPProtocol.recv_until(conn, b"|")
                        if f3_bytes is None:
                            break
                        sender_label = f1_str
                        raw_name = f2_str
                        file_size = int(f3_bytes.decode("utf-8", errors="replace"))

                    self.file_handler.receive_file(conn, sender_label, raw_name, file_size)

                elif cmd == "BYE":
                    clean_bye = True
                    if peer_name:
                        self._emit(f"[*] {peer_name} closed the chat.")
                    break

                else:
                    self._emit(f"[!] Unknown header from {remote_ip}:{remote_port}: {cmd}")
                    break

            # Kiểm tra thoát đột ngột (crashes, mất mạng, đóng socket mà không gửi BYE)
            with self._state_lock:
                is_active_chat = (peer_name is not None and self.chat_conns.get(peer_name) is conn)

            if not clean_bye and is_active_chat and self._running:
                self._emit(f"[!] {peer_name} disconnected (connection closed).")
                with self._state_lock:
                    if self.current_partner == peer_name:
                        self.current_partner = None

        except (ConnectionResetError, ValueError, OSError) as exc:
            with self._state_lock:
                is_active_chat = (peer_name is not None and self.chat_conns.get(peer_name) is conn)
            # Chỉ thông báo lỗi khi kết nối này vẫn là kết nối chat đang hoạt động
            # (Tránh in lỗi giả khi user chủ động /leave hoặc đóng socket nội bộ)
            if self._running and peer_name and is_active_chat:
                self._emit(f"[!] Connection with {peer_name} lost: {exc}")
        finally:
            self._remove_chat_conn(peer_name, conn)
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def _resolve_ip(self, ip):
        users = self.udp_discovery.get_online_users()
        for name, info in users.items():
            if info.get("ip") == ip:
                return name
        return None

    def _on_incoming_message(self, peer_name, text):
        formatted = f"[{peer_name}] {text}"
        with self._state_lock:
            self.chat_histories.setdefault(peer_name, []).append(formatted)
            is_current = (self.current_partner == peer_name)
            if not is_current:
                self.unread_counts[peer_name] = self.unread_counts.get(peer_name, 0) + 1
                unread = self.unread_counts[peer_name]

        if is_current:
            self._emit(formatted)
        else:
            self._emit(f"[*] New message from {peer_name} ({unread} unread)")

    def open_chat(self, target):
        """Mở hoặc chuyển phiên chat tới một peer (qua tên hoặc STT)."""
        peer_info = self.udp_discovery.get_peer(target)
        if peer_info is None:
            self._emit(f"[!] User '{target}' is not online.")
            return False

        peer_name, peer_ip, peer_tcp_port = peer_info

        with self._state_lock:
            existing_conn = self.chat_conns.get(peer_name)

        # Nếu chưa có kết nối TCP với peer này, thiết lập kết nối mới
        if existing_conn is None:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((peer_ip, peer_tcp_port))
                sock.settimeout(None)
                # Gửi IDENT để peer nhận biết ai vừa kết nối
                sock.sendall(TCPProtocol.encode_ident(self.username))
            except OSError as exc:
                self._emit(
                    f"[!] Cannot connect to {peer_name} "
                    f"({peer_ip}:{peer_tcp_port}): {exc}"
                )
                return False

            self._register_chat_conn(peer_name, sock)
            threading.Thread(
                target=self._handle_connection,
                args=(sock, (peer_ip, peer_tcp_port), peer_name),
                daemon=True,
            ).start()
            self._emit(f"[*] Connected to {peer_name} ({peer_ip}:{peer_tcp_port})")

        # Cập nhật partner hiện tại và đọc các tin nhắn chưa đọc
        with self._state_lock:
            self.current_partner = peer_name
            unread = self.unread_counts.pop(peer_name, 0)
            history = list(self.chat_histories.get(peer_name, []))

        if unread > 0:
            self._emit(f"[*] Switched to {peer_name} — {unread} unread:")
            for msg in history[-unread:]:
                self._emit(msg)
        elif existing_conn is not None:
            self._emit(f"[*] Switched to {peer_name}")

        return True

    def send_message(self, text):
        """Gửi tin nhắn văn bản tới current chat partner."""
        with self._state_lock:
            partner = self.current_partner
            sock = self.chat_conns.get(partner) if partner else None

        if not partner or sock is None:
            self._emit("[!] No active chat. Use /chat <name|number> first.")
            return False

        try:
            sock.sendall(TCPProtocol.encode_msg(text))
            formatted = f"[{self.username}] {text}"
            with self._state_lock:
                self.chat_histories.setdefault(partner, []).append(formatted)
            self._emit(formatted)
            return True
        except OSError as exc:
            self._emit(f"[!] Failed to send message to {partner}: {exc}")
            self._remove_chat_conn(partner, sock)
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
            return False

    def send_file(self, filepath):
        """Gửi file tới current chat partner kèm tên người gửi."""
        with self._state_lock:
            partner = self.current_partner

        if not partner:
            self._emit("[!] No active chat. Use /chat <name|number> first.")
            return False

        peer_info = self.udp_discovery.get_peer(partner)
        if peer_info is None:
            self._emit(f"[!] Peer '{partner}' has gone offline.")
            return False

        _, peer_ip, peer_tcp_port = peer_info
        return self.file_handler.send_file_async(
            partner=partner,
            ip=peer_ip,
            tcp_port=peer_tcp_port,
            filepath=filepath,
            sender_username=self.username,
        ) is not None

    def leave_chat(self):
        """Rời phiên chat hiện tại và gửi BYE."""
        with self._state_lock:
            partner = self.current_partner
            self.current_partner = None
            sock = self.chat_conns.pop(partner, None) if partner else None

        if partner is None:
            self._emit("[!] You are not in a chat.")
            return

        if sock is not None:
            try:
                sock.sendall(TCPProtocol.encode_bye())
            except OSError:
                pass
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self._emit(f"[*] Left chat with {partner}.")
