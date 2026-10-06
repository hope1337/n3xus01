# Kiểm tra trên máy thật

Offline tests không SSH. Flow thật cần user đã chuẩn bị SSH/Tailscale:

1. setup → add một device → prepare tmux/linger → status/check/inspect. Không đổi driver/Conda sẵn có.
2. sync examples/hello → run → wait/logs → fetch. Nội dung hello.txt đúng; exit failed được báo, không giả success.
3. Gửi một task foreground chạy đủ lâu; tắt host terminal, mở lại jobs/logs, task còn chạy. Stop đúng task; tmux cá nhân giữ nguyên.
4. Sync revision mới trong khi job cũ chạy: workspace cũ không bị sửa. Job hoàn tất rồi clean sau khi fetch; output đã tải giữ nguyên.
5. Conda list/inspect env đã có; dùng env với run. Với user approval, plan/install env test hoặc create/remove một managed env. Không chạm base/driver.
6. GPU: inspect GPU/VRAM; chạy code CUDA/PyTorch đã có bằng --env ENV --gpu 0; xem CUDA device và kết quả computation thật. nvidia-smi alone không chứng minh CUDA training hoạt động.
7. sync examples/http → serve → service check trả HTTP 200; tắt host vẫn request được từ tailnet; reboot device rồi check lại. Endpoint bind Tailscale, không wildcard. Stop/remove giữ outputs, không đụng service khác.
8. Host OS switch: cùng workspace/config/devices.json, SSH/key chuẩn bị trên OS mới; setup/status/jobs/services đọc đúng state mà không reprovision.
9. Thêm device thứ hai: đăng ký/inspect/run độc lập, không join cluster, không cấp SSH key giữa devices.

Record OS/version, commands, outcomes in validation.md. Không chạy reboot, package mutation hay dọn kết quả nếu user chưa yêu cầu. Repo không tự thao tác device thật trong offline tests.

## Dashboard và handoff mới

- Gửi hai job có name/description/agent; dashboard thấy đúng active jobs trên các device, --all thấy lịch sử; job-note cập nhật summary/phase mà không restart tiến trình.
- Chọn job bằng j/k và kiểm tra details/logs. Hủy stop/delete phải không thay đổi job; xác nhận stop chỉ tác động đúng ID. Clean sau fetch phải giữ bản kết quả đã tải.
- communication init cho hai agent, note mỗi agent và show chung. Snapshot ghi thời điểm, không ghi đè SUMMARY.md; không lấy snapshot cũ làm trạng thái live.
- Setup lại giữ profile/registration và không SSH. Chuyển config root cũ sang workspace/config; config xung đột phải báo lỗi và giữ cả hai.
- Dashboard trên Windows và terminal Ubuntu thật: phím ↑/↓/j/k, màu, refresh, q/Ctrl+C phục hồi cursor. Offline tests chỉ mô phỏng vòng phím; cần nghiệm thu terminal thực để xác nhận trải nghiệm.

## Global CLI

Run setup from repo, then move to another directory and run n3xus doctor/demo; config must remain the same. On Windows verify PowerShell/CMD and user PATH without admin. On Ubuntu verify fresh Bash terminal and source ~/.bashrc. Setup again creates no duplicate PATH/startup entries. Unregister removes only owned launchers/managed blocks, preserving later PATH/profile edits, config and remote jobs. Modified launcher must refuse overwrite/delete. Re-run setup after moving checkout. These are host-only checks; do not stop n3xus jobs.
