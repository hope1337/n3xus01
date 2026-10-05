# Host setup

Lệnh người dùng: Windows `.\cluster.ps1 setup`, Ubuntu `./cluster setup`. Lệnh chỉ chuẩn bị **host**, không SSH hay thay đổi device.

## Ubuntu

Khuyến nghị Ubuntu 24.04. Wrapper tự cài Python/venv, curl, OpenSSH client khi thiếu; có thể hỏi sudo **host**. Ansible cài trong môi trường riêng, kubectl v1.36.4 tải từ Kubernetes và kiểm SHA256. Không đổi kubectl hay `~/.kube/config` chung; không cần activate mỗi terminal.

Source clone cần giữ executable bit của `cluster`. Nếu copy source bằng cách mất bit này, chạy `bash ./cluster setup` một lần hoặc `chmod +x cluster`.

## Windows

Windows 11 hoặc Windows 10 có WSL2, virtualization được bật; OpenSSH client/SSH key đã được bạn chuẩn bị. Wrapper dùng distro **Ubuntu-24.04**; có thì tái sử dụng, thiếu thì setup yêu cầu Windows cài bằng WSL. Có thể cần UAC và reboot, không có auto reboot. Sau restart chạy lại cùng lệnh.

WSL controller chạy bằng user root trong distro, không cần tạo Linux user tương tác. Nó gọi **Windows `ssh.exe`** qua WSL interop để dùng đúng Windows keys, known_hosts và ssh-agent. Transfer Ansible dùng pipe, không scp/sftp với đường dẫn WSL. Không copy private key, không cài Tailscale trong WSL, không đổi Windows firewall hoặc policy SSH.

Credential/state nằm trên filesystem Linux của WSL dưới `/root/.local/share/personal-compute/<checkout-id>/`, directory `0700`, file `0600`. Source/config `devices.yml` ở checkout Windows chỉ chứa thông tin máy; không chứa token/key/certificate. Wrapper tự tìm state, không cần nhớ đường dẫn.

Nếu PowerShell chặn chạy script chưa ký, có thể dùng invocation chỉ áp dụng cho tiến trình đó:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\cluster.ps1 setup
```

Không cần đổi execution policy toàn máy. Nếu dùng Git for Windows SSH riêng, hãy chắc `ssh.exe` được chọn trong PATH là client đã có key/known_hosts hoạt động; Windows OpenSSH là đường dùng đã thiết kế cho wrapper.

## Chuyển giữa Windows và Ubuntu

Dùng cùng `devices.yml` (gồm `cluster_id`) trên hai OS. Credentials không tự copy giữa hai OS: chạy `add-device SERVER_NAME` để lấy lại quyền truy cập qua SSH; rồi rerun `add-device` cho worker để ghi metadata local khi cần. Không tạo cluster mới hoặc xóa marker. Clone mới không có devices.yml thì không biết cluster cũ thuộc bạn; cố nhận quản lý sẽ bị từ chối.

Nguồn: [Ansible controller/WSL](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html), [WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).
