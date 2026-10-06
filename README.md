# Personal Device — giao việc cho các máy của bạn

Repo này giúp bạn và AI agent **gửi code từ laptop sang máy Ubuntu, chạy nền và biết công việc đang làm gì**. Laptop là **host**; các máy nhận việc là **device**. Bạn chuẩn bị Tailscale và SSH key trước; CLI sử dụng kết nối đó.

Ví dụ: “Chạy script xử lý PDF trên genichiro” hoặc “Host model trên sekiro”. Agent kiểm tra tài nguyên/Conda, gửi code, tạo job, đọc log rồi lấy kết quả hoặc kiểm tra endpoint. Không cần đóng image, học Kubernetes hay giữ một terminal SSH mở liên tục.

## Repo gồm những gì?

| Thành phần | Công dụng |
|---|---|
| **CLI `device`** | Gửi code, chạy/dừng/xóa job, xem máy, env, log và lấy kết quả |
| **Dashboard terminal** | Bảng tự cập nhật mọi device và job, giống cách xem nvitop; không cần website |
| **`AGENTS.md`** | Quy tắc agent: được làm gì, hỏi khi nào, lưu dữ liệu ở đâu |
| **`docs/agent-usage.md`** | Các lệnh và quy trình giao việc cho agent |
| **`workspace/`** | Config, receipt, code tác vụ, báo cáo, kết quả và giao tiếp giữa agent |
| **`scripts/`, `tests/`, `docs/`** | Phần triển khai, kiểm tra và tài liệu của công cụ; không phải nơi agent viết code tác vụ |

Mặc định agent **chỉ được dùng**, không được sửa CLI/rules/docs nếu bạn chưa trực tiếp yêu cầu sửa repo. Đây là quy tắc làm việc, không phải cơ chế khóa quyền filesystem.

## Job thực sự chạy ở đâu?

```text
Host: người dùng / agent → CLI → SSH qua Tailscale → device Ubuntu
                                                   └─ mỗi job một tmux session riêng
                                                      code + state + log + kết quả
```

CLI gửi một helper nhỏ vào home của user trên device. Helper chỉ chạy khi cần, không phải server điều phối. Mỗi job nhận bản code riêng: sync code mới không sửa job cũ đang chạy. Khi xong, tmux session có thể kết thúc; lịch sử/log còn để kiểm tra.

Đóng dashboard/SSH hoặc tắt host không chủ động dừng job. Device phải còn bật, có mạng và chính sách login cho phép tiến trình nền tồn tại; `prepare --enable-linger` là cách chuẩn bị user services. **Device reboot thì job tmux không tự chạy lại.** Dịch vụ systemd là tính năng tùy chọn nếu cần tự khởi động sau reboot.

Không có đầu sỏ, Kubernetes, Ansible, WSL bắt buộc, scheduler hay gộp VRAM. Code chạy bằng quyền SSH user, không phải sandbox. CLI chỉ quản lý job/session do nó tạo, không dọn tmux cá nhân của bạn.

## Chuẩn bị một lần

- Host Windows hoặc Ubuntu: **Python 3.10+ và OpenSSH** có trong PATH. Terminal Conda hiện tại dùng được, không cần thêm pip package.
- Device: Ubuntu 22.04+, Python 3.10+, Tailscale và SSH key đã chuẩn bị. SSH thử một lần để xác nhận host key. Conda/driver GPU có sẵn được giữ nguyên.

Windows PowerShell tại repo:

```powershell
.\device.ps1 setup
.\device.ps1 add sekiro --address 100.123.148.6 --user manh
.\device.ps1 prepare sekiro --install-tools --enable-linger
.\device.ps1 check sekiro
```

Ubuntu dùng `./device` thay `.\device.ps1`. Chỉ thay **tên device, địa chỉ Tailscale và SSH user** cho máy của bạn. Thêm máy khác bằng `add` với tên/IP/user của máy đó. `prepare` hỏi xác nhận và có thể hỏi mật khẩu sudo **trong terminal** để cài tmux nếu thiếu/bật linger. CLI không cài Conda/driver, sửa firewall hay tạo SSH key.

