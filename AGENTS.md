# Personal Device CLI — maintenance and agent instructions

Read before editing or submitting work. User authorization takes precedence. The current architecture replaces the old K3s design: native Windows/Ubuntu host, Ubuntu devices, direct Tailscale SSH, no Kubernetes/Ansible/WSL/containers/coordinator/MCP. Do not restore the old architecture. No subagents unless explicitly requested.

## Product and source map

Keep the Vietnamese README short enough for a CS/ML student. Human CLI has colors, tables and a menu. Agent commands use `--json` and never open prompts. Host need not remain online for submitted work. No shared pool of RAM/VRAM, scheduling, HA or backup promised.

- `device`: native Bash launcher; `device.ps1`: native Windows Python launcher. Windows passes argv as a JSON/base64 environment variable to preserve literal quotes, dollar signs and Unicode. No shell eval, WSL, key copies or global execution policy changes.
- `scripts/device_cli.py`: validates ignored `devices.json`, runs native OpenSSH, command routing, confirmation, status concurrency, downloads, HTTP checks. SSH helper source and requests travel as JSON stdin; the remote command is a fixed quoted Python bootstrap, never interpolated user code.
- `scripts/device_common.py`: validation, strict JSON, private atomic writes, safe paths, bounded regular-file archives.
- `scripts/device_remote.py`: short-lived helper over SSH and owned job/service runners. Private state `~/.local/share/personal-device/PROFILE/`. No server daemon listens for CLI commands.
- `scripts/device_ui.py`: standard-library terminal colors/layout; sanitize remote output; JSON mode bypasses presentation. `demo` is explicitly fake data.
- `examples/hello`, `examples/http`: dependency-free real end-to-end examples.
- `tests/`: offline safety/transport tests and Linux isolated runner/tmux integration; Windows launcher tests. CI runs Linux and Windows.

## State and ownership

`devices.json` has schema, a stable 32-hex profile identity, and a devices map (address, nonroot user, port, optional host key PATH and remote conda executable PATH). Ignore user config; never commit keys, passwords, tokens or env secrets. Preserve the profile on host OS changes. SSH key/known_hosts/Tailscale are prepared by the user; StrictHostKeyChecking=yes and BatchMode=yes. Device verifies SSH_CONNECTION destination belongs to Tailscale IPv4 100.64/10. CLI doesn't change network/firewall/SSH policy.

Remote profile uses owner.json, UID and schema checks. Files 0600, directories 0700 when created; no adopting unknown state or bypassing guards. Installed helper hashes protect manual changes. Device metadata belongs to the SSH user, not to a security boundary against that user. Existing legacy devices.yml/.cluster/WSL caches are left alone. Never read old credentials merely to report status.

Code sync excludes common secret/cache/dataset directories, rejects symlinks and path traversal, and uses SHA256 immutable revisions. Exclusions are not a secret detector: inspect the dedicated source directory first. Jobs/services each copy their selected revision to their own workspace. Outputs default to DEVICE_OUTPUT_DIR; datasets/models stay at existing paths. No root, host mounts, driver reinstall or automatic dependencies.

## Running work

Read `docs/agent-usage.md` and help. Use Windows `./device.ps1`, Ubuntu `./device`. Start with status/inspect, then env list/inspect. Check GPU usage before heavy work; --gpu INDEX only sets CUDA_VISIBLE_DEVICES for CUDA software and does not reserve the GPU. All programs run with the full permission of the SSH user: do not run untrusted code. Never put credentials in command argv or logs.

`sync DEVICE DIR --project NAME`, `run DEVICE PROJECT [--env ENV] [--gpu 0] -- PROGRAM ARGS`. No shell interpretation unless the user explicitly asks for a shell program. Read returned ID; logs/wait/fetch refer to it. A wait timeout doesn't stop the job. Device reboot interrupts tmux jobs; read live process/boot identity before claiming completion. Never stop unrelated tmux sessions/processes. Job stops use boot ID + PID start ticks to prevent PID reuse mistakes; force only when normal stop fails and user intent warrants it. Logs rotate at roughly 8MiB ×3, workspaces/results remain until explicit clean. Clean removes only a finished owned job and needs confirmation; fetch first.

Services use systemd --user, exact owned unit names/fingerprints, linger, nonprivileged ports and mandatory {bind}/{port} placeholders. Bind on Tailscale only; no wildcard/public listeners. Start isn't health: run service check and read logs before giving an endpoint. No automatic HTTP authentication/TLS or tailnet access-policy changes. systemd restarts failures and after device reboot. systemd journal retention follows the device configuration. Service remove keeps outputs/receipt; names are not reused. User systemd requires a working user manager (prepare --enable-linger).

## Conda permissions and size

Never install/create/remove packages or envs without user approval. Inspect/reuse first; env plan is read-only with respect to the env but the solver may update conda cache/index. --yes records an already obtained human decision, not agent permission. No auto-install Conda, no base mutation, no auto-delete external envs. Existing non-base env installation is allowed only with approval. Removal only for CLI-created prefixes after exact path ownership validation. Maximum 8 managed envs. A failed create stays registered so partial content can be removed explicitly. Refuse mutation when a managed running job/service uses the env; external processes cannot be detected reliably, ask user about them. Don't silently accept Conda channel terms. Pip dry-run requires a sufficiently recent pip; surface the failure instead of upgrading automatically.

## Maintenance and verification

After edits run `python tests/static_check.py`, `python -m unittest discover -s tests -p 'test_*.py'`, `bash -n device`, and on Windows `pwsh -NoProfile -File tests/test_windows_launcher.ps1`. Linux integration is skipped on Windows; test it natively on Linux. Tests never SSH or change a real device. Record exact results and limitations in docs/validation.md. Do not imply mocks prove actual GPU/Conda/service operation. Real acceptance instructions are in docs/acceptance.md.

Preserve config, personal data, user changes. Git diff before editing; no commit unless requested. No setup/deletion on real devices just to test repository changes without user intent. Install-tools/linger is explicitly requested preparation and confirmed; sudo password is entered only in a terminal, never stored. Dependencies are stdlib Python 3.10+, OpenSSH, remote tmux; systemd-user and conda are optional per feature. Keep scope small.
