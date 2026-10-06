"""Shared host configuration and separate project-local handoff data."""
from datetime import datetime, timezone
import json
import hashlib
import re
from pathlib import Path
import uuid
from device_common import DeviceError, atomic_json, clean_text, name, read_json, safe_path

def now():
    return datetime.now(timezone.utc).isoformat()

PROJECT_MARKER = '.n3xus-project.json'
GUIDE_BLOCK = '''<!-- n3xus:agent-guide:start -->
## n3xus device tools and project handoff

Before using devices, read [the guide index](communication/guides/n3xus/GUIDE_INDEX.md)
and its onboarding/rules/CLI guide. They are local documentation snapshots,
not workload source or authorization to edit the n3xus tool.
Read this project's communication/shared/SUMMARY.md and communication show --json,
then verify live state before resuming work. Keep agent data in your own
communication/agents/ID folder. Human authorization takes precedence.
<!-- n3xus:agent-guide:end -->
'''

def install_guides(root,tool_root):
    """Refresh owned snapshots only; preserve project-authored instructions."""
    tool_root=Path(tool_root)
    destination=safe_path(root/'communication/guides/n3xus')
    manifest=safe_path(destination/'manifest.json')
    instructions=safe_path(root/'AGENTS.md')
    original=instructions.read_text(encoding='utf-8') if instructions.exists() else ''
    if 'n3xus:agent-guide:' in original and (original.count(GUIDE_BLOCK)!=1 or original.count('n3xus:agent-guide:start')!=1 or original.count('n3xus:agent-guide:end')!=1):
        raise DeviceError('Project AGENTS.md n3xus block was modified. Preserve/reconcile it manually.','guide_modified')
    sources=['AGENTS.md','START_HERE.md','README.md','workspace/README.md']+[f'docs/{p.name}' for p in sorted((tool_root/'docs').glob('*.md'))]
    payload={relative:safe_path(tool_root/relative).read_bytes() for relative in sources}
    payload['GUIDE_INDEX.md']=('''# Project-local n3xus guides

These copies are installed by n3xus project init. This folder is documentation,
not the CLI checkout. References to the tool repository in the rules mean the
original installed n3xus checkout, not your workload project. Existing project
instructions also apply; human authorization takes precedence.

Read in order:
1. [START_HERE.md](START_HERE.md): onboarding, project context and handoff.
2. [AGENTS.md](AGENTS.md): permissions, sudo blockers and storage rules.
3. [Agent usage](docs/agent-usage.md): command workflow and examples.
4. [Storage layout](workspace/README.md): shared config versus project data.

References: [human README](README.md), [architecture](docs/architecture.md),
[project overview](docs/PROJECT_OVERVIEW.md), [troubleshooting](docs/troubleshooting.md),
[safety](docs/safety.md), [acceptance](docs/acceptance.md), [validation](docs/validation.md).

Project code belongs outside this guide folder. Shared task context is in
communication/shared relative to the PROJECT root, not relative to this guide.
Notes/validation are historical; use CLI JSON to inspect actual devices/jobs.
Run project init again after updating n3xus to refresh unchanged copies. Modified
copies are preserved and cause an error rather than being overwritten.
Agents must not edit these copies unless the human explicitly requests it.
CLI behavior is determined by the installed tool, not by this snapshot.
''').encode('utf-8')
    old={}
    if manifest.exists():
        metadata=read_json(manifest)
        if not isinstance(metadata,dict) or metadata.get('schema')!=1 or not isinstance(metadata.get('files'),dict):
            raise DeviceError('Invalid guide manifest. Refusing overwrite.','guide_modified')
        old=metadata['files']
    elif destination.exists() and any(destination.iterdir()):
        raise DeviceError('Guide folder has unowned files. Refusing to adopt it.','guide_modified')
    # Verify every old owned file, including docs removed from newer versions.
    for relative,digest in old.items():
        from device_common import relative_path
        relative_path(relative)
        target=safe_path(destination/relative)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
            raise DeviceError(f'Guide {relative} was modified; it was not overwritten.','guide_modified')
    for relative in payload:
        target=safe_path(destination/relative)
        if target.exists() and relative not in old:
            raise DeviceError(f'Unowned guide {relative}; refusing overwrite.','guide_modified')
    for relative,content in payload.items():
        target=safe_path(destination/relative)
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        temporary=safe_path(target.with_name(target.name+'.tmp-'+uuid.uuid4().hex))
        temporary.write_bytes(content); temporary.chmod(0o600); temporary.replace(target)
    atomic_json(manifest,{'schema':1,'tool_repo':str(tool_root.resolve()),'copied_at':now(),
                          'files':{**old,**{key:hashlib.sha256(value).hexdigest() for key,value in payload.items()}}})
    if GUIDE_BLOCK not in original:
        with instructions.open('a',encoding='utf-8',newline='\n') as handle:
            handle.write(('\n\n' if original else '# Project agent instructions\n\n')+GUIDE_BLOCK)
    return {'agent_instructions':str(instructions),'guides':str(destination)}

