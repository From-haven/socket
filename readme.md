# LAN Chat & File Sharing (Command-Line)
> **Đồ án Lập trình Socket Mạng (Computer Networking)**  
> **Giao thức:** Kết hợp TCP và UDP Socket nguyên bản (Native Socket API)  
> **Ngôn ngữ:** Python 3.9+  

---

## 1. Giới thiệu tổng quan

Dự án xây dựng ứng dụng chat ngang hàng (Peer-to-Peer - P2P) và chia sẻ file chạy trên giao diện dòng lệnh (Console). Mỗi máy người dùng chạy cùng một mã nguồn chương trình và giao tiếp trực tiếp với nhau không qua máy chủ trung tâm (Serverless):
- **UDP Socket (Port 9999):** Dò tìm người dùng tự động trong mạng LAN (Peer Discovery), duy trì trạng thái hoạt động và cập nhật trạng thái `online`/`away`.
- **TCP Socket (Cổng động cấu hình):** Mở kết nối tin cậy trực tiếp giữa 2 peer để gửi/nhận tin nhắn văn bản UTF-8 và truyền file dữ liệu nhị phân với luồng riêng kèm hiển thị tiến độ.
- **Console UI:** Tích hợp `prompt_toolkit` với `patch_stdout()` giải quyết triệt để bài toán giữ nguyên dòng người dùng đang gõ khi có tin nhắn hoặc thông báo mạng ập đến bất ngờ (Typing While Messages Arrive).

---

## 2. Cấu trúc thư mục

```text
subsocket/
├── lanchat.py              # File thực thi chính của ứng dụng
├── requirements.txt        # Danh sách thư viện cần thiết (prompt_toolkit)
├── readme.md               # Hướng dẫn chi tiết cài đặt, kiểm thử & báo cáo
├── udp/
│   ├── __init__.py
│   └── udp_manager.py      # Quản lý UDP Discovery, Broadcast định kỳ & Timeout
├── test/
│   ├── helpers.py
│   ├── test.py             # Nơi chạy toàn bộ test
│   ├── test_error_handing.py
│   ├── test_file_transfer.py
│   ├── test_protocol.py
│   ├── test_tcp_chat.py
│   └── test_udp.py         
├── tcp/
│   ├── __init__.py
│   ├── tcp_protocol.py     # Đóng gói và bóc tách khung dữ liệu TCP (Framing an toàn)
│   ├── tcp_chat.py         # Quản lý TCP Server, phiên chat P2P & unread counter
│   └── file_transfer.py    # Quản lý truyền file luồng riêng & tính tiến độ %
├── downloads/              # Thư mục tự động lưu các file nhận được
└── document project/       # Tài liệu đặc tả yêu cầu & file mẫu của giảng viên
```

---

## 3. Cài đặt môi trường

Chương trình yêu cầu **Python 3.9 trở lên**.

Cài đặt thư viện hỗ trợ giao diện dòng lệnh:
```bash
pip install -r requirements.txt
```
*(Lưu ý: Chỉ cài đặt `prompt_toolkit` phục vụ hiển thị CLI theo đúng tùy chọn Option (a) được giảng viên cho phép. Toàn bộ giao tiếp mạng đều sử dụng thư viện chuẩn `socket` có sẵn của Python).*

---

## 4. Hướng dẫn chạy chương trình & Kiểm thử (Testing)

### 4.1. Kịch bản 1: Chạy thử nghiệm nhiều tiến trình trên CÙNG 1 MÁY (Localhost)

Mở 2 hoặc 3 cửa sổ Terminal khác nhau trong thư mục `subsocket/`. Mỗi terminal đóng vai trò một Peer riêng biệt.

> **Lưu ý cốt lõi khi test Localhost:**
> - Các tiến trình trên 1 máy **phải chọn `--tcp-port` khác nhau** (ví dụ: `5001`, `5002`, `5003`).
> - Cổng UDP **giữ nguyên mặc định 9999** (nhờ cờ `SO_REUSEADDR` nên các tiến trình cùng bind chung vào 9999 mà không bị xung đột).
> - Nếu máy tính đang ngắt kết nối Wi-Fi (offline), thêm tham số `--bcast 127.255.255.255`.
> - Giao thức đã hỗ trợ kèm nhãn người gửi trong header file để tránh nhầm lẫn khi tất cả peer đều chung IP `127.0.0.1`.

**Terminal 1 (Alice):**
```bash
python lanchat.py --name Alice --tcp-port 5001 --bcast 127.255.255.255
```

**Terminal 2 (Bob):**
```bash
python lanchat.py --name Bob --tcp-port 5002 --bcast 127.255.255.255
```

**Terminal 3 (Charlie):**
```bash
python lanchat.py --name Charlie --tcp-port 5003 --bcast 127.255.255.255
```

---

### 4.2. Kịch bản 2: Chạy thử nghiệm trên 2 MÁY TÍNH KHÁC NHAU (Mạng LAN / Wi-Fi)

