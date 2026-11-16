# Module TCP Chat & File Transfer

Tài liệu hướng dẫn cài đặt, chạy thử và tích hợp module TCP
trong dự án LAN Chat & File Sharing.

Module TCP đảm nhiệm:
- Gửi và nhận tin nhắn.
- Gửi và nhận file.
- Xử lý nhiều kết nối bằng đa luồng.
- Báo lỗi kết nối và xóa file nhận chưa hoàn chỉnh.

Chương trình `tcp/main.py` dùng để test riêng TCP, không sử dụng UDP.

## 1. Cấu trúc thư mục

```text
socket/
├── requirements.txt
├── tcp/
│   ├── main.py
│   ├── protocol.py
│   ├── tcp_manager.py
│   └── NOTE_TCP.md
└── udp/
    └── ...
```

Vai trò từng file:

| File | Chức năng |
|---|---|
| `protocol.py` | Đóng gói header và đọc dữ liệu theo giao thức |
| `tcp_manager.py` | Lớp TCPManager xử lý kết nối, tin nhắn và file |
| `main.py` | Giao diện dòng lệnh để test riêng TCP |

## 2. Yêu cầu cài đặt

- Python 3.9 trở lên.
- Thư viện `prompt_toolkit`.
- Hai terminal để test trên cùng máy, hoặc hai máy cùng LAN.

Kiểm tra phiên bản Python:

```bash
python --version
```

Trên một số hệ thống Linux/macOS, sử dụng `python3` thay cho `python`.

File `requirements.txt` ở thư mục gốc cần có:

```text
prompt_toolkit>=3.0,<4.0
```

Thư viện `prompt_toolkit` giúp thông báo từ luồng nền không làm
trộn nội dung dòng người dùng đang nhập.

## 3. Cài đặt

Mở terminal tại thư mục gốc repo, nơi chứa thư mục `tcp/`
và file `requirements.txt`.

### 3.1. GitHub Codespaces

Cài thư viện:

```bash
python -m pip install -r requirements.txt
```

Mở hai terminal trong cùng một Codespace để chạy hai peer.

Không cần mở cổng public hoặc chuyển tiếp cổng để test giữa
hai tiến trình trong cùng Codespace bằng `127.0.0.1`.

### 3.2. Windows

Tạo môi trường ảo và cài thư viện:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Khi chạy chương trình, có thể dùng:

```powershell
.\.venv\Scripts\python.exe -m tcp.main --name Hiu --tcp-port 5001 --downloads downloads/Hiu
```

### 3.3. Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Nếu mở terminal mới, cần kích hoạt lại môi trường:

```bash
source .venv/bin/activate
```

## 4. Cách chạy chương trình

Chạy từ thư mục gốc repo bằng:

```bash
python -m tcp.main --name Hiu --tcp-port 5001 --downloads downloads/Hiu
```

Không chạy bằng:

```bash
python tcp/main.py
```

Lý do: code sử dụng import tương đối trong package:

```python
from .tcp_manager import TCPManager
```

### Các tham số

| Tham số | Bắt buộc | Ý nghĩa |
|---|---|---|
| `--name` | Có | Tên hiển thị của người gửi |
| `--tcp-port` | Có | Cổng TCP lắng nghe |
| `--downloads` | Không | Thư mục lưu file nhận, mặc định `downloads` |

Khi khởi động thành công:

```text
[*] Hiu đang nhận TCP tại cổng 5001
```

Mỗi tiến trình vừa mở server TCP để nhận, vừa có thể tạo
kết nối client để gửi dữ liệu cho peer khác.

## 5. Các lệnh sử dụng

| Lệnh | Chức năng |
|---|---|
| `/connect <IP> <port>` | Chọn địa chỉ người nhận |
| `/send <đường dẫn file>` | Gửi file tới địa chỉ đã chọn |
| `/leave` | Bỏ chọn người nhận |
| `/help` | Hiển thị hướng dẫn |
| `/quit` | Dừng chương trình |
| Nội dung thông thường | Gửi tin nhắn tới người đã chọn |

Lưu ý:
- `/connect` chỉ lưu địa chỉ người nhận.
- Kết nối TCP thực sự được mở khi gửi tin nhắn hoặc file.
- Mỗi lượt gửi sử dụng một kết nối riêng.
- `/leave` bỏ chọn người nhận, chương trình vẫn nhận dữ liệu đến.
- Không có `/list`, `/chat` hoặc `/status` trong bản test TCP riêng.

