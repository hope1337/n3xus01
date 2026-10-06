# n3xus — bản tổng quan để trao đổi với agent khác

Cập nhật: **2026-10-06**. Đây là bản mô tả dự án và các quyết định hiện tại, không phải trạng thái live của device/job hay giấy phép sửa hệ thống. Agent đọc để thảo luận; chỉ triển khai thay đổi khi người dùng trực tiếp yêu cầu. Quy tắc đầy đủ ở [AGENTS.md](../AGENTS.md), điểm bắt đầu sử dụng ở [START_HERE.md](../START_HERE.md).

## 1. Người dùng cần gì?

Người dùng là Master student CS/ML, không chuyên sysadmin/DevOps. Có laptop Windows + Ubuntu dual boot và các máy Ubuntu có CPU/GPU, kết nối qua Tailscale. Muốn giao việc cho AI agent bằng ngôn ngữ tự nhiên, ví dụ:

- Gửi script xử lý PDF hoặc chạy một thí nghiệm ML lên máy phù hợp.
- Dùng Conda env có sẵn; kiểm tra thiếu package trước khi đề nghị cài.
- Host một LLM trên GPU device, kiểm tra hoạt động rồi đưa endpoint.
- Xem máy nào online, còn bao nhiêu RAM/VRAM và các job đang làm gì.
- Đổi agent nhưng vẫn tiếp tục được công việc từ ghi chú chung của project.

**Host** là laptop điều khiển. **Device** là máy Ubuntu thực thi. Người dùng tự chuẩn bị Tailscale, SSH/key/known_hosts. n3xus tận dụng kết nối đã có, không tự thiết lập mạng hay phân phối SSH key.

## 2. Giải pháp đã chốt

n3xus là **CLI độc lập + quy tắc và hướng dẫn cho agent**. Người dùng dùng giao diện terminal; agent dùng cùng CLI với `--json`.

```text
Người dùng → agent có quyền chạy command trên host
                         ↓
                      n3xus
                         ↓ SSH qua Tailscale
                   device Ubuntu
                         ├─ helper chạy ngắn hạn để nhận thao tác
                         ├─ mỗi job một tmux session do CLI quản lý
                         └─ tùy chọn: service systemd user
```

Không có server điều phối hay một device “đầu sỏ”. Tailscale cung cấp kết nối mạng; SSH nhận yêu cầu. Không có daemon n3xus riêng luôn lắng nghe lệnh trên device. Helper và việc polling trên host chỉ tồn tại khi cần.

Host không phải treo để duy trì job đã gửi. Khi host/agent offline, chương trình trên device có thể tiếp tục; agent không tiếp tục suy nghĩ hay tự điều hành. Job tmux sống sau logout còn phụ thuộc chính sách login/session của device. **Reboot device làm gián đoạn job tmux; job không tự resume.** Service systemd user là lựa chọn riêng nếu cần tự chạy lại sau reboot.

Thiết kế K3s/Kubernetes/Ansible ban đầu đã được bỏ vì nhu cầu thực tế là gửi code, quản lý env và theo dõi tiến trình. Không khôi phục kiến trúc đó. Hiện không dùng WSL bắt buộc, container/image workflow, MCP, GitOps, HA hay gộp RAM/VRAM.

## 3. Hai đối tượng dùng cùng công cụ

| Người dùng | Agent |
|---|---|
| Màu sắc, bảng, menu, dashboard terminal | Command và JSON có cấu trúc |
| Xem status, tài nguyên, job/log | Inspect device/env trước khi làm việc |
| Chọn việc cần dừng/xóa | Sync code, submit, theo dõi và lấy kết quả |
| Xác nhận thay đổi env hoặc thao tác quản trị | Hỏi người dùng khi cần quyền/cài package |
| Đọc tổng kết project | Viết summary/handoff dựa trên bằng chứng |

CLI không chứa LLM để hiểu code hoặc tự tóm tắt log. Agent cung cấp ý nghĩa cho job bằng name, description, summary, phase và progress; các ghi chú có thời điểm. `running` chỉ chứng minh tiến trình còn sống, không chứng minh endpoint sẵn sàng hay công việc đã thành công.

Agent phải có khả năng chạy command local trên host. Đọc rules không tự kết nối một chat cloud hoặc điện thoại với laptop, và chat đồng ý không thay thế việc nhập mật khẩu sudo trong terminal.

