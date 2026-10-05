# Giao việc cho agent

Agent cần quyền chạy command local ở checkout repo và quyền mạng tới tailnet. OpenCode hoặc ChatGPT Work local có thể gọi CLI; chat chỉ có text/cloud không tự dùng được máy bạn. Chưa cung cấp MCP/plugin hoặc yêu cầu cài agent trên device.

Đọc `AGENTS.md`, `devices.yml` và `cluster help` trước. Windows dùng `.\cluster.ps1`, Ubuntu dùng `./cluster`. Các ví dụ dưới dùng cú pháp Ubuntu; đổi entry point trên Windows.

```bash
./cluster status
./cluster run home-4090 --image busybox:1.37.0 -- sh -c 'echo hello > /data/results/hello.txt'
./cluster jobs
./cluster logs task-xxxxxxxxxxxx
./cluster wait task-xxxxxxxxxxxx --timeout 600
./cluster delete-job task-xxxxxxxxxxxx
```

GPU:

```bash
./cluster test --gpu home-4090
./cluster run home-4090 --image nvidia/cuda:12.5.0-base-ubuntu22.04 --gpu -- nvidia-smi
```

`check`/`test --gpu` chạy CUDA nbody benchmark thực sự. `run --gpu` yêu cầu **một GPU**, runtime nvidia và node đã khai báo GPU; không chia GPU/tự phân phối model nhiều máy. CUDA image/code của người dùng cần tương thích driver; image ví dụ cần driver hỗ trợ CUDA 12.5, không phải test tương thích mọi driver.

`run` trả job name, không giữ tiến trình host. `wait` kiểm tra Complete/Failed, in log khi kết thúc; timeout giữ job để tiếp tục xem/dừng. Không tự retry computation lỗi (tránh ghi đè kết quả), không auto-delete dữ liệu. User jobs không có TTL tự xóa; hãy `delete-job` sau khi lấy log. Namespace user jobs: `personal-compute-jobs`; smoke test riêng: `personal-compute-smoke`.

Job chạy trên đúng device, UID/GID của SSH user, không root. Datasets chỉ đọc; results/checkpoints được ghi. Thư mục mặc định ở device được mount dưới `/data`. Một device khác không tự có dataset đó. Image phải chứa code/dependencies hoặc code phải sẵn trong thư mục được mount; repo không tự đóng gói project/đẩy file/download dataset cho bạn.

Đề nghị prompt:

> Đọc AGENTS.md và devices.yml. Kiểm tra home-4090 sẵn sàng. Chạy bài test GPU qua command của repo, chờ kết quả và báo log. Không reset cluster hoặc thay driver.

Đừng đọc/in/share `.cluster`, join-token hay kubeconfig; đó là quyền cluster-admin. Không reset, sửa host firewall, thay driver đang hoạt động hoặc triển khai privileged workload nếu người dùng chưa yêu cầu. Không tự chọn image không tin cậy vì job được đọc dataset và ghi vào results/checkpoints của người dùng.

Nguồn kết nối agent: [OpenCode MCP](https://opencode.ai/docs/mcp-servers/), [ChatGPT Work local access](https://learn.chatgpt.com/docs/remote-connections). CLI này chưa cấu hình các kết nối đó thay người dùng.
