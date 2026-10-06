"""Runs over SSH, or as one owned task/service runner. No listening daemon."""
from __future__ import annotations
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from device_common import DeviceError, OWNER, SCHEMA, MAX_ARCHIVE, archive_payload, atomic_json, clean_text, name, pack_directory, read_json, relative_path, safe_path, unpack

BASE = Path.home() / '.local/share/personal-device'
LOG_LIMIT = 8 * 1024 * 1024

def now():
    return datetime.now(timezone.utc).isoformat()

def command(argv, *, timeout=30, check=True, cwd=None):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceError(f'{Path(str(argv[0])).name}: {exc}') from exc
    if check and result.returncode:
        raise DeviceError(f"{Path(str(argv[0])).name} failed ({result.returncode}): {(result.stderr or result.stdout)[-4000:]}")
    return result

def root_for(request):
    profile = request.get('profile', '')
    if not re.fullmatch(r'[a-f0-9]{32}', profile):
        raise DeviceError('Invalid profile identity.', 'invalid_config')
    return safe_path(BASE / profile)

def require_owned(root):
    owner = read_json(root / 'owner.json')
    if owner != {'owner': OWNER, 'schema': SCHEMA, 'profile': root.name, 'uid': os.getuid()}:
        raise DeviceError('Remote state belongs to another profile/version/user. Refusing adoption.', 'not_owned')

@contextmanager
def locked(root):
    import fcntl
    require_owned(root)
    path = safe_path(root / 'state.lock')
    with path.open('a') as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield

def boot_id():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        return ''

def pid_start(pid):
    try:
        # comm may contain spaces or ')'; fields after the last ')' start at #3.
        return Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, ValueError, IndexError):
        return None

def alive(record):
    return record.get('boot_id') == boot_id() and record.get('pid_start') is not None and pid_start(record.get('pid', 0)) == record['pid_start']

def tailnet_ip():
    fields = os.environ.get('SSH_CONNECTION', '').split()
    if len(fields) != 4:
        raise DeviceError('Run through SSH to a Tailscale address.', 'not_tailnet')
    address = ipaddress.ip_address(fields[2])
    if address.version != 4 or address not in ipaddress.ip_network('100.64.0.0/10'):
        raise DeviceError('SSH destination is not a Tailscale IPv4; use its tailnet IP.', 'not_tailnet')
    return str(address)

def find_conda(request):
    explicit = request.get('conda')
    if explicit:
        clean_text(explicit)
        if not explicit.startswith('/'):
            raise DeviceError('Conda path must be absolute on the device.')
        candidates = [explicit]
    else:
        candidates = [shutil.which('conda')]
        for directory in ('miniconda3', 'anaconda3', 'miniforge3', 'mambaforge'):
            candidates.append(str(Path.home() / directory / 'bin/conda'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).absolute())
    raise DeviceError('Conda not found. Register with --conda /absolute/path/to/bin/conda; CLI does not install conda.', 'conda_missing')

def conda_json(request, arguments, timeout=60):
    result = command([find_conda(request), *arguments, '--json'], timeout=timeout)
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise DeviceError('Conda did not return JSON; inspect its configuration/output.') from exc

