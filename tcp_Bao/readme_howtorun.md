## Module TCP: Chat P2P & Truyền File (`tcp/`)

### 1. Tổng quan kiến trúc

Module TCP chịu trách nhiệm thiết lập kết nối trực tiếp giữa các Peer trong mạng P2P, hỗ trợ hai chức năng chính:

- **P2P Chat:** Trao đổi tin nhắn văn bản trực tiếp giữa các Peer thông qua kết nối TCP.
- **P2P File Transfer:** Gửi và nhận file nhị phân thông qua một kết nối TCP riêng biệt, không làm gián đoạn luồng chat.

Mỗi Peer vừa đóng vai trò TCP Server để tiếp nhận kết nối đến, vừa có thể chủ động kết nối tới Peer khác.

Module sử dụng Multithreading để xử lý đồng thời các kết nối và tác vụ truyền file. Ngoài ra, `PeerRegistry` được sử dụng để quản lý danh sách Peer dùng chung với module UDP Discovery.

### 2. Cấu trúc và chức năng các file

| File | Class / Thành phần chính | Chức năng |
| :--- | :--- | :--- |
| `peer_registry.py` | `PeerRegistry` | Quản lý danh sách `online_peers` dùng chung giữa UDP và TCP. Sử dụng `threading.Lock` để đồng bộ truy cập, quản lý 4 trường `ip`, `tcp_port`, `status`, `last_seen`. |
| `tcp_protocol.py` | `TCPProtocol` | Đóng gói và phân tách dữ liệu trên TCP byte stream thông qua các header `IDENT`, `MSG`, `FILE`, `BYE`. Xử lý hiện tượng dính gói và rách gói bằng cơ chế đọc theo độ dài dữ liệu. |
| `file_transfer.py` | `TCPFileHandler` | Xử lý gửi và nhận file nhị phân qua một kết nối TCP riêng. Sử dụng Thread riêng cho tác vụ gửi file, chia dữ liệu thành các chunk 4KB, hiển thị tiến độ và xóa file tải dở khi phát hiện lỗi truyền. |
| `tcp_chat.py` | `TCPChatNode` | Triển khai TCP Server, tiếp nhận kết nối bằng `accept()`, quản lý các phiên chat P2P, gửi và nhận tin nhắn, lưu lịch sử hội thoại trong RAM và đếm tin nhắn chưa đọc (`unread`). |
| `tcp_cli.py` | `TCPTestCLI` | Xây dựng giao diện dòng lệnh (CLI) độc lập để kiểm thử chức năng chat và truyền file trước khi tích hợp với module UDP Discovery. |

### 3. Cơ chế giao tiếp và đóng gói dữ liệu TCP

#### 3.1. Định dạng giao thức

Module TCP sử dụng các header riêng để phân biệt từng loại dữ liệu được truyền qua kết nối TCP.

| Header | Cấu trúc | Chức năng |
| :--- | :--- | :--- |
| `IDENT` | `IDENT\|<length>\|<username>` | Xác định username của Peer khi thiết lập kết nối chat. |
| `MSG` | `MSG\|<length>\|<message>` | Truyền nội dung tin nhắn văn bản UTF-8. |
| `FILE` | `FILE\|<filename>\|<size>\|<raw_bytes>` | Truyền tên file, dung lượng và dữ liệu nhị phân của file. |
| `BYE` | `BYE\|` | Thông báo kết thúc phiên chat và đóng kết nối. |

#### 3.2. Xử lý TCP Byte Stream

Do TCP là giao thức truyền dữ liệu dạng byte stream, hệ thống không giả định mỗi lần `send()` tương ứng với một lần `recv()`.

Để xử lý hiện tượng dính gói và rách gói, module triển khai hai phương thức:

- `recv_until()`: Đọc dữ liệu cho đến khi gặp ký tự phân cách `|`.
- `recv_exact()`: Tiếp tục nhận dữ liệu cho đến khi đủ chính xác số byte được khai báo trong header.

Đối với `IDENT` và `MSG`, độ dài payload được tính theo số byte sau khi mã hóa UTF-8, thay vì số lượng ký tự.

Nhờ vậy, hệ thống hỗ trợ:
- Tin nhắn tiếng Việt có dấu.
- Nội dung tin nhắn chứa ký tự đặc biệt `|`.
- Dữ liệu được phân chia thành nhiều lần truyền TCP mà vẫn có thể khôi phục chính xác nội dung ban đầu.

