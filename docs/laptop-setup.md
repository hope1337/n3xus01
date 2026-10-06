# Host Windows / Ubuntu

Có Python 3.10+ và OpenSSH trong PATH. Windows dùng terminal Conda cũng được: `python --version`, `ssh -V`; Ubuntu `python3 --version`, `ssh -V`. Repo không cài Python toàn máy, không cần WSL/venv/activate thêm.

Clone repo rồi setup theo README. SSH thủ công vào user@TAILSCALE_IP một lần để known_hosts tin cậy; key và Tailscale do bạn chuẩn bị trước. Windows và Ubuntu dual boot có SSH config/key/known_hosts riêng. Không copy private key vào Git.

Giữ cùng workspace/config/devices.json khi đổi OS (profile phải giữ nguyên). Chỉnh key path nếu có. `setup` không ghi đè config cũ. Repo không lấy config/secret K3s cũ; Dữ liệu cũ của phiên làm việc này được chuyển vào workspace/legacy/ và vẫn ngoài Git; không đọc hay xóa credential cũ. CLI không tự gom mọi thư mục tùy ý khi setup.

Nếu PowerShell chặn .ps1, có thể dùng `python scripts/device_cli.py setup` và các lệnh tương tự. Không đổi execution policy toàn máy. Trên Ubuntu, nếu checkout thiếu executable bit: `chmod +x device` một lần; hoặc gọi `python3 scripts/device_cli.py`.

## Lệnh device ở mọi thư mục

`setup` mặc định đăng ký user PATH, không dùng sudo/admin/pip. Windows chạy `.\device.ps1 setup` trong repo lần đầu; terminal PowerShell đó gọi ngay `device doctor`. Ubuntu chạy `./device setup`, rồi terminal mới hoặc `source ~/.bashrc`; gọi `device doctor`. Host app mở sẵn có thể cần khởi động lại để nhận PATH. Launcher pin Python đã chạy setup, không cần activate env sau đó. Nếu Python bị xóa/di chuyển thì chạy setup từ repo bằng Python mới.

Windows: `%LOCALAPPDATA%/PersonalDevice/bin/device.ps1` cho PowerShell và device.cmd cho CMD; chỉ HKCU user PATH, không system PATH/execution policy. Ubuntu Bash: `~/.local/bin/device`, block có marker trong .profile/.bashrc khi cần. Repo di chuyển thì setup lại trỏ về vị trí mới; chỉ một checkout được dùng bởi lệnh toàn cục. Launcher không copy config; giữ profile trong workspace/config.

`device unregister` gỡ global command của checkout hiện tại, giữ config/jobs/services/dataset. Modified/unowned launcher hoặc edited startup block phải báo lỗi thay vì ghi đè. PATH khác người dùng thêm sau đó vẫn giữ. `setup --no-register` không tạo launcher/chỉnh PATH. Python CLI setup thay cho .ps1 cần mở terminal mới để nhận user PATH. CMD vẫn cần quote các shell metacharacters theo quy tắc CMD; agent trên Windows dùng PowerShell launcher để giữ argv literal/Unicode.