Nếu Conda nằm ở đường dẫn khác: `add ... --conda /duong/dan/bin/conda`. Key mặc định được dùng; thêm `--key DUONG_DAN_KEY` nếu cần. Không lưu mật khẩu.

Config ở **`workspace/config/devices.json`**, Git bỏ qua. `setup` chuyển config JSON cũ ở root vào đây và giữ nguyên profile. Đổi Windows ↔ Ubuntu: giữ cùng workspace/config, chuẩn bị SSH/key ở OS mới rồi setup/status; key path có thể cần đổi. Không reprovision device.

## Xem máy và công việc

```powershell
.\device.ps1 status
.\device.ps1 inspect sekiro
.\device.ps1 jobs
.\device.ps1 dashboard
```

`jobs` xem job đang hoạt động trên mọi device; `jobs sekiro` lọc một máy; `jobs --all` thêm lịch sử. Dashboard tự cập nhật qua SSH, hiển thị RAM/VRAM và job, không tự quản lý scheduler.

Trong dashboard: **j/k hoặc ↑/↓** chọn job, **i** chi tiết, **l** log, **s** dừng, **d** xóa, **h** bật/tắt lịch sử, **r** refresh, **q** thoát. Dừng/xóa có xác nhận; xóa chỉ được khi job/runner đã kết thúc. `dashboard --once` lấy một bảng duy nhất. Mở CLI không kèm lệnh để vào menu. Xem bảng minh họa không SSH bằng `demo --view dashboard`; dữ liệu demo là giả.

`running` chỉ nói tiến trình còn sống, có thể đang chờ dữ liệu. Tên/mô tả giúp hiểu mục đích; summary/phase/progress là ghi chú có thời điểm do agent báo, **không phải tiến độ CLI tự đoán**. Máy offline thì CLI báo không đọc được trạng thái mới, không giả vờ cached data vẫn live.

## Gửi code và chạy thử

```powershell
.\device.ps1 sync sekiro examples/hello --project hello
.\device.ps1 run sekiro hello --name hello-test --description 'Thử chạy code và tạo kết quả' -- python3 -u main.py
.\device.ps1 job sekiro hello-test
.\device.ps1 logs sekiro hello-test
.\device.ps1 wait sekiro hello-test
.\device.ps1 fetch sekiro hello-test --output workspace/communication/agents/human/downloads/hello-test
```

Mở hello.txt trong thư mục tải về để xem kết quả. Job có ID riêng; tên chỉ cần duy nhất trong các job đang hoạt động trên cùng device. Nếu lịch sử có nhiều job cùng tên, `jobs --all` in đầy đủ ID để bạn chọn đúng job. `logs --follow` theo dõi log trong terminal, Ctrl+C không dừng job. `wait` timeout cũng không dừng job.

Code tác vụ của bạn đặt trong `workspace/communication/agents/human/work/TEN_TAC_VU/`, rồi sync đúng thư mục code đó. Sync giới hạn **64 MiB / 20.000 file**, bỏ các tên secret/cache/dataset phổ biến và từ chối symlink. Không sync cả workspace/home; exclusions không phải máy dò secret. Dataset/model lớn giữ trên device, code dùng đường dẫn sẵn có. Kết quả mặc định ghi vào biến `DEVICE_OUTPUT_DIR` do CLI cung cấp.

## Conda và GPU

```powershell
.\device.ps1 env list sekiro
.\device.ps1 env inspect sekiro TEN_ENV
.\device.ps1 run sekiro hello --name gpu-demo --description 'Chạy script trong env có sẵn' --env TEN_ENV --gpu 0 -- python -u main.py
```

Không cần activate env. CLI không tự tạo env hoặc cài package; agent phải inspect/reuse và hỏi bạn trước khi thay đổi. `env plan` xem kế hoạch; `env install/create/remove` có xác nhận. Base không được chỉnh sửa, env riêng không được xóa; tối đa 8 env do CLI tạo. Không đổi env đang được managed job/service dùng. `--gpu 0` chọn CUDA_VISIBLE_DEVICES, **không giữ độc quyền GPU**.

