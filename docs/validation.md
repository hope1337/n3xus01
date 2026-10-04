# Validation tại môi trường tạo repository

Ngày: 2026-10-04. Môi trường: Windows; Git Bash và Python có sẵn, WSL/Linux controller và target Ubuntu chưa có.

Đã chạy tại đây:

- Bash syntax cho `cluster` và `tests/test_wrapper.sh` bằng Git Bash.
- Regression tests offline cho wrapper, sử dụng fake Ansible/kubectl/curl trong một thư mục tạm riêng (không dùng cluster thật).
- Python static checks: YAML với duplicate-key detection, Jinja render, endpoint Tailscale, secrets handling, manifest nội bộ, route overlap với cả node fresh và node đã chạy K3s, command/path consistency.
- Git whitespace/diff checks và kiểm tra ignore inventory, kubeconfig, key/token.

**Chưa chạy Ansible `--syntax-check` bằng Linux controller, provisioning qua SSH, workload thật hay reboot thật** tại môi trường Windows này. `./cluster check` và GitHub workflow đã chuẩn bị sẵn để chạy native Ansible syntax trên Ubuntu; workflow không có nghĩa CI đã được chạy. Làm `docs/acceptance.md` để xác nhận flow đầu-cuối trên máy của bạn.

Không có host thật hoặc credential nào được khai báo trong repo. Không có thao tác remote provisioning, uninstall hoặc reboot nào đã được thực hiện.
