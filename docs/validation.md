# Validation — n3xus command rename 2026-10-06

## Kiểm tra đã chạy

Môi trường: Windows, native Python 3.14.7, Windows OpenSSH. Không SSH hoặc thay đổi device để kiểm thử phiên sửa repo này.

- `python tests/static_check.py`: PASS — AST syntax, LF launchers/source, document links, obsolete-source checks, ignored config/workspace, unsafe archive/shell APIs.
- `python -m unittest discover -s tests -p 'test_*.py' -v`: **68 tests: 62 passed, 6 skipped**. New tests cover migration from owned legacy device launchers without duplicate PATH, preservation of unrelated commands, refusal of modified legacy launchers, and owned user launchers, Windows user PATH retention/removal, Bash startup block preservation, refusing manual changes/conflicts, global PowerShell argv from an unrelated directory, setup default/opt-out, and config migration/conflict preservation, separate append-only agent notes, snapshot timestamps/unknown offline counts, workspace transfer refusal, successful submission after local receipt failure, named-job resolution, dated metadata without process replacement, progress validation, one overview RPC/device, dashboard selection/confirmation/cursor restoration/unbuffered POSIX arrow keys, JSON bypass of interactive mode, sanitized output. Existing archive, env ownership/busy/base, PID reuse/reboot, SSH transport and native launcher tests also pass.
- Git Bash `bash -n n3xus`: PASS (syntax only).
- `pwsh -NoProfile -File tests/test_windows_launcher.ps1`: PASS — literal quotes/dollar signs/Unicode and name/description/agent/numeric flags through repo and global launchers on actual Windows PowerShell 5.1 and PowerShell 7 launchers; doctor JSON, terminal demo and dashboard demo. PATH adjustment is scoped to the test process and restored.
- `git diff --check`: PASS.
- Actual Windows `setup --json`: registered user launchers in LocalAppData/PersonalDevice/bin and appended only that directory to HKCU user PATH. Calling `n3xus doctor --json` and dashboard demo from the OS temp directory passed through the real global PowerShell command; n3xus.cmd doctor also passed. No admin/system PATH/execution-policy changes. Linux registry/startup tests are isolated simulations.
- Local `setup --json`: kept the exact existing profile/device registration and moved canonical config to workspace/config/devices.json. No network action.
- Local `communication init/note`: agent folders and a unique shared handoff note created successfully. Human SUMMARY.md retained. Previous local task sources moved into an agent work folder; opaque legacy cache/cluster/devices.yml preserved under workspace/legacy without reading credentials.

Windows sandbox blocked temporary test cleanup/Git Bash startup; tests were run with approved execution outside sandbox. No package installation, helper refresh, job stop/delete, service modification or device reboot was performed. No commit.

## Giới hạn

Six skipped tests: four real Linux runner/tmux integration tests, one real Linux global launcher test, one Windows symlink test because the account lacks symlink privilege. Native Linux execution was not available here. CI is configured for Linux/Windows with Python 3.10/3.14, but CI was not run from this session.

Dashboard keyboard loop/confirmation/restoration was tested with simulated keys; its once/demo layout and native Windows launcher were exercised. Native Ubuntu global command/startup behavior, real interactive dashboard behavior on Ubuntu/Windows, multi-device SSH, current remote GPU/Conda/service operation, reboot and dual-boot acceptance have not been certified by these offline tests. Follow docs/acceptance.md with user authorization. Mock tests are not proof that an LLM endpoint is currently working. Existing remote jobs were left untouched.

## Rename acceptance

Actual Windows setup migrated device.ps1/device.cmd to n3xus.ps1/n3xus.cmd in the same user bin. Legacy files verified absent afterward. Both n3xus doctor (PowerShell) and n3xus.cmd doctor worked from the OS temp directory. Native launcher tests use the new names on PowerShell 5.1/7. The Linux source launcher is renamed n3xus with Git executable bit 100755 (intent-to-add only; no commit). CI syntax command and README/agent examples updated. Internal device protocol/state/profile identifiers were retained; no SSH, helper refresh or remote job changes.
