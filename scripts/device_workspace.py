"""Shared host configuration and separate project-local handoff data."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import uuid
from device_common import DeviceError, atomic_json, clean_text, name, read_json, safe_path

def now():
    return datetime.now(timezone.utc).isoformat()

PROJECT_MARKER = '.n3xus-project.json'

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
    return {**project_info(root,tool_root),'note':'Project ready. Device config remains shared; previous CLI workspace data was not moved.'}

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
