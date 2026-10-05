# Máy của bạn, tài nguyên cho agent

**Chuẩn bị một lần → thêm device → kiểm tra → mở agent và giao việc.**

- **Host:** laptop Windows hoặc Ubuntu; nơi mở OpenCode/ChatGPT Work.
- **Device:** máy Ubuntu chạy công việc, có thể có NVIDIA GPU.
- Device đầu tiên giữ K3s chạy thường trực, đồng thời chạy workload. Các device sau là workers. Host không phải giữ Kubernetes chạy.

## Bạn tự chuẩn bị trước

Host và device đã có Tailscale. Bạn SSH được từ host vào device bằng key, đã xác minh host key, không hỏi SSH password. User trên device có sudo; **sudo vẫn có thể hỏi password** lúc cài đặt.

Device dùng Ubuntu 22.04/24.04, ít nhất 2 CPU, 2GB RAM, 10GiB trống và không bật swap. Chọn máy chưa cài Kubernetes. Host Ubuntu khuyến nghị 24.04. GPU flow hỗ trợ NVIDIA trên Ubuntu x86_64, gồm RTX 4090.

## 1. Chuẩn bị host — một lệnh

Chạy trong thư mục repo vừa clone:

| Windows PowerShell | Ubuntu terminal |
| --- | --- |
| `.\cluster.ps1 setup` | `./cluster setup` |

Repo tự cài công cụ; những lần sau không cần activate môi trường hoặc nhớ lệnh Ansible. Windows dùng Ubuntu-24.04 trong WSL và **SSH/key sẵn có của Windows**, không chép key hoặc yêu cầu join Tailscale trong WSL. Windows có thể hỏi quyền admin/restart khi cài WSL lần đầu. [Chi tiết host](docs/laptop-setup.md).

## 2. Thêm device

Chạy lệnh rồi trả lời tên máy, địa chỉ Tailscale, SSH user và có dùng GPU không:

```powershell
.\cluster.ps1 add-device
```

```bash
./cluster add-device
```

Hoặc khai báo hết trong một command; thay **IP và user** bằng của bạn:

```powershell
.\cluster.ps1 add-device home-4090 --address 100.101.102.103 --user student --gpu
```

```bash
./cluster add-device home-4090 --address 100.101.102.103 --user student --gpu
```

Thông tin được lưu trong **`devices.yml`**, Git ignore. Máy đầu tiên tự thành server; máy tiếp theo tự thành worker. Không có secret trong file này. Nếu SSH cần key khác mặc định, thêm `--key PATH` (chỉ đường dẫn).

Repo push qua SSH, bật service tự chạy sau reboot và lấy quyền điều khiển về host. Với GPU: giữ driver đang hoạt động, cài driver khi chưa có, cài runtime và NVIDIA device plugin. Nếu cài driver mới, lệnh dừng, báo bạn **reboot device** rồi chạy lại cùng command. Không tự reboot hoặc sửa driver lỗi.

Retry hoặc lấy lại quyền truy cập sau khi đổi Windows/Ubuntu: dùng lại **cùng `devices.yml`** rồi chạy `add-device home-4090`; không cần nhập lại. Chạy lại không reset cluster. Thêm máy lab bằng `add-device lab-01 --address ... --user ...`, không `--gpu` nếu không cần GPU.

## 3. Kiểm tra đã sẵn sàng

```powershell
.\cluster.ps1 check
```

```bash
./cluster check
```

Lệnh kiểm tra node Ready, chạy CPU workload và truy cập nginx qua mạng nội bộ từ mỗi device; với GPU, chạy **CUDA benchmark thật**, không chỉ `nvidia-smi`. Kết quả đạt yêu cầu có `PASS`. Không mở service ra Internet. Khi đang chạy training chiếm GPU, hãy đợi job xong trước khi check.

## 4. Mở agent và giao việc

Cho agent quyền chạy command local và yêu cầu nó đọc **[AGENTS.md](AGENTS.md)** cùng **[hướng dẫn giao việc](docs/agent-usage.md)**. Chưa cần MCP; đây không phải tự động kết nối mọi chat cloud với laptop.

Ví dụ thử việc nhỏ trên GPU:

```powershell
.\cluster.ps1 run home-4090 --image nvidia/cuda:12.5.0-base-ubuntu22.04 --gpu -- nvidia-smi
```

```bash
./cluster run home-4090 --image nvidia/cuda:12.5.0-base-ubuntu22.04 --gpu -- nvidia-smi
```

Lệnh trả tên job; agent dùng `jobs`, `logs JOB`, `wait JOB`, `delete-job JOB`. Bài CUDA trong `check` là kiểm tra tính toán GPU; ví dụ trên chỉ giúp làm quen luồng giao việc.

Dataset/checkpoint/kết quả nằm trên device, mặc định:

```text
/srv/personal-compute/data/datasets/
/srv/personal-compute/data/checkpoints/
/srv/personal-compute/data/results/
```

Trong job, chúng nằm tại `/data/datasets` (chỉ đọc), `/data/checkpoints`, `/data/results`. Công việc chạy trên device bạn chọn, dùng quyền user Ubuntu của bạn. Code/thư viện phải có trong image hoặc sẵn trên device; repo không tự upload dataset hay biến nhiều VRAM thành một GPU lớn.

Không phải bật terminal giữ kết nối. Tailscale và K3s chạy nền. Công việc đã gửi và đủ dữ liệu trên device tiếp tục chạy khi đóng agent/tắt host.

## Khi cần xử lý thêm

- `status`: chỉ xem trạng thái; `test --gpu home-4090`: chạy lại riêng bài GPU.
- `check --static`: kiểm tra source, không SSH, không chạy workload.
- `reset DEVICE --yes-delete-cluster`: **xóa workload/database/local PV của K3s**, giữ các thư mục data riêng, Tailscale và driver. Reset workers trước server. Không có backup, HA hoặc tự chuyển vai trò khi server hỏng.
- [Lỗi thường gặp](docs/troubleshooting.md) · [Kiểm chứng máy thật](docs/acceptance.md) · [Kiểm tra đã chạy](docs/validation.md) · [Chi tiết an toàn](docs/safety.md).
