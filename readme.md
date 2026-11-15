# Ghi chú dự án

## Thống nhất định dạng `online_peers`

`online_peers` lưu thông tin của các user đang online. Dùng username làm key; mỗi peer phải có cùng một bộ trường để các phần khác của chương trình truy cập dữ liệu nhất quán:

```python
online_peers = {
    "Alice": {
        "ip": "192.168.1.15",
        "tcp_port": 5001,
        "status": "online",
        "last_seen": 1710000000.0,  # Giá trị time.time() gần nhất
    }
}
```

Quy ước:

- `ip`: địa chỉ IP của peer, kiểu chuỗi.
- `tcp_port`: cổng TCP của peer, kiểu số nguyên.
- `status`: trạng thái của peer, ví dụ `"online"` hoặc `"away"`.
- `last_seen`: thời điểm nhận được thông tin gần nhất, lấy bằng `time.time()`.

Khi thêm hoặc cập nhật peer, luôn giữ nguyên cấu trúc và tên các trường trên. 
(nếu mà có muốn mở rộng thông tin cho mỗi peer, nhớ nhắc lên nhóm để biết nha, ko crassh đó)

## Nhắc nhở về thứ tự phát triển

T nghĩ xây mấy cái lõi trước như t là UDP, còn hoàng vs bảo là tcp t nghĩ còn có giao đoạn merge lại rồi thiết kế lại UI nữa.
build code thì nhớ dùng class nha, đừng build bằng hàm, tại cx cần lập trình hướng đối tượng để merge cho dễ