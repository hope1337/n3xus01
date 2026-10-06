# Validation — redesign 2026-10-06

## Ran on this host

- Windows, native Python 3.14.7 + Windows OpenSSH. No pip dependency/WSL bootstrap.
- `python tests/static_check.py`: Python AST syntax, LF launchers, document links, obsolete implementation removal, ignored config, unsafe archive/shell APIs — PASS.
- `python -m unittest discover -s tests -p 'test_*.py' -v`: recorded final count below. Includes archive/path/secret exclusions, immutable snapshots, env ownership/base/busy/partial-install protection, SSH JSON transport, PID reuse/reboot, terminal colors/layout and native PowerShell argv.
- `pwsh -NoProfile -File tests/test_windows_launcher.ps1`: PASS. Tests actual Windows PowerShell 5.1 and available PowerShell 7 argument transport with a local Python capture helper; no SSH. Doctor JSON and plain terminal demo run through the real launcher.
- Git Bash `bash -n device`: PASS; `git diff --check`: PASS. Launcher executable bit recorded for Linux checkout.

Windows sandbox denied temporary test-file cleanup and Git Bash startup; reran those checks outside sandbox with approved test-only execution. No real device changes.

## Limitations

This host no longer has Ubuntu-24.04 WSL installed (WSL reported distro not found). Native Linux runner/tmux integration tests were skipped here; CI is configured for Ubuntu 24.04 with Python 3.10/3.14 and tmux, but CI has not run from this session. Windows symlink creation test was skipped because the current account lacks that privilege.

No live SSH provisioning, CUDA computation, Conda install/remove, systemd service, reboot or dual-boot acceptance was run. Unit mocks do not prove those behaviors. Follow acceptance.md on an authorized device. The old K3s smoke output does not validate this new implementation.

## Final local test result

37 discovered tests: 32 passed, 5 skipped (4 Linux integration + 1 Windows symlink privilege). Native launcher transport checked on both Windows PowerShell 5.1 and available PowerShell 7.
