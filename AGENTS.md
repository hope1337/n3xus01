# Personal compute repository: instructions for maintaining and using it

Read this file before changing the repo or submitting workloads. User authorization takes precedence. Do not confuse the AI agent with the K3s worker/agent service.

## Intended user experience

The user is a CS/ML student, not a sysadmin. Host is Windows or Ubuntu; devices are Ubuntu, already in Tailscale with passwordless SSH key access. The three main commands are setup, add-device, check. Keep README short and Vietnamese. Put implementation details here or in docs. Do not require shell activation, manual Ansible commands, public ports or a continuously open host terminal.

GPU NVIDIA/RTX 4090 is IN scope. Workers are IN scope. HA, backup/restore, server promotion, GitOps, monitoring stacks, shared storage, GPU Operator and MCP implementation are OUT of scope. CPU/GPU jobs and agent-readable command help are in scope. Do not expand scope just because a tool exists.

## Architecture and source map

- `cluster`: Bash entry point, selects private state/tools, calls host bootstrap once and Python CLI. Not the provisioning engine.
- `cluster.ps1`: Windows entry point. Uses Ubuntu-24.04 WSL as root controller, Windows ssh.exe/key/known_hosts/agent, piped Ansible transfer. No key copy, WSL Tailscale join or global execution-policy change. Container argv travels JSON/base64 to survive Windows legacy quoting. Do not replace with shell eval/string interpolation.
- `scripts/setup-host.sh`: local prerequisites/venv, pinned kubectl with SHA256, initializes devices.yml only if absent. No SSH/device mutation.
- `scripts/cluster_cli.py`: validates/records devices.yml, creates private Ansible inventory, targets ONE device; kubectl always uses isolated kubeconfig/context. First device server (SQLite), subsequent devices workers. Also builds/checks/waits for Jobs.
- `playbooks/setup.yml`, `roles/k3s_node/`: read-only preflight, optional GPU driver/toolkit setup, official pinned K3s install, boot wait for Tailscale, private kubeconfig/join token export, data directories/device receipt. Config templates differ server/worker. No changing roles/IPs/version in place.
- `playbooks/reset.yml`: exact owned node cleanup with explicit confirmation/integrity checks. Data directories never removed. Worker Node password is cleaned by CLI after uninstall. Never reset server with configured workers.
- `kubernetes/`: ClusterIP nginx smoke, NVIDIA device plugin; no Helm/GPU Operator. CLI generates CPU/DNS/HTTP and CUDA nbody test Jobs, and user Jobs.
- `tests/`: offline unit/safety tests plus Windows mock routing; CI adds Linux Ansible syntax. Live tests are `check` and `test --gpu DEVICE`.

## Config, credentials and lifecycle

`devices.yml` is generated, ignored, no secrets. Fields: cluster_id (nonsecret identity) and devices mapping; per device address, user, role, gpu, data_root, optional key PATH. Preserve cluster_id and device identities. No two servers/duplicate addresses; reject unknown fields/duplicate YAML keys. Do not commit user config.

Ubuntu host state `.cluster/`; Windows WSL private state `/root/.local/share/personal-compute/<checkout-id>/`. Includes venv/tools, isolated kubeconfig, join-token, generated inventory and nodes/NAME.json receipts. All credentials stay on Linux filesystem, directory 0700, files 0600; slurp/copy tasks no_log. Never print/share/read credentials for an ordinary status report.

Remote owner marker `/var/lib/personal-compute-v1/owner.json` schema 2 includes cluster ID, role, IP, node name, version, data_root. Do not adopt unowned clusters, delete the marker to bypass checks, silently migrate schema 1 from previous repo, or auto-upgrade. Config and managed service/uninstall hashes prevent overwriting manual changes. Partial setup keeps config for retry.

