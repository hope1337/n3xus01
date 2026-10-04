# Personal compute cluster — V1

Laptop → Tailscale/SSH → Ansible → một Ubuntu single-node K3s → kubectl → nginx.

Laptop chỉ quản trị. `first-node` là server **đồng thời chạy workload**, dùng SQLite mặc định của K3s; không HA, worker, GPU hay agent integration trong V1.

## 1. Prerequisite trên laptop

Chạy từ **Ubuntu 24.04 trên laptop dual boot**, với Tailscale đã kết nối. Cần Git, OpenSSH client, curl, Python 3.11–3.13, Ansible và kubectl cùng minor 1.36. Native Windows/PowerShell/Git Bash không chạy provisioning. [Lệnh cài công cụ một lần](docs/laptop-setup.md).

Sau khi clone repo vào filesystem Linux, mở terminal trong repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
chmod +x cluster
```

Mỗi terminal mới: `source .venv/bin/activate`. Wrapper không cài công cụ hoặc tải gì lên laptop khi chạy `setup`.

## 2. Prerequisite trên target

- Ubuntu 22.04/24.04 x86_64 hoặc arm64; systemd, Python 3, sudo và SSH đã hoạt động.
- Tối thiểu 2 CPU, 2GB RAM, 10GiB đĩa trống; không bật swap. Repo kiểm tra và dừng, không tự sửa swap/boot/firewall.
- Tailscale đã join tailnet, có `tailscale0`, `/usr/bin/tailscale`, hỗ trợ `tailscale wait`, và service `tailscaled` đã enabled khi boot.
- Laptop SSH được vào target bằng SSH key/ssh-agent và hostname/IP Tailscale; user có sudo. Dùng OpenSSH qua Tailscale là lựa chọn mặc định; không cần Tailscale SSH.
- Target tải được package Ubuntu, release K3s từ GitHub và container image. Tailnet policy hiện có cho phép laptop tới target TCP 22 và 6443.
- Máy chưa có Kubernetes/K3s khác. Dải mạng hiện có không trùng `10.42.0.0/16` (Pods) hoặc `10.43.0.0/16` (Services).

Không cần cài Ansible hay kubectl trên target. Repo không join Tailscale, thêm auth key, mở port router, sửa Tailscale policy hoặc tắt UFW.

## 3. Khai báo target

```bash
cp inventory/hosts.example.yml inventory/hosts.yml
nano inventory/hosts.yml
```

Chỉ sửa **hai giá trị** dưới host `first-node`:

| Giá trị | Điền gì |
| --- | --- |
| `ansible_host` | IP **Tailscale** `100.x.y.z` của target, hoặc MagicDNS hostname trỏ tới IP đó. Ưu tiên IP để tránh nhầm DNS. |
| `ansible_user` | Tên user Ubuntu dùng để SSH và sudo. |

Không đổi tên alias `first-node`. Nếu SSH chưa chọn đúng key, bỏ comment `ansible_ssh_private_key_file` và điền **đường dẫn** key trên laptop; không chép key vào repo. Hostname phải resolve đúng trên cả laptop và target.

SSH một lần từ laptop, xác minh fingerprint của target trước khi chấp nhận host key:

```bash
ssh USER@TAILSCALE_HOST_OR_IP 'hostname; sudo -v'
```

Thay `USER` và `TAILSCALE_HOST_OR_IP` bằng đúng hai giá trị vừa khai báo. Repo giữ host-key checking; không dùng `StrictHostKeyChecking=no`.

## 4. Setup bằng một command

```bash
./cluster setup first-node
```

Nhập **sudo password của user trên target** ở `BECOME password:`; password chỉ dùng trong phiên, không lưu vào Git/config. Nếu target đã có passwordless sudo: `./cluster setup first-node --no-sudo-prompt`.

Lệnh kiểm tra an toàn → cài release K3s cố định → bật systemd → chờ node Ready → lấy kubeconfig về laptop → kiểm tra API từ laptop. Lần đầu có thể mất vài phút tải image. Khi lỗi, xem bước `[cluster] ERROR (...)` và task Ansible báo `FAILED`/`UNREACHABLE`.

Chạy lại chính command này để retry hoặc kiểm tra idempotence: không tạo node mới, không reset dữ liệu, không restart K3s nếu cấu hình không đổi. Repo từ chối nhận quản lý cài đặt có sẵn, sửa cấu hình đã bị đổi hoặc nâng phiên bản ngầm.

## 5. Kiểm tra cluster

```bash
./cluster status
./cluster kubectl get nodes -o wide
```

Kỳ vọng node `first-node` ở trạng thái `Ready`, Internal IP là IP Tailscale. Kubeconfig admin nằm tại `.cluster/kubeconfig.yaml` (directory `0700`, file `0600`, Git ignore); repo không đổi `~/.kube/config` hoặc context khác. Muốn gọi kubectl trực tiếp:

```bash
kubectl --kubeconfig "$PWD/.cluster/kubeconfig.yaml" --context personal-compute-v1 get nodes
```

API chỉ bind IP Tailscale, kubelet dùng IP Tailscale, Flannel chọn `tailscale0`. Traefik, ServiceLB và metrics-server bị tắt. K3s vẫn cần tạo CNI interfaces, routes và iptables cho Pod networking như Kubernetes thông thường; repo không tắt firewall hoặc mở inbound public. [Chi tiết an toàn và giới hạn](docs/safety.md).

## 6. Chạy workload test

```bash
./cluster test
```

Lệnh deploy nginx một replica trong namespace riêng, chờ Pod Ready rồi kiểm tra **HTTP 200 + trang Welcome to nginx** qua port-forward chỉ bind `127.0.0.1` trên laptop. Service là `ClusterIP`; không Ingress, NodePort hay public LoadBalancer. Port tạm tự đóng khi lệnh kết thúc.

Kỳ vọng output `PASS`. nginx tiếp tục chạy để bạn quan sát; test chạy lại được. Dọn **chỉ namespace test có nhãn ownership đúng**:

```bash
./cluster test --cleanup
```

Chứng minh reboot persistence: khi sẵn sàng, **tự reboot target**, chờ nó online Tailscale rồi chạy lại `./cluster status` và `./cluster test`. Không cần chạy setup lại. [Checklist kiểm chứng trên máy thật](docs/acceptance.md).

## 7. Uninstall/reset để thử lại

**Xóa vĩnh viễn workload, K3s database và local persistent-volume data của node này.** Chỉ dùng khi bạn chấp nhận mất dữ liệu:

```bash
./cluster reset first-node --yes-delete-cluster
./cluster setup first-node
```

Reset dùng uninstaller chính thức của K3s sau khi kiểm tra ownership, phiên bản, cấu hình và fingerprint service/scripts. Không gỡ Tailscale, SSH hay package Ubuntu. Không có ownership marker thì dừng, không xóa. Reset lần hai cũng dừng an toàn vì cluster không còn thuộc quản lý. Nếu cài lần đầu dở dang mà chưa có uninstaller, rerun setup trước. Không tự xóa marker để vượt qua safety checks.

Repo chặn riêng thao tác upstream xóa advertised routes Tailscale, để reset giữ cấu hình Tailscale hiện tại.

## Kiểm tra repo và cấu trúc

```bash
./cluster check
```

Không SSH hay thay đổi target: kiểm tra Bash, YAML/Jinja, CIDR/network safety, wrapper bằng công cụ giả lập và Ansible `--syntax-check`. CI làm cùng việc trên Ubuntu. [Những kiểm tra đã chạy trong môi trường tạo repo](docs/validation.md).

```text
cluster                 wrapper UX; không chứa logic provisioning
ansible/ansible.cfg      cấu hình SSH/Ansible
inventory/              example được commit; hosts.yml của bạn bị ignore
playbooks/              setup và reset
roles/k3s_server/        kiểm tra an toàn, cài K3s, export kubeconfig
kubernetes/             manifest nginx test
tests/                  kiểm tra offline, không cần node thật
docs/                   cài công cụ, an toàn, troubleshooting, acceptance
.cluster/               kubeconfig/state local, bị ignore
```

`add-worker`/`add-gpu-worker` chưa implement; lệnh lạ sẽ dừng rõ ràng. Nguồn kỹ thuật: [K3s server flags](https://docs.k3s.io/cli/server), [installer variables](https://docs.k3s.io/reference/env-variables), [release đã pin](https://github.com/k3s-io/k3s/releases/tag/v1.36.4%2Bk3s1).