Đối với dữ liệu file, hệ thống sử dụng dung lượng file được khai báo trong header để xác định chính xác số byte cần nhận.

**Lưu ý:** Header `FILE` hiện sử dụng ký tự `|` để phân tách tên file và dung lượng. Vì vậy, tên file không nên chứa ký tự này.

#### 3.3. Cơ chế kết nối và trao đổi dữ liệu

Quy trình chat P2P được thực hiện như sau:

1. Mỗi Peer khởi chạy một TCP Server và lắng nghe kết nối tại TCP port đã cấu hình.
2. Khi người dùng chọn một Peer thông qua `/chat`, chương trình tra cứu địa chỉ IP và TCP port trong `online_peers`.
3. Peer khởi tạo kết nối TCP đến đối phương.
4. Sau khi kết nối thành công, chương trình gửi header `IDENT` kèm username.
5. Peer nhận kết nối xác định danh tính đối phương và đăng ký socket vào `chat_conns`.
6. Hai Peer sử dụng kết nối TCP này để trao đổi tin nhắn thông qua header `MSG`.
7. Khi muốn rời hội thoại, Peer gửi header `BYE` và đóng kết nối hiện tại.

Mỗi kết nối được xử lý bởi một Receiver Thread riêng để chương trình có thể tiếp nhận nhiều kết nối đồng thời.

#### 3.4. Cơ chế truyền file độc lập với luồng chat

Chức năng truyền file sử dụng một kết nối TCP mới, độc lập với kết nối chat hiện tại.

Quy trình thực hiện:

1. Người dùng nhập lệnh `/send <đường_dẫn_file>`.
2. Hệ thống kiểm tra file có tồn tại hay không.
3. `TCPFileHandler` tạo một Thread riêng để thực hiện tác vụ gửi file.
4. Thread tạo kết nối TCP tới IP và TCP port của Peer nhận.
5. Bên gửi truyền header `FILE` chứa tên file và dung lượng.
6. Dữ liệu file được đọc ở chế độ nhị phân (`rb`) và chia thành từng chunk 4096 bytes (4KB).
7. Bên nhận đọc header, xác định dung lượng file và ghi dữ liệu vào thư mục downloads.
8. Khi nhận đủ số byte được khai báo, file được lưu hoàn tất.
9. Nếu quá trình truyền bị gián đoạn và bên nhận phát hiện lỗi, file tải chưa hoàn tất sẽ được xóa.

Việc sử dụng kết nối riêng và Thread riêng giúp hoạt động chat tiếp tục trong khi truyền file.

### 4. Các chức năng hỗ trợ và danh sách lệnh CLI

Giao diện CLI cung cấp các lệnh sau để kiểm thử module TCP:

| Lệnh | Cú pháp | Chức năng |
| :--- | :--- | :--- |
| **Xem danh sách Peer** | `/list` | Hiển thị danh sách Peer trong `online_peers`, bao gồm số thứ tự, username, IP, TCP port và trạng thái. |
| **Mở hội thoại** | `/chat <tên\|số_thứ_tự>` | Kết nối TCP tới Peer được chọn theo username hoặc số thứ tự trong danh sách. |
| **Gửi tin nhắn** | `<nội dung bất kỳ>` | Gửi tin nhắn văn bản UTF-8 tới Peer đang được chọn. |
| **Gửi file** | `/send <đường_dẫn_file>` | Gửi file bất kỳ qua một kết nối TCP riêng và Thread riêng. Hỗ trợ đường dẫn có khoảng trắng khi đặt trong dấu ngoặc kép. |
| **Rời hội thoại** | `/leave` | Gửi gói `BYE\|`, đóng kết nối chat hiện tại và reset trạng thái hội thoại. |
| **Trợ giúp** | `/help` | Hiển thị danh sách các lệnh CLI hợp lệ. |
| **Thoát chương trình** | `/quit` | Dừng TCP Server, đóng các kết nối chat đang được quản lý và thoát chương trình. |

#### 4.1. Quản lý lịch sử hội thoại và tin nhắn chưa đọc

Hệ thống sử dụng hai cấu trúc dữ liệu trong `TCPChatNode`:

- `chat_histories`: Lưu lịch sử tin nhắn của từng Peer.
- `unread_counts`: Đếm số tin nhắn chưa đọc từ từng Peer.

Khi nhận được tin nhắn:

- Nếu người dùng đang mở hội thoại với Peer gửi tin, tin nhắn được hiển thị trực tiếp.
- Nếu người dùng chưa mở hội thoại tương ứng, hệ thống tăng bộ đếm `unread` và hiển thị thông báo có tin nhắn mới.

