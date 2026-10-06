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

## Agent onboarding document — 2026-10-06

Added START_HERE.md as a single reusable entry point, linking AGENTS.md, agent usage, workspace layout and local shared handoff. README contains the short onboarding prompt. Existing use-only rules explicitly protect the onboarding file. Directly checked all onboarding document links and ran static_check.py plus git diff --check. Documentation-only change: unit/launcher/device tests were not rerun; the 68-test result above belongs to the previous code revision. No SSH, remote job changes or commit.

## English agent documentation — 2026-10-06

Translated START_HERE.md, docs/agent-usage.md and docs/architecture.md into English, preserving permissions, storage, approval and execution rules. AGENTS.md was already English. Human README/workspace guide remain Vietnamese; the user-facing response language remains Vietnamese. Document links, static_check.py and git diff --check passed. Documentation-only: no unit/launcher tests rerun, no SSH or device changes. No tokenizer-specific percentage reduction claimed for these files.

## Resource table — 2026-10-06

Status and dashboard (once/live) share a resource formatter: CPU logical threads, available/total RAM and free/total VRAM in GiB, with one row per GPU. Existing probe fields are reused; JSON schema and remote helper are unchanged. CPU is a thread count, not utilization. Unknown values are not reported as zero.

Checks: static_check.py PASS; unittest discovery 68 tests (62 passed, 6 skipped as described above); Git Bash `bash -n n3xus` PASS; native Windows launcher script PASS on PowerShell 5.1/7; git diff --check PASS. Offline status/dashboard demos passed. Manual offline fixtures checked multiple GPUs, zero/missing memory, offline/CPU-only devices and table widths of 48/110/150 columns. No new test files were needed for this presentation change. No SSH, remote helper updates, device changes or live GPU measurement; native Linux checks remain unverified here.

## Progressive terminal feedback — 2026-10-06

Human terminal status/jobs/dashboard publishes devices as responses arrive. Read-only probe/overview streams CPU/RAM before GPU/Conda/linger; overview keeps job-list placeholders until job information arrives. Inspect uses the same probe stages. Other SSH operations and HTTP health checks show a waiting spinner; wait displays the latest observed job between polls. Loading placeholders are temporary, not offline or zero metrics. JSON and redirected output retain complete responses without terminal animation. Confirmation/sudo prompts are not animated. Progress threads and local SSH pipe readers are temporary and cleaned up; no new server, dependency, helper installation or remote state mutation.

Checks: `python tests/static_check.py` PASS; unittest discovery **74 tests: 68 passed, 6 skipped** (same platform limitations above); Git Bash `bash -n n3xus` PASS; native Windows launcher script PASS on PowerShell 5.1/7; `git diff --check` PASS. Six new offline tests cover progress arriving before the final response, draining large stderr without pipe deadlock, timeout while stdin is blocked and child cleanup, malformed/missing final responses, fast-device/CPU results while another device waits, final config order, JSON isolation, loading placeholders and exception cleanup. Child processes are local Python programs, not SSH. No live device requests or GPU/Conda/service changes were performed. Actual terminal animation and streamed probes over real Tailscale SSH on Windows/Ubuntu remain acceptance checks; Linux integration tests remain skipped here.

## Dashboard refresh correction — 2026-10-06

Fixed generic progress being appended below the interactive dashboard. Refresh now uses the dashboard's full-screen renderer and retains previously observed fields/job lists only while their new response is pending, with an explicit refreshing banner. Fresh fields replace old values; final errors discard cached resources/jobs. Cached data does not become a CLI JSON result or an action target during refresh.

Checks: static_check.py PASS; unittest discovery **76 tests: 70 passed, 6 skipped**; Git Bash launcher syntax PASS; native Windows PowerShell 5.1/7 launcher checks PASS; git diff --check PASS. Two added offline tests cover pending GPU/job retention alongside fresh RAM, cache removal on final errors, no input snapshot mutation, and two dashboard polling cycles that replace the same screen without the generic loading table, retaining selection/job display and restoring the terminal. These use simulated snapshots/terminal keys, not real SSH or visual acceptance on a physical terminal. No device/helper/job changes, package installation or commit.

## Independent workload projects — 2026-10-06

Shared device/profile/launcher configuration stays in CLI workspace/config. Setup no longer creates task communication/runs. Added project init/show and --project-dir; nearest ancestor project markers identify local workload roots outside the CLI repo. Communication, agent scratch/downloads and job/service receipts go to the selected project's communication folder. Relative source/output/message-file paths resolve from that root and cannot escape it; project-writing commands require context before remote work. Fetch defaults to agent downloads, or human. Project snapshots filter job rows by local receipts while global device resources/counts remain explicitly labelled. Remote labels/profiles/jobs, existing user config and legacy workspace data are not renamed, moved or deleted. Updated README, onboarding/rules, agent/storage/architecture guides and acceptance instructions.

