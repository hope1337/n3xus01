# Kiểm chứng trên máy thật

Các static checks không chứng minh Ubuntu, Tailscale, firewall hoặc reboot thật đã hoạt động. Chạy checklist này khi đã khai báo target:

1. `./cluster check` — PASS, không kết nối target.
2. `./cluster setup first-node` — target `first-node` Ready, laptop `kubectl` thấy đúng IP Tailscale.
3. `./cluster status` — `/readyz` trả `ok`, node Ready.
4. `./cluster test` — Pod Ready, HTTP 200 và đúng trang nginx. Service là ClusterIP, không external IP.
5. Ghi lại UID: `./cluster kubectl get node first-node -o jsonpath='{.metadata.uid}'`.
6. `./cluster setup first-node` lần hai — không đổi config/service, không restart K3s hay tạo cluster/node mới. Ansible `copy` kubeconfig có thể changed nếu K3s cập nhật certificate; readiness/reads không changed. UID vẫn như bước 5.
7. Tự reboot target khi chấp nhận downtime, ví dụ `ssh USER@TAILSCALE_HOST_OR_IP 'sudo reboot'`. Chờ Tailscale/SSH hoạt động lại.
8. **Không chạy setup.** `./cluster status` và `./cluster test` — vẫn PASS, UID như cũ. Deployment có thể tạo lại Pod nhưng cluster/node không được tạo lại.
9. `./cluster test --cleanup` — chỉ dọn test; `./cluster status` vẫn thấy cluster.

Chỉ nếu muốn thử lại từ đầu và chấp nhận mất **mọi workload/local PV data**:

```bash
./cluster reset first-node --yes-delete-cluster
./cluster setup first-node
./cluster test
```

Sau reset/setup mới, node UID sẽ đổi. Reset không tự reboot, gỡ Tailscale hoặc sửa SSH.
