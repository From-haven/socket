# Module UDP Discovery & Presence (`udp_manager.py`)

Tài liệu này mô tả chi tiết cấu trúc, các hàm/phương thức hỗ trợ của module **UDP Peer Discovery**, cũng như cách tích hợp (merge) module này với **TCP Chat/File Transfer** và **Giao diện dòng lệnh (CLI)** trong dự án **LAN Chat & File Sharing**.

---

## 1. Tổng quan & Giao thức hoạt động

Module `UDPDiscovery` đảm nhiệm việc tự động phát hiện người dùng trong mạng LAN và đồng bộ trạng thái hoạt động mà không cần máy chủ trung tâm:

* **Cổng UDP cố định:** `9999` (hỗ trợ `SO_REUSEADDR` và `SO_REUSEPORT` để chạy nhiều tiến trình trên cùng 1 máy tính).
* **Định dạng gói tin (Presence Packet):**
  ```text
  HELLO|<username>|<tcp_port>|<status>
  ```
  *Ví dụ:* `HELLO|Quan|5000|online`
* **Chu kỳ phát (Broadcast):** Gửi gói tin quảng bá mỗi **3 giây** tới địa chỉ `255.255.255.255` (hoặc `127.255.255.255` khi test offline trên 1 máy).
* **Cơ chế Timeout:** Tự động xóa người dùng khỏi danh sách và thông báo *offline* nếu không nhận được gói tin `HELLO` từ họ trong vòng **10 giây**.
* **An toàn đa luồng (Thread-safe):** Sử dụng `threading.Lock()` để bảo vệ cấu trúc dữ liệu `online_users` khi các luồng UDP (ghi) và luồng TCP/Main (đọc) truy cập đồng thời.

---

## 2. Cấu trúc Module & Các phương thức hỗ trợ

### 2.1. Khởi tạo đối tượng (`__init__`)

```python
udp = UDPDiscovery(
    username="Quan",
    tcp_port=5000,
    udp_port=9999,
    bcast_ip="255.255.255.255",
    on_notify=None
)
```

| Tham số | Kiểu dữ liệu | Mặc định | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `username` | `str` | *(Bắt buộc)* | Tên hiển thị của người dùng hiện tại. |
| `tcp_port` | `int` | *(Bắt buộc)* | Cổng TCP mà máy này đang lắng nghe để nhận tin nhắn/file. |
| `udp_port` | `int` | `9999` | Cổng UDP dùng chung toàn mạng LAN. |
| `bcast_ip` | `str` | `"255.255.255.255"` | Địa chỉ IP Broadcast. Dùng `"127.255.255.255"` nếu test offline không có Wi-Fi/LAN. |
| `on_notify` | `callable` | `print` | Hàm callback dùng để in thông báo (ví dụ truyền hàm `show_message` của UI vào để không làm vỡ dòng đang gõ). |

---

### 2.2. Các phương thức Public API (Dùng để gọi từ bên ngoài)

Đây là các hàm chuẩn được thiết kế sẵn để phần **Main CLI** và **TCP** gọi trực tiếp mà không cần can thiệp vào logic bên trong:

1. **`start()`**
   * **Chức năng:** Kích hoạt 2 luồng chạy ngầm (`daemon=True`): luồng phát broadcast định kỳ 3s (`_broadcast_loop`) và luồng lắng nghe gói tin đến (`_listen_loop`).
   * **Thời điểm gọi:** Ngay khi khởi động chương trình chính, sau khi đã mở xong cổng lắng nghe TCP.

2. **`get_online_users() -> dict`**
   * **Chức năng:** Trả về một bản sao an toàn (thread-safe copy) của danh sách người dùng đang trực tuyến.
   * **Cấu trúc dữ liệu trả về:**
     ```python
     {
         "Minh": {
             "ip": "192.168.1.12",
             "tcp_port": 5002,
             "status": "online",       # "online" hoặc "away"
             "last_seen": 1710000000.0 # Timestamp lần cuối nhận gói UDP
         }
     }
     ```
   * **Thời điểm gọi:** Khi người dùng nhập lệnh `/list`.