def initialize_host(root):
    root=safe_path(root)
    safe_path(root/'config').mkdir(parents=True,exist_ok=True,mode=0o700)
    return root

def validate_project(root, tool_root):
    root=safe_path(root).resolve()
    tool_root=Path(tool_root).resolve()
    if root==tool_root or root.is_relative_to(tool_root):
        raise DeviceError('Use a separate project folder outside the n3xus repository.','project_in_tool')
    if not root.is_dir():
        raise DeviceError('Project directory must already exist. Create your project folder first.','project_required')
    return root

def project_info(root, tool_root):
    root=validate_project(root,tool_root)
    marker=safe_path(root/PROJECT_MARKER)
    if not marker.exists():
        raise DeviceError('No project initialized here. Run n3xus project init in your project folder.','project_required')
    data=read_json(marker)
    if not isinstance(data,dict) or set(data)!={'schema','project_id'} or type(data['schema']) is not int or data['schema']!=1 or not isinstance(data['project_id'],str) or not re.fullmatch('[a-f0-9]{32}',data['project_id']):
        raise DeviceError('Invalid project marker; refusing to overwrite it.','invalid_project')
    return {'project_dir':str(root),'project_id':data['project_id'],'communication':str(root/'communication')}

def find_project(explicit, tool_root):
    start=safe_path(Path(explicit).expanduser() if explicit else Path.cwd())
    if explicit:
        return Path(project_info(start,tool_root)['project_dir'])
    validate_project(start,tool_root)
    for root in (start,*start.parents):
        if (root/PROJECT_MARKER).exists() or (root/PROJECT_MARKER).is_symlink():
            return Path(project_info(root,tool_root)['project_dir'])
    raise DeviceError('No project found. Run n3xus project init in your project folder, or supply --project-dir PATH.','project_required')

def init_project(explicit,tool_root):
    root=validate_project(Path(explicit).expanduser() if explicit else Path.cwd(),tool_root)
    marker=safe_path(root/PROJECT_MARKER)
    ignore=safe_path(root/'.gitignore')
    content=ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    if marker.exists():
        project_info(root,tool_root)
    else:
        # Exclusive creation preserves identity if two agents initialize together.
        try:
            with marker.open('x',encoding='utf-8',newline='\n') as handle:
                marker.chmod(0o600)
                json.dump({'schema':1,'project_id':uuid.uuid4().hex},handle,indent=2)
                handle.write('\n')
        except FileExistsError:
            project_info(root,tool_root)
    initialize(root)
    if '/communication/' not in content.splitlines():
        with ignore.open('a',encoding='utf-8',newline='\n') as handle:
            handle.write(('\n' if content and not content.endswith('\n') else '')+'/communication/\n')
    guides=install_guides(root,tool_root)
    return {**project_info(root,tool_root),**guides,'note':'Project ready. Root AGENTS.md links local guide copies. Shared config and previous data were not moved.'}

def project_path(root,value):
    path=Path(value).expanduser()
    path=safe_path(path if path.is_absolute() else root/path).resolve()
    if not path.is_relative_to(root):
        raise DeviceError('Workload paths must stay inside the selected project.','outside_project')
    return path