Checks: `python tests/static_check.py` PASS; unittest discovery **85 tests: 79 passed, 6 skipped**; Git Bash `bash -n n3xus` PASS; native Windows launcher script PASS (PowerShell 5.1/7); git diff --check PASS. Nine added offline tests cover two-project note isolation, nested discovery/explicit override, stable marker and ignore-file preservation, refusal of missing/tool-repo/invalid contexts before remote submission, path escapes/literal program flags, project-only snapshots/receipts, real archive extraction into default agent downloads and overwrite refusal, project-independent global setup/status, and receipt routing after submission. Updated receipt-failure regression to select a real isolated project before simulating disk failure.

Tests use isolated temporary folders and mocked SSH responses; no real project was initialized, no existing user communication was migrated, no actual device requests/helper refresh/job stops/service/package changes or commit. Native Linux integration remains skipped on this Windows host. Live multi-project workload acceptance on devices is not claimed by these offline results.

## Project discussion overview — 2026-10-06

Added docs/PROJECT_OVERVIEW.md as a Vietnamese, standalone discussion brief covering user needs, current architecture, independent projects, CLI/agent workflows, boundaries, source map, historical validation and open design questions. Historical device/LLM observations are explicitly not live state; suggestions are not approved implementation plans. static_check.py and git diff --check PASS. Documentation-only: unit/launcher tests were not rerun; the 85-test result above belongs to the preceding code validation. No SSH, device changes or commit.

## Sudo blocker workflow and used/total display — 2026-10-06

Expanded AGENTS.md, START_HERE.md, agent guide, README and project overview: agents must identify the device/user, exact privileged operation/commands, reason, expected changes, blocked step and terminal action; pause dependent work while continuing independent authorized work, preserve the task/handoff, verify and resume after the blocker is handled. Chat approval is not sudo authentication. No new privilege mechanism was implemented.

Human status/dashboard/inspect now show RAM/VRAM used/total in GiB: RAM total minus available, GPU total minus free. Missing/inconsistent metrics remain unknown, never fabricated as zero. JSON/probe fields remain unchanged. Updated the existing refresh regression expectation to used RAM; historical validation sections above retain their original metric descriptions.

Checks: static_check.py PASS; unittest discovery **85 tests: 79 passed, 6 skipped**; Git Bash syntax PASS; native Windows PowerShell 5.1/7 launcher/demo checks PASS; git diff --check PASS. Manual offline checks verified subtraction, full/empty GPU, unknown/invalid inputs and inspect formatting. No new tests needed for the reversible presentation change. No SSH, sudo/device configuration, helper refresh or job changes. Native Linux/live-device acceptance remains unverified here.

## Project-local guide onboarding — 2026-10-06

Project init copies Markdown onboarding/rules/usage/reference docs into communication/guides/n3xus, preserving relative links, with a generated GUIDE_INDEX.md. Project-root AGENTS.md gains one managed onboarding block while preserving user-authored instructions. A per-file SHA256 manifest protects manual guide changes/unowned conflicts on re-init; no CLI code, config, credentials or task state is copied. Existing projects gain guides by re-running init. Guide snapshots are protected usage docs, not permission to maintain the tool or proof of live state. Automatic discovery requires an agent that reads project-root AGENTS.md.

Checks: static_check.py and git diff --check PASS; unittest discovery **87 tests: 81 passed, 6 skipped**; Git Bash syntax PASS; Windows launcher checks PASS on PowerShell 5.1/7. Two added offline tests check guide-copy/link integrity, idempotent onboarding with existing project rules, exclusion of config, modified-guide preservation and unowned-folder refusal. No real project/device initialization or SSH, no commit/push. Platform acceptance limitations above remain.

## Context recovery rules — 2026-10-06

Added explicit recovery requirements to AGENTS.md, START_HERE.md and docs/agent-usage.md: re-read project instructions, linked rules/usage and relevant handoff after compaction/restoration/project switches or uncertain memory; resolve project identity, recover objective/IDs/approval scope and verify relevant live state before remote work. Preserve the session ID across compaction, inspect uncertain submissions before retrying, and re-check applicable rules/authorization before sensitive actions without re-requesting valid approvals. Missing instructions block dependent actions; summaries cannot broaden permission. Existing projects refresh unchanged guide snapshots via human-run project init. These are behavioral instructions, not an automatic compaction hook or enforcement guarantee.

Documentation-only checks: `python tests/static_check.py` PASS; `git diff --check` PASS. Unit/launcher tests were not rerun; the 87-test result above is from the preceding implementation. No CLI code changes, real project initialization, SSH/device/job changes or commit/push.