3. **`get_peer(name_or_index: str) -> tuple | None`**
   * **Chức năng:** Tra cứu thông tin kết nối của một người dùng dựa trên **tên** (ví dụ `"Minh"`) hoặc **số thứ tự** hiển thị trong lệnh `/list` (ví dụ `"1"`).
   * **Giá trị trả về:**
     * Trả về tuple `(name, ip, tcp_port)` nếu tìm thấy (ví dụ: `("Minh", "192.168.1.12", 5002)`).
     * Trả về `None` nếu người dùng không tồn tại hoặc đã offline.
   * **Thời điểm gọi:** Khi người dùng nhập lệnh `/chat <name|number>` để bên TCP lấy `ip` và `tcp_port` tiến hành `connect()`.

4. **`set_status(new_status: str)`**
   * **Chức năng:** Cập nhật trạng thái của bản thân (`"online"` hoặc `"away"`). Trạng thái mới sẽ tự động được đính kèm vào gói tin `HELLO` ở chu kỳ phát tiếp theo.
   * **Thời điểm gọi:** Khi người dùng nhập lệnh `/status online` hoặc `/status away`.

5. **`stop()`**
   * **Chức năng:** Dừng an toàn các vòng lặp ngầm và đóng socket UDP.
   * **Thời điểm gọi:** Khi người dùng nhập lệnh `/quit` hoặc thoát chương trình (`Ctrl+C`).

---

### 2.3. Các phương thức nội bộ (Private Methods)

* `_create_socket()`: Khởi tạo socket `AF_INET`, `SOCK_DGRAM`, thiết lập `SO_REUSEADDR`, `SO_REUSEPORT`, `SO_BROADCAST`, gắn cổng `bind(("", udp_port))` và đặt `settimeout(1.0)`.
* `_broadcast_loop()`: Vòng lặp gửi datagram `HELLO|...` mỗi 3 giây và gọi `_check_timeouts()`.
* `_listen_loop()`: Vòng lặp nhận dữ liệu qua `recvfrom(1024)`, lọc bỏ gói tin của chính mình, cập nhật `ip` (lấy từ `addr[0]`), `tcp_port`, `status`, `last_seen` và gọi `on_notify` nếu có người mới vào mạng.
* `_check_timeouts()`: Quét danh sách `online_users`, xóa các user có `time.time() - last_seen > 10.0` và phát thông báo offline.

---

## 3. Hướng dẫn kết nối (Merge) với TCP & Chương trình chính

Để ghép module UDP với phần TCP của nhóm, file chính (`lanchat.py`) chỉ cần import `UDPDiscovery` và kết nối theo các điểm chạm sau:

### 3.1. Sơ đồ luồng dữ liệu giữa UDP và TCP

```text
[Mạng LAN] --(UDP Port 9999)--> UDPDiscovery.online_users (Lưu IP & TCP Port trên RAM)
                                        │
                                        ▼ (Gọi udp.get_peer("Minh") hoặc udp.get_peer("1"))
[Lệnh /chat] -------------------> Lấy được (name, ip, tcp_port)
                                        │
                                        ▼
[TCP Client] -------------------> tcp_sock.connect((ip, tcp_port)) -> Bắt đầu chat / gửi file
```

### 3.2. Code mẫu tích hợp trong file `lanchat.py`

