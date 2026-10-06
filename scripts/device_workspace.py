"""Host-local runtime and handoff data. Never upload the entire workspace."""
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from device_common import DeviceError, atomic_json, clean_text, name, read_json, safe_path

def now():
    return datetime.now(timezone.utc).isoformat()

def initialize(root):
    root = safe_path(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    for part in ('config', 'runs', 'communication', 'communication/shared', 'communication/shared/notes', 'communication/agents'):
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

def receipt(root, device, record):
    root = initialize(root)
    identifier = name(record['id'])
    atomic_json(root/'runs'/f'{name(device)}-{identifier}.json', {'device':device, **record, 'submitted_at':now()})
