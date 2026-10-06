# n3xus — giao việc cho các máy của bạn

Repo này giúp bạn và AI agent **gửi code từ laptop sang máy Ubuntu, chạy nền và biết công việc đang làm gì**. Laptop là **host**; các máy nhận việc là **device**. Bạn chuẩn bị Tailscale và SSH key trước; CLI sử dụng kết nối đó. n3xus là công cụ dùng chung; mỗi công việc có project folder riêng ngoài repo CLI.

Ví dụ: “Chạy script xử lý PDF trên genichiro” hoặc “Host model trên sekiro”. Agent kiểm tra tài nguyên/Conda, gửi code, tạo job, đọc log rồi lấy kết quả hoặc kiểm tra endpoint. Không cần đóng image, học Kubernetes hay giữ một terminal SSH mở liên tục.

## Repo gồm những gì?

| Thành phần | Công dụng |
|---|---|
| **CLI `n3xus`** | Gửi code, chạy/dừng/xóa job, xem máy, env, log và lấy kết quả |
| **Dashboard terminal** | Bảng tự cập nhật mọi device và job, giống cách xem nvitop; không cần website |
| **`AGENTS.md`** | Quy tắc agent: được làm gì, hỏi khi nào, lưu dữ liệu ở đâu |
| **`docs/agent-usage.md`** | Các lệnh và quy trình giao việc cho agent |
| **`workspace/config/`** | Config device và đăng ký lệnh, dùng chung cho mọi project |
| **`PROJECT/communication/`** | Receipt, báo cáo, kết quả và bàn giao giữa agent của riêng project |
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
.\n3xus.ps1 setup
n3xus add sekiro --address 100.123.148.6 --user manh
n3xus prepare sekiro --install-tools --enable-linger
n3xus check sekiro
```

Trên Ubuntu, lần đầu chạy `./n3xus setup`, rồi mở terminal mới (hoặc `source ~/.bashrc` một lần). Sau đó cả Windows và Ubuntu đều gọi `n3xus ...` từ bất kỳ thư mục nào. Chỉ thay **tên device, địa chỉ Tailscale và SSH user** cho máy của bạn. Thêm máy khác bằng `add` với tên/IP/user của máy đó. `prepare` hỏi xác nhận và có thể hỏi mật khẩu sudo **trong terminal** để cài tmux nếu thiếu/bật linger. CLI không cài Conda/driver, sửa firewall hay tạo SSH key.

`setup` tự đăng ký lệnh **n3xus** cho user hiện tại. Windows đặt launcher trong `%LOCALAPPDATA%/PersonalDevice/bin` và thêm vào **user PATH**; chạy bằng `.\n3xus.ps1 setup` cập nhật luôn PATH của terminal PowerShell hiện tại. Ubuntu đặt launcher trong `~/.local/bin`, thêm block PATH riêng vào `~/.profile` và `~/.bashrc` khi cần. Không cần admin/sudo hay pip package. Nếu terminal/app đã mở từ trước chưa nhận PATH, mở lại terminal/app. Các shell Ubuntu khác Bash có thể cần tự thêm `~/.local/bin` vào PATH.

Launcher trỏ về repo và Python đang dùng lúc setup. Di chuyển repo hoặc đổi Python: chạy lại setup ở vị trí mới; tại một thời điểm, lệnh toàn cục trỏ về một repo. `setup --no-register` chỉ chuẩn bị config. Cấu hình device dùng chung nằm trong repo CLI; code và dữ liệu công việc nằm trong project riêng.

Gỡ **lệnh toàn cục**, giữ config và toàn bộ job/data:

```powershell
n3xus unregister
```

Lệnh chỉ gỡ launcher do CLI tạo cùng phần PATH nó đã thêm. Không ghi đè/xóa launcher khác hoặc launcher/block PATH bị sửa thủ công. Sau gỡ vẫn có thể gọi `.\n3xus.ps1` / `./n3xus` tại repo. Đây khác với `remove DEVICE` (bỏ đăng ký một máy).

Nếu Conda nằm ở đường dẫn khác: `add ... --conda /duong/dan/bin/conda`. Key mặc định được dùng; thêm `--key DUONG_DAN_KEY` nếu cần. Không lưu mật khẩu.

Config ở **`workspace/config/devices.json`**, Git bỏ qua. `setup` chuyển config JSON cũ ở root vào đây và giữ nguyên profile. Đổi Windows ↔ Ubuntu: giữ cùng workspace/config, chuẩn bị SSH/key ở OS mới rồi setup/status; key path có thể cần đổi. Không reprovision device.

## Xem máy và công việc

```powershell
n3xus status
n3xus inspect sekiro
n3xus jobs
n3xus dashboard
```

`jobs` xem job đang hoạt động trên mọi device; `jobs sekiro` lọc một máy; `jobs --all` thêm lịch sử. Status và dashboard hiển thị CPU(T) là số luồng logic, RAM khả dụng/tổng và VRAM trống/tổng theo GiB. Mỗi GPU có một dòng riêng; máy offline hoặc thiếu thông tin hiện dấu —/?. Dashboard tự cập nhật qua SSH và hiển thị job, không tự quản lý scheduler.

Trong terminal, thông tin về trước hiện trước: CPU/RAM có thể hiện trong lúc GPU còn `loading…`; device trả lời nhanh không phải đợi device chậm. Danh sách job đang chờ cũng có dòng loading riêng. Những lệnh khác (log, môi trường, kiểm tra dịch vụ…) có biểu tượng xoay khi đang chờ phản hồi. Loading không có nghĩa là offline; khi timeout/lỗi, CLI sẽ ghi rõ lỗi. `--json` hoặc chuyển output vào file vẫn trả một kết quả hoàn chỉnh, không kèm animation.

Dashboard tự refresh định kỳ ngay trong cùng một màn hình. Trong lúc chờ, bảng giữ thông tin/job đã lấy được và hiện `Refreshing` để báo dữ liệu cũ đang chờ cập nhật; chỉ phần chưa từng có thông tin mới hiện loading. Kết quả mới thay từng phần; nếu device báo lỗi/offline, thông tin cũ của máy đó được thay bằng lỗi.

Trong dashboard: **j/k hoặc ↑/↓** chọn job, **i** chi tiết, **l** log, **s** dừng, **d** xóa, **h** bật/tắt lịch sử, **r** refresh, **q** thoát. Dừng/xóa có xác nhận; xóa chỉ được khi job/runner đã kết thúc. `dashboard --once` lấy một bảng duy nhất. Mở CLI không kèm lệnh để vào menu. Xem bảng minh họa không SSH bằng `demo --view dashboard`; dữ liệu demo là giả.

`running` chỉ nói tiến trình còn sống, có thể đang chờ dữ liệu. Tên/mô tả giúp hiểu mục đích; summary/phase/progress là ghi chú có thời điểm do agent báo, **không phải tiến độ CLI tự đoán**. Máy offline thì CLI báo không đọc được trạng thái mới, không giả vờ cached data vẫn live.

## Gửi code và chạy thử

Tạo project riêng **ngoài repo n3xus** một lần; các lệnh này dùng được trên Windows/Ubuntu:

```text
mkdir my-project
cd my-project
n3xus project init
n3xus communication init human
```

Nếu đang đứng trong repo CLI, hãy cd sang thư mục chứa các project của bạn trước. Đặt code vào `src/main.py` của project (có thể copy ví dụ `examples/hello` của repo CLI vào `src`). Sau đó:

```powershell
n3xus sync sekiro src --project my-project
n3xus run sekiro my-project --name hello-test --description 'Thử chạy code và tạo kết quả' -- python3 -u main.py
n3xus job sekiro hello-test
n3xus logs sekiro hello-test
n3xus wait sekiro hello-test
n3xus fetch sekiro hello-test
```

Mở hello.txt trong thư mục tải về để xem kết quả. Job có ID riêng; tên chỉ cần duy nhất trong các job đang hoạt động trên cùng device. Nếu lịch sử có nhiều job cùng tên, `jobs --all` in đầy đủ ID để bạn chọn đúng job. `logs --follow` theo dõi log trong terminal, Ctrl+C không dừng job. `wait` timeout cũng không dừng job.

Code đặt trong `PROJECT/src/` hoặc `PROJECT/communication/agents/ID/work/TEN_TAC_VU/`, rồi sync đúng thư mục code đó. Sync giới hạn **64 MiB / 20.000 file**, bỏ các tên secret/cache/dataset phổ biến và từ chối symlink. Không sync cả project/home; exclusions không phải máy dò secret. Dataset/model lớn giữ trên device, code dùng đường dẫn sẵn có. Kết quả trên device mặc định ghi vào `DEVICE_OUTPUT_DIR`; fetch mặc định tải vào `communication/agents/human/downloads/DEVICE-JOB/`, dùng `--agent ID` cho agent khác.

`project init` tạo marker `.n3xus-project.json`, communication và thêm `/communication/` vào .gitignore; chạy lại giữ nguyên dữ liệu/ID. CLI tìm marker từ thư mục đang đứng lên thư mục cha. `n3xus project show` cho biết project đang chọn. Nếu chạy từ nơi khác, thêm `--project-dir "ĐƯỜNG_DẪN_PROJECT"`. Các đường dẫn code/output/message-file tương đối tính từ **gốc project**, và phải nằm trong project. Chưa xác định được project thì các lệnh ghi dữ liệu sẽ báo lỗi, không tự ghi vào repo CLI. Status/jobs/dashboard/inspect vẫn dùng được ở mọi nơi.

`--project my-project` khi sync và tên sau device khi run là **nhãn code trên device**, khác với `--project-dir` là thư mục local. Chọn nhãn riêng cho mỗi project để không nhầm revision giữa các công việc.

## Conda và GPU

```powershell
n3xus env list sekiro
n3xus env inspect sekiro TEN_ENV
n3xus run sekiro my-project --name gpu-demo --description 'Chạy script trong env có sẵn' --env TEN_ENV --gpu 0 -- python -u main.py
```

Không cần activate env. CLI không tự tạo env hoặc cài package; agent phải inspect/reuse và hỏi bạn trước khi thay đổi. `env plan` xem kế hoạch; `env install/create/remove` có xác nhận. Base không được chỉnh sửa, env riêng không được xóa; tối đa 8 env do CLI tạo. Không đổi env đang được managed job/service dùng. `--gpu 0` chọn CUDA_VISIBLE_DEVICES, **không giữ độc quyền GPU**.

## Dừng và xóa khác nhau

```powershell
n3xus stop sekiro hello-test
n3xus jobs sekiro --all
n3xus clean sekiro JOB_ID
```

**Stop** dừng tiến trình và giữ code/log/kết quả. **Clean** hỏi xác nhận rồi xóa workspace/log/kết quả của đúng job đã kết thúc; fetch trước. Project revisions và Conda env vẫn giữ. CLI không tự xóa job chỉ vì bảng lịch sử dài. `remove DEVICE` chỉ bỏ đăng ký trên host, không dừng việc trên device.

## Dữ liệu và chuyển giao giữa agent

```text
MY_PROJECT/
  .n3xus-project.json              nhận diện project; không chứa secret
  src/                            code của project
  communication/
    runs/                         receipt gửi job/service, không phải trạng thái live
    shared/                       ngữ cảnh chung, notes, snapshot có thời điểm
    agents/AGENT_ID/
      work/                       code, script, báo cáo của agent này
      downloads/                  kết quả tải về
      notes/                      ghi chú của agent này