```python
from udp_manager import UDPDiscovery
# from tcp_manager import TCPManager  # Module của thành viên làm TCP
# from ui_helper import show_message  # Hàm in không làm mất dòng đang gõ

def main():
    my_name = "Quan"
    my_tcp_port = 5000

    # 1. Khởi tạo TCP Server trước để sẵn sàng nhận kết nối
    # tcp = TCPManager(username=my_name, tcp_port=my_tcp_port, on_message=show_message)
    # tcp.start_server()

    # 2. Khởi tạo và chạy UDP Discovery (truyền hàm show_message vào on_notify)
    udp = UDPDiscovery(
        username=my_name,
        tcp_port=my_tcp_port,
        bcast_ip="255.255.255.255",
        on_notify=print  # Thay bằng show_message khi ghép UI
    )
    udp.start()

    # 3. Vòng lặp xử lý lệnh người dùng
    try:
        while True:
            user_input = input("> ").strip()
            if not user_input:
                continue

            # Lệnh /list: Lấy danh sách từ UDP
            if user_input == "/list":
                users = udp.get_online_users()
                if not users:
                    print("[*] Không có ai đang online.")
                else:
                    for idx, (name, info) in enumerate(users.items(), 1):
                        print(f"{idx}. {name:<10} ({info['ip']})  {info['status']}")

            # Lệnh /status: Đổi trạng thái qua UDP
            elif user_input.startswith("/status "):
                status = user_input.split(" ", 1)[1].strip()
                if status in ("online", "away"):
                    udp.set_status(status)
                    print(f"[*] Trạng thái đã đổi thành: {status}")
                else:
                    print("[!] Chỉ hỗ trợ: /status online hoặc /status away")

            # Lệnh /chat: Tra cứu IP/Port từ UDP -> Truyền sang TCP kết nối
            elif user_input.startswith("/chat "):
                target = user_input.split(" ", 1)[1].strip()
                peer = udp.get_peer(target)
                if peer is None:
                    print(f"[!] Không tìm thấy người dùng '{target}' hoặc người này đã offline.")
                else:
                    peer_name, peer_ip, peer_tcp_port = peer
                    print(f"[*] Đang kết nối tới {peer_name} ({peer_ip}:{peer_tcp_port})...")
                    # Gọi hàm kết nối của bên TCP:
                    # tcp.connect_to_peer(peer_name, peer_ip, peer_tcp_port)

            # Lệnh /quit: Dọn dẹp cả UDP và TCP
            elif user_input == "/quit":
                break

            else:
                # Gửi tin nhắn chat thông thường qua TCP tới current_partner
                # tcp.send_chat_message(user_input)
                pass

    except KeyboardInterrupt:
        pass
    finally:
        udp.stop()
        # tcp.stop()
        print("[*] Đã thoát chương trình.")

if __name__ == "__main__":
    main()
```

---

## 4. Lưu ý quan trọng khi nhóm chạy thử nghiệm (Testing)

1. **Xử lý khi nhận kết nối TCP đến (Incoming TCP Connection):**
   * Khi Máy A gõ `/chat Máy B`, Máy B sẽ nhận được một kết nối TCP mới thông qua `accept()`.
   * Để Máy B biết ai vừa kết nối tới mình (và hiển thị đúng tên thay vì chỉ hiện địa chỉ IP), bên TCP có thể tra ngược địa chỉ IP của kết nối đến trong `udp.get_online_users()`, hoặc gửi một gói tin chào hỏi nhỏ chứa `<username>` ngay khi vừa thiết lập kết nối TCP.
2. **Test trên 1 máy tính (Localhost):**
   * Mỗi cửa sổ terminal bắt buộc phải chạy với một `--tcp-port` khác nhau (ví dụ `5001`, `5002`, `5003`), trong khi cổng UDP vẫn giữ nguyên là `9999`.
   * Nếu máy tính ngắt kết nối Wi-Fi/mạng dây, cần truyền `bcast_ip="127.255.255.255"` để các tiến trình nội bộ nhìn thấy nhau.
3. **Firewall trên Windows:**
   * Khi chạy trên 2 máy tính khác nhau qua Wi-Fi, cần cấp quyền cho Python vượt qua **Windows Defender Firewall** (tích cả *Private* và *Public networks*), nếu không gói tin UDP Broadcast sẽ bị chặn ở chiều nhận.