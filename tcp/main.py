import argparse
import threading

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from .tcp_manager import TCPManager


HELP = """\
Các lệnh:
/connect <IP> <port>     Chọn địa chỉ người nhận
/send <đường dẫn file>   Gửi file tới người đã chọn
/leave                  Bỏ chọn người nhận
/help                   Xem hướng dẫn
/quit                   Thoát

Sau khi /connect, gõ nội dung bình thường để gửi tin nhắn.
"""


def run_background(action, *args):
    """Gửi dữ liệu ở luồng riêng để không chặn nhập lệnh."""
    def worker():
        try:
            action(*args)
        except (OSError, ValueError) as exc:
            print(f"[Lỗi gửi] {exc}")

    threading.Thread(
        target=worker,
        daemon=True,
    ).start()


def main():
    parser = argparse.ArgumentParser(
        description="Test riêng TCP Chat và truyền file"
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Tên người dùng, ví dụ Alice",
    )

    parser.add_argument(
        "--tcp-port",
        type=int,
        required=True,
        help="Cổng TCP nhận dữ liệu",
    )

    parser.add_argument(
        "--downloads",
        default="downloads",
        help="Thư mục lưu file nhận được",
    )

    args = parser.parse_args()

    if not args.name.strip():
        parser.error("Tên người dùng không được rỗng")

    if not 1 <= args.tcp_port <= 65535:
        parser.error("TCP port phải nằm trong khoảng 1..65535")

    tcp = TCPManager(
        username=args.name,
        tcp_port=args.tcp_port,
        download_dir=args.downloads,
        on_notify=print,
    )

    # None hoặc tuple (ip, port).
    peer = None

    session = PromptSession()

    # Giữ dòng đang nhập khi luồng nền in thông báo.
    with patch_stdout():
        try:
            tcp.start()

            print(
                f"[*] {args.name} đang nhận TCP "
                f"tại cổng {args.tcp_port}"
            )
            print(HELP)

            while True:
                target = (
                    f"{peer[0]}:{peer[1]}"
                    if peer
                    else "chưa chọn"
                )

                line = session.prompt(
                    f"{args.name} -> {target}> "
                ).strip()

                if not line:
                    continue

                command, _, value = line.partition(" ")
                value = value.strip()

                if command == "/quit":
                    break

                elif command == "/help":
                    print(HELP)

                elif command == "/connect":
                    try:
                        ip, port_text = value.split()
                        port = int(port_text)

                        if not 1 <= port <= 65535:
                            raise ValueError()

                        peer = (ip, port)

                        print(
                            f"[*] Đã chọn {ip}:{port}. "
                            "Kết nối sẽ mở khi gửi dữ liệu."
                        )

                    except ValueError:
                        print(
                            "[!] Cú pháp: "
                            "/connect 127.0.0.1 5002"
                        )

                elif command == "/leave":
                    peer = None
                    print("[*] Đã bỏ chọn người nhận.")

                elif command == "/send":
                    if peer is None:
                        print(
                            "[!] Hãy /connect IP port trước."
                        )

                    elif not value:
                        print(
                            "[!] Cú pháp: "
                            "/send đường_dẫn_file"
                        )

                    else:
                        run_background(
                            tcp.send_file,
                            peer[0],
                            peer[1],
                            value,
                        )

                elif command.startswith("/"):
                    print(
                        "[!] Lệnh không hợp lệ. "
                        "Gõ /help để xem hướng dẫn."
                    )

                elif peer is None:
                    print(
                        "[!] Hãy /connect IP port trước."
                    )

                else:
                    run_background(
                        tcp.send_message,
                        peer[0],
                        peer[1],
                        line,
                    )

        except (KeyboardInterrupt, EOFError):
            pass

        except OSError as exc:
            print(f"[Lỗi khởi động TCP] {exc}")

        finally:
            tcp.stop()
            print("[*] Đã dừng TCP.")


if __name__ == "__main__":
    main()