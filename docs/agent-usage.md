# Agent: sử dụng CLI, không chỉnh sửa công cụ

Đọc AGENTS.md trước. User giao task không tự cấp quyền sửa repo. Mặc định chỉ sử dụng; code task ở workspace/communication/agents/ID/work, kết quả vào downloads, ghi chú qua communication. Sau khi user setup đăng ký PATH, dùng `device` từ mọi thư mục. Nếu process hiện tại chưa nhận PATH, Windows dùng đường dẫn tuyệt đối tới device.ps1 của repo, Ubuntu tới device; không suy ra repo từ cwd. Thêm --json trước dấu --; phản hồi schema/ok/action/data hoặc error. Exit 0 nghĩa thao tác thành công, không nhất thiết job hoàn tất. Help vẫn là văn bản. Không mở dashboard/watch interactive trong agent.

## Bắt đầu phiên

```powershell
.\device.ps1 communication init codex-20261006-a1 --json
.\device.ps1 communication show --json
.\device.ps1 status --json
.\device.ps1 dashboard --once --json
.\device.ps1 inspect sekiro --json
.\device.ps1 env list sekiro --json
.\device.ps1 env inspect sekiro TEN_ENV --json
```

ID riêng mỗi phiên, không dùng folder của agent trước để ghi mới. Snapshot/handoff cũ phải được đối chiếu live. Chỉ các device đã đăng ký được hiển thị; CLI không quét toàn tailnet tự nhận máy lạ. Không đọc key/password/legacy kubeconfig để lấy status.

## Gửi việc dễ hiểu

Viết code vào work/TASK; inspect secret và dependency. Không sửa examples hay scripts để viết workload. Tên job nên nói mục đích, mô tả một câu. Nếu --agent có mặt thì CLI yêu cầu --name và --description.

```powershell
.\device.ps1 sync sekiro workspace/communication/agents/codex-20261006-a1/work/pdf-extract --project pdf-extract --json
.\device.ps1 run sekiro pdf-extract --name extract-pdfs --description 'Đọc PDF và xuất text' --agent codex-20261006-a1 --env TEN_ENV --json -- python -u main.py
.\device.ps1 job sekiro extract-pdfs --json
.\device.ps1 logs sekiro extract-pdfs --json
```

Lưu ID trả về. Trên một device, tên không trùng với job active; lịch sử có thể trùng tên nên dùng ID nếu ambiguous. jobs mặc định active; jobs --all xem lịch sử mọi máy. Mỗi job có workspace riêng của revision đã sync; agent chạy sau không sửa code của job trước.

```powershell
.\device.ps1 job-note sekiro JOB_ID --summary 'Đã xử lý 40/100 file theo log' --phase extracting --progress 40 --agent codex-20261006-a1 --json
```

Summary/phase/progress là thông tin do agent chịu trách nhiệm, có note_author/note_updated_at; không đoán phần trăm từ thời gian. State/observed_at là đọc live. Tiến trình running có thể đang chờ; API phải request thật để kết luận ready. Job cũ thiếu name/description có thể được đặt lại qua job-note; không restart để đổi mô tả.

Wait/logs/fetch/stop/clean chấp nhận ID hoặc tên không ambiguous. --follow là terminal-only; agent lấy log snapshots. Wait timeout giữ job. Fetch default DEVICE_OUTPUT_DIR; --path là thư mục tương đối trong workspace job. Fetch không overwrite, max64MiB. Không tự clean lịch sử/results; user intent + confirmation, fetch trước.

## Dependencies và privileges

Inspect Conda trước. `env plan DEVICE ENV --package pypdf --pip --json` không cài vào env nhưng solver có thể cập nhật cache. Hỏi user trước install/create/remove; chỉ thêm --yes sau khi được đồng ý. Không đổi base/driver, accept channel terms hay nâng pip tự động. Kiểm tra env dùng bởi external notebook với user; CLI chỉ biết managed jobs/services.

Chạy --gpu INDEX chỉ chọn CUDA device, không reservation. Kiểm tra sử dụng GPU trước và không dừng training riêng. Không mở public listener. prepare --install-tools/--enable-linger có thể cần sudo password nhập ở terminal; chat approval không tự cung cấp password. Báo blocker, không skip và báo task done.

## Handoff

```powershell
.\device.ps1 communication note codex-20261006-a1 --title 'PDF extraction handoff' --message-file workspace/communication/agents/codex-20261006-a1/work/handoff.txt --device sekiro --job JOB_ID --json
.\device.ps1 communication snapshot --json
```

Nội dung note: mục tiêu, device/project/job ID, tiến trình đã kiểm tra lúc nào, kết quả ở đâu, lệnh/log chứng minh, approval đã có, phần chưa xong và cách tiếp tục. Notes có file riêng nên agent khác không ghi đè. Snapshot có timestamp và cả offline/errors; không lấy snapshot làm bằng chứng live. shared/SUMMARY.md dành cho ngữ cảnh bền vững, không xóa phần người khác. Never secrets. Runtime toàn bộ ở workspace, không force-add vào Git.

Service systemd tùy chọn: serve cần linger và {bind}/{port}; logs DEVICE NAME --service; service check từ host phải thành công. Không bypass guards bằng cách sửa source/helper. Direct SSH read-only diagnostics được phép nếu cần; mutation ngoài CLI cần user intent và ghi lại. Không tạo hệ quản lý job song song bằng tmux thủ công rồi gọi là managed job.

Host offline: job vẫn chạy theo login policy, agent không tiếp tục suy nghĩ. Device reboot: tmux job interrupted, systemd có thể restart. Không auto-retry mutation timeout; inspect job/service trước để tránh duplicate.

User setup mặc định cài launcher/PATH trên host, không SSH. Không tự chạy unregister hoặc thay checkout của global command trong tác vụ workload. Source/output path tương đối theo cwd; config/workspace theo vị trí repo. `setup --no-register` dành cho kiểm thử/host không muốn đổi PATH.