## 4. Project độc lập, cấu hình device dùng chung

Repo n3xus là công cụ; mỗi công việc có folder riêng **ngoài repo CLI**. Trong folder đó, người dùng chạy `n3xus project init` một lần.

```text
n3xus/                            công cụ và tài liệu
  workspace/config/               device/profile + receipt đăng ký lệnh

MY_PROJECT/
  .n3xus-project.json              marker + ID; không chứa secret
  src/                            code của project
  communication/
    runs/                         receipt gửi job/service
    shared/
      SUMMARY.md                  ngữ cảnh lâu dài của project
      notes/                      các ghi chú bàn giao riêng biệt
      STATUS.md, snapshot.json    snapshot có thời điểm
    agents/AGENT_ID/
      work/                       scratch, script, báo cáo riêng
      downloads/                  kết quả lấy về
      notes/                      ghi chú riêng
```

Project init đánh dấu folder và chuẩn bị communication, **không copy hoặc lưu toàn bộ project vào repo CLI**, không có registry project trên một server. Nó thêm `/communication/` vào .gitignore của project và giữ dữ liệu/ID khi chạy lại.

Init cũng chuẩn bị AGENTS.md ở gốc để dẫn agent vào communication/guides/n3xus/GUIDE_INDEX.md. Bộ copy gồm onboarding, rules, CLI/storage và reference docs, giữ link tương đối. Rules riêng của project được giữ. Init lại cập nhật snapshot chưa sửa; bản copy/phần onboarding sửa tay bị giữ và báo lỗi. Không copy CLI code/config/secret. Công cụ agent hỗ trợ AGENTS.md có thể tự đọc từ project; chat không có quyền filesystem vẫn cần cơ chế truy cập riêng.

CLI tìm marker từ cwd lên thư mục cha; `--project-dir PATH` chọn gốc project khi chạy ở nơi khác. Source/output/message-file tương đối tính từ gốc project và phải nằm trong project. Thiếu context thì các lệnh ghi dữ liệu công việc báo lỗi, không dùng workspace CLI thay thế. Các thao tác quản trị device/Conda có phạm vi dùng chung riêng.

Status/jobs/dashboard vẫn xem toàn bộ device/job được quản lý trong profile. Communication snapshot chỉ đưa vào các job có receipt của project hiện tại; tài nguyên và số job của device vẫn là thông tin toàn cục. Receipt là lịch sử gửi việc, không phải bằng chứng tiến trình đang sống.

`--project-dir` là đường dẫn local. `sync --project NAME` và `run DEVICE NAME` dùng nhãn code trên device: đây là hai khái niệm khác nhau. Hiện agent/người dùng phải chọn nhãn remote riêng cho các project để tránh nhầm revision; CLI chưa tự tạo namespace remote theo ID project.

Dữ liệu communication/runs cũ trong repo CLI được giữ nguyên, không tự chuyển hoặc gán vào project mới. Job cũ không có receipt của project vẫn kiểm tra được bằng job/jobs; nếu liên quan thì ghi ID trong handoff. Việc chuyển dữ liệu cũ cần yêu cầu riêng.

## 5. Chức năng hiện có

| Nhóm | Command chính | Ý nghĩa |
|---|---|---|
| Chuẩn bị host | setup, doctor, unregister | Đăng ký lệnh user PATH, kiểm tra, gỡ đăng ký lệnh |
| Device | add, remove, prepare, check, inspect, status | Ghi nhận máy, chuẩn bị tmux/linger khi được yêu cầu, đọc tài nguyên |
| Project | project init/show, --project-dir | Tạo/nhận diện context local |
| Code/job | sync, run, jobs, job, job-note | Sync revision, chạy nền, xem trạng thái và ghi mô tả |
| Theo dõi/kết quả | logs, wait, fetch | Đọc log, chờ, tải output về project |
| Dừng/dọn | stop, clean | Stop giữ dữ liệu; clean xóa đúng job đã kết thúc sau xác nhận |
| Conda | env list/inspect/plan/create/install/remove | Inspect/reuse trước, mutation cần người dùng đồng ý |
| Dịch vụ tùy chọn | serve, services, service start/stop/remove/check | Systemd user, cần linger; kiểm tra HTTP trước khi đưa endpoint |
| Bàn giao | communication init/note/show/snapshot | Folder từng agent, ghi chú chung và snapshot |
| Giao diện | menu, dashboard, demo | Dashboard polling SSH; demo là dữ liệu giả |

