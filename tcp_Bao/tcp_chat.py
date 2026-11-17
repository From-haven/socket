import socket
import threading

from file_transfer import TCPFileHandler
from tcp_protocol import TCPProtocol


class TCPChatNode:
    """
    Lõi TCP server (acceptor) và quản lý phiên chat P2P (1 receiver thread / connection).
    """

    def __init__(
        self,
        username,
        tcp_port,
        registry,
        host="0.0.0.0",
        file_handler=None,
        on_output=None,
    ):
        self.username = username
        self.host = host
        self.tcp_port = int(tcp_port)
        self.registry = registry
        self.on_output = on_output if on_output is not None else print
        self.file_handler = (
            file_handler
            if file_handler is not None
            else TCPFileHandler(on_output=self.on_output)
        )

        self._running = False
        self._server_sock = None
        self._accept_thread = None

        self._state_lock = threading.Lock()
        self.current_partner = None
        self.chat_conns = {}
        self.chat_histories = {}
        self.unread_counts = {}

    def _emit(self, text):
        self.on_output(text)

    def start(self):
        if self._running:
            return
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.tcp_port))
        self._server_sock.listen(10)
        self._server_sock.settimeout(1.0)

        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self._emit(f"[*] Listening on TCP port {self.tcp_port}")

    def stop(self):
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
        peer_name = known_peer
        remote_ip, remote_port = addr[0], addr[1]
        try:
            while self._running:
                cmd_bytes = TCPProtocol.recv_until(conn, b"|")
                if cmd_bytes is None:
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
                        peer_name = (
                            self.registry.find_username_by_ip(remote_ip)
                            or f"{remote_ip}:{remote_port}"
                        )
                        self._register_chat_conn(peer_name, conn)

                    self._on_incoming_message(peer_name, text)

                elif cmd == "FILE":
                    name_bytes = TCPProtocol.recv_until(conn, b"|")
                    size_bytes = TCPProtocol.recv_until(conn, b"|")
                    if name_bytes is None or size_bytes is None:
                        break
                    raw_name = name_bytes.decode("utf-8", errors="replace")
                    file_size = int(size_bytes.decode("utf-8"))
                    sender_label = (
                        peer_name
                        or self.registry.find_username_by_ip(remote_ip)
                        or f"{remote_ip}:{remote_port}"
                    )
                    self.file_handler.receive_file(conn, sender_label, raw_name, file_size)

                elif cmd == "BYE":
                    if peer_name:
                        self._emit(f"[*] {peer_name} closed the chat.")
                    break

                else:
                    self._emit(f"[!] Unknown header from {remote_ip}:{remote_port}: {cmd}")
                    break

        except (ConnectionResetError, ValueError, OSError) as exc:
            if self._running and peer_name:
                self._emit(f"[!] Connection with {peer_name} lost: {exc}")
        finally:
            self._remove_chat_conn(peer_name, conn)
            try:
                conn.close()
            except OSError:
                pass

    def _on_incoming_message(self, peer_name, text):
        formatted = f"[{peer_name}] {text}"
        with self._state_lock:
            self.chat_histories.setdefault(peer_name, []).append(formatted)
            is_current = self.current_partner == peer_name
            if not is_current:
                self.unread_counts[peer_name] = self.unread_counts.get(peer_name, 0) + 1
                unread = self.unread_counts[peer_name]

        if is_current:
            self._emit(formatted)
        else:
            self._emit(f"[*] New message from {peer_name} ({unread} unread)")

    def open_chat(self, target):
        peer_name = self._resolve_target(target)
        if peer_name is None:
            self._emit(f"[!] User '{target}' is not online.")
            return False

        peer_info = self.registry.get_peer(peer_name)
        if peer_info is None:
            self._emit(f"[!] User '{peer_name}' has gone offline.")
            return False

        with self._state_lock:
            existing = self.chat_conns.get(peer_name)

        if existing is None:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((peer_info["ip"], peer_info["tcp_port"]))
                sock.settimeout(None)
                sock.sendall(TCPProtocol.encode_ident(self.username))
            except OSError as exc:
                self._emit(
                    f"[!] Cannot connect to {peer_name} "
                    f"({peer_info['ip']}:{peer_info['tcp_port']}): {exc}"
                )
                return False

            self._register_chat_conn(peer_name, sock)
            threading.Thread(
                target=self._handle_connection,
                args=(sock, (peer_info["ip"], peer_info["tcp_port"]), peer_name),
                daemon=True,
            ).start()
            self._emit(f"[*] Connected to {peer_name} ({peer_info['ip']}:{peer_info['tcp_port']})")

        with self._state_lock:
            self.current_partner = peer_name
            unread = self.unread_counts.pop(peer_name, 0)
            history = list(self.chat_histories.get(peer_name, []))

        if unread > 0:
            self._emit(f"[*] Switched to {peer_name} — {unread} unread:")
            for msg in history[-unread:]:
                self._emit(msg)
        else:
            self._emit(f"[*] Chatting with {peer_name}")
        return True

    def send_message(self, text):
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
            return True
        except OSError as exc:
            self._emit(f"[!] Failed to send message to {partner}: {exc}")
            self._remove_chat_conn(partner, sock)
            try:
                sock.close()
            except OSError:
                pass
            return False

    def send_file(self, filepath):
        with self._state_lock:
            partner = self.current_partner

        if not partner:
            self._emit("[!] No active chat. Use /chat <name|number> first.")
            return False

        peer_info = self.registry.get_peer(partner)
        if peer_info is None:
            self._emit(f"[!] Peer '{partner}' has gone offline.")
            return False

        return self.file_handler.send_file_async(partner, peer_info, filepath) is not None

    def leave_chat(self):
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
                sock.close()
            except OSError:
                pass
        self._emit(f"[*] Left chat with {partner}.")

    def _resolve_target(self, target):
        peers = self.registry.list_peers()
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(peers):
                return peers[idx][0]
            return None
        for name, _ in peers:
            if name == target:
                return name
        return None