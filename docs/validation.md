# Kiểm tra tại môi trường tạo repo

Ngày 2026-10-04. Windows có Python, Git Bash và PowerShell; chưa có WSL/Linux controller hay device Ubuntu/RTX 4090 kết nối.

Đã chạy và PASS: **19 Python regression tests**, kiểm tra **16 file YAML** và template server/worker, Bash syntax, PowerShell parser và WSL/SSH argument routing bằng mock. Test bao gồm config/role/state, secret rejection, duplicate YAML, command/job routing, dataset mounts, ownership/reset, failures; mô phỏng thêm worker và bài CPU từng device/CUDA GPU. Mock không cài WSL, SSH, sửa driver hoặc gọi API thật.

Chưa xác minh tại đây: host bootstrap Linux/WSL thật, bridge Windows SSH trên account thật, Ansible native --syntax-check, provisioning/worker networking, driver/MOK/toolkit/NVIDIA device plugin, CUDA kernel và reboot persistence. CI Linux/Windows và `check --static` đã chuẩn bị để kiểm tra native syntax, không có nghĩa CI đã chạy.

`check`/`test --gpu` là live tests đã implement để bạn xác minh trên máy thật. Chỉ coi thiết lập GPU sẵn sàng sau CUDA benchmark PASS. Làm docs/acceptance.md trước khi dùng cho workload quan trọng. Không có credentials/device thật nào trong source Git.