## 6. Demo hai peer trên cùng máy

Mở hai terminal tại thư mục gốc repo.

### Terminal A: Hiu

```bash
python -m tcp.main --name Hiu --tcp-port 5001 --downloads downloads/Hiu
```

### Terminal B: Hon

```bash
python -m tcp.main --name Hon --tcp-port 5002 --downloads downloads/Hon
```

Hai peer dùng cùng IP `127.0.0.1` nhưng phải khác cổng TCP.

### 6.1. Gửi tin nhắn từ Hiu sang Hon

Tại terminal Hiu, nhập:

```text
/connect 127.0.0.1 5002
```

Nhấn Enter và chờ thông báo:

```text
[*] Đã chọn 127.0.0.1:5002. Kết nối sẽ mở khi gửi dữ liệu.
```

Sau đó nhập riêng dòng tiếp theo:

```text
Xin chào Hon!
```

Terminal Hon hiển thị:

```text
[Hiu] Xin chào Hon!
```

Terminal Hiu nhận xác nhận:

```text
[Đã gửi MSG] 127.0.0.1:5002
```

Không dán lệnh `/connect` và tin nhắn cùng lúc thành nhiều dòng.
`prompt_toolkit` có thể nhận toàn bộ nội dung đó trong một lần nhập,
khiến lệnh `/connect` bị báo sai cú pháp.

### 6.2. Trả lời từ Hon sang Hiu

Tại terminal Hon:

```text
/connect 127.0.0.1 5001
```

Nhấn Enter, sau đó nhập:

```text
Chào Hiu, mình nhận được rồi!
```

Hiu sẽ nhận được tin nhắn của Hon.

## 7. Demo gửi file

### 7.1. Chuẩn bị file

Tạo `demo.txt` tại thư mục gốc repo:

```text
socket/
├── demo.txt
├── requirements.txt
└── tcp/
    └── ...
```

Nội dung ví dụ:

```text
Xin chào!
Đây là file thử nghiệm truyền qua TCP.
```

### 7.2. Gửi file

Tại terminal Hiu, chọn Hon nếu chưa chọn:

```text
/connect 127.0.0.1 5002
```

Sau đó nhập:

```text
/send demo.txt
```

Chương trình hiển thị tiến độ và xác nhận:

```text
[*] Đang gửi demo.txt: 100%
[Đã gửi FILE] 127.0.0.1:5002
```

`100%` cho biết đã gửi hết payload qua socket.
Thông báo `[Đã gửi FILE]` xuất hiện sau khi nhận ACK.

### 7.3. Kiểm tra phía nhận

File nằm trong:

```text
downloads/Hon/
```

Tên có dạng:

```text
<mã_UUID>_demo.txt
```

Ví dụ:

```text
a3f8c29e91b74f18a89a5ee03fd67210_demo.txt
```

Đây là hành vi hiện tại của code:

```python
target = self.download_dir / (
    f"{uuid.uuid4().hex}_{name}"
)
```

UUID giúp tránh ghi đè khi nhận nhiều file có cùng tên.
Nội dung file không bị thay đổi.

Bản code này chưa đổi sang cách đặt tên `demo_1.txt`, `demo_2.txt`.

Mở file nhận được và đối chiếu nội dung với file nguồn.

### 7.4. Đường dẫn file

Đường dẫn tương đối được tính từ thư mục đang chạy lệnh,
không phải từ vị trí của `tcp/main.py`.

Nếu chạy từ thư mục gốc repo:

```text
/send demo.txt
```

sẽ tìm `demo.txt` tại thư mục gốc.

Có thể nhập đường dẫn tuyệt đối:

```text
/send C:\Users\YourName\Documents\bai tap.pdf
```

Không thêm dấu nháy bao quanh đường dẫn trong CLI này.
Toàn bộ nội dung sau `/send` được dùng làm đường dẫn.

## 8. Gửi file đồng thời với chat

Gửi một file đủ lớn:

```text
/send video.mp4
```

Sau đó tiếp tục nhập tin nhắn:

```text
Mình đang gửi video cho bạn.
```

Việc gửi chạy ở luồng nền nên không chặn nhập lệnh.

