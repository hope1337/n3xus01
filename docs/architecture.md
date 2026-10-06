# Cấu trúc

Host Windows/Ubuntu chạy native Python stdlib + OpenSSH. CLI gửi JSON stdin tới một Python helper qua SSH/Tailscale; không giữ kết nối lâu, không có coordinator/server. Windows argv dùng JSON/base64 để giữ nguyên dấu quote/Unicode/$; không shell eval.

Config canonical: workspace/config/devices.json, schema/profile/devices. setup chuyển root devices.json cũ bằng rename sau validate, không tạo profile mới. Local receipts ở workspace/runs chỉ là lịch sử gửi. Remote state vẫn ~/.local/share/personal-device/PROFILE, ownership bằng UID/schema/profile, helper/unit fingerprints và private paths. Repo update không tự ghi lên remote helper hay restart job.

Một job tương ứng tmux session trên socket riêng. Record có ID, name/description/agent, revision, command/env/GPU, PID+startticks+bootID, state/log/output và dated notes. State đọc live; phase/progress không tự infer. Tmux kết thúc khi runner xong; metadata/log giữ tới clean. Mất process/reboot không coi là completed. Không auto-resume job, không quản lý session tmux cá nhân. Chương trình phải chạy foreground, không tự daemonize.

Jobs mặc định active. Job name lookup ưu tiên active; history trùng tên yêu cầu ID. job_detail thêm log gần nhất; job_note ghi dưới file lock và không thay command/process. Dashboard polling một overview RPC/device, tối đa 8 device song song, ghi rõ observed/error; không dùng stale snapshot làm trạng thái live. Dashboard terminal dùng native keyboard, khôi phục cursor/terminal trong finally, các thao tác stop/delete phải xác nhận. Đóng dashboard không stop job.

Workspace host chứa communication/shared và communication/agents/ID/{work,downloads,notes}. Handoff notes dùng unique JSON filenames, tránh lost update giữa agent. snapshot.json/STATUS.md được thay nguyên file; SUMMARY.md không bị CLI overwrite. Folder riêng chỉ là tổ chức, không phân quyền bảo mật. Những dữ liệu này Git ignored; chỉ workspace/README.md tracked.

Immutable sync revisions + per-job copies tránh sửa job đang chạy. Secret exclusions chỉ giúp tránh lỗi phổ biến; không scanner. Dataset/model lớn giữ disk device. No GPU scheduling/quota/sandbox/pool/backup. Conda existing env inspect/reuse; managed env max8 không phải disk quota. Cache/code/results/journal vẫn chiếm disk.

Systemd-user service là tính năng tùy chọn: linger + owned unit fingerprint + Tailnet bind + foreground runner monitor, KillMode=control-group, Restart=on-failure. Không auth/TLS tự động. Runner kiểm tra port configured; untrusted app có thể mở port khác, nên đây không network sandbox. Endpoint cần real check, active chưa đủ.

## Command registration

Setup installs user launchers pointing to the checkout and the resolved Python executable. Windows PowerShell launcher delegates to the repository argv-preserving launcher; CMD is also available. Linux shim execs Python with literal argv. Only user PATH/startup blocks are changed; registration does not SSH. Markers encode public paths and the generated body must match before replacement/removal. Runtime receipt stays in workspace/config; global launcher location is the sole host-runtime placement exception. Unknown/manual-modified files are preserved and reported. unregister affects only the current checkout registration; profile/config/remote state are independent.
