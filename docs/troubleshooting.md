# Khi có lỗi

`n3xus doctor` kiểm tra host; `n3xus status`, `inspect DEVICE` kiểm tra SSH và device. Lỗi nói rõ mã/bước; agent dùng --json.

- SSH failed/offline: thử `ssh USER@TAILSCALE_IP`, xem Tailscale/key/known_hosts ở OS host hiện tại. Không tự xóa known_hosts để bypass cảnh báo.
- Python thiếu: host và device cần 3.10+. Ubuntu 22.04+ có python3; repo không tự upgrade Python hệ thống.
- tmux missing: prepare DEVICE --install-tools. Jobs dùng socket tmux riêng; không cần xem/dọn các session tmux cá nhân.
- Linger/systemd unavailable: prepare DEVICE --enable-linger, rồi inspect. Cần Ubuntu có systemd user; không đổi sang WSL/daemon khác tự động.
- Conda missing: add lại cùng tên/address/user với --conda /full/path/bin/conda. Không tự cài Conda. Env ambiguous: dùng full path từ env list. Pip dry-run không hỗ trợ: báo user thay vì nâng pip.
- Env busy: dừng managed job/service trước. Env create fail: env list vẫn ghi nhận prefix, env remove có xác nhận dọn phần dang dở; không tự delete ngoài profile. Conda channels/terms do user chọn.
- Job failed: logs + jobs xem exit code. interrupted có thể do reboot/mất tiến trình; không coi là thành công. wait timeout không stop job. stop --force chỉ khi stop thường không hiệu quả. Chạy chương trình foreground; không tự daemonize.
- Service active nhưng không gọi được: service check, logs DEVICE TEN_SERVICE --service. Model có thể đang load; xem Tailscale ACL và đúng bind. App phải dùng {bind}/{port}; CLI stop nếu thấy wildcard trên port. Không mở firewall public để sửa lỗi.
- not_owned/helper/unit changed: dừng và investigate; không xóa owner/fingerprint để bypass. Không overwrite thủ công cho tác vụ cũ.
- Download >64MiB: chọn thư mục kết quả nhỏ hơn; code/model/dataset lớn dùng cơ chế copy riêng được user duyệt. Output tồn tại: dùng tên output mới, không overwrite.
- Giao diện không màu: CLI tắt màu khi redirect/NO_COLOR. `--color always demo` xem demo màu, không gửi lệnh cho device. Không phải trạng thái thật.

- Tên job lịch sử trùng nhau: jobs --all liệt kê đầy đủ ID, dùng job/logs/stop với ID đó. Không tự đoán job cần xóa.
- Dashboard refresh có thể chờ SSH timeout khi máy offline; q đóng màn hình, Ctrl+C ngắt việc lấy trạng thái nhưng không dừng job. --once/--json dành cho agent và redirect.
- Hai config cũ/mới khác nhau: setup báo config_conflict; giữ nguyên cả hai để bạn chọn đúng profile, không tự tạo profile mới.
- Agent không có quyền sửa CLI: lưu lỗi trong shared notes rồi yêu cầu người dùng cho phép sửa repo. Không patch helper để né lỗi.