File và tin nhắn sử dụng các kết nối riêng.
Thứ tự nhận giữa các kết nối khác nhau không được bảo đảm.

## 9. Demo trên hai máy trong LAN

Ví dụ:

| Máy | Tên | IP LAN | TCP port |
|---|---|---|---|
| A | Hiu | `192.168.1.10` | `5001` |
| B | Hon | `192.168.1.20` | `5002` |

Máy A:

```bash
python -m tcp.main --name Hiu --tcp-port 5001 --downloads downloads/Hiu
```

Máy B:

```bash
python -m tcp.main --name Hon --tcp-port 5002 --downloads downloads/Hon
```

Tại máy A:

```text
/connect 192.168.1.20 5002
```

Sau đó nhập tin nhắn hoặc `/send`.

Tại máy B, chọn máy A để trả lời:

```text
/connect 192.168.1.10 5001
```

Thay các IP trên bằng IP thật của hai máy.

Điều kiện:
- Hai máy liên lạc được trong LAN.
- Firewall cho phép Python nhận kết nối TCP trên cổng đã chọn.
- Wi-Fi không bật chế độ cô lập các thiết bị.

Không dùng `127.0.0.1` để kết nối sang máy khác.

Nếu chạy trong GitHub Codespaces, IP LAN của máy tính cá nhân
không phải IP của Codespace. Nên test hai terminal trong cùng
Codespace hoặc chạy Python trực tiếp trên hai máy LAN.

## 10. Giao thức truyền dữ liệu

### 10.1. Định dạng

```text
HELLO|<tên người gửi>|
MSG|<số byte>|<nội dung UTF-8>
FILE|<tên file>|<số byte>|<dữ liệu nhị phân>
ACK|
BYE|
```

Tên người gửi và tên file được mã hóa phần trăm trước khi
đưa vào header để tránh xung đột với dấu `|`.

Payload được đọc theo số byte, nên tin nhắn có thể chứa dấu `|`.

### 10.2. Một lượt gửi tin nhắn

```text
Bên gửi → Bên nhận: HELLO|Hiu|MSG|5|hello
Bên nhận → Bên gửi: ACK|
Bên gửi → Bên nhận: BYE|
```

Sau đó kết nối được đóng.

### 10.3. Một lượt gửi file

```text
Bên gửi → Bên nhận: HELLO|Hiu|FILE|demo.txt|5|hello
Bên nhận → Bên gửi: ACK|
Bên gửi → Bên nhận: BYE|
```

ACK chỉ được gửi sau khi bên nhận xử lý xong payload.

### 10.4. Các giới hạn

| Nội dung | Giá trị |
|---|---|
| Kích thước mỗi khối dữ liệu | 4096 byte |
| Độ dài tối đa mỗi trường header | 4096 byte |
| Tin nhắn tối đa | 1 MiB |
| File tối đa | 1 GiB |
| Timeout kết nối | 5 giây |
| Timeout thao tác truyền nhận | 30 giây |

Timeout 30 giây áp dụng cho thao tác socket, không phải
giới hạn tổng thời gian truyền một file.

## 11. Mô hình đa luồng

| Luồng | Nhiệm vụ |
|---|---|
| Main thread | Đọc và xử lý lệnh |
| TCP acceptor | Chấp nhận kết nối mới |
| TCP receiver | Nhận dữ liệu của từng kết nối |
| Sender worker | Gửi tin nhắn hoặc file |

Danh sách socket đang hoạt động được bảo vệ bằng `threading.Lock()`.

`patch_stdout()` giúp các thông báo từ luồng nền được hiển thị
phía trên dòng đang nhập.

## 12. Xử lý file nhận dở

Khi nhận file, chương trình ghi vào:

```text
<mã_UUID>_demo.txt.part
```

Sau khi nhận đủ dữ liệu, file được đổi thành:

```text
<mã_UUID>_demo.txt
```

Nếu phát hiện mất kết nối hoặc lỗi khi đang nhận,
chương trình xóa file `.part`.

Nếu tiến trình nhận bị buộc dừng đột ngột hoặc máy mất điện,
khối dọn dẹp có thể không chạy và file `.part` có thể còn lại.

## 13. Lỗi thường gặp

### 13.1. No module named 'prompt_toolkit'

