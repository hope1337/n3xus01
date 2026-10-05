# Kiểm chứng trên máy thật

Thay entry point bằng `.\cluster.ps1` trên Windows. Không có static test nào thay thế được checklist này.

1. `./cluster setup` — host sẵn sàng, chưa kết nối device.
2. `./cluster add-device home-4090 --address IP --user USER --gpu` — ghi config, provisioning. Driver mới cần reboot thì làm theo thông báo và rerun.
3. `./cluster check` — node Ready, CPU/network test PASS, CUDA benchmark PASS.
4. Rerun `./cluster add-device home-4090` — không đổi cluster/node, không reinstall driver, config/service unchanged thì không restart K3s.
5. `./cluster run home-4090 --image busybox:1.37.0 -- sh -c 'echo persistent > /data/results/proof.txt'` — ghi file trên device bằng UID của bạn. `wait JOB` hoàn thành.
6. Mở agent và yêu cầu đọc AGENTS.md rồi chạy `test --gpu home-4090`, theo dõi log, báo kết quả.
7. Khi chấp nhận downtime, tự reboot device. Không chạy setup lại; `status` và `check` vẫn PASS, proof.txt vẫn còn.
8. Thêm lab worker, `check` kiểm tra HTTP/DNS qua Pod network từ worker tới nginx trên server. GPU worker dùng --gpu và CUDA test nếu có card.
9. Trên host OS khác, dùng cùng devices.yml rồi rerun add-device server/worker để lấy quyền truy cập và metadata local, `check` PASS. Không copy private key/credential vào Git.

Chỉ thử reset khi chấp nhận mất workloads/K3s local PV: `reset WORKER --yes-delete-cluster` trước, rồi server. Kiểm tra data_root còn nguyên, setup lại được, worker rejoin không node-password mismatch.

No HA/failover/backup. Máy server hỏng thì cần sửa/dựng lại; test này không chứng minh tự failover.