```

Mỗi agent chọn ID riêng cho một phiên. Agent đọc shared của **project đang làm**, kiểm tra lại máy/job rồi làm việc trong thư mục riêng. Ghi chú có tên duy nhất để không ghi đè nhau; thư mục riêng là tổ chức dữ liệu, **không phải phân quyền bí mật**. Không lưu password/key/token. Code/kết quả không đặt trong repo CLI. Config device vẫn ở `n3xus/workspace/config`; dữ liệu workspace cũ được giữ nguyên, không tự chuyển hoặc gán vào project mới.

```powershell
n3xus communication init human
n3xus communication show
n3xus communication snapshot
```

Snapshot là ảnh chụp lúc chạy lệnh, không tự cập nhật sau khi host tắt. Snapshot giữ tài nguyên/count device chung, nhưng danh sách job chỉ lấy các job có receipt trong project này. Jobs/dashboard vẫn xem tất cả job; job cũ chưa có receipt được nhắc riêng trong handoff nếu liên quan. `SUMMARY.md` lưu ngữ cảnh lâu dài; STATUS.md/snapshot.json do CLI tạo. Agent lưu quyết định, job IDs, phần chưa xong và bước tiếp theo bằng `communication note`.

## Dùng cùng AI agent

Mỗi khi mở agent mới, cho quyền đọc file/chạy lệnh local và chỉ cần nói:

> Đọc START_HERE.md trong repo n3xus. Làm việc trong project folder [đường dẫn project]. Yêu cầu: …

Nếu agent ở ngoài repo, đưa đường dẫn tuyệt đối tới [START_HERE.md](START_HERE.md). File dẫn agent tới rules, hướng dẫn CLI và handoff chung để hiểu ngữ cảnh mà không cần bạn kể lại các chat trước. Tài liệu dành cho agent dùng tiếng Anh; README dành cho bạn giữ tiếng Việt và agent vẫn báo lại bằng tiếng Việt. Khi chưa giao tác vụ, agent chỉ đọc và chờ; trạng thái cũ vẫn phải kiểm tra lại trước khi làm việc.

Agent dùng cùng CLI với `--json`, không mở dashboard tương tác. Một prompt giao việc cụ thể:

> Đọc rules và handoff chung. Tôi muốn chạy code X trên device phù hợp. Kiểm tra tài nguyên và Conda trước, hỏi nếu cần cài package. Đặt tên/mô tả job dễ hiểu, theo dõi log, lưu tóm tắt và lấy kết quả. Không sửa CLI/rules của repo.

Agent có thể cập nhật tên/mô tả cho job cũ bằng job-note; các job cũ không bị reset khi nâng CLI. CLI không tự chạy AI, tự tóm tắt log hay tự nối một chat cloud với laptop. Bạn vẫn cần agent có khả năng chạy command trên host.

## Tùy chọn: dịch vụ tự chạy sau reboot

`serve`/`service` dùng systemd user và cần linger; không phải flow tmux chính. Ví dụ:

Copy nội dung `examples/http` của repo CLI vào `src-http/` trong project trước khi chạy:

```powershell
n3xus sync sekiro src-http --project my-project-web
n3xus serve sekiro my-project-web --name hello-api --port 8088 -- python3 -u main.py --host '{bind}' --port '{port}'
n3xus service sekiro check hello-api
n3xus logs sekiro hello-api --service
```

Bind chỉ vào IP Tailscale; không có HTTP authentication/TLS tự động. Chỉ đưa endpoint cho người dùng khi kiểm tra request thật đã qua. Service stop/remove giữ kết quả, remove giữ receipt nên dùng tên mới khi tạo lại.

[Hướng dẫn agent](docs/agent-usage.md) · [Workspace](workspace/README.md) · [Cấu trúc](docs/architecture.md) · [Lỗi](docs/troubleshooting.md) · [An toàn](docs/safety.md) · [Kết quả kiểm tra](docs/validation.md)

Tên CLI hiện tại là **n3xus**. Chạy setup sẽ chuyển launcher device cũ do chính repo này tạo sang n3xus; không thay profile/job/device state và không xóa lệnh device của công cụ khác.
