# Giao việc cho agent

Agent cần chạy lệnh trên host tại repo. Không cần MCP. Windows dùng `.\device.ps1`, Ubuntu `./device`. `--json` đặt trước/sau lệnh, trước dấu `--`; stdout là một JSON với schema, ok, data hoặc error. Exit 0 là thành công của thao tác, chưa chắc job đã hoàn tất. Exit 1 là lỗi, 130 là host bị ngắt. Help vẫn là văn bản.

Prompt gợi ý:

> Đọc AGENTS.md và docs/agent-usage.md. Xem device nào online và tài nguyên hiện tại. Tôi muốn chạy code trong thư mục X trên genichiro. Inspect Conda trước và dùng env phù hợp. Nếu thiếu package/env thì giải thích và hỏi tôi trước khi cài. Gửi code, chạy nền, xem log và lấy kết quả.

> Tôi muốn host một LLM trên sekiro. Kiểm tra GPU/RAM/disk và công cụ đã có trước. Đề xuất model phù hợp, hỏi trước khi tải model lớn/cài package. Dùng service Tailscale, kiểm tra endpoint thật rồi trả URL và cách gọi. Không mở public port.

Quy trình tác vụ:

```powershell
.\device.ps1 status --json
.\device.ps1 inspect genichiro --json
.\device.ps1 env list genichiro --json
.\device.ps1 env inspect genichiro TEN_ENV --json
.\device.ps1 sync genichiro DUONG_DAN_CODE --project extract --json
.\device.ps1 run genichiro extract --env TEN_ENV --gpu 0 --json -- python -u main.py
```

Lưu ID do run trả; dùng jobs/logs/wait. Khi completed, fetch tải thư mục DEVICE_OUTPUT_DIR; code cần ghi kết quả vào biến đó. Hoặc fetch --path THU_MUC_TUONG_DOI tải một thư mục trong workspace. Download từ chối ghi đè, giới hạn 64 MiB. Dataset/checkpoint lớn giữ trên disk device.

```powershell
.\device.ps1 env plan genichiro TEN_ENV --package pypdf --pip --json
```

Trình bày plan cho người dùng. Chỉ sau khi được đồng ý mới dùng env install cùng flags và --yes. Nếu tạo mới: env create DEVICE TEN_MOI --python 3.11 --yes. Không chạm base hoặc env riêng khi chưa có yêu cầu; ngoài managed jobs, user có thể đang chạy notebook/training riêng.

Host service bằng serve, với {bind}/{port} trong argv, xem ví dụ README. Dịch vụ không tự có authentication; tailnet ACL vẫn do user quản lý. services → logs DEVICE TEN_SERVICE → service DEVICE check TEN_SERVICE. Nếu model load lâu, chờ và check lại; không coi một process active là endpoint hoạt động.

Agent được viết code trong thư mục source riêng, sync và chạy literal argv. Không tự upload toàn home hoặc repo chứa secrets; exclusions chỉ hỗ trợ, không bảo đảm phát hiện mọi secret. CLI không biết độ phù hợp của package/model, agent phải xem cấu hình và chọn. Không tự download model lớn hay đổi driver. Ollama/llama.cpp là công cụ khác nhau: xác minh executable thực tế trước.

Mất host kết nối: job/service đã gửi vẫn chạy, agent không tiếp tục suy nghĩ khi host tắt. Bật host lại → status/jobs/services/logs. Không tự retry một mutation vừa timeout: inspect trước để tránh gửi trùng. Device reboot: jobs có thể interrupted, services tự khởi động lại. Hỏi trước khi chạy lại việc tốn tài nguyên hoặc ghi dữ liệu.