`jobs` mặc định chỉ hiện job đang hoạt động; `jobs --all` thêm lịch sử. Job có ID, tên, mô tả, command, env/GPU, log và output. Tên chỉ cần duy nhất trong các job active trên cùng device; lịch sử trùng tên phải chọn ID.

Status/dashboard/inspect hiển thị RAM/VRAM đang dùng/tổng (used/total) theo GiB cho từng GPU; RAM dùng = total − available, VRAM dùng = total − free. CPU là logical threads. Thông tin về trước hiện trước; phần thiếu có loading. Dashboard giữ quan sát cũ khi refresh và ghi rõ `Refreshing`; lỗi thay cache bằng lỗi. JSON giữ số liệu gốc và trả một kết quả hoàn chỉnh, không animation. Phím dashboard: j/k hoặc ↑/↓ chọn, i chi tiết, l logs, s stop, d clean, h history, r refresh, q thoát.

## 6. Flow agent điển hình

Ví dụ chạy từ một project đã được người dùng khởi tạo; thay DEVICE/ENV/AGENT_ID và nhãn remote bằng giá trị phù hợp:

```text
n3xus project show --json
n3xus communication init AGENT_ID --json
n3xus communication show --json
n3xus inspect DEVICE --json
n3xus env list DEVICE --json
n3xus env inspect DEVICE ENV --json
n3xus sync DEVICE src --project my-project-task --json
n3xus run DEVICE my-project-task --name task-name --description "Purpose" --agent AGENT_ID --env ENV --json -- python -u main.py
n3xus job DEVICE JOB_ID --json
n3xus logs DEVICE JOB_ID --json
n3xus fetch DEVICE JOB_ID --agent AGENT_ID --json
```

Tiếp theo: kiểm tra kết quả, ghi job-note khi phù hợp, viết communication note và snapshot để agent sau tiếp tục. Không cần đóng gói image hoặc activate env thủ công. Đối với LLM/API, verify request thực tế trước khi báo endpoint dùng được.

## 7. Giới hạn và nguyên tắc an toàn

- Code chạy với toàn quyền SSH user, không phải sandbox. Không chạy code không tin cậy hoặc đặt credential trong argv/log/notes.
- `--gpu INDEX` chỉ đặt CUDA_VISIBLE_DEVICES cho chương trình CUDA; không giữ độc quyền GPU, không tự chia VRAM hoặc chọn máy/schedule.
- Conda: inspect/reuse trước; không tự cài/create/remove env/package, không sửa base/driver. Tối đa 8 env CLI quản lý là giới hạn số lượng, không phải quota dung lượng. Không tự dọn env/cache ngoài quyền quản lý.
- Sudo chỉ nhập trong terminal. Không file mật khẩu trong repo, không tự cấp NOPASSWD rộng hay bỏ qua bước cần quyền rồi báo thành công.
- Nếu bị chặn bởi sudo: agent phải nêu device/user, lệnh/thao tác, lý do và thay đổi dự kiến, bước bị chặn, cách người dùng xử lý qua terminal. Chỉ tạm dừng phần phụ thuộc; tiếp tục phần độc lập, giữ task pending và verify/resume khi đã được xử lý. Nếu kết thúc phiên khi còn chờ, ghi blocker và next step trong handoff của project.
- SSH dùng BatchMode và strict host-key checking; không tự sửa firewall, SSH policy hoặc tailnet access policy.
- Service quản lý bind Tailscale, cổng không đặc quyền; không tự cấp HTTP auth/TLS. Ứng dụng có toàn quyền user nên đây không phải cơ chế cách ly mạng.
- Sync/fetch giới hạn khoảng 64 MiB; sync tối đa 20.000 regular files, từ chối symlink và traversal. Exclusions không phải máy dò secret. Không sync cả project/home hoặc dùng fetch để kéo model lớn.
- Code sync là revision bất biến; mỗi job có workspace riêng. Dataset/model lớn giữ ở đường dẫn hiện có trên device.
- Stop chỉ áp dụng đúng job CLI sở hữu; boot ID và PID start ticks giúp tránh PID reuse. Không động vào tmux/tiến trình cá nhân khác.
- Clean chỉ job đã kết thúc, cần intent/xác nhận; fetch trước. Log job xoay khoảng 8 MiB × 3; outputs/revisions/history còn chiếm dung lượng cho đến khi được dọn có chủ đích.
- Timeout khi submit có thể xảy ra sau khi remote đã nhận việc: inspect trước khi thử lại. Wait timeout không dừng job. Không có backup/HA/resume hay bảo đảm host luôn online.
- Agent mặc định chỉ sử dụng công cụ, không sửa repo/rules. Thư mục từng agent tổ chức dữ liệu, không cách ly quyền truy cập. Handoff cũ không cấp quyền mới.