## Dừng và xóa khác nhau

```powershell
.\device.ps1 stop sekiro hello-test
.\device.ps1 jobs sekiro --all
.\device.ps1 clean sekiro JOB_ID
```

**Stop** dừng tiến trình và giữ code/log/kết quả. **Clean** hỏi xác nhận rồi xóa workspace/log/kết quả của đúng job đã kết thúc; fetch trước. Project revisions và Conda env vẫn giữ. CLI không tự xóa job chỉ vì bảng lịch sử dài. `remove DEVICE` chỉ bỏ đăng ký trên host, không dừng việc trên device.

## Dữ liệu và chuyển giao giữa agent

```text
workspace/
  config/                         config máy
  runs/                           receipt gửi job, không phải trạng thái live
  legacy/                         dữ liệu cũ đã lưu lại khi chuyển repo này
  communication/
    shared/                       ngữ cảnh chung, notes, snapshot có thời điểm
    agents/AGENT_ID/
      work/                       code, script, báo cáo của agent này
      downloads/                  kết quả tải về
      notes/                      ghi chú của agent này
```

Mỗi agent chọn ID riêng cho một phiên. Agent đọc ghi chú chung trước, kiểm tra lại máy/job rồi làm việc trong thư mục riêng. Ghi chú có tên file duy nhất để không ghi đè nhau; thư mục riêng là tổ chức dữ liệu, **không phải phân quyền bí mật**. Không lưu password/key/token vào bất cứ ghi chú nào. Thư mục legacy có thể chứa credential cũ: giữ ngoài Git, không upload hoặc sync; chúng không được CLI mới sử dụng.

```powershell
.\device.ps1 communication init human
.\device.ps1 communication show
.\device.ps1 communication snapshot
```

Snapshot là ảnh chụp trạng thái lúc chạy lệnh, không tự cập nhật sau khi host tắt. `SUMMARY.md` lưu ngữ cảnh lâu dài; STATUS.md/snapshot.json do CLI tạo. Agent lưu quyết định, job IDs, phần chưa xong và bước tiếp theo bằng `communication note`; agent khác đọc lại mà không phải dựa vào trí nhớ của một cuộc chat.

## Dùng cùng AI agent

Mở agent trong repo, cho quyền chạy lệnh local và yêu cầu đọc **AGENTS.md + docs/agent-usage.md**. Agent dùng cùng CLI với `--json`, không mở dashboard tương tác. Một prompt đủ rõ:

> Đọc rules và handoff chung. Tôi muốn chạy code X trên device phù hợp. Kiểm tra tài nguyên và Conda trước, hỏi nếu cần cài package. Đặt tên/mô tả job dễ hiểu, theo dõi log, lưu tóm tắt và lấy kết quả. Không sửa CLI/rules của repo.

Agent có thể cập nhật tên/mô tả cho job cũ bằng job-note; các job cũ không bị reset khi nâng CLI. CLI không tự chạy AI, tự tóm tắt log hay tự nối một chat cloud với laptop. Bạn vẫn cần agent có khả năng chạy command trên host.

## Tùy chọn: dịch vụ tự chạy sau reboot

`serve`/`service` dùng systemd user và cần linger; không phải flow tmux chính. Ví dụ:

```powershell
.\device.ps1 sync sekiro examples/http --project web
.\device.ps1 serve sekiro web --name hello-api --port 8088 -- python3 -u main.py --host '{bind}' --port '{port}'
.\device.ps1 service sekiro check hello-api
.\device.ps1 logs sekiro hello-api --service
```

Bind chỉ vào IP Tailscale; không có HTTP authentication/TLS tự động. Chỉ đưa endpoint cho người dùng khi kiểm tra request thật đã qua. Service stop/remove giữ kết quả, remove giữ receipt nên dùng tên mới khi tạo lại.

[Hướng dẫn agent](docs/agent-usage.md) · [Workspace](workspace/README.md) · [Cấu trúc](docs/architecture.md) · [Lỗi](docs/troubleshooting.md) · [An toàn](docs/safety.md) · [Kết quả kiểm tra](docs/validation.md)