Khi người dùng mở lại hội thoại bằng `/chat`, hệ thống hiển thị các tin nhắn chưa đọc và reset bộ đếm tương ứng.

**Lưu ý:** Lịch sử hội thoại và số tin nhắn chưa đọc hiện chỉ được lưu trong RAM. Dữ liệu sẽ mất khi chương trình kết thúc.

#### 4.2. Xử lý tên file trùng nhau

Khi nhận một file có tên đã tồn tại trong thư mục downloads, hệ thống tự động tạo tên mới để tránh ghi đè.

Ví dụ:

```text
test file.txt
test file_1.txt
test file_2.txt
```

#### 4.3. Xử lý lỗi

Một số trường hợp lỗi được xử lý trong module:

- File không tồn tại: thông báo lỗi và không khởi chạy tác vụ gửi.
- Kết nối TCP thất bại: hiển thị thông báo lỗi kết nối.
- Truyền file bị gián đoạn: phát hiện lỗi khi không nhận đủ số byte và xóa file tải dở.
- Kết nối chat bị đóng: xóa socket tương ứng khỏi danh sách kết nối đang quản lý.
- Nhận dữ liệu sai định dạng: phát hiện header không hợp lệ và kết thúc xử lý kết nối tương ứng.

### 5. Hướng dẫn chạy Demo trên một máy tính (Localhost)

Để kiểm thử module TCP độc lập trước khi tích hợp UDP Discovery, sử dụng tham số `--peer` để giả lập danh sách Peer đã được khám phá.

Tham số `--downloads` được sử dụng để tách riêng thư mục lưu file nhận được của từng Peer.

#### Bước 1: Chuẩn bị môi trường

Đảm bảo đã có Python và các file trong cùng thư mục:

```text
tcp/
├── peer_registry.py
├── tcp_protocol.py
├── file_transfer.py
├── tcp_chat.py
└── tcp_cli.py
```

Mở hai cửa sổ Terminal tại thư mục chứa các file trên.

#### Bước 2: Khởi chạy hai Peer

**Terminal 1 — Alice (TCP port 5001):**

```bash
python tcp_cli.py --name Alice --port 5001 --peer Bob:127.0.0.1:5002 --downloads downloads_alice
```

**Terminal 2 — Bob (TCP port 5002):**

```bash
python tcp_cli.py --name Bob --port 5002 --peer Alice:127.0.0.1:5001 --downloads downloads_bob
```

Trong đó:

- `--name`: Username của Peer.
- `--port`: TCP port dùng để lắng nghe kết nối đến.
- `--peer`: Thông tin Peer được giả lập theo định dạng `name:ip:tcp_port`.
- `--downloads`: Thư mục lưu file nhận được.

Sau khi chạy, mỗi Terminal sẽ hiển thị thông báo TCP Server đang lắng nghe trên port tương ứng.

#### Bước 3: Kiểm thử chức năng Chat P2P

**3.1. Alice kiểm tra danh sách Peer**

Trên Terminal 1:

```text
> /list
  1. Bob (127.0.0.1:5002) online
```

**3.2. Alice mở hội thoại với Bob**

```text
> /chat Bob
[*] Connected to Bob (127.0.0.1:5002)
[*] Chatting with Bob
```

**3.3. Alice gửi tin nhắn có tiếng Việt và ký tự đặc biệt**

```text
> Chào Bob! Test ký tự | trên TCP framing nhé.
```

**3.4. Bob nhận thông báo tin nhắn chưa đọc**

Trên Terminal 2, vì Bob chưa mở hội thoại với Alice nên chương trình thông báo:

```text
[*] New message from Alice (1 unread)
```

**3.5. Bob mở hội thoại với Alice**

```text
> /chat 1
[*] Switched to Alice — 1 unread:
[Alice] Chào Bob! Test ký tự | trên TCP framing nhé.
```

**3.6. Bob gửi tin nhắn phản hồi**

```text
> Ok Alice, đã nhận đủ không lỗi ký tự!
```

Alice sẽ nhận được tin nhắn trực tiếp trên Terminal 1 nếu đang mở hội thoại với Bob.

Qua bước kiểm thử này, có thể xác nhận:
- Hai Peer thiết lập được kết nối TCP.
- Tin nhắn được trao đổi hai chiều.
- Nội dung tiếng Việt được truyền chính xác.
- Ký tự `|` trong nội dung tin nhắn không làm sai lệch framing.
- Chức năng thông báo và quản lý tin nhắn chưa đọc hoạt động.

