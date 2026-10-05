# Khi một bước lỗi

Wrapper báo `[cluster] ERROR (bước)`; Ansible in tên task cụ thể. Sửa nguyên nhân rồi rerun cùng `add-device NAME`. Config đã được ghi để retry, không reset để sửa lỗi cài dở.

| Lỗi | Làm gì |
| --- | --- |
| Windows chưa có WSL/distro | `cluster.ps1 setup`; chấp nhận UAC, restart nếu Windows yêu cầu, rerun setup. |
| Python host không hỗ trợ | Dùng Ubuntu 24.04/Python 3.11–3.13; Windows wrapper tự dùng Ubuntu-24.04. |
| SSH host key/password lỗi | Thử SSH bằng host OS, xác minh fingerprint/key/agent. Không tắt kiểm tra host key. Windows dùng Windows ssh.exe, không phải key của WSL. |
| Sudo lỗi | Nhập password device. Chỉ dùng `--no-sudo-prompt` khi device đã passwordless sudo. |
| Swap hoặc thiếu disk/RAM | Chọn/configure device phù hợp; repo không tự sửa swap hoặc boot. |
| Driver vừa được cài | Reboot device, làm MOK enrollment ở màn hình máy nếu cần, rồi rerun command. |
| Driver có nhưng nvidia-smi lỗi | Reboot/check driver/Secure Boot. Repo không tự thay driver đang cài. |
| Toolkit version không tải được | Repo NVIDIA/DNS/apt; xem version pin trong gpu.yml, không đổi nguồn sang mirror ngẫu nhiên. |
| GPU không allocatable | Driver/runtime/plugin. Check device plugin Pod logs, K3s restart discovery, RuntimeClass nvidia. |
| GPU test Pending | GPU có thể đang bị job khác chiếm; đợi hoặc dừng job bạn đã yêu cầu. |
| Node Ready nhưng network test lỗi | Policy giữa devices: TCP 6443/10250, UDP 8472; Pod CIDR/firewall cni0/flannel.1; DNS/image registry. Không mở public ports hoặc tắt firewall. |
| Windows SSH tốt nhưng API không tới | WSL network/VPN tới 100.x IP; repo không tự sửa Windows network settings. |
| CIDR overlap | Mạng hiện có trùng 10.42/16 hoặc 10.43/16; V1 không tự rewrite routes. |
| Namespace/config/marker không owned | Dừng để bảo vệ cài đặt khác. Không xóa marker hoặc force overwrite. |
| Permission denied dưới /data trong job | Kiểm tra quyền directory/file của user device. Dataset mount intentionally read-only; ghi vào results/checkpoints. |
| Không thấy metadata sau đổi OS | Dùng cùng devices.yml, rerun add-device server rồi worker trên host OS mới. |
| Worker rejoin bị node password mismatch | Nếu reset thành công nhưng bước delete Node thất bại, dọn stale Node bằng kubectl đúng cluster trước rejoin; không uninstall server. |

Agent có thể xem lỗi ngay từ host (Windows thay `./cluster` bằng `.\\cluster.ps1`):

```bash
./cluster kubectl get pods -A -o wide
./cluster kubectl get events -A --sort-by=.lastTimestamp
./cluster kubectl logs -n kube-system daemonset/personal-compute-nvidia
```

Nếu worker đã được reset nhưng xóa Node thất bại, dùng `./cluster kubectl delete node WORKER --ignore-not-found` trước khi retry reset/rejoin. Chỉ áp dụng cho worker bạn vừa yêu cầu reset.

Log device (đổi USER/IP theo devices.yml; server service `k3s`, worker `k3s-agent`):

```bash
ssh USER@TAILSCALE_IP 'sudo journalctl -u k3s -n 80 --no-pager'
```

Không share kubeconfig hoặc join token khi báo lỗi. Job lỗi: dùng `logs JOB`, `wait JOB`; failed job không tự retry để tránh ghi đè output. Dataset/checkpoint/result được lưu ở device bạn chọn, không nằm trên mọi device.