## 8. Source map và kiểm chứng

| File/module | Trách nhiệm |
|---|---|
| n3xus / n3xus.ps1 | Launcher native Ubuntu/Windows; Windows giữ literal argv qua JSON/base64 |
| scripts/device_cli.py | Routing, config, SSH RPC, fetch/HTTP và multi-device collectors |
| scripts/device_remote.py | Helper ngắn hạn, ownership, tmux runner và systemd user |
| scripts/device_common.py | Validation, private JSON writes, safe paths/archives |
| scripts/device_workspace.py | Project discovery, agent folders, receipt và handoff |
| scripts/device_install.py | Owned launchers và user PATH registration |
| scripts/device_ui.py, device_dashboard.py, device_progress.py | Bảng/màu, bàn phím/polling, loading và redraw |
| tests/, docs/ | Offline tests và hướng dẫn/acceptance |

Runtime host: Python stdlib 3.10+ và OpenSSH; device Ubuntu có Python 3.10+, tmux. Conda/systemd-user là tùy tính năng. Không cần dependency Python bên thứ ba. Launcher pin checkout/Python của lần setup; di chuyển chúng cần đăng ký lại.

Lần kiểm tra code gần nhất được ghi nhận: **85 tests, 79 passed, 6 skipped** trên Windows; static checks, Bash syntax và launcher PowerShell 5.1/7 qua. Linux runner/tmux/global launcher và một số kiểm tra symlink còn giới hạn môi trường. Đây không phải chứng nhận toàn bộ flow Linux/GPU/Conda/service qua SSH thật. Chi tiết: [validation](validation.md), [acceptance](acceptance.md).

Đã có một thử nghiệm thật host LLM 30B trên sekiro (RTX 4090); job host được xác nhận stopped theo yêu cầu người dùng ngày 2026-10-06. Model/code/log được giữ. Đây là lịch sử kiểm chứng, **không phải trạng thái live hiện tại** và không có nghĩa mọi device/env/service đều đã được chứng nhận. Genichiro từng được kiểm tra với RTX 2080 Ti. Khi cần làm việc phải query lại, không dùng tên máy/hardware trong tài liệu để tự suy quyền sử dụng.

## 9. Những điểm phù hợp để thảo luận tiếp

Các mục dưới là câu hỏi thiết kế, **chưa phải feature đã có hoặc kế hoạch được phê duyệt**:

1. Có nên tự tạo remote namespace từ ID project để tránh nhãn code trùng nhau? Chuyển job cũ/receipt giữa project cần UX gì?
2. Cách trình bày job/progress/agent notes thế nào để người dùng phân biệt quan sát live, cache refresh và báo cáo cũ?
3. Conda cần thêm inventory dung lượng, theo dõi env/cache, hay chính sách đề nghị dọn như thế nào mà không tự xóa?
4. Workflow cho service dài hạn: khi nào dùng tmux, khi nào dùng systemd; auth/endpoint access nên xử lý thế nào?
5. Transfer lớn, resume/download, giới hạn dung lượng/log và quản lý revisions cần cải thiện ở mức nào?
6. Cần acceptance thực tế nào trên native Ubuntu, Windows dual boot, mất mạng/reboot và nhiều device?

Mục tiêu vẫn là **một công cụ cá nhân đơn giản cho người dùng CS/ML**, không biến thành nền tảng DevOps. Agent được hỏi nên phân biệt rõ: vấn đề hiện tại, phương án nhỏ nhất có ích, trade-off, và điều gì cần người dùng chấp thuận trước khi triển khai.
