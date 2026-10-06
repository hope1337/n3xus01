# Phạm vi an toàn

- Không sửa SSH/Tailscale/firewall/GPU driver, không sudo cho workloads. `prepare --install-tools --enable-linger` là ngoại lệ có yêu cầu và xác nhận: cài tmux bằng apt nếu thiếu, bật user linger.
- Strict SSH host key verification; không copy private key hoặc lưu password. JSON mode không mở sudo/prompt.
- Config/profile/helper/unit ownership guards. Refuse symlink và metadata có duplicate keys. Archive chỉ regular files, tên portable, giới hạn 64 MiB/20k files; không shell-eval argv.
- Sync bỏ các tên secret thông dụng (.env/key/pem), cache và datasets/checkpoints; **không phải scanner bí mật**. Chỉ sync thư mục code đã kiểm tra. Dữ liệu cũ không tự xóa, chown/chmod.
- Workloads chạy bằng SSH user, có quyền đọc/ghi file của user đó; không isolation hay resource limits. --gpu chỉ chọn CUDA_VISIBLE_DEVICES. App có thể không tuân theo biến này.
- Conda install/create/remove yêu cầu xác nhận. Base được bảo vệ khỏi install; env riêng không được remove. CLI chỉ phát hiện env dùng trong jobs/services nó quản lý, không thấy mọi notebook/process riêng.
- Service bind Tailscale bằng placeholders; listener kiểm tra lúc launch/restart runner. App vẫn có thể mở port khác: dùng code tin cậy. Không tự thêm HTTPS/authentication hoặc tailnet ACL.
- stop chỉ nhắm process group với PID identity còn khớp; clean chỉ job đã kết thúc và không có runner. Service unit kiểm tra fingerprint trước control/remove. Không động vào tmux/systemd cá nhân.
- Logs job giữ tối đa khoảng 3×8 MiB, output/code không tự xóa. Conda cache/journal do công cụ tương ứng quản lý. clean sẽ xóa đúng outputs/logs/workspace sau xác nhận; fetch trước.
- Không có backup/HA/coordinator. Mất disk device có thể mất state/results; ổ local không phải backup.

- Host setup mặc định đăng ký global CLI: launcher riêng cho user, HKCU PATH trên Windows hoặc marked PATH block trong .profile/.bashrc trên Ubuntu. Không system PATH/admin/pip/execution-policy changes. setup --no-register tránh các thay đổi này. Unregister chỉ gỡ launcher khớp template và block nguyên vẹn, không xóa config hoặc remote state; giữ PATH/profile khác của người dùng.
