# Kiểm tra trên máy thật

Offline tests không SSH. Flow thật cần user đã chuẩn bị SSH/Tailscale:

1. setup → add một device → prepare tmux/linger → status/check/inspect. Không đổi driver/Conda sẵn có.
2. sync examples/hello → run → wait/logs → fetch. Nội dung hello.txt đúng; exit failed được báo, không giả success.
3. Gửi một task foreground chạy đủ lâu; tắt host terminal, mở lại jobs/logs, task còn chạy. Stop đúng task; tmux cá nhân giữ nguyên.
4. Sync revision mới trong khi job cũ chạy: workspace cũ không bị sửa. Job hoàn tất rồi clean sau khi fetch; output đã tải giữ nguyên.
5. Conda list/inspect env đã có; dùng env với run. Với user approval, plan/install env test hoặc create/remove một managed env. Không chạm base/driver.
6. GPU: inspect GPU/VRAM; chạy code CUDA/PyTorch đã có bằng --env ENV --gpu 0; xem CUDA device và kết quả computation thật. nvidia-smi alone không chứng minh CUDA training hoạt động.
7. sync examples/http → serve → service check trả HTTP 200; tắt host vẫn request được từ tailnet; reboot device rồi check lại. Endpoint bind Tailscale, không wildcard. Stop/remove giữ outputs, không đụng service khác.
8. Host OS switch: cùng devices.json, SSH/key chuẩn bị trên OS mới; setup/status/jobs/services đọc đúng state mà không reprovision.
9. Thêm device thứ hai: đăng ký/inspect/run độc lập, không join cluster, không cấp SSH key giữa devices.

Record OS/version, commands, outcomes in validation.md. Không chạy reboot, package mutation hay dọn kết quả nếu user chưa yêu cầu. Repo không tự thao tác device thật trong offline tests.