#### Bước 4: Kiểm thử chức năng gửi và nhận file

**4.1. Chuẩn bị file mẫu**

Tạo một file mẫu có tên:

```text
test file.txt
```

Đặt file trong thư mục hiện tại của Alice.

Có thể sử dụng file văn bản, hình ảnh, PDF, ZIP hoặc các file nhị phân khác để kiểm thử.

**4.2. Alice gửi file cho Bob**

Trên Terminal 1:

```text
> /send "test file.txt"
```

Thông báo ví dụ:

```text
[*] Sending test file.txt to Bob: 100%
[*] Sent test file.txt (1024 bytes) ... 100% Done.
```

**4.3. Bob nhận file**

Trên Terminal 2:

```text
[*] Receiving test file.txt from Alice: 100%
[*] Saved file to downloads_bob/test file.txt (1024 bytes)
```

Sau khi nhận thành công, file được lưu trong thư mục:

```text
downloads_bob/
└── test file.txt
```

**4.4. Kiểm thử truyền file đồng thời với chat**

Trong lúc Alice gửi file cho Bob, hai Peer vẫn có thể tiếp tục gửi tin nhắn thông qua kết nối chat hiện tại.

Điều này có được nhờ tác vụ gửi file chạy trên Thread riêng và sử dụng kết nối TCP độc lập.

**4.5. Kiểm thử tên file trùng nhau**

Gửi cùng một file nhiều lần theo thứ tự và kiểm tra thư mục nhận.

Hệ thống sẽ tự động đổi tên để tránh ghi đè:

```text
downloads_bob/
├── test file.txt
├── test file_1.txt
└── test file_2.txt
```

#### Bước 5: Kiểm thử rời hội thoại và xử lý lỗi

**5.1. Kiểm thử lệnh `/leave`**

Trên một trong hai Terminal, nhập:

```text
> /leave
```

Peer thực hiện lệnh sẽ nhận thông báo:

```text
[*] Left chat with Bob.
```

Peer còn lại nhận được thông báo:

```text
[*] Bob closed the chat.
```

Kết nối chat được đóng và trạng thái hội thoại hiện tại được reset.

**5.2. Kiểm tra trường hợp file không tồn tại**

Nhập:

```text
> /send khong_ton_tai.pdf
```

Kết quả:

```text
[!] File not found: khong_ton_tai.pdf
```

Chương trình tiếp tục hoạt động bình thường.

**5.3. Kiểm tra ngắt kết nối khi đang truyền file**

Trong quá trình gửi file, thử ngắt kết nối truyền file trước khi receiver nhận đủ dữ liệu.

Khi receiver phát hiện kết nối bị đóng giữa chừng:

- Quá trình nhận file được đánh dấu thất bại.
- File tải chưa hoàn tất được xóa khỏi thư mục downloads.
- Chương trình hiển thị thông báo lỗi truyền file.

Lưu ý: Cơ chế này xử lý trường hợp receiver phát hiện kết nối bị gián đoạn khi đang nhận. Không đảm bảo dọn dẹp file nếu tiến trình receiver bị kết thúc đột ngột hoặc máy tính mất nguồn.

#### Bước 6: Thoát chương trình

Trên mỗi Terminal, nhập:

```text
> /quit
```

Chương trình dừng TCP Server, đóng các kết nối chat đang được quản lý và kết thúc CLI.

Lưu ý: Các Thread truyền file đang chạy hiện chưa được quản lý hoàn tất một cách đồng bộ khi thoát chương trình.

### 6. Hướng dẫn chạy Demo trên hai máy tính thật (LAN / Wi-Fi)

Sau khi kiểm thử thành công trên Localhost, có thể tiếp tục kiểm thử giữa hai máy tính trong cùng mạng LAN hoặc Wi-Fi.

#### Bước 1: Chuẩn bị kết nối mạng

Đảm bảo:

- Hai máy tính kết nối cùng một mạng LAN hoặc Wi-Fi.
- Xác định địa chỉ IPv4 nội bộ của từng máy.
- Các TCP port được cho phép thông qua Firewall.
- Hai máy tính có thể liên lạc trực tiếp với nhau qua mạng nội bộ.

Có thể kiểm tra địa chỉ IPv4 bằng lệnh:

**Windows:**

```bash
ipconfig
```

