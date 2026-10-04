# Công cụ trên Ubuntu laptop (một lần)

Khuyến nghị boot Ubuntu **24.04**, dùng thư mục repo trong filesystem Linux. Tailscale trên phân vùng Windows không thay thế Tailscale trên Ubuntu: Ubuntu phải join tailnet và SSH tới target được.

Cài công cụ nền:

```bash
sudo apt update
sudo apt install -y git openssh-client curl python3 python3-venv
```

Clone repository từ remote của bạn rồi `cd` vào repo. Repo tạo ở đây chưa được publish lên GitHub nên không có URL clone giả định. Nếu đã copy source sang Ubuntu, mở thư mục đó trực tiếp.

Cài Ansible vào môi trường riêng (không dùng sudo pip):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
chmod +x cluster
```

Ansible core 2.19 yêu cầu controller Python 3.11–3.13; Python 3.12 của Ubuntu 24.04 phù hợp. Target Ubuntu 22.04 vẫn dùng được. [Ma trận hỗ trợ chính thức](https://docs.ansible.com/projects/ansible-core/2.19/reference_appendices/release_and_maintenance.html).

Cài kubectl **v1.36.4** đã verify SHA256 vào `~/.local/bin`; không chép đè kubectl có sẵn. Đoạn dưới hỗ trợ laptop amd64/arm64, chạy trong Bash. Nếu máy đã có kubectl 1.36, bỏ qua download:

```bash
mkdir -p "$HOME/.local/bin" .cluster/downloads
export PATH="$HOME/.local/bin:$PATH"
if ! command -v kubectl >/dev/null 2>&1; then
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64) arch=arm64 ;;
    *) echo 'Unsupported laptop architecture'; exit 1 ;;
  esac
  (
    set -e
    cd .cluster/downloads
    curl -fL --retry 3 -o kubectl "https://dl.k8s.io/release/v1.36.4/bin/linux/$arch/kubectl"
    curl -fL --retry 3 -o kubectl.sha256 "https://dl.k8s.io/release/v1.36.4/bin/linux/$arch/kubectl.sha256"
    printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check
    install -m 0755 kubectl "$HOME/.local/bin/kubectl"
  )
fi
kubectl version --client
```

Mỗi terminal mới trong repo:

```bash
source .venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
```

Sau đó làm mục khai báo target trong README và chạy `./cluster check`, `./cluster setup first-node`.

Không cần Docker, Helm, external Ansible collection hoặc Kubernetes trên laptop. Không cần học Ansible trước khi dùng ba lệnh chính.
