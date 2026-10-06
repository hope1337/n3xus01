# Workspace cá nhân

CLI tạo các thư mục bên dưới khi chạy `setup` / `communication init`. Dữ liệu thực tế được Git bỏ qua; chỉ file hướng dẫn này được theo dõi.

```text
workspace/
  config/devices.json             máy đã đăng ký và profile
  runs/                          receipt khi gửi job, không phải trạng thái live
  communication/
    shared/
      SUMMARY.md                 ngữ cảnh lâu dài, sửa có chủ đích
      STATUS.md                  snapshot do CLI tạo, có thời điểm
      snapshot.json              dữ liệu snapshot cho agent
      notes/                     các ghi chú riêng biệt, không ghi đè nhau
    agents/AGENT_ID/
      work/                      code tác vụ, script, scratch, báo cáo
      downloads/                 kết quả tải về
      notes/                     bản ghi chú của agent này
  legacy/                        dữ liệu cũ được giữ để đối chiếu
```

Agent chọn ID riêng cho mỗi phiên, dùng `communication init ID`. Chỉ viết trong thư mục của mình; giao tiếp bằng `communication note`, đọc ghi chú chung bằng `communication show`. Không sửa file của agent khác. Không lưu mật khẩu/key/token vào ghi chú hay báo cáo. Snapshot phải được kiểm tra lại với trạng thái live trước khi hành động.

Code trên device và log/state của job nằm trong home của SSH user do CLI quản lý. Dataset/model lớn giữ tại đường dẫn hiện có trên device; không gom về repo hoặc upload toàn bộ workspace.