**Linux:**

```bash
ip addr
```

#### Bước 2: Khởi chạy Peer trên Máy 1

Ví dụ:

- Tên Peer: Alice
- Địa chỉ IP: `192.168.1.10`
- TCP port: `5001`

Chạy lệnh:

```bash
python tcp_cli.py --name Alice --port 5001 --peer Bob:192.168.1.20:5002 --downloads downloads_alice
```

#### Bước 3: Khởi chạy Peer trên Máy 2

Ví dụ:

- Tên Peer: Bob
- Địa chỉ IP: `192.168.1.20`
- TCP port: `5002`

Chạy lệnh:

```bash
python tcp_cli.py --name Bob --port 5002 --peer Alice:192.168.1.10:5001 --downloads downloads_bob
```

Lưu ý: Các địa chỉ IP trong ví dụ chỉ mang tính minh họa. Cần thay thế bằng địa chỉ IPv4 thực tế của hai máy.

#### Bước 4: Kiểm thử giao tiếp giữa hai máy

Sau khi cả hai Peer khởi chạy thành công, thực hiện các thao tác:

1. Sử dụng `/list` để kiểm tra danh sách Peer.
2. Sử dụng `/chat <tên>` để mở hội thoại.
3. Trao đổi tin nhắn tiếng Việt giữa hai máy.
4. Kiểm tra chức năng unread bằng cách gửi tin nhắn khi Peer nhận chưa mở hội thoại.
5. Sử dụng `/send <đường_dẫn_file>` để truyền file.
6. Kiểm tra file nhận được trong thư mục downloads.
7. Sử dụng `/leave` để kiểm tra đóng kết nối.
8. Sử dụng `/quit` để thoát chương trình.

### 7. Tích hợp với module UDP Discovery

Module TCP có thể kiểm thử độc lập thông qua dữ liệu Peer giả lập bằng tham số `--peer`.

Khi tích hợp với module UDP Discovery, hai module phối hợp như sau:

| Module | Trách nhiệm |
| :--- | :--- |
| UDP Discovery | Khám phá các Peer trong cùng mạng và cập nhật thông tin Peer. |
| PeerRegistry | Quản lý danh sách `online_peers` dùng chung giữa UDP và TCP. |
| TCP Chat | Thiết lập kết nối TCP và trao đổi tin nhắn giữa các Peer. |
| TCP File Transfer | Truyền file nhị phân thông qua kết nối TCP riêng biệt. |

Dữ liệu `online_peers` được thống nhất với cấu trúc:

```python
online_peers = {
    "Alice": {
        "ip": "192.168.1.10",
        "tcp_port": 5001,
        "status": "online",
        "last_seen": 1730000000.0
    }
}
```

Khi tích hợp, cần đảm bảo UDP và TCP sử dụng chung dictionary và cùng đối tượng `threading.Lock` thông qua `PeerRegistry` để đồng bộ dữ liệu giữa các luồng.

TCP sẽ sử dụng thông tin `ip` và `tcp_port` trong danh sách Peer để thiết lập kết nối trực tiếp, không cần tự khám phá địa chỉ mạng.

### 8. Tổng kết

Module TCP hoàn thành hai nhóm chức năng cốt lõi của hệ thống P2P:

**1. P2P Chat**
- Thiết lập kết nối TCP trực tiếp giữa các Peer.
- Trao đổi tin nhắn văn bản UTF-8 hai chiều.
- Xử lý framing để tránh lỗi dính gói và rách gói.
- Quản lý nhiều kết nối thông qua Multithreading.
- Lưu lịch sử hội thoại và theo dõi số tin nhắn chưa đọc trong RAM.
- Hỗ trợ đóng phiên chat bằng header `BYE`.

**2. P2P File Transfer**
- Gửi và nhận file nhị phân qua TCP.
- Sử dụng kết nối riêng biệt với luồng chat.
- Chia dữ liệu thành các chunk 4KB.
- Hiển thị tiến độ truyền file.
- Hỗ trợ nhiều loại file.
- Tự động đổi tên khi file nhận bị trùng tên.
- Xử lý lỗi truyền và xóa file tải dở khi phát hiện kết nối bị gián đoạn.

Thông qua việc kết hợp TCP Chat, TCP File Transfer và UDP Discovery, hệ thống hướng tới xây dựng một ứng dụng giao tiếp P2P cho phép các Peer khám phá nhau, trao đổi tin nhắn và chia sẻ file trực tiếp trong mạng nội bộ.