def probe(request):
    if sys.version_info < (3, 10) or sys.platform != 'linux':
        raise DeviceError('Device needs Linux with Python 3.10+ (Ubuntu 22.04 or newer).', 'unsupported_device')
    address = tailnet_ip()
    root = root_for(request)
    prepared = (root / 'owner.json').exists()
    if prepared:
        require_owned(root)
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, rest = line.split(':', 1)
        memory[key] = int(rest.split()[0]) / 1024 ** 2
    os_release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            os_release[key] = value.strip('"')
    gpus = []
    warnings = []
    if shutil.which('nvidia-smi'):
        gpu = command(['nvidia-smi', '--query-gpu=name,memory.total,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], check=False, timeout=10)
        if gpu.returncode == 0:
            for line in gpu.stdout.splitlines():
                parts = line.split(',')
                if len(parts) == 4:
                    try:
                        gpus.append({'name': parts[0].strip(), 'total_mib': int(parts[1]), 'free_mib': int(parts[2]), 'utilization': int(parts[3])})
                    except ValueError:
                        warnings.append('GPU metrics unavailable for one device.')
        else:
            warnings.append('nvidia-smi failed; driver is left unchanged.')
    try:
        conda = find_conda(request)
    except DeviceError:
        conda = None
    linger = command(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value'], check=False).stdout.strip() if shutil.which('loginctl') else 'unknown'
    tmux = bool(shutil.which('tmux'))
    if linger != 'yes':
        warnings.append('Linger is not enabled. Services need it for boot/after logout; job survival also depends on login policy.')
    return {'online': True, 'prepared': prepared, 'ready': prepared and tmux, 'hostname': socket.gethostname(), 'tailscale_ip': address,
            'os': os_release.get('PRETTY_NAME', 'Linux'), 'python': platform.python_version(), 'cpu_count': os.cpu_count(),
            'memory_total_gib': round(memory.get('MemTotal', 0), 2), 'memory_available_gib': round(memory.get('MemAvailable', 0), 2),
            'disk_free_gib': round(shutil.disk_usage(Path.home()).free / 1024 ** 3, 2), 'gpus': gpus, 'conda': conda,
            'tmux': tmux, 'linger': linger, 'state_directory': str(root), 'warnings': warnings}

def prepare(request):
    info = probe(request)
    root = root_for(request)
    if os.getuid() == 0:
        raise DeviceError('Use a non-root SSH user.', 'root_refused')
    if root.exists() and not (root / 'owner.json').exists():
        raise DeviceError('State directory already exists without an owner marker. Refusing overwrite.', 'not_owned')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(root / 'owner.json', {'owner': OWNER, 'schema': SCHEMA, 'profile': root.name, 'uid': os.getuid()})
    with locked(root):
        old = read_json(root / 'helper-hashes.json') if (root / 'helper-hashes.json').exists() else {}
        hashes = {}
        for filename, content in (('device_common.py', request['_common_source']), ('device_remote.py', request['_helper_source'])):
            target = safe_path(root / filename)
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != old.get(filename):
                raise DeviceError('Installed helper was modified. Refusing overwrite.', 'not_owned')
            temporary = root / (filename + '.new')
            safe_path(temporary).write_text(content, encoding='utf-8', newline='\n')
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            hashes[filename] = hashlib.sha256(target.read_bytes()).hexdigest()
        atomic_json(root / 'helper-hashes.json', hashes)
        for directory in ('projects', 'jobs', 'services', 'envs'):
            safe_path(root / directory).mkdir(exist_ok=True, mode=0o700)
        if not (root / 'envs.json').exists():
            atomic_json(root / 'envs.json', {})
    info.update(prepared=True, ready=info['tmux'])
    return info

def sync_project(request):
    root = root_for(request)
    project = name(request['project'])
    raw = base64.b64decode(request['archive'], validate=True)
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != request['sha256']:
        raise DeviceError('Archive checksum mismatch.', 'unsafe_archive')
    revision = checksum[:24]
    with locked(root):
        project_root = safe_path(root / 'projects' / project)
        project_root.mkdir(exist_ok=True, mode=0o700)
        destination = project_root / revision
        if destination.exists():
            receipt = read_json(destination / '.device-revision.json')
            if receipt != {'sha256': checksum, 'owner': OWNER}:
                raise DeviceError('Revision is not owned.', 'not_owned')
        else:
            temporary = project_root / ('upload-' + uuid.uuid4().hex)
            try:
                unpack(raw, temporary)
                if (temporary / '.device-revision.json').exists():
                    raise DeviceError('Reserved metadata filename in source.', 'unsafe_archive')
                atomic_json(temporary / '.device-revision.json', {'sha256': checksum, 'owner': OWNER})
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    shutil.rmtree(safe_path(temporary))
        atomic_json(project_root / 'current.json', {'revision': revision, 'path': str(destination), 'updated_at': now()})
    return {'project': project, 'revision': revision, 'path': str(destination), 'bytes': len(raw)}

def project_snapshot(root, project, destination):
    current = read_json(root / 'projects' / name(project) / 'current.json')
    revision = current['revision']
    if not re.fullmatch(r'[a-f0-9]{24}', revision):
        raise DeviceError('Invalid project revision.', 'invalid_metadata')
    source = safe_path(root / 'projects' / project / revision)
    # Never share a writable working directory between jobs or with later syncs.
    unpack(pack_directory(source, exclusions=False), destination)
    return revision

def env_list(request):
    root = root_for(request)
    require_owned(root)
    info = conda_json(request, ['info', '--envs'])
    managed = read_json(root / 'envs.json')
    paths = list(dict.fromkeys(info.get('envs', []) + list(managed.values())))
    return {'envs': [{'name': 'base' if path == info.get('root_prefix') else Path(path).name, 'path': path, 'managed': path in managed.values()} for path in paths]}

def resolve_env(request, value):
    if not value:
        return None
    clean_text(value)
    envs = env_list(request)['envs']
    matches = [entry for entry in envs if value in (entry['name'], entry['path'])]
    if len(matches) != 1 or not Path(matches[0]['path']).is_dir():
        raise DeviceError('Env missing or ambiguous. Use env list/inspect, or its full path. No env is auto-created.', 'env_missing')
    return matches[0]['path']

def env_inspect(request):
    prefix = resolve_env(request, request['env'])
    packages = conda_json(request, ['list', '--prefix', prefix])
    total = 0
    count = 0
    deadline = time.monotonic() + 10
    limited = False
    for directory, dirs, files in os.walk(prefix, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
        for filename in files:
            path = Path(directory) / filename
            if not path.is_symlink():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
            count += 1
        if count > 200000 or time.monotonic() > deadline:
            limited = True
            break
    return {'env': request['env'], 'path': prefix, 'size_gib': round(total / 1024 ** 3, 3), 'size_is_partial': limited,
            'packages': packages, 'note': 'Logical file size; conda hardlinks/cache can change actual disk usage.'}

def active_env_users(root, prefix):
    used = []
    for metadata in (root / 'jobs').glob('*/job.json'):
        record = read_json(metadata)
        if record.get('env_path') == prefix and job_state(root, record)['state'] in ('queued', 'running'):
            used.append(record['id'])
    for metadata in (root / 'services').glob('*/service.json'):
        record = read_json(metadata)
        if record.get('env_path') == prefix and service_state(record)['state'] in ('active', 'activating', 'reloading'):
            used.append(record['name'])
    return used

def approved(request):
    if request.get('approved') is not True:
        raise DeviceError('This changes an env/service. Human approval required; use --yes only after approval.', 'confirmation_required')

def package_args(values):
    if not isinstance(values, list) or not values:
        raise DeviceError('Provide at least one --package specification.')
    for value in values:
        clean_text(value)
        if value.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.\[\],<>=!+~:-]+', value):
            raise DeviceError('Use package names/version constraints, not flags, URLs or shell commands.')
    return values

def env_change(request):
    root = root_for(request)
    operation = request['operation']
    if operation != 'env_plan':
        approved(request)
    with locked(root):
        managed = read_json(root / 'envs.json')
        if operation == 'env_create':
            env_name = name(request['env'])
            if env_name in managed or (root / 'envs' / env_name).exists():
                raise DeviceError('Managed env already exists. Inspect/reuse it; no overwrite.')
            if len(managed) >= 8:
                raise DeviceError('Limit: 8 managed envs. Inspect/remove unused managed envs before creating another.', 'env_limit')
            version = request.get('python', '3.11')
            if not re.fullmatch(r'3\.\d{1,2}(?:\.\d{1,2})?', version):
                raise DeviceError('Use a Python version such as 3.11.')
            prefix = str(safe_path(root / 'envs' / env_name))
            managed[env_name] = prefix
            atomic_json(root / 'envs.json', managed)
            # Register before conda starts: a failed/partial install stays owned
            # and can be inspected/removed explicitly instead of being abandoned.
            result = conda_json(request, ['create', '--prefix', prefix, '--yes', 'python=' + version], timeout=1800)
            return {'env': env_name, 'path': prefix, 'result': result}
        if operation == 'env_remove':
            matches = [(k, v) for k, v in managed.items() if request['env'] in (k, v)]
            if len(matches) != 1:
                raise DeviceError('Only envs created by this CLI can be removed.', 'not_owned')
            env_name, prefix = matches[0]
            if safe_path(prefix) != safe_path(root / 'envs' / name(env_name)):
                raise DeviceError('Managed env path changed; refusing deletion.', 'not_owned')
        else:
            prefix = resolve_env(request, request['env'])
        if operation in ('env_install', 'env_plan') and prefix == conda_json(request, ['info']).get('root_prefix'):
            raise DeviceError('Base env is protected. Reuse a non-base env or create a managed one.', 'base_protected')
        if operation != 'env_plan' and active_env_users(root, prefix):
            raise DeviceError('Env is used by a running managed job/service. Stop it before changing the env.', 'env_busy')
        if operation == 'env_remove':
            if prefix not in managed.values():
                raise DeviceError('Only envs created by this CLI can be removed. Existing/base envs are protected.', 'not_owned')
            safe_path(prefix)
            if (Path(prefix) / 'conda-meta/history').is_file():
                result = conda_json(request, ['env', 'remove', '--prefix', prefix, '--yes'], timeout=1800)
            else:
                result = {'note': 'Removing an owned incomplete env.'}
            if Path(prefix).exists():
                shutil.rmtree(safe_path(prefix))
            managed = {k: v for k, v in managed.items() if v != prefix}
            atomic_json(root / 'envs.json', managed)
            return {'removed': prefix, 'result': result}
        packages = package_args(request['packages'])
        if request.get('pip'):
            arguments = [find_conda(request), 'run', '--no-capture-output', '--prefix', prefix, 'python', '-m', 'pip', 'install']
            if operation == 'env_plan':
                arguments.append('--dry-run')
            result = command([*arguments, *packages], timeout=1800)
            return {'env': prefix, 'dry_run': operation == 'env_plan', 'output': result.stdout[-12000:]}
        arguments = ['install', '--prefix', prefix, '--yes']
        if operation == 'env_plan':
            arguments.append('--dry-run')
        result = conda_json(request, [*arguments, *packages], timeout=1800)
        return {'env': prefix, 'dry_run': operation == 'env_plan', 'plan': result}

def tmux(root, *arguments, check=True):
    return command(['tmux', '-S', str(root / 'tmux.sock'), *arguments], check=check)

def job_file(root, identifier):
    if not re.fullmatch(r'job-[a-f0-9]{16}', identifier):
        raise DeviceError('Invalid job ID.', 'invalid_name')
    path = safe_path(root / 'jobs' / identifier / 'job.json')
    data = read_json(path)
    if data.get('owner') != OWNER or data.get('id') != identifier:
        raise DeviceError('Job is not owned.', 'not_owned')
    return path, data

def resolve_job(root, reference):
    if re.fullmatch(r'job-[a-f0-9]{16}', reference):
        job_file(root, reference)
        return reference
    name(reference)
    matches = [job_file(root,p.parent.name)[1] for p in (root/'jobs').glob('*/job.json') if read_json(p).get('name') == reference]
    active = [r for r in matches if job_state(root,r)['state'] in ('queued','running')]
    choices = active or matches
    if len(choices) != 1:
        raise DeviceError('Job name missing or ambiguous. Use its full ID from jobs --all.', 'unknown_job')
    return choices[0]['id']

def job_note(request):
    root = root_for(request)
    with locked(root):
        metadata, record = job_file(root, resolve_job(root,request['id']))
        changed = False
        for field in ('name','description','summary','phase','progress'):
            value = request.get(field)
            if value is None:
                continue
            if field == 'name':
                value = name(value)
                for path in (root/'jobs').glob('*/job.json'):
                    other = read_json(path)
                    if other['id'] != record['id'] and other.get('name') == value and job_state(root,other)['state'] in ('queued','running'):
                        raise DeviceError('Another active job has that name.', 'duplicate_job_name')
            elif field == 'progress':
                if type(value) not in (int,float) or not 0 <= value <= 100:
                    raise DeviceError('Progress must be 0-100.')
            else:
                clean_text(value)
                if len(value)>2000: raise DeviceError('Job text limit: 2000 characters.')
            record[field] = value
            changed = True
        if not changed:
            raise DeviceError('Provide --summary, --phase, --progress, --name or --description.')
        author = request.get('agent') or 'human'
        name(author)
        record.update(note_updated_at=now(),note_author=author)
        atomic_json(metadata,record)
    return job_state(root,record)

def validate_argv(arguments):
    if not isinstance(arguments, list) or not arguments:
        raise DeviceError('Provide a program and arguments after --.')
    for value in arguments:
        clean_text(value)
    if not arguments[0]:
        raise DeviceError('Empty program.')
    return arguments

def gpu_selection(request):
    index = request.get('gpu')
    if index is None:
        return None
    if type(index) is not int or index < 0:
        raise DeviceError('--gpu requires a nonnegative physical GPU index.')
    result = command(['nvidia-smi', '--query-gpu=index', '--format=csv,noheader,nounits'], timeout=10)
    if str(index) not in result.stdout.split():
        raise DeviceError('GPU index not found. Inspect the device first.', 'gpu_missing')
    return index

def launch_job(request):
    root = root_for(request)
    require_owned(root)
    if not shutil.which('tmux'):
        raise DeviceError('tmux missing. Run n3xus prepare DEVICE --install-tools first.', 'tmux_missing')
    arguments = validate_argv(request['command'])
    gpu = gpu_selection(request)
    with locked(root):
        prefix = resolve_env(request, request.get('env'))
        conda = find_conda(request) if prefix else None
        label = name(request['name']) if request.get('name') else None
        description = clean_text(request.get('description') or '')
        if len(description) > 2000: raise DeviceError('Description limit: 2000 characters.')
        author = name(request['agent']) if request.get('agent') else 'human'
        if label:
            for path in (root/'jobs').glob('*/job.json'):
                old = read_json(path)
                if old.get('name') == label and job_state(root,old)['state'] in ('queued','running'):
                    raise DeviceError('Another active job has that name.', 'duplicate_job_name')
        identifier = 'job-' + uuid.uuid4().hex[:16]
        directory = safe_path(root / 'jobs' / identifier)
        directory.mkdir(mode=0o700)
        revision = project_snapshot(root, request['project'], directory / 'workspace')
        (directory / 'outputs').mkdir(mode=0o700)
        record = {'owner': OWNER, 'id': identifier, 'name':label or identifier, 'description':description, 'agent':author, 'project': request['project'], 'revision': revision, 'command': arguments,
                  'env_path': prefix, 'env_name': request.get('env'), 'conda': conda, 'gpu': gpu, 'state': 'queued', 'created_at': now(),
                  'boot_id': boot_id(), 'workspace': str(directory / 'workspace'), 'outputs': str(directory / 'outputs')}
        atomic_json(directory / 'job.json', record)
        launcher = shlex.join([sys.executable, str(root / 'device_remote.py'), 'run-job', str(root), identifier])
        try:
            tmux(root, 'new-session', '-d', '-s', identifier, launcher)
        except DeviceError as exc:
            record.update(state='failed', error=str(exc), finished_at=now())
            atomic_json(directory / 'job.json', record)
            raise
    return {'id': identifier, 'name':record['name'], 'description':description, 'agent':author, 'state': 'queued', 'project': request['project'], 'outputs': record['outputs'], 'note': 'Submitted; jobs/logs/wait read live state. A job does not resume automatically after reboot.'}

def execution(record):
    args = record['command']
    if record.get('env_path'):
        args = [record['conda'], 'run', '--no-capture-output', '--prefix', record['env_path'], *args]
    return args

def rotate_log(path):
    if path.exists() and path.stat().st_size >= LOG_LIMIT:
        previous = safe_path(path.with_suffix('.log.1'))
        oldest = safe_path(path.with_suffix('.log.2'))
        if previous.exists():
            os.replace(previous, oldest)
        os.replace(path, previous)

def run_job(root, identifier):
    root = safe_path(root)
    log = root / 'jobs' / identifier / 'task.log'
    process = None
    try:
        with locked(root):
            metadata, record = job_file(root, identifier)
            if record.get('stop_requested'):
                record.update(state='stopped', finished_at=now())
                atomic_json(metadata, record)
                return
            environment = os.environ.copy()
            environment.update(DEVICE_JOB_ID=identifier, DEVICE_OUTPUT_DIR=record['outputs'], PYTHONUNBUFFERED='1')
            if record.get('gpu') is not None:
                environment['CUDA_VISIBLE_DEVICES'] = str(record['gpu'])
            process = subprocess.Popen(execution(record), cwd=safe_path(record['workspace']), env=environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            record.update(state='running', started_at=now(), pid=process.pid, pid_start=pid_start(process.pid), boot_id=boot_id())
            atomic_json(metadata, record)
        while chunk := process.stdout.read1(4096):
            rotate_log(log)
            with safe_path(log).open('ab') as output:
                os.chmod(log, 0o600)
                output.write(chunk)
        code = process.wait()
        with locked(root):
            metadata, record = job_file(root, identifier)
            record.update(state='stopped' if record.get('stop_requested') else 'completed' if code == 0 else 'failed', exit_code=code, finished_at=now())
            atomic_json(metadata, record)
    except Exception as exc:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        with locked(root):
            metadata, record = job_file(root, identifier)
            record.update(state='failed', error=str(exc), finished_at=now())
            atomic_json(metadata, record)

def job_state(root, record):
    result = dict(record)
    result.setdefault('name',record['id'])
    result.setdefault('description','')
    result['observed_at'] = now()
    try:
        start = datetime.fromisoformat(record.get('started_at',record['created_at']))
        end = datetime.fromisoformat(record['finished_at']) if record.get('finished_at') else datetime.now(timezone.utc)
        result['elapsed_seconds'] = max(0,int((end-start).total_seconds()))
    except (ValueError,KeyError):
        result['elapsed_seconds'] = None
    if record['state'] == 'running' and not alive(record):
        result.update(state='interrupted', reason='Process disappeared or device rebooted; not marked successful.')
    elif record['state'] == 'queued':
        present = tmux(root, 'has-session', '-t', record['id'], check=False).returncode == 0 if shutil.which('tmux') else False
        if record.get('boot_id') != boot_id() or not present:
            result.update(state='interrupted', reason='Queued runner is no longer present.')
    return result

def stop_job(request):
    root = root_for(request)
    with locked(root):
        metadata, record = job_file(root, request['id'])
        if record['state'] in ('completed', 'failed', 'stopped'):
            return job_state(root, record)
        record['stop_requested'] = True
        atomic_json(metadata, record)
        if alive(record):
            os.killpg(record['pid'], signal.SIGKILL if request.get('force') else signal.SIGTERM)
        elif record['state'] == 'queued':
            # Runner will acquire this lock, see the request, and exit before spawn.
            record.update(state='stopped', finished_at=now())
            atomic_json(metadata, record)
        else:
            record.update(state='interrupted', finished_at=now())
            atomic_json(metadata, record)
    return {'id': record['id'], 'state': record['state'], 'stop_requested': True}

def clean_job(request):
    approved(request)
    root = root_for(request)
    with locked(root):
        metadata, record = job_file(root, request['id'])
        state = job_state(root, record)['state']
        present = tmux(root, 'has-session', '-t', record['id'], check=False).returncode == 0 if shutil.which('tmux') else False
        if alive(record) or present or state in ('queued', 'running'):
            raise DeviceError('Job/runner is still active. Stop/wait before cleaning.', 'job_busy')
        shutil.rmtree(safe_path(metadata.parent))
    return {'removed': request['id'], 'note': 'Owned job workspace, outputs and logs deleted. Project revisions/envs remain.'}

def unit_name(root, service):
    return f'device-cli-{root.name[:12]}-{name(service)}.service'

def service_file(root, service):
    path = safe_path(root / 'services' / name(service) / 'service.json')
    record = read_json(path)
    if record.get('owner') != OWNER or record.get('name') != service or record.get('unit') != unit_name(root, service):
        raise DeviceError('Service is not owned.', 'not_owned')
    return path, record

def user_systemctl(*arguments, check=True):
    env = os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
    try:
        result = subprocess.run(['systemctl', '--user', *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceError(str(exc), 'systemd_unavailable') from exc
    if check and result.returncode:
        raise DeviceError('User systemd unavailable or failed: ' + result.stderr.strip() + '. Use prepare --enable-linger if needed.', 'systemd_unavailable')
    return result

def service_state(record):
    result = user_systemctl('show', record['unit'], '--property=ActiveState,SubState,MainPID,ExecMainStatus', check=False)
    properties = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    return {**record, 'state': properties.get('ActiveState', 'unknown'), 'substate': properties.get('SubState'),
            'pid': properties.get('MainPID'), 'exit_code': properties.get('ExecMainStatus'), 'status_error': result.stderr.strip() or None}

def systemd_quote(value):
    clean_text(value)
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'

def service_unit(root, record):
    argv = [sys.executable, str(root / 'device_remote.py'), 'run-service', str(root), record['name']]
    return '[Unit]\nDescription=Device CLI ' + record['name'] + '\n\n[Service]\nType=simple\nExecStart=' + ' '.join(systemd_quote(x) for x in argv) + '\nRestart=on-failure\nRestartPreventExitStatus=78\nRestartSec=5\nKillMode=control-group\nTimeoutStopSec=15\nNoNewPrivileges=yes\n\n[Install]\nWantedBy=default.target\n'

def listeners(port):
    result = command(['ss', '-H', '-ltn'], timeout=10)
    endpoints = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3].rsplit(':', 1)[-1] == str(port):
            endpoints.append(parts[3].rsplit(':', 1)[0].strip('[]'))
    return endpoints

def serve(request):
    root = root_for(request)
    require_owned(root)
    service = name(request['name'])
    arguments = validate_argv(request['command'])
    gpu = gpu_selection(request)
    if not any('{bind}' in arg for arg in arguments) or not any('{port}' in arg for arg in arguments):
        raise DeviceError('Service command must use {bind} and {port}, e.g. --host {bind} --port {port}. Never bind public/wildcard addresses.', 'unsafe_bind')
    ip = tailnet_ip()
    port = request['port']
    if type(port) is not int or not 1024 <= port <= 65535:
        raise DeviceError('Service port must be 1024-65535.')
    if listeners(port):
        raise DeviceError('Port already occupied. Pick another; existing listeners are not stopped.', 'port_busy')
    if command(['loginctl', 'show-user', str(os.getuid()), '--property=Linger', '--value']).stdout.strip() != 'yes':
        raise DeviceError('Persistent service needs linger. Run prepare DEVICE --enable-linger with your approval.', 'linger_required')
    user_systemctl('show-environment')
    with locked(root):
        prefix = resolve_env(request, request.get('env'))
        conda = find_conda(request) if prefix else None
        directory = safe_path(root / 'services' / service)
        unit_path = safe_path(Path.home() / '.config/systemd/user' / unit_name(root, service))
        if directory.exists() or unit_path.exists():
            raise DeviceError('Service name already exists. Inspect/stop/remove it explicitly; no overwrite.', 'already_exists')
        directory.mkdir(mode=0o700)
        revision = project_snapshot(root, request['project'], directory / 'workspace')
        (directory / 'outputs').mkdir(mode=0o700)
        record = {'owner': OWNER, 'name': service, 'unit': unit_name(root, service), 'project': request['project'], 'revision': revision,
                  'command': [arg.replace('{bind}', ip).replace('{port}', str(port)) for arg in arguments], 'bind': ip, 'port': port,
                  'env_path': prefix, 'env_name': request.get('env'), 'conda': conda, 'gpu': gpu, 'workspace': str(directory / 'workspace'),
                  'outputs': str(directory / 'outputs'), 'created_at': now(), 'endpoint': f'http://{ip}:{port}', 'unit_path': str(unit_path)}
        unit = service_unit(root, record)
        record['unit_sha256'] = hashlib.sha256(unit.encode()).hexdigest()
        atomic_json(directory / 'service.json', record)
        unit_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        unit_path.write_text(unit, encoding='utf-8', newline='\n')
        os.chmod(unit_path, 0o600)
        user_systemctl('daemon-reload')
        user_systemctl('enable', '--now', record['unit'])
    # Do not claim health from launch alone. Stop if the program ignores bind.
    for _ in range(20):
        bound = listeners(port)
        if bound:
            if any(address != ip for address in bound):
                user_systemctl('stop', record['unit'])
                raise DeviceError('Program ignored the Tailscale bind; service stopped. Inspect its command.', 'unsafe_bind')
            return {**service_state(record), 'listening': True}
        if service_state(record)['state'] == 'failed':
            break
        time.sleep(0.5)
    return {**service_state(record), 'listening': False, 'note': 'Not listening yet. Check logs/health; large models can take time to load.'}

def run_service(root, service):
    require_owned(root)
    _, record = service_file(root, service)
    os.chdir(safe_path(record['workspace']))
    environment = os.environ.copy()
    environment.update(DEVICE_OUTPUT_DIR=record['outputs'], DEVICE_BIND_ADDRESS=record['bind'], DEVICE_PORT=str(record['port']), PYTHONUNBUFFERED='1')
    if record.get('gpu') is not None:
        environment['CUDA_VISIBLE_DEVICES'] = str(record['gpu'])
    arguments = execution(record)
    # The runner also guards later binds/restarts, rather than only SSH launch.
    # It is not a network sandbox: untrusted apps can still open other ports.
    process = subprocess.Popen(arguments, env=environment, stdin=subprocess.DEVNULL)
    try:
        while process.poll() is None:
            bound = listeners(record['port'])
            if any(address != record['bind'] for address in bound):
                print('Unsafe bind detected. Stopping this service.', file=sys.stderr, flush=True)
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise SystemExit(78)
            time.sleep(1)
        raise SystemExit(process.returncode if process.returncode >= 0 else 1)
    finally:
        if process.poll() is None:
            process.terminate()

def service_action(request):
    root = root_for(request)
    with locked(root):
        metadata, record = service_file(root, request['name'])
        path = safe_path(record['unit_path'])
        expected = safe_path(Path.home() / '.config/systemd/user' / record['unit'])
        if path != expected or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record['unit_sha256']:
            raise DeviceError('Unit changed or missing. Refusing to overwrite/delete/control it.', 'not_owned')
        action = request['action']
        if action == 'remove':
            approved(request)
            user_systemctl('disable', '--now', record['unit'])
            path.unlink()
            user_systemctl('daemon-reload')
            # Keep workspace/outputs and receipt as an archived service; no data loss.
            record.update(removed_at=now())
            atomic_json(metadata, record)
            return {'removed': record['name'], 'outputs_preserved': record['outputs']}
        if action == 'start' and listeners(record['port']):
            if service_state(record)['state'] != 'active':
                raise DeviceError('Port occupied by another process.', 'port_busy')
        user_systemctl(action, record['unit'])
    return service_state(record)

def logs(request):
    root = root_for(request)
    identifier = request['id']
    lines = max(1, min(int(request.get('lines', 100)), 2000))
    if identifier.startswith('job-'):
        job_file(root, identifier)
        path = safe_path(root / 'jobs' / identifier / 'task.log')
        if path.exists():
            with path.open('rb') as handle:
                handle.seek(max(0, path.stat().st_size - 512 * 1024))
                text = handle.read().decode('utf-8', errors='replace')
        else:
            text = ''
    else:
        _, record = service_file(root, identifier)
        text = command(['journalctl', '--user', '-u', record['unit'], '-n', str(lines), '--no-pager', '-o', 'cat']).stdout
    return {'id': identifier, 'log': '\n'.join(text.splitlines()[-lines:])}

def fetch(request):
    root = root_for(request)
    _, record = job_file(root, request['id'])
    relative = request.get('path')
    source = safe_path(Path(record['workspace']) / str(relative_path(relative))) if relative else safe_path(record['outputs'])
    if relative and not source.is_relative_to(Path(record['workspace'])):
        raise DeviceError('Fetch path leaves workspace.', 'unsafe_path')
    return archive_payload(pack_directory(source, exclusions=False))

def dispatch(request):
    operation = request['operation']
    if operation == 'probe':
        return probe(request)
    if operation == 'prepare':
        return prepare(request)
    root = root_for(request)
    if operation == 'overview':
        info = probe(request)
        if not info['prepared']:
            return {'device':info,'jobs':[],'jobs_error':'Device is not prepared for this profile.'}
        records = [job_state(root,job_file(root,p.parent.name)[1]) for p in sorted((root/'jobs').glob('*/job.json'))]
        active = sum(r['state'] in ('queued','running') for r in records)
        return {'device':{**info,'active_jobs':active}, 'jobs':records if request.get('all') else [r for r in records if r['state'] in ('queued','running')]}
    require_owned(root)
    if operation in ('job','job_detail','job_note','stop','clean','fetch') or (operation == 'logs' and not request.get('service')):
        request = {**request,'id':resolve_job(root,request['id'])}
    if operation == 'job_note':
        return job_note(request)
    if operation == 'job_detail':
        record = job_state(root,job_file(root,request['id'])[1])
        return {**record,'recent_log':logs({**request,'lines':20})['log']}
    if operation == 'sync':
        return sync_project(request)
    if operation == 'env_list':
        return env_list(request)
    if operation == 'env_inspect':
        return env_inspect(request)
    if operation in ('env_create', 'env_plan', 'env_install', 'env_remove'):
        return env_change(request)
    if operation == 'run':
        return launch_job(request)
    if operation == 'jobs':
        return {'jobs': [job_state(root, job_file(root, p.parent.name)[1]) for p in sorted((root / 'jobs').glob('*/job.json'))]}
    if operation == 'job':
        return job_state(root, job_file(root, request['id'])[1])
    if operation == 'stop':
        return stop_job(request)
    if operation == 'clean':
        return clean_job(request)
    if operation == 'logs':
        return logs(request)
    if operation == 'fetch':
        return fetch(request)
    if operation == 'serve':
        return serve(request)
    if operation == 'services':
        return {'services': [service_state(service_file(root, p.parent.name)[1]) for p in sorted((root / 'services').glob('*/service.json')) if not read_json(p).get('removed_at')]}
    if operation == 'service_action':
        return service_action(request)
    raise DeviceError('Unknown remote operation.', 'invalid_operation')

def entrypoint(request):
    os.umask(0o077)
    try:
        data = dispatch(request)
        response = {'schema': SCHEMA, 'ok': True, 'data': data}
    except Exception as exc:
        response = {'schema': SCHEMA, 'ok': False, 'error': {'code': getattr(exc, 'code', 'operation_failed'), 'message': str(exc)}}
    print(json.dumps(response, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    mode, root, identifier = sys.argv[1:]
    if mode == 'run-job':
        run_job(Path(root), identifier)
    elif mode == 'run-service':
        run_service(Path(root), identifier)
    else:
        raise SystemExit('Invalid runner mode')
