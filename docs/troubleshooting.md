# Khi một bước lỗi

Wrapper báo tên bước; Ansible báo đúng task và hostname lỗi. Sau khi sửa nguyên nhân, rerun `./cluster setup first-node`. Không xóa owner marker để bypass kiểm tra.

| Lỗi | Việc cần kiểm tra |
| --- | --- |
| `Missing ansible-playbook/kubectl` | Activate `.venv`, PATH; xem `laptop-setup.md`. |
| `UNREACHABLE`, host key | SSH thủ công với đúng `ansible_user`/`ansible_host`; xác minh fingerprint. Không tắt host-key checking. |
| `Permission denied (publickey)` | SSH key/ssh-agent trên laptop. Key phải được target chấp nhận trước; repo không tự phân phối key. |
| `Missing sudo password` / sudo failed | Dùng command mặc định và nhập sudo password **target**. `--no-sudo-prompt` chỉ dành cho passwordless sudo. |
| Target không supported / có swap | V1 yêu cầu Ubuntu 22.04/24.04, systemd, RAM/CPU/đĩa như README; tự chọn target phù hợp, repo không tự sửa boot/swap. |
| Tailscale IP/hostname không khớp | Điền IP `100.x.y.z` thật; kiểm tra `tailscale status`, MagicDNS. Không dùng LAN IP/public IP. |
| `tailscale wait` thiếu | Cập nhật Tailscale bằng cách thông thường của bạn trước khi setup; repo không quản lý Tailscale. |
| Existing/unowned files hoặc config changed | Target có cài đặt khác hoặc chỉnh sửa ngoài repo. Repo dừng để bảo vệ nó. Không force overwrite; dùng target sạch hoặc kiểm tra thủ công. |
| CIDR overlap | LAN/VPN/subnet route trùng `10.42/16` hoặc `10.43/16`. V1 không tự đổi networking; chọn mạng/target không trùng. |
| K3s download/image pull failed | Internet, DNS, GitHub/registry và disk; retry sau khi mạng hồi phục. |
| Server Ready nhưng laptop không tới API | Laptop đã join tailnet, policy cho phép TCP 6443, target firewall cho phép traffic trên tailscale0. Không mở API trên public interface. |
| nginx rollout không Ready | Xem Pod events mà wrapper in ra; `ImagePullBackOff` thường là registry/DNS, `FailedScheduling` là tài nguyên hoặc node chưa Ready. |
| `x509` sau thời gian dài | Rerun setup để lấy kubeconfig hiện tại; không bỏ certificate verification. |
| Sau reboot không online | Target phải boot Ubuntu, tailscaled enabled và đăng nhập còn hiệu lực. Kiểm tra service logs. |

Đọc log/diagnostics khi cần, thay đúng user/hostname:

```bash
ssh USER@TAILSCALE_HOST_OR_IP 'sudo systemctl status k3s --no-pager; sudo journalctl -u k3s -n 80 --no-pager'
./cluster kubectl get pods -A
./cluster kubectl get events -A --sort-by=.lastTimestamp
```

UFW/firewalld active không bị repo tắt. Firewall phải cho phép API trên tailnet và Pod networking giữa local CNI interfaces; rule đúng phụ thuộc policy sẵn có. Repo dừng với lỗi readiness nếu traffic bị chặn. Không dùng giải pháp mở mọi port hoặc `ufw disable`. [Yêu cầu networking chính thức của K3s](https://docs.k3s.io/installation/requirements).

Nếu setup thất bại sau khi tạo marker, rerun được. Nếu chưa cài được uninstaller, reset sẽ từ chối; hoàn thành setup trước. Nếu service/config đã bị sửa thủ công, sửa lại thay đổi đó trước khi dùng wrapper; không có lệnh force-adopt/force-reset trong V1.
