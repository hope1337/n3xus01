# Agent CLI usage — use the tool, do not edit it

New agents start at [START_HERE.md](../START_HERE.md). Read AGENTS.md first. A workload request does not authorize CLI repository edits. Source belongs in the human-selected project (src/ or your work folder); scratch/results/notes belong in PROJECT/communication/agents/ID. Shared handoff belongs in PROJECT/communication/shared. The CLI repository stores shared device config only, never new task data.

Use `n3xus` from any directory after user setup. If PATH is stale, use this repo's absolute n3xus.ps1 (Windows) or n3xus (Ubuntu), never assume cwd is the repo. Put --json before the program's -- separator. Responses contain schema/ok/action/data or error. Exit 0 means the operation succeeded, not necessarily that a job finished. Help is text. Never open interactive dashboard/watch/menu from an agent.

## Start a session

The human creates a separate project outside the CLI repo and runs `n3xus project init` once. The marker is discovered from cwd/parents; explicit --project-dir selects an initialized root. If no project is resolved, report the missing context instead of creating one in arbitrary cwd. Project init preserves existing files/identity and appends /communication/ to .gitignore. Read the current project's SUMMARY.md/notes, not the CLI repo's legacy workspace handoff. Commands below assume cwd is in the selected project; append --project-dir PATH when elsewhere.

```text
n3xus project show --json
n3xus communication init codex-20261006-a1 --json
n3xus communication show --json
n3xus status --json
n3xus dashboard --once --json
n3xus inspect DEVICE --json
n3xus env list DEVICE --json
n3xus env inspect DEVICE ENV --json
```

Use a fresh session ID; do not write into earlier agents' folders. Recheck saved handoff/snapshots against live state. Only registered devices appear; the CLI does not scan the tailnet and adopt unknown machines. Never read keys/passwords/legacy kubeconfig for status.

## Submit understandable work

Write code in your work/TASK folder; inspect secrets and dependencies. Do not modify examples/scripts to create workloads. Give jobs a meaningful name and one-sentence purpose. Supplying --agent requires --name and --description.

Relative source/output/message-file paths resolve from the project root, even from nested directories or with explicit --project-dir. Paths must stay inside that project. Replace DEVICE/ENV/JOB_ID and the illustrative agent ID:

```text
n3xus sync DEVICE communication/agents/codex-20261006-a1/work/pdf-extract --project my-project-pdf --json
n3xus run DEVICE my-project-pdf --name extract-pdfs --description "Extract PDF text" --agent codex-20261006-a1 --env ENV --json -- python -u main.py
n3xus job DEVICE extract-pdfs --json
n3xus logs DEVICE extract-pdfs --json
```

Keep the returned ID. Names must be unique among active jobs on a device; duplicate historical names require the ID. jobs defaults to active jobs across devices; jobs --all includes history. Sync creates immutable revisions; each job takes its own workspace copy. Do not change another running job's code.

```text
n3xus job-note DEVICE JOB_ID --summary "Logs confirm 40 of 100 files processed" --phase extracting --progress 40 --agent codex-20261006-a1 --json
```

Summary/phase/progress are your reports with note_author/note_updated_at. Do not infer percentages from elapsed time. State/observed_at are checked live. A running process may be waiting; make a real API request before claiming readiness. Rename/describe legacy jobs via job-note without restarting them.

Wait/logs/fetch/stop/clean accept ID or unambiguous name. --follow is terminal-only; agents read log snapshots. Wait timeout leaves jobs running. Fetch defaults to DEVICE_OUTPUT_DIR; --path is a relative directory inside the job workspace. Fetch refuses overwrite, max 64 MiB. Never auto-clean history/results: require user intent and confirmation, and fetch first.

`fetch DEVICE JOB_ID --agent ID --json` downloads to PROJECT/communication/agents/ID/downloads/DEVICE-JOB_ID. Explicit --output must be inside the project and should point to your own downloads folder. Run/serve save local receipts under communication/runs; a receipt failure after successful submission is a warning, never retry the job blindly. The remote project label (sync --project / run PROJECT) is distinct from the local --project-dir: use a meaningful label unique across projects sharing this device profile. Existing remote jobs/revisions are not renamed/migrated.

## Dependencies and privileges

Inspect Conda before changing it. `env plan DEVICE ENV --package pypdf --pip --json` does not install into the env, but the solver can update its cache. Ask before install/create/remove; use --yes only after approval. Do not change base/driver, silently accept channel terms or automatically upgrade pip. Check with the user whether external notebooks use the env; the CLI only detects its managed jobs/services.

--gpu INDEX selects CUDA_VISIBLE_DEVICES, not a reservation. Inspect GPU use and never stop unrelated training. No public listeners. prepare --install-tools/--enable-linger may require a sudo password in a terminal; chat approval does not supply it. Report the blocked step; do not skip it and claim success.

For every sudo blocker, tell the human: device and SSH user; exact proposed commands/operation; reason for root; expected changes; blocked task step; and the terminal action needed to authorize/authenticate or perform it. Do not run it before the necessary approval/authentication is available. Continue independent authorized steps, but keep dependent work pending. Do not abandon the objective or mark it complete. When the human confirms they handled it, inspect the actual result, then resume the original task. If waiting outlasts the session, write a project handoff with completed work, the blocker and the next action. Do not ask for a password in chat or save one; a chat "yes" cannot authenticate sudo.

## Handoff

```text
n3xus communication note codex-20261006-a1 --title "PDF extraction handoff" --message-file communication/agents/codex-20261006-a1/work/handoff.txt --device DEVICE --job JOB_ID --json
n3xus communication snapshot --json
```

Include objective, device/project/job ID, observation time, result location, evidence, approvals, remaining work and next action. Unique note files prevent overwrites. Project snapshots list only jobs with this project's local receipts; device metrics/counts and jobs/dashboard remain global. Legacy jobs without receipts require an explicit relevant handoff note; never silently adopt them. Snapshots are historical. shared/SUMMARY.md is durable context; preserve others' content. Never store secrets or force-add communication data to Git. Old CLI workspace data is left untouched; do not read/migrate it unless requested.

Optional systemd services: serve requires linger and {bind}/{port}; logs DEVICE NAME --service reads journal logs. service check from the host must succeed. Do not patch source/helpers to bypass guards. Read-only SSH diagnostics are allowed when needed; mutations outside the CLI require user intent and documentation. Do not create a parallel manager with manual tmux jobs and claim they are managed.

Host offline: jobs continue subject to login policy, but the agent stops thinking. Device reboot interrupts tmux jobs; systemd services may restart. After a mutation timeout, inspect before retrying to avoid duplicates.

User setup installs host launchers/PATH without SSH. Do not unregister or change the global checkout for workloads. Config/profile and registration receipts remain shared in CLI workspace/config; projects never re-register devices. Status/inspect/jobs/env reads need no project. setup --no-register is available for hosts that do not want PATH changes. Report in Vietnamese unless requested otherwise.