1. Kết nối cả 2 máy tính vào cùng một mạng Wi-Fi (hoặc switch LAN).
2. **Cấu hình Windows Firewall:** Cấp quyền cho `python.exe` truy cập cả mạng *Private* và *Public*. Nếu không mở, Windows Firewall sẽ chặn các gói tin UDP Broadcast.
3. **Lưu ý về Card mạng ảo & Địa chỉ Broadcast:**
   - Mặc định chương trình dùng `--bcast 255.255.255.255` (Limited Broadcast).
   - Trên Windows, nếu máy có cài các card mạng ảo (WSL, VMware, VirtualBox, Docker...), gói broadcast `255.255.255.255` có thể bị hệ điều hành định tuyến nhầm vào card ảo thay vì card Wi-Fi thật, khiến 2 máy không nhìn thấy nhau.
   - **Giải pháp:** Mở `cmd` gõ `ipconfig`, xem địa chỉ IPv4 và Subnet Mask của card Wi-Fi (ví dụ IP là `192.168.1.15`, Subnet Mask `255.255.255.0` thì địa chỉ Subnet Directed Broadcast là `192.168.1.255`). Khi đó, chạy kèm cờ `--bcast 192.168.1.255`:

**Máy 1 (Minh):**
```bash
python lanchat.py --name Minh --tcp-port 5000 --bcast 192.168.1.255
```

**Máy 2 (Quan):**
```bash
python lanchat.py --name Quan --tcp-port 5000 --bcast 192.168.1.255
```
### 4.3. Test bằng unittest

Bộ kiểm thử tự động nằm trong thư mục `test/` và được gom trong `test/main_test.py`. Tất cả test sử dụng thư viện chuẩn `unittest` của Python, vì vậy không cần cài thêm framework test.

Các test mô phỏng trực tiếp UDP/TCP trên localhost:

| Nhóm | File test | Số test | Kiểm tra |
| :--- | :--- | ---: | :--- |
| `protocol` | `test_protocol.py` | 19 | Đóng gói và bóc tách frame MSG, IDENT, FILE, BYE; đọc đúng độ dài UTF-8; chống dính/rách gói; giới hạn header |
| `udp` | `test_udp.py` | 11 | Định dạng/broadcast HELLO, chu kỳ 3 giây, nhận peer, trạng thái away/online, timeout 10 giây và tra cứu theo tên/STT |
| `tcp` | `test_tcp_chat.py` | 9 | Kết nối và IDENT, chat hai chiều, Unicode/Emoji, unread counter, chuyển phòng chat, /leave và ngắt kết nối |
| `file` | `test_file_transfer.py` | 7 | Gửi file text/binary, SHA256, tiến độ %, đổi tên file trùng, `.part`, chống traversal và chat khi truyền file |
| `error` | `test_error_handling.py` | 8 | User/offline không tồn tại, connection refused, thiếu chat, file không tồn tại, header rác/header quá dài |

**Điều kiện trước khi chạy:** Mở terminal tại thư mục gốc của dự án (`subsocket/`) và đảm bảo Python đã cài đặt.

#### Chạy toàn bộ test

```bash
python test/main_test.py
```

Trong PowerShell trên Windows, nếu terminal không hiển thị đúng tiếng Việt, đặt mã hóa UTF-8 trước:

```powershell
$env:PYTHONIOENCODING="utf-8"
python test/main_test.py
```

Trong Command Prompt:

```bat
set PYTHONIOENCODING=utf-8
python test/main_test.py
```

Mã thoát của runner là `0` khi tất cả test đạt và `1` khi có test fail hoặc error.

#### Chạy test theo từng nhóm

```bash
# Chạy test giao thức TCP
python test/main_test.py -s protocol

# Chạy test UDP
python test/main_test.py -s udp

# Chạy test chat TCP
python test/main_test.py -s tcp

# Chạy test truyền file
python test/main_test.py -s file

# Chạy test xử lý lỗi
python test/main_test.py -s error

# Chạy nhiều nhóm
python test/main_test.py -s udp tcp file

# Chạy tất cả các nhóm (mặc định)
python test/main_test.py -s all
```

Liệt kê các nhóm test mà không chạy test:

```bash
python test/main_test.py -l
```

In chi tiết từng test case thay vì ký hiệu `.`/`F`/`E`:

```bash
python test/main_test.py -v
python test/main_test.py -v -s udp tcp
```

**Kết quả mong đợi:** Tổng cộng có **54 test**. Khi môi trường mạng/socket hoạt động bình thường, kết quả cuối cùng là `54 passed`, không có `failed` hoặc `skipped`.

---

## 5. Danh sách lệnh CLI (Command-Line Interface)

Văn bản gõ thông thường được gửi như tin nhắn chat. Các văn bản bắt đầu bằng dấu `/` là lệnh điều khiển:

