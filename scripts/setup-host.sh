#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT=$1
STATE=$2
trap 'echo "[cluster] Host setup failed. Fix the error above, then rerun setup." >&2' ERR
echo '[cluster] Preparing local tools. No device is contacted.'
[[ ! -L "$STATE" ]] || { echo 'Refusing symlink state directory.' >&2; exit 1; }
mkdir -p "$STATE/tools/bin" "$STATE/downloads"
chmod 700 "$STATE"
sudo_command=()
if [[ $(id -u) != 0 ]]; then sudo_command=(sudo); fi
if ! command -v python3 >/dev/null || ! python3 -c 'import venv; import ensurepip' 2>/dev/null || ! command -v curl >/dev/null || ! command -v ssh >/dev/null; then
  echo '[cluster] Installing local prerequisites; local sudo may be requested.'
  "${sudo_command[@]}" apt-get update
  "${sudo_command[@]}" apt-get install -y python3 python3-venv openssh-client curl ca-certificates
fi
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,13), "Use Ubuntu 24.04 (Python 3.11-3.13 required)."'
if [[ ! -x "$STATE/venv/bin/python" ]]; then python3 -m venv "$STATE/venv"; fi
"$STATE/venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"
case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) echo 'Unsupported host architecture' >&2; exit 1 ;; esac
if [[ ! -x "$STATE/tools/bin/kubectl" ]]; then
  (
    cd "$STATE/downloads"
    curl -fL --retry 3 -o kubectl "https://dl.k8s.io/release/v1.36.4/bin/linux/$arch/kubectl"
    curl -fL --retry 3 -o kubectl.sha256 "https://dl.k8s.io/release/v1.36.4/bin/linux/$arch/kubectl.sha256"
    printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check
    install -m 0755 kubectl "$STATE/tools/bin/kubectl"
  )
fi
if [[ ! -f "$ROOT/devices.yml" ]]; then cp "$ROOT/devices.example.yml" "$ROOT/devices.yml"; fi
echo '[cluster] Tools ready. No shell activation needed in future terminals.'
