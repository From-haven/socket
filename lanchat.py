#!/usr/bin/env python3
"""
LAN Chat & File Sharing (Command-Line)
--------------------------------------
Ứng dụng chat ngang hàng P2P qua mạng LAN kết hợp cả TCP và UDP:
- UDP: Dò tìm người dùng trong mạng (Peer Discovery) & đồng bộ trạng thái (Online/Away).
- TCP: Mở phiên chat P2P tin cậy và truyền file nhị phân kèm hiển thị tiến độ.
- Console UI: Sử dụng prompt_toolkit + patch_stdout() chống vỡ dòng nhập khi tin nhắn đến.
"""

import argparse
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from tcp.tcp_chat import TCPChatNode
from udp.udp_manager import UDPDiscovery


HELP_TEXT = """
Danh sách lệnh:
  /list                  Hiển thị danh sách người dùng đang online
  /chat <name|number>    Mở kết nối chat với người dùng theo Tên hoặc Số thứ tự
  <any text>             Gửi tin nhắn cho người đang chat cùng
  /send <file>           Gửi file cho người đang chat cùng
  /leave                 Rời phiên chat hiện tại
  /status <online|away>  Đổi trạng thái của bản thân (phát qua UDP)
  /help                  Hiển thị trợ giúp danh sách lệnh
  /quit                  Thoát chương trình
"""


def main():
    parser = argparse.ArgumentParser(description="LAN Chat & File Sharing (P2P)")
    parser.add_argument("--name", required=True, help="Tên hiển thị của bạn (VD: Quan, Minh, Alice)")
    parser.add_argument("--tcp-port", type=int, default=5000, help="Cổng TCP lắng nghe (mặc định: 5000)")
    parser.add_argument("--udp-port", type=int, default=9999, help="Cổng UDP discovery (mặc định: 9999)")
    parser.add_argument(
        "--bcast",
        default="255.255.255.255",
        help="Địa chỉ UDP Broadcast (dùng 127.255.255.255 khi test offline trên 1 máy, hoặc Subnet Broadcast)",
    )
    parser.add_argument(
        "--downloads",
        default="downloads",
        help="Thư mục lưu file nhận được (mặc định: downloads)",
    )

    args = parser.parse_args()

    username = args.name.strip()
    if not username:
        print("[!] Tên người dùng không được để trống.")
        sys.exit(1)

    if "|" in username:
        print("[!] Tên người dùng không được chứa ký tự '|' (tránh làm vỡ gói tin giao thức).")
        sys.exit(1)

    if not (1 <= args.tcp_port <= 65535):
        print("[!] Cổng TCP phải nằm trong khoảng 1 - 65535.")
        sys.exit(1)

    print(f"[*] Khởi động LAN Chat cho '{username}'...")

    # 1. Khởi tạo module UDP Discovery
    udp = UDPDiscovery(
        username=username,
        tcp_port=args.tcp_port,
        udp_port=args.udp_port,
        bcast_ip=args.bcast,
        on_notify=print,
    )

    # 2. Khởi tạo module TCP Chat Node
    tcp_node = TCPChatNode(
        username=username,
        tcp_port=args.tcp_port,
        udp_discovery=udp,
        downloads_dir=args.downloads,
        on_output=print,
    )

    # 3. Kích hoạt dịch vụ mạng
    try:
        tcp_node.start()
        udp.start()
        print(f"[*] Broadcasting presence on UDP port {args.udp_port}")
    except OSError as exc:
        print(f"[!] Không thể mở socket mạng: {exc}")
        udp.stop()
        tcp_node.stop()
        sys.exit(1)

    # 4. Giao diện dòng lệnh tương tác (Prompt Toolkit với patch_stdout chống vỡ dòng)
    session = PromptSession()

    with patch_stdout():
        try:
            while True:
                try:
                    line = session.prompt("> ").strip()
                except (KeyboardInterrupt, EOFError):
                    break

                if not line:
                    continue

                if line.startswith("/"):
                    # Tách lệnh và đối số: tránh lỗi khi gõ lệnh không kèm đối số
                    parts = line.split(maxsplit=1)
                    cmd = parts[0].lower()
                    arg = parts[1].strip() if len(parts) > 1 else ""

                    if cmd == "/quit":
                        break

                    elif cmd == "/help":
                        print(HELP_TEXT)

                    elif cmd == "/list":
                        users = udp.get_online_users()
                        if not users:
                            print("  (Chưa có người dùng nào khác online)")
                        else:
                            for idx, (name, info) in enumerate(users.items(), 1):
                                print(f"  {idx}. {name:<10} ({info['ip']})  {info['status']}")

                    elif cmd == "/chat":
                        if not arg:
                            print("[!] Cú pháp: /chat <tên|số_thứ_tự>")
                        else:
                            tcp_node.open_chat(arg)

                    elif cmd == "/send":
                        filepath = arg.strip("\"'")
                        if not filepath:
                            print("[!] Cú pháp: /send <đường_dẫn_file>")
                        else:
                            tcp_node.send_file(filepath)

                    elif cmd == "/leave":
                        tcp_node.leave_chat()

                    elif cmd == "/status":
                        new_status = arg.lower()
                        if new_status in ("online", "away"):
                            udp.set_status(new_status)
                            print(f"[*] Trạng thái của bạn đã đổi thành: {new_status}")
                        else:
                            print("[!] Cú pháp: /status <online|away>")

                    else:
                        print("[!] Lệnh không hợp lệ. Gõ /help để xem danh sách lệnh.")

                else:
                    # Gửi tin nhắn chat thông thường tới người đang mở chat
                    tcp_node.send_message(line)

        finally:
            print("[*] Đang đóng các kết nối và dừng chương trình...")
            udp.stop()
            tcp_node.stop()
            print("[*] Tạm biệt!")


if __name__ == "__main__":
    main()
