# Cấu hình chung và dữ liệu từng project

`workspace/` của **repo n3xus** chỉ dùng cho cấu hình device/profile, receipt đăng ký lệnh trong `config/` và dữ liệu cũ được giữ nguyên. Setup mới không tạo communication/runs ở đây. Chỉ file hướng dẫn này được Git theo dõi. Giữ config/profile khi đổi Windows ↔ Ubuntu; không đăng ký device lại cho mỗi project.

Mỗi công việc có folder riêng **ngoài repo CLI**. Người dùng tạo folder rồi chạy `n3xus project init` một lần:

```text
MY_PROJECT/
  .n3xus-project.json             ID project, không có secret
  .gitignore                     được thêm /communication/, giữ các rule cũ
  src/                           code project do bạn/agent viết
  communication/
    runs/                        receipt gửi job/service, không phải trạng thái live
    shared/
      SUMMARY.md                 ngữ cảnh lâu dài, sửa có chủ đích
      STATUS.md                  snapshot do CLI tạo, có thời điểm
      snapshot.json              snapshot cho agent
      notes/                     các ghi chú riêng biệt
    agents/AGENT_ID/
      work/                      script, scratch, báo cáo riêng
      downloads/                 kết quả tải về
      notes/                     ghi chú riêng
```

CLI tìm marker từ thư mục hiện tại lên các thư mục cha. `n3xus project show` cho biết project đang chọn; `--project-dir PATH` chọn project khi chạy ở nơi khác. Đường dẫn code/output/message-file tương đối tính từ gốc project, không được thoát ra ngoài. Chưa có project thì lệnh ghi dữ liệu báo lỗi; không ghi vào workspace CLI thay thế.

Agent chọn ID riêng cho mỗi phiên, dùng `communication init ID`; đọc shared của project, không sửa folder của agent khác. Giao tiếp bằng communication note/show. Không lưu password/key/token. Snapshot job chỉ lấy receipt của project; trạng thái/count device và jobs/dashboard vẫn toàn cục. Luôn kiểm tra lại trạng thái live.

Communication/runs cũ trong workspace của repo CLI không bị xóa, chuyển hay tự gán vào project mới. Chỉ chuyển các file liên quan khi người dùng yêu cầu; không gom/read credential cũ. Code/log/state từ xa và dataset/model vẫn nằm trên device.