Cài thư viện bằng đúng Python dùng để chạy chương trình:

```bash
python -m pip install -r requirements.txt
```

### 13.2. Attempted relative import with no known parent package

Chạy từ thư mục gốc bằng:

```bash
python -m tcp.main --name Hiu --tcp-port 5001
```

Không chạy trực tiếp `python tcp/main.py`.

### 13.3. Address already in use

Cổng đang được tiến trình khác sử dụng.

Dừng tiến trình cũ hoặc chọn cổng khác:

```bash
python -m tcp.main --name Hiu --tcp-port 5003
```

### 13.4. Connection refused

Kiểm tra:
- Peer bên nhận đã chạy chưa.
- IP và cổng có đúng không.
- Peer có đang lắng nghe trên cổng đó không.

Thông báo chọn địa chỉ sau `/connect` chưa chứng minh kết nối
thành công. Chương trình chỉ mở kết nối khi gửi dữ liệu.

### 13.5. Báo sai cú pháp /connect

Nhập đúng:

```text
/connect 127.0.0.1 5002
```

Nhấn Enter rồi mới nhập tin nhắn ở lượt tiếp theo.
Không dán nhiều dòng cùng lúc.

### 13.6. Không tìm thấy file

Kiểm tra đường dẫn sau `/send`.

Đường dẫn tương đối được tính từ thư mục đang chạy chương trình.

### 13.7. Tên file nhận có thêm dãy ký tự

Đó là UUID được thêm để tránh trùng tên.
Đây là hành vi được thiết kế trong bản code hiện tại.

## 14. Các trường hợp cần test

| Trường hợp | Kết quả mong đợi |
|---|---|
| Gửi tin nhắn hai chiều | Nhận đúng nội dung |
| Tin nhắn tiếng Việt có dấu `\|` | Không lỗi giải mã hoặc framing |
| Gửi file văn bản | Nhận và mở đúng nội dung |
| Gửi ảnh hoặc PDF | File nhận sử dụng được |
| Gửi file rỗng | Nhận thành công |
| Gửi lại file trùng tên | Các file có UUID khác nhau |
| Chat khi đang gửi file | Vẫn nhập và gửi tin nhắn được |
| Gửi file không tồn tại | Báo lỗi, CLI tiếp tục chạy |
| Gửi tới peer đã tắt | Báo lỗi, CLI tiếp tục chạy |
| Ngắt bên gửi giữa lúc truyền | Bên nhận xóa file nhận dở khi phát hiện lỗi |

## 15. API để tích hợp với phần khác

Khởi tạo:

```python
from tcp.tcp_manager import TCPManager

tcp = TCPManager(
    username="Hiu",
    tcp_port=5001,
    download_dir="downloads/Hiu",
    on_notify=print,
)
```

Mở server:

```python
tcp.start()
```

Gửi tin nhắn:

```python
tcp.send_message(
    "127.0.0.1",
    5002,
    "Xin chào!",
)
```

Gửi file:

```python
tcp.send_file(
    "127.0.0.1",
    5002,
    "demo.txt",
)
```

Dừng module:

```python
tcp.stop()
```

`send_message()` và `send_file()` là các phương thức blocking.
Trong giao diện tương tác, gọi chúng ở luồng nền như cách
`run_background()` trong `tcp/main.py` đang thực hiện.

Khi ghép với UDP:
1. Mở server TCP trước.
2. Khởi động UDP để quảng bá cổng TCP.
3. Lấy IP và cổng peer từ `udp.get_online_users()`.
4. Truyền IP và cổng đó cho TCPManager.

Tên người gửi trong HELLO là thông tin do phía gửi tự khai báo,
chưa có cơ chế xác thực.

## 16. Thoát chương trình

Nhập:

```text
/quit
```

Chương trình đóng server và các socket đang hoạt động.

Nếu đang gửi file, nên chờ thông báo `[Đã gửi FILE]` trước khi thoát.

## 17. Giới hạn hiện tại

- Mỗi lượt gửi sử dụng một kết nối TCP riêng.
- Chưa có phiên chat duy trì lâu dài.
- Chưa có lịch sử chat hoặc số tin chưa đọc.
- Chưa có xác thực hay mã hóa ở tầng ứng dụng.
- Tên file nhận vẫn có tiền tố UUID.