def initialize(root):
    root = safe_path(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    for part in ('communication', 'communication/runs', 'communication/shared', 'communication/shared/notes', 'communication/agents'):
        safe_path(root / part).mkdir(parents=True, exist_ok=True, mode=0o700)
    summary = safe_path(root / 'communication/shared/SUMMARY.md')
    if not summary.exists():
        summary.write_text('# Shared handoff\n\nRead notes and STATUS.md before starting. This file is for durable human context; live device state is read via CLI. Never store secrets here.\n', encoding='utf-8')
        summary.chmod(0o600)
    return root

def agent(root, identity):
    identity = name(identity)
    root = initialize(root)
    directory = safe_path(root / 'communication/agents' / identity)
    directory.mkdir(exist_ok=True,mode=0o700)
    for part in ('work', 'downloads', 'notes'):
        safe_path(directory / part).mkdir(parents=True, exist_ok=True, mode=0o700)
    return {'agent':identity, 'directory':str(directory), 'work':str(directory/'work'), 'downloads':str(directory/'downloads'), 'notes':str(directory/'notes')}

def note(root, identity, title, message, device=None, job=None):
    directory = Path(agent(root, identity)['directory'])
    clean_text(title)
    if not title or len(title) > 160 or not isinstance(message, str) or not message.strip() or len(message) > 16000 or '\0' in message:
        raise DeviceError('Provide a title (max 160 chars) and message (max 16000 chars).')
    if device: name(device)
    if job: clean_text(job)
    record = {'id':uuid.uuid4().hex, 'agent':identity, 'title':title, 'message':message, 'device':device, 'job':job, 'updated_at':now()}
    # Unique filenames prevent agents from overwriting one another's notes.
    filename = record['id'] + '.json'
    atomic_json(directory / 'notes' / filename, record)
    atomic_json(root / 'communication/shared/notes' / filename, record)
    return record

def show(root, identity=None):
    root = initialize(root)
    directory = root / 'communication/shared/notes'
    if identity:
        directory = root / 'communication/agents' / name(identity) / 'notes'
    records = [read_json(safe_path(p)) for p in directory.glob('*.json')]
    records.sort(key=lambda r:r['updated_at'], reverse=True)
    summary = read_json(root/'communication/shared/snapshot.json') if (root/'communication/shared/snapshot.json').exists() else None
    return {'notes':records[:100], 'snapshot':summary, 'summary':(root/'communication/shared/SUMMARY.md').read_text(encoding='utf-8'), 'warning':'Saved snapshot/notes are historical. Use dashboard --once for live state.'}

def snapshot(root, data):
    root = initialize(root)
    destination = safe_path(root/'communication/shared')
    atomic_json(destination/'snapshot.json', data)
    lines = ['# Last observed device status', '', 'Observed: ' + data['observed_at'], '', 'This is a snapshot, not a live monitor. Run dashboard --once to refresh.', '']
    if data.get('scope'):
        lines.extend(['Scope: '+data['scope'],'Project: '+data['project_dir'],''])
    for device in data['devices']:
        lines.append(f"- {device['name']}: {'online' if device.get('online') else 'offline'}; jobs: {device.get('active_jobs', 'unknown')}")
    for job in data['jobs']:
        description = str(job.get('summary') or job.get('description') or 'No description').replace('\n',' ')
        lines.append(f"- {job['device']} / {job.get('name',job['id'])} [{job['state']}]: {description}")
    status = safe_path(destination/'STATUS.md')
    temporary = safe_path(destination/('STATUS.tmp-'+uuid.uuid4().hex))
    temporary.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(status)
    return {'snapshot':str(destination/'snapshot.json'), 'status':str(status), 'observed_at':data['observed_at']}

def receipt(root, device, record, kind='job'):
    root = initialize(root)
    identifier = name(record['id'] if kind=='job' else record['name'])
    atomic_json(root/'communication/runs'/f'{kind}-{name(device)}-{identifier}.json', {'device':device, **record, 'kind':kind, 'submitted_at':now()})

def project_snapshot(root,data):
    directory=safe_path(root/'communication/runs')
    owned=set()
    if directory.exists():
        for path in directory.glob('job-*.json'):
            record=read_json(safe_path(path))
            owned.add((record['device'],record['id']))
    return snapshot(root,{**data,'jobs':[r for r in data['jobs'] if (r['device'],r['id']) in owned],
                          'scope':'project receipts; device resource/count data is global','project_dir':str(root)})
