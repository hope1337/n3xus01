# Personal Device · gửi code qua SSH

Laptop **host** điều khiển các máy Ubuntu **device** qua Tailscale + SSH. Không còn K3s, Ansible, image hay máy đầu sỏ. Host có thể tắt sau khi gửi tác vụ; trạng thái và log nằm trên device.

## Bắt đầu

Host cần **Python 3.10+ và OpenSSH**; terminal Conda hiện tại của bạn dùng được. Device cần Ubuntu 22.04+, Python 3.10+, Tailscale và SSH key đã chuẩn bị. Hãy SSH thử một lần để xác nhận host key. Conda và driver NVIDIA có sẵn thì giữ nguyên.

**Windows — PowerShell tại thư mục repo:**

```powershell
.\device.ps1 setup
.\device.ps1 add genichiro --address 100.71.182.15 --user hope
.\device.ps1 prepare genichiro --install-tools --enable-linger
.\device.ps1 status
```

**Ubuntu — terminal tại thư mục repo:**

```bash
./device setup
./device add genichiro --address 100.71.182.15 --user hope
./device prepare genichiro --install-tools --enable-linger
./device status
```

Bạn chỉ thay **tên device, địa chỉ Tailscale, SSH user**. `add` không cần sudo: chỉ ghi helper và trạng thái trong home của user trên device. `prepare` hỏi xác nhận, có thể hỏi mật khẩu sudo của **device** để cài tmux nếu thiếu và bật linger. Linger giữ dịch vụ user hoạt động khi logout và sau reboot. Không cài Conda/GPU driver, không sửa SSH hay firewall. Windows chạy trực tiếp, **không cần WSL**.

`devices.json` được tạo tự động và không đưa vào Git. Nếu Conda nằm ở nơi riêng, thêm `--conda /duong/dan/bin/conda` vào lệnh `add`. SSH key mặc định được dùng; có thể thêm `--key DUONG_DAN_KEY` trên host. Không cần điền password.

Mở `device` không kèm lệnh để vào menu; `device --help` xem danh sách. Ví dụ dưới dùng Windows; Ubuntu thay `.\device.ps1` bằng `./device`.

## Thử gửi code

```powershell
.\device.ps1 sync genichiro examples/hello --project hello
.\device.ps1 run genichiro hello -- python3 -u main.py
.\device.ps1 jobs genichiro
```

`run` trả một ID như `job-...`. Thay `JOB_ID` bằng ID đó:

```powershell
.\device.ps1 logs genichiro JOB_ID
.\device.ps1 wait genichiro JOB_ID
.\device.ps1 fetch genichiro JOB_ID --output downloads/hello
```

Đọc `downloads/hello/hello.txt` là hoàn tất flow. Chạy `check genichiro` để kiểm tra SSH/helper/tmux; đây không phải bài test GPU. `inspect genichiro` xem RAM, VRAM, Conda. Online không có nghĩa GPU đang rảnh.

## Conda và GPU

```powershell
.\device.ps1 env list genichiro
.\device.ps1 env inspect genichiro TEN_ENV
.\device.ps1 run genichiro hello --env TEN_ENV --gpu 0 -- python -u main.py
```

Agent đọc env trước, đề xuất bổ sung hoặc tạo mới, **hỏi bạn trước khi cài**. CLI không tự tạo env. Tối đa 8 env do CLI tạo; env đang chạy tác vụ/dịch vụ được bảo vệ. `--gpu 0` chọn GPU qua `CUDA_VISIBLE_DEVICES`, không chia hay giữ độc quyền GPU. Dùng `--` trước chương trình; không cần activate env.

## Host một dịch vụ

Ví dụ HTTP không cần thêm package:

```powershell
.\device.ps1 sync genichiro examples/http --project web
.\device.ps1 serve genichiro web --name hello-api --port 8088 -- python3 -u main.py --host '{bind}' --port '{port}'
.\device.ps1 service genichiro check hello-api
.\device.ps1 services genichiro
```

CLI trả endpoint Tailscale. Dịch vụ dùng systemd user, tự khởi động lại sau reboot khi Tailscale sẵn sàng; host không cần treo. Tác vụ `run` dùng tmux, tiếp tục sau khi host tắt nhưng **không tự chạy lại sau device reboot**. Chương trình dịch vụ phải hỗ trợ địa chỉ bind/port; agent tự viết code hoặc dùng công cụ có sẵn, không cần đóng image. Endpoint không có xác thực HTTP tự động: chỉ gọi trong tailnet của bạn và dùng quyền Tailscale phù hợp.

## Dừng và dọn

```powershell
.\device.ps1 stop genichiro JOB_ID
.\device.ps1 clean genichiro JOB_ID
.\device.ps1 service genichiro stop hello-api
.\device.ps1 service genichiro remove hello-api
```

`clean` hỏi trước và xóa **kết quả/log/workspace của đúng job đã kết thúc**; tải kết quả trước. Gỡ service giữ workspace/kết quả và receipt; dùng tên mới nếu tạo lại. `env remove` chỉ gỡ env do CLI tạo, hỏi trước; env riêng/base được giữ. `remove DEVICE` chỉ bỏ tên khỏi config host, không dừng việc trên device.

## Giao việc cho agent

Mở agent ngay trong repo, cho phép chạy lệnh local và yêu cầu đọc [AGENTS.md](AGENTS.md) + [hướng dẫn agent](docs/agent-usage.md). Agent có thể inspect → gửi code → chạy/host → xem log → trả kết quả hoặc endpoint. Thêm `--json` để đọc dữ liệu có cấu trúc. Không cần MCP hay server điều phối.

Đổi Windows ↔ Ubuntu: giữ **cùng devices.json**, chuẩn bị SSH/key ở OS mới rồi `setup` và `status`. Không setup lại device. SSH key path có thể cần đổi theo OS; đừng tạo profile mới nếu muốn đọc lịch sử cũ.

Sync chỉ dành cho code, giới hạn 64 MiB; không upload dataset/model lớn. Code chạy với quyền SSH user, có thể đọc dữ liệu của user đó: đây không phải sandbox. Bạn/agent tự dùng đường dẫn dataset có sẵn trên device.

[Chi tiết cấu trúc](docs/architecture.md) · [Lỗi thường gặp](docs/troubleshooting.md) · [An toàn](docs/safety.md) · [Kết quả kiểm tra](docs/validation.md)
