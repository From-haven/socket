import argparse

from file_transfer import TCPFileHandler
from peer_registry import PeerRegistry
from tcp_chat import TCPChatNode


class TCPTestCLI:
    """CLI tạm để test độc lập phần TCP trước khi ghép UDP và UI."""

    def __init__(self, chat_node, registry):
        self.chat_node = chat_node
        self.registry = registry

    def run(self):
        self.chat_node.start()
        print("Commands: /list, /chat <name|number>, /send <file>, /leave, /help, /quit")
        try:
            while True:
                line = input("> ").strip()
                if not line:
                    continue
                if line == "/quit":
                    break
                elif line == "/list":
                    peers = self.registry.list_peers()
                    if not peers:
                        print("(No online peers)")
                    for i, (name, info) in enumerate(peers, 1):
                        print(f"  {i}. {name} ({info['ip']}:{info['tcp_port']}) {info['status']}")
                elif line.startswith("/chat "):
                    target = line[6:].strip()
                    if not target:
                        print("[!] Usage: /chat <name|number>")
                    else:
                        self.chat_node.open_chat(target)
                elif line.startswith("/send "):
                    filepath = line[6:].strip().strip("\"'")
                    if not filepath:
                        print("[!] Usage: /send <file>")
                    else:
                        self.chat_node.send_file(filepath)
                elif line == "/leave":
                    self.chat_node.leave_chat()
                elif line == "/help":
                    print("/list | /chat <name|number> | /send <file> | /leave | /quit")
                elif line.startswith("/"):
                    print("[!] Invalid command. Type /help for commands.")
                else:
                    self.chat_node.send_message(line)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            self.chat_node.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--peer", action="append", default=[], help="name:ip:tcp_port")
    parser.add_argument("--downloads", default="downloads", help="Thu muc luu file nhan duoc")
    args = parser.parse_args()

    registry = PeerRegistry()
    for item in args.peer:
        p_name, p_ip, p_port = item.split(":")
        registry.upsert_peer(p_name, p_ip, int(p_port), "online")

    file_handler = TCPFileHandler(downloads_dir=args.downloads)
    chat_node = TCPChatNode(
        username=args.name,
        tcp_port=args.port,
        registry=registry,
        file_handler=file_handler,
    )
    TCPTestCLI(chat_node, registry).run()