K3s `v1.36.4+k3s1` and kubectl `v1.36.4` are paired; Ansible core `2.19.3`, controller Python 3.11-3.13. Toolkit new install `1.20.1-1` (existing working runtime retained), device plugin `v0.17.1`, smoke CUDA image `nvcr.io/nvidia/k8s/cuda-sample:nbody` (upstream floating tag), CPU image busybox 1.37.0. Check official docs/release sources before changing versions; runtime compatibility must be live tested. Do not blindly replace pins with latest.

Official K3s generated killall script clears advertised Tailscale routes by default. We replace ONLY that line with no-op and fingerprint the result. Preserve this guard on installer/version updates. Default server API/kubelet bind Tailscale IP; worker API endpoint comes from server receipt. Flannel tailscale0; no network/firewall/SSH/tailnet policy modifications.

GPU: keep a healthy driver. Missing driver -> Ubuntu recommended driver -> intentional error requiring manual device reboot/MOK, then retry. Existing driver package but nvidia-smi failing -> stop, no reinstall. New toolkit adds signed NVIDIA repository. K3s discovers runtime on startup; do not run nvidia-ctk against system containerd/Docker configs. Device plugin gets runtimeClass nvidia and is restricted to explicit GPU node label. Beware NVIDIA runtime/cgroup interactions: avoid unnecessary systemd daemon reloads/restarts on rerun; adding runtime can restart K3s, do not do so during user training without authorization.

Data default `/srv/personal-compute/data/{datasets,checkpoints,results}`. Absolute normalized path outside system/K3s paths; no symlink ancestor. Create missing dirs only, don't chmod/chown existing datasets/files. Workloads pin node and UID/GID of nonroot SSH user, read-only datasets, writable results/checkpoints. No automounted API token, privileged/hostNetwork/hostPID/root mounts. User namespace permits hostPath for these mounts. Image/code/dependencies must already be available; repo does not upload datasets/source or pool RAM/VRAM. Disk-local storage is not backup.

## Using the cluster as an agent

Host must grant local command execution/network access. Windows use `./cluster.ps1` (PowerShell), Linux use `./cluster`. No automatically provided MCP or cloud-local connection. Read `docs/agent-usage.md` and command help. Use status first, then run NAME --image IMAGE [--gpu] -- COMMAND ARGS. Logs/wait/delete-job require an owned Job; timeout keeps it. Submit returns job name; devices execute without host staying online. Do not run check while GPU already occupied without accounting for waiting. Advanced troubleshooting uses `kubectl` subcommand with the repo's isolated context; never override its credentials/endpoint or delete resources without authorization.

Ask for destructive actions only when not authorized; reset requires explicit user intent and confirmation flag. Do not reset to fix image/driver/network errors. Do not install GPU support on an unrequested device, open public ports, replace a working driver, force-add ignored secrets, or use untrusted images against private datasets.

## Validation and honesty

After relevant changes: `python tests/static_check.py`, `python -m unittest discover -s tests -p 'test_*.py'`, `bash -n cluster`, `bash -n scripts/setup-host.sh`. Windows: `pwsh -NoProfile -File tests/test_windows_launcher.ps1` (mocks WSL, no real device). On Linux use `check --static` to additionally run native Ansible syntax; CI has equivalent checks. No SSH/device checks in offline tests.

Real acceptance: follow `docs/acceptance.md`: GPU setup/reboot retry, CPU/network/CUDA tests, second-device worker, repeat idempotence, file persistence after device reboot, host OS switch, explicit reset/rejoin if user wants it. State exactly which native/live checks ran. Do not imply mocked GPU/WSL tests prove live operation. Record material environment limitations in docs/validation.md. Preserve user edits/config/state; use git diff before work. No subagents unless the user explicitly asks for delegation.

Official references: K3s docs (server/agent flags, advanced NVIDIA runtime, uninstall); NVIDIA Container Toolkit install guide; NVIDIA k8s-device-plugin tagged source; Microsoft WSL commands; Ansible controller and SSH connection plugin docs. The current implementation has no live-device credentials in source.
