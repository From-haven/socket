from udp.udp_manager import UDPDiscovery


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test UDP Discovery")
    parser.add_argument("--name", required=True, help="Tên của bạn (VD: Quan)")
    parser.add_argument("--tcp-port", type=int, default=5000, help="Cổng TCP giả lập")
    parser.add_argument("--bcast", default="255.255.255.255", help="IP Broadcast (dùng 127.255.255.255 nếu không có mạng)")
    args = parser.parse_args()

    # Khởi tạo và chạy UDP
    udp = UDPDiscovery(username=args.name, tcp_port=args.tcp_port, bcast_ip=args.bcast)
    udp.start()
    print(f"[*] Đã bật UDP cho '{args.name}' (TCP port: {args.tcp_port}, Broadcast: {args.bcast})")
    print("[*] Gõ lệnh: /list | /status online | /status away | /quit")

    try:
        while True:
            cmd = input().strip()
            if cmd == "/list":
                users = udp.get_online_users()
                if not users:
                    print("-> Chưa thấy ai online.")
                else:
                    for idx, (name, info) in enumerate(users.items(), 1):
                        print(f"{idx}. {name} ({info['ip']}:{info['tcp_port']}) - {info['status']}")
            elif cmd.startswith("/status "):
                new_status = cmd.split(" ", 1)[1].strip()
                udp.set_status(new_status)
                print(f"-> Đã đổi trạng thái của bạn thành: {new_status}")
            elif cmd == "/quit":
                break
            else:
                print("-> Lệnh không hợp lệ. Thử: /list, /status away, /quit")
    except KeyboardInterrupt:
        pass
    finally:
        udp.stop()  
        print("[*] Đã thoát.")