| Lệnh | Cú pháp | Ý nghĩa & Hành vi |
| :--- | :--- | :--- |
| **Xem danh sách** | `/list` | Hiển thị danh sách peer đang online kèm STT, Tên, IP và trạng thái. |
| **Mở chat** | `/chat <name\|number>` | Mở kết nối TCP tới peer được chọn theo Tên hoặc Số thứ tự. Hiển thị lại các tin nhắn chưa đọc nếu có. |
| **Gửi tin nhắn** | `<nội dung bất kỳ>` | Gửi tin nhắn tức thì tới người đang mở khung chat. |
| **Gửi file** | `/send <đường_dẫn_file>` | Gửi file nhị phân qua luồng riêng và hiển thị thanh tiến độ `%`. Chat vẫn hoạt động bình thường. |
| **Rời khung chat** | `/leave` | Đóng phiên chat hiện tại và gửi gói tin `BYE\|`. |
| **Đổi trạng thái**| `/status <online\|away>` | Thay đổi trạng thái của bản thân và broadcast ngay lập tức qua UDP. |
| **Trợ giúp** | `/help` | Xem danh sách các lệnh khả dụng. |
| **Thoát** | `/quit` | Dừng tất cả luồng, gửi thông báo đóng kết nối và thoát an toàn. |

---

## 6. Thiết kế kỹ thuật & Xử lý biên (Edge Cases)

### 6.1. Định dạng gói tin UDP (Presence Message)
- **Cấu trúc:** `HELLO|<username>|<tcp_port>|<status>`
- **Validation:** Tên người dùng (`username`) được kiểm tra không chứa ký tự `|` để tránh làm vỡ framing của gói UDP.
- **Tần suất:** Broadcast mỗi 3 giây tới địa chỉ Broadcast mạng.
- **Cơ chế Timeout:** Tự động xóa khỏi danh sách nếu sau 10 giây không nhận được gói tin mới.

### 6.2. Đóng khung dữ liệu TCP (Framing over Byte Stream)
- **Nhận diện:** `IDENT|<length>|<utf-8 username>` (gửi ngay khi kết nối TCP mở).
- **Tin nhắn văn bản:** `MSG|<length>|<utf-8 text>`
- **Truyền file:** `FILE|[<sender>|]<filename>|<size_in_bytes>|<raw file bytes>`
  - Tên file được tự động chuẩn hóa: ký tự `|` được thay bằng `_` để bảo vệ định dạng header.
- **Đóng kết nối:** `BYE|`
- Sử dụng hàm `recv_exact(sock, length)` đảm bảo đọc chính xác số byte cần thiết, chống hoàn toàn hiện tượng dính gói hoặc rách gói.

### 6.3. Xử lý ngắt kết nối đột ngột & Thoát an toàn
- **Peer thoát đột ngột (Crash / Tắt app / Rớt mạng):** Khi socket bị đóng bất ngờ mà không kịp gửi `BYE|`, vòng lặp nhận phát hiện EOF (`None`) và in thông báo `[!] <peer> disconnected (connection closed)` theo đúng mục 5.3 của đề bài.
- **Tránh lỗi giả sau `/leave`:** Hàm `leave_chat()` thực hiện `shutdown(socket.SHUT_RDWR)` trước khi `close()`, đồng thời luồng nhận kiểm tra cờ kết nối hoạt động trước khi in lỗi, đảm bảo không in thông báo "Connection lost" giả mạo trên Windows.

### 6.4. Mô hình đa luồng (Thread Model)
- **Main Thread:** Nhận diện ký tự gõ từ bàn phím qua `PromptSession`, thực thi lệnh CLI và gửi tin nhắn.
- **UDP Broadcaster Thread:** Bộ đếm thời gian (Timer 3s) gửi bản tin hiện diện.
- **UDP Listener Thread:** Nhận gói tin UDP và cập nhật danh bạ `online_users`.
- **TCP Acceptor Thread:** Lắng nghe và tiếp nhận các kết nối TCP mới đến.
- **TCP Receiver Thread (1 luồng/kết nối):** Đọc stream dữ liệu, nhận diện tin nhắn chat hoặc tiếp nhận file nhị phân.
- **File Sender Thread (1 luồng/tác vụ gửi):** Truyền file bất đồng bộ qua socket riêng, không làm nghẽn luồng chat.

---

## 7. Hướng dẫn bắt gói tin Wireshark (Phục vụ chấm điểm)

1. Mở **Wireshark** và chọn card mạng đang kết nối (Wi-Fi hoặc Adapter mạng loopback/Npcap nếu test trên 1 máy).
2. **Chụp UDP Broadcast:**
   - Đặt bộ lọc (Display Filter): `udp.port == 9999`
   - Quan sát các gói tin UDP định kỳ mỗi 3s với payload `HELLO|...`. Chụp ảnh màn hình chi tiết packet payload.
3. **Chụp quá trình bắt tay 3 bước TCP (Three-Way Handshake):**
   - Đặt bộ lọc: `tcp.port == 5001 || tcp.port == 5002` (hoặc cổng TCP bạn đang dùng).
   - Tại terminal, gõ `/chat <name>` hoặc `/send <file>`.
   - Quan sát chuỗi 3 gói tin:
     1. `[SYN]` từ client gửi đến server.
     2. `[SYN, ACK]` từ server phản hồi.
     3. `[ACK]` từ client xác nhận.
   - Chụp ảnh màn hình 3 gói tin này để đưa vào báo cáo đồ án.
