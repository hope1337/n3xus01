# Host Windows / Ubuntu

Có Python 3.10+ và OpenSSH trong PATH. Windows dùng terminal Conda cũng được: `python --version`, `ssh -V`; Ubuntu `python3 --version`, `ssh -V`. Repo không cài Python toàn máy, không cần WSL/venv/activate thêm.

Clone repo rồi setup theo README. SSH thủ công vào user@TAILSCALE_IP một lần để known_hosts tin cậy; key và Tailscale do bạn chuẩn bị trước. Windows và Ubuntu dual boot có SSH config/key/known_hosts riêng. Không copy private key vào Git.

Giữ cùng devices.json khi đổi OS (profile phải giữ nguyên). Chỉnh key path nếu có. `setup` không ghi đè config cũ. Repo không lấy config/secret K3s cũ; devices.yml/.cluster hoặc WSL state cũ được giữ ngoài Git cho bạn tự xử lý nếu còn.

Nếu PowerShell chặn .ps1, có thể dùng `python scripts/device_cli.py setup` và các lệnh tương tự. Không đổi execution policy toàn máy. Trên Ubuntu, nếu checkout thiếu executable bit: `chmod +x device` một lần; hoặc gọi `python3 scripts/device_cli.py`.
