# Cấu trúc hoạt động

```text
Host (Windows hoặc Ubuntu)
  agent / người dùng → device CLI → SSH qua Tailscale
                                     └─ Ubuntu device
                                          ├─ helper ngắn hạn
                                          ├─ tmux: mỗi job một phiên riêng
                                          ├─ systemd user: mỗi service một unit riêng
                                          └─ code, state, logs, outputs trong home
```

Không có đầu sỏ; SSH là nơi nhận lệnh, đã do bạn chuẩn bị. Helper không mở port và kết thúc sau mỗi thao tác. Chỉ dịch vụ bạn yêu cầu host mới mở endpoint Tailscale.

`setup` kiểm tra Python/OpenSSH và tạo config. `add` đăng ký máy, gửi hai file helper vào thư mục riêng. `prepare` có hai lựa chọn rõ ràng: cài tmux và bật linger. Không cần môi trường Python riêng trên host.

Config là `devices.json`, có `profile` dùng chung giữa Windows/Ubuntu. Trạng thái trên mỗi device nằm tại `~/.local/share/personal-device/PROFILE/`: projects, jobs, services, envs. Máy khác nhau có trạng thái riêng. Host đọc trạng thái qua SSH; device offline thì không biết tình trạng mới nhất. Không báo cached state là trạng thái sống.

Mỗi lần sync tạo revision có checksum; run/serve chụp riêng revision đó. Sync sau không sửa job đang chạy. Job runner ghi PID + thời điểm tạo PID + boot ID, exit code và log. Không coi mất process/reboot là thành công. CLI theo dõi tiến trình chính/process group; chương trình tự daemonize/tách process có thể thoát quản lý, nên chạy foreground trong job/service. Tmux jobs không tự phục hồi sau reboot; systemd services có Restart=on-failure và enable lúc boot.

Services dùng systemd user với quyền user, KillMode=control-group; cần linger. Bind vào Tailscale IP. Kiểm tra listener lúc launch và HTTP check từ host; chương trình tự mở port khác hoặc đổi bind sau đó nằm ngoài kiểm soát CLI. Không có firewall sandbox hoặc scheduler.

Conda đã có trên device: CLI dùng executable tuyệt đối, chạy qua `conda run --prefix`, không activate shell. Env do CLI tạo ở PROFILE/envs; env cũ được inspect/reuse. Tối đa 8 managed env không phải quota dung lượng. Conda cache, code revisions, kết quả và journal cũng chiếm disk; inspect xem disk trống, clean job cũ sau khi tải kết quả. Không tự xóa dataset.
