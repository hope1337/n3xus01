"""Native Windows/Linux CLI. All remote execution uses SSH argv + JSON stdin."""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from device_common import DeviceError, SCHEMA, archive_payload, atomic_json, name, pack_directory, read_json, unpack, validate_device
from device_ui import UI, init_terminal
import device_workspace as workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'workspace'
CONFIG = WORKSPACE / 'config/devices.json'
LEGACY_CONFIG = ROOT / 'devices.json'
BOOTSTRAP = "import json,sys,types; b=json.load(sys.stdin); m=types.ModuleType('device_common'); exec(compile(b['common'],'<device-common>','exec'),m.__dict__); sys.modules['device_common']=m; n={'__name__':'device_remote'}; exec(compile(b['helper'],'<device-helper>','exec'),n); r=b['request']; r['_common_source']=b['common']; r['_helper_source']=b['helper']; n['entrypoint'](r)"

def config():
    path = CONFIG
    if not path.exists() and CONFIG == WORKSPACE/'config/devices.json' and LEGACY_CONFIG.exists():
        path = LEGACY_CONFIG
    if not path.exists():
        raise DeviceError('Run device setup first.', 'setup_required')
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {'schema', 'profile', 'devices'} or value['schema'] != SCHEMA:
        raise DeviceError('Invalid devices.json schema. Keep your profile ID when switching host OS.', 'invalid_config')
    import re
    if not re.fullmatch(r'[a-f0-9]{32}', value['profile']) or not isinstance(value['devices'], dict):
        raise DeviceError('Invalid profile/devices mapping.', 'invalid_config')
    destinations = set()
    for device_name, entry in value['devices'].items():
        name(device_name)
        validate_device(entry)
        destination = (entry['address'].lower(), entry['user'], entry.get('port', 22))
        if destination in destinations:
            raise DeviceError('Duplicate SSH destination in config.', 'invalid_config')
        destinations.add(destination)
    return value

def overview(conf, device=None, include_all=False):
    items = [(device,selected(conf,device))] if device else list(conf['devices'].items())
    def inspect(item):
        identity, entry = item
        try:
            data = remote(entry,conf['profile'],'overview',all=include_all)
            information = {'name':identity,**data['device']}
            if data.get('jobs_error'): information['jobs_error'] = data['jobs_error']
            return information,[{'device':identity,**record} for record in data['jobs']]
        except DeviceError as exc:
            return {'name':identity,'online':exc.code not in ('ssh_failed','ssh_timeout','ssh_missing','protocol_error'),'ready':False,'error':str(exc),'jobs_error':str(exc)},[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(inspect,items))
    return {'observed_at':workspace.now(),'devices':[d for d,_ in values],'jobs':[j for _,records in values for j in records],'include_history':include_all}

def ssh_arguments(entry, *, interactive=False):
    executable = shutil.which('ssh')
    if not executable:
        raise DeviceError('OpenSSH client missing. Install it on host before using devices.', 'ssh_missing')
    args = [executable, '-tt' if interactive else '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ControlMaster=no', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3',
            '-p', str(entry.get('port', 22))]
    if entry.get('key'):
        args.extend(['-i', str(Path(entry['key']).expanduser())])
    return [*args, f"{entry['user']}@{entry['address']}"]

def remote(entry, profile, operation, **arguments):
    request = {'profile': profile, 'operation': operation, **arguments}
    if entry.get('conda'):
        request['conda'] = entry['conda']
    body = {'common': (ROOT / 'scripts/device_common.py').read_text(encoding='utf-8'),
            'helper': (ROOT / 'scripts/device_remote.py').read_text(encoding='utf-8'), 'request': request}
    argv = [*ssh_arguments(entry), shlex.join(['python3', '-c', BOOTSTRAP])]
    timeout = 1860 if operation.startswith('env_') and operation not in ('env_list', 'env_inspect') else 90 if operation in ('sync', 'serve', 'prepare', 'fetch') else 35
    try:
        # Bytes prevent Windows CRLF conversion and preserve arbitrary Unicode.
        result = subprocess.run(argv, input=json.dumps(body, ensure_ascii=False).encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DeviceError('SSH operation timed out. An already-submitted job/service continues; inspect before retrying a mutation.', 'ssh_timeout') from exc
    except OSError as exc:
        raise DeviceError(f'SSH failed: {exc}', 'ssh_failed') from exc
    if result.returncode:
        raise DeviceError(result.stderr.decode('utf-8', errors='replace').strip()[-3000:] or f'SSH exited {result.returncode}', 'ssh_failed')
    try:
        response = json.loads(result.stdout.decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise DeviceError('Device returned unexpected output. Check Python 3.10+ and SSH startup scripts.', 'protocol_error') from exc
    if response.get('schema') != SCHEMA:
        raise DeviceError('Unsupported response schema.', 'protocol_error')
    if not response.get('ok'):
        raise DeviceError(response['error']['message'], response['error']['code'])
    return response['data']

def selected(conf, device):
    name(device)
    if device not in conf['devices']:
        raise DeviceError('Unknown device. Use device add NAME --address ... --user ...', 'unknown_device')
    return conf['devices'][device]

def confirm(args, message):
    if getattr(args, 'yes', False):
        return
    if args.json or not sys.stdin.isatty():
        raise DeviceError(message + ' Explicit approval required (--yes after human approval).', 'confirmation_required')
    if input(message + ' [y/N]: ').strip().lower() not in ('y', 'yes'):
        raise DeviceError('Cancelled; nothing changed.', 'cancelled')

def add_device(args):
    conf = config()
    if not args.name and not sys.stdin.isatty():
        raise DeviceError('Provide device name/address/user for noninteractive use.', 'invalid_argument')
    device = name(args.name or input('Device name: ').strip())
    old = conf['devices'].get(device, {})
    entry = {'address': args.address or old.get('address'), 'user': args.user or old.get('user'), 'port': args.port or old.get('port', 22)}
    for field in ('address', 'user'):
        if not entry[field]:
            if args.json or not sys.stdin.isatty():
                raise DeviceError(f'Provide --{field}.', 'invalid_argument')
            entry[field] = input('Tailscale IP/hostname: ' if field == 'address' else 'SSH user: ').strip()
    for field in ('key', 'conda'):
        value = getattr(args, field) or old.get(field)
        if value:
            entry[field] = value
    validate_device(entry)
    if old and any(entry[field] != old[field] for field in ('address', 'user', 'port')):
        raise DeviceError('Existing device identity differs. Remove the local registration explicitly before replacing it.', 'identity_changed')
    if any(k != device and (v['address'].lower(), v['user'], v.get('port', 22)) == (entry['address'].lower(), entry['user'], entry['port']) for k, v in conf['devices'].items()):
        raise DeviceError('Another name already points to this SSH destination.', 'invalid_config')
    information = remote(entry, conf['profile'], 'prepare')
    conf['devices'][device] = entry
    atomic_json(CONFIG, conf)
    return {'device': device, 'registered': True, 'ready': information['ready'], 'conda': information['conda'], 'state_directory': information['state_directory'],
            'next': 'device status' if information['ready'] else f'device prepare {device} --install-tools'}

def status(conf):
    def inspect(item):
        device, entry = item
        try:
            return {'name': device, **remote(entry, conf['profile'], 'probe')}
        except DeviceError as exc:
            connected = exc.code not in ('ssh_missing', 'ssh_failed', 'ssh_timeout', 'protocol_error')
            return {'name': device, 'online': connected, 'ready': False, 'blocked': connected, 'error': str(exc), 'error_code': exc.code}
    with ThreadPoolExecutor(max_workers=8) as pool:
        return {'devices': list(pool.map(inspect, conf['devices'].items()))}

def install_tools(args, entry):
    if not args.install_tools and not args.enable_linger:
        return
    confirm(args, 'Install tmux / enable user linger on this device as requested?')
    steps = []
    if args.install_tools:
        steps.append('command -v tmux >/dev/null 2>&1 || { sudo apt-get update && sudo apt-get install -y tmux; }')
    if args.enable_linger:
        steps.append(shlex.join(['sudo', 'loginctl', 'enable-linger', entry['user']]))
    if args.json:
        raise DeviceError('Preparation may ask sudo password. Run interactively in your terminal; JSON never opens an interactive sudo session.', 'interactive_required')
    result = subprocess.run([*ssh_arguments(entry, interactive=True), ' && '.join('(' + s + ')' for s in steps)])
    if result.returncode:
        raise DeviceError('Device preparation failed. Read its output and retry; SSH/driver/conda were not reconfigured.', 'prepare_failed')

def fetch_files(args, entry, profile):
    destination = Path(args.output).expanduser().absolute()
    if destination.exists():
        raise DeviceError('Output directory already exists. Choose a new directory; existing files are never overwritten.', 'already_exists')
    response = remote(entry, profile, 'fetch', id=args.id, path=args.path)
    raw = base64.b64decode(response['archive'], validate=True)
    import hashlib
    if hashlib.sha256(raw).hexdigest() != response['sha256']:
        raise DeviceError('Download checksum mismatch.', 'protocol_error')
    unpack(raw, destination)
    return {'id': args.id, 'downloaded_to': str(destination)}

def health(entry, profile, service_name, path):
    name(service_name)
    if not path.startswith('/') or '\r' in path or '\n' in path:
        raise DeviceError('Health path must start with /.')
    records = remote(entry, profile, 'services')['services']
    record = next((r for r in records if r['name'] == service_name), None)
    if record is None:
        raise DeviceError('Unknown active service.', 'unknown_service')
    endpoint = record['endpoint'] + path
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(endpoint, timeout=10) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (OSError, urllib.error.URLError) as exc:
        return {'name': service_name, 'endpoint': endpoint, 'reachable': False, 'healthy': False, 'error': str(exc)}
    return {'name': service_name, 'endpoint': endpoint, 'reachable': True, 'healthy': 200 <= code < 400, 'http_status': code}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise DeviceError(message + ' (Use --help.)', 'invalid_argument')

def parser():
    cli = ArgumentParser(prog='device', description='Your devices. Your code. Direct SSH — no cluster, no images.')
    cli.add_argument('--json', action='store_true', help='one JSON response, no colors/prompts')
    cli.add_argument('--color', choices=('auto', 'always', 'never'), default='auto')
    commands = cli.add_subparsers(dest='action')
    for action in ('setup', 'status', 'doctor'):
        commands.add_parser(action)
    demo = commands.add_parser('demo',help='fake data, no SSH')
    demo.add_argument('--view',choices=('status','dashboard'),default='status')
    add = commands.add_parser('add', help='register SSH device and install a small owned helper, without sudo')
    add.add_argument('name', nargs='?')
    for field in ('address', 'user', 'key', 'conda'):
        add.add_argument('--' + field)
    add.add_argument('--port', type=int)
    remove = commands.add_parser('remove', help='forget local registration only; remote jobs/data remain')
    remove.add_argument('device')
    remove.add_argument('--yes', action='store_true')
    for action in ('inspect', 'check', 'services'):
        commands.add_parser(action).add_argument('device')
    jobs = commands.add_parser('jobs',help='active jobs; omit DEVICE to see all registered devices')
    jobs.add_argument('device',nargs='?')
    jobs.add_argument('--all',action='store_true',help='include finished/stopped history')
    board = commands.add_parser('dashboard',help='live terminal board; q exit, j/k select, i details, l logs, s stop, d delete, h history')
    board.add_argument('device',nargs='?')
    board.add_argument('--all',action='store_true')
    board.add_argument('--once',action='store_true')
    board.add_argument('--interval',type=float,default=5)
    for action in ('job','job-note'):
        detail=commands.add_parser(action)
        detail.add_argument('device')
        detail.add_argument('id',help='job ID or unambiguous name')
        if action=='job-note':
            for option in ('name','description','summary','phase','agent'): detail.add_argument('--'+option)
            detail.add_argument('--progress',type=float)
    communication=commands.add_parser('communication',help='agent work folders, append-only handoff notes and saved snapshots')
    communication.add_argument('operation',choices=('init','note','show','snapshot'))
    communication.add_argument('agent',nargs='?')
    communication.add_argument('--title')
    communication.add_argument('--message')
    communication.add_argument('--message-file')
    communication.add_argument('--device')
    communication.add_argument('--job')
    prepare = commands.add_parser('prepare')
    prepare.add_argument('device')
    prepare.add_argument('--install-tools', action='store_true')
    prepare.add_argument('--enable-linger', action='store_true')
    prepare.add_argument('--yes', action='store_true')
    sync = commands.add_parser('sync', help='upload code only; secrets/datasets excluded; immutable revisions')
    sync.add_argument('device')
    sync.add_argument('source')
    sync.add_argument('--project', required=True)
    for action in ('run', 'serve'):
        launch = commands.add_parser(action)
        launch.add_argument('device')
        launch.add_argument('project')
        launch.add_argument('--env')
        launch.add_argument('--gpu', type=int)
        if action=='run':
            launch.add_argument('--name',help='human-readable job name; unique among active jobs on this device')
            launch.add_argument('--description',default='',help='what this job does')
            launch.add_argument('--agent',help='agent identity from communication init')
        if action == 'serve':
            launch.add_argument('--name', required=True)
            launch.add_argument('--port', type=int, required=True)
    for action in ('logs', 'wait', 'stop', 'fetch', 'clean'):
        command = commands.add_parser(action)
        command.add_argument('device')
        command.add_argument('id')
        if action == 'logs':
            command.add_argument('--lines', type=int, default=100)
            command.add_argument('--service',action='store_true',help='read a systemd service instead of a job')
            command.add_argument('--follow',action='store_true',help='terminal polling; Ctrl+C leaves job running')
        elif action == 'wait':
            command.add_argument('--timeout', type=int, default=600)
        elif action == 'stop':
            command.add_argument('--force', action='store_true')
        elif action == 'clean':
            command.add_argument('--yes', action='store_true')
        else:
            command.add_argument('--path', help='relative DIRECTORY within this job workspace; default outputs')
            command.add_argument('--output', required=True)
    service = commands.add_parser('service')
    service.add_argument('device')
    service.add_argument('operation', choices=('start', 'stop', 'remove', 'check'))
    service.add_argument('name')
    service.add_argument('--yes', action='store_true')
    service.add_argument('--path', default='/')
    env = commands.add_parser('env')
    env.add_argument('operation', choices=('list', 'inspect', 'plan', 'create', 'install', 'remove'))
    env.add_argument('device')
    env.add_argument('env', nargs='?')
    env.add_argument('--package', action='append', default=[])
    env.add_argument('--python', default='3.11')
    env.add_argument('--pip', action='store_true')
    env.add_argument('--yes', action='store_true')
    return cli

def arguments(argv):
    # --json/--color can be before or after subcommand, never inside program argv.
    payload = []
    if '--' in argv:
        position = argv.index('--')
        payload, argv = argv[position + 1:], argv[:position]
    global_args, rest = [], []
    index = 0
    while index < len(argv):
        if argv[index] == '--json':
            global_args.append(argv[index])
        elif argv[index] == '--color' and index + 1 < len(argv):
            global_args.extend(argv[index:index + 2])
            index += 1
        elif argv[index].startswith('--color='):
            global_args.append(argv[index])
        else:
            rest.append(argv[index])
        index += 1
    args = parser().parse_args([*global_args, *rest])
    args.command = payload
    return args

def execute(args):
    if args.action == 'setup':
        if sys.version_info < (3, 10):
            raise DeviceError('Host needs Python 3.10+; conda Python is fine.')
        if not shutil.which('ssh'):
            raise DeviceError('Host needs OpenSSH client. Prepare SSH keys/known_hosts yourself.')
        workspace.initialize(WORKSPACE)
        if CONFIG.exists() and LEGACY_CONFIG.exists() and CONFIG == WORKSPACE/'config/devices.json':
            if read_json(CONFIG) != read_json(LEGACY_CONFIG):
                raise DeviceError('Both config files exist with different data. Resolve them manually; no profile was replaced.', 'config_conflict')
            from device_common import safe_path
            legacy = safe_path(WORKSPACE/'legacy'); legacy.mkdir(exist_ok=True, mode=0o700)
            archived = safe_path(legacy/'devices-'+uuid.uuid4().hex+'.json')
            safe_path(LEGACY_CONFIG).rename(archived)
        if not CONFIG.exists():
            if CONFIG == WORKSPACE/'config/devices.json' and LEGACY_CONFIG.exists():
                config()  # Validate before moving; preserve the exact profile/data.
                from device_common import safe_path
                safe_path(LEGACY_CONFIG).rename(safe_path(CONFIG))
            else:
                atomic_json(CONFIG, {'schema': SCHEMA, 'profile': uuid.uuid4().hex, 'devices': {}})
        config()
        return 'setup', {'ready': True, 'python': sys.version.split()[0], 'config': str(CONFIG), 'next': 'device add'}
    if args.action == 'doctor':
        return 'doctor', {'python': sys.version.split()[0], 'ssh': shutil.which('ssh'), 'config_exists': CONFIG.exists(), 'native_host': sys.platform, 'wsl_required': False}
    if args.action == 'demo':
        if args.view=='dashboard':
            return 'dashboard', {'observed_at':'DEMO / FAKE DATA / NO SSH','include_history':False,'devices':[{'name':'demo-device','online':True,'active_jobs':1,'memory_available_gib':24,'memory_total_gib':32,'gpus':[{'total_mib':24576,'free_mib':6144}]}],'jobs':[{'device':'demo-device','id':'job-'+'a'*16,'name':'llm-example','state':'running','phase':'serving','description':'Example LLM service (fake data)'}]}
        return 'status', {'devices': [{'name': 'sekiro', 'online': True, 'ready': True, 'memory_available_gib': 27.4, 'gpus': [{'name': 'RTX 4090 · 22 GiB free'}]}, {'name': 'genichiro', 'online': True, 'ready': True, 'memory_available_gib': 12.1, 'gpus': [{'name': 'RTX 2080 Ti · 10 GiB free'}]}, {'name': 'lab-01', 'online': False, 'ready': False}]}
    if args.action == 'add':
        return 'add', add_device(args)
    if args.action=='communication':
        if args.operation=='init':
            if not args.agent: raise DeviceError('Provide an agent ID, e.g. codex-20261006-a1.')
            return 'communication_init',workspace.agent(WORKSPACE,args.agent)
        if args.operation=='show': return 'communication',workspace.show(WORKSPACE,args.agent)
        if args.operation=='note':
            if not args.agent or not args.title or bool(args.message)==bool(args.message_file):
                raise DeviceError('Provide AGENT --title and exactly one of --message / --message-file.')
            message=Path(args.message_file).read_text(encoding='utf-8') if args.message_file else args.message
            return 'communication_note',workspace.note(WORKSPACE,args.agent,args.title,message,args.device,args.job)
        result=overview(config(),include_all=True)
        return 'communication_snapshot',workspace.snapshot(WORKSPACE,result)
    conf = config()
    if args.action == 'status':
        return 'status', status(conf)
    if args.action in ('jobs','dashboard'):
        if args.action=='dashboard' and args.interval<1: raise DeviceError('Dashboard interval must be >=1 second.')
        return args.action,overview(conf,args.device,args.all)
    entry = selected(conf, args.device)
    if args.action == 'remove':
        confirm(args, 'Forget this device locally? Remote jobs/services/data will remain.')
        conf['devices'].pop(args.device)
        atomic_json(CONFIG, conf)
        return 'remove', {'forgotten': args.device, 'remote_data_untouched': True}
    call = lambda operation, **kwargs: remote(entry, conf['profile'], operation, **kwargs)
    if args.action in ('inspect', 'check'):
        data = call('probe')
        if args.action == 'check' and not data['ready']:
            raise DeviceError('SSH works but device needs add/prepare --install-tools before jobs.', 'not_ready')
        return 'inspect', data
    if args.action == 'prepare':
        call('probe')  # Verify the actual SSH destination before any sudo task.
        install_tools(args, entry)
        return 'inspect', call('prepare')
    if args.action == 'sync':
        return 'sync', call('sync', project=name(args.project), **archive_payload(pack_directory(Path(args.source).expanduser())))
    if args.action in ('run', 'serve'):
        if not args.command:
            raise DeviceError('Put program arguments after --. Example: run DEVICE PROJECT --env ENV -- python -u main.py')
        if args.gpu is not None and not 0 <= args.gpu <= 31:
            raise DeviceError('GPU index must be 0-31.')
        kwargs = {'project': name(args.project), 'env': args.env, 'command': args.command, 'gpu': args.gpu}
        if args.action == 'serve':
            kwargs.update(name=name(args.name), port=args.port)
        else:
            kwargs.update(name=args.name,description=args.description,agent=args.agent)
            if args.agent and (not args.name or not args.description.strip()):
                raise DeviceError('Agent submissions require --name and --description so humans can understand the job.')
            if args.agent: workspace.agent(WORKSPACE,args.agent)
        result=call(args.action, **kwargs)
        if args.action=='run':
            try:
                workspace.receipt(WORKSPACE,args.device,result)
            except (OSError,DeviceError) as exc:
                result['warning']='Job submitted; local receipt could not be saved: '+str(exc)+'. Inspect its ID before retrying.'
        return args.action,result
    if args.action=='job': return 'job',call('job_detail',id=args.id)
    if args.action=='job-note':
        if args.agent: workspace.agent(WORKSPACE,args.agent)
        result=call('job_note',id=args.id,**{k:getattr(args,k) for k in ('name','description','summary','phase','progress','agent')})
        if args.agent:
            try:
                workspace.note(WORKSPACE,args.agent,'Job update: '+result['name'],result.get('summary') or result.get('description') or result.get('phase') or 'Job metadata updated.',args.device,result['id'])
            except (OSError,DeviceError) as exc:
                result['warning']='Device metadata updated; local handoff note could not be saved: '+str(exc)
        return 'job',result
    if args.action == 'services':
        return args.action, call(args.action)
    if args.action == 'logs':
        if args.follow and args.json: raise DeviceError('--follow is for terminals; use JSON snapshots for agents.')
        return 'logs', call('logs', id=args.id, lines=args.lines,service=args.service)
    if args.action == 'stop':
        return 'stop', call('stop', id=args.id, force=args.force)
    if args.action == 'fetch':
        return 'fetch', fetch_files(args, entry, conf['profile'])
    if args.action == 'wait':
        if args.timeout <= 0:
            raise DeviceError('Timeout must be positive.')
        deadline = time.monotonic() + args.timeout
        while True:
            data = call('job', id=args.id)
            if data['state'] in ('completed', 'failed', 'stopped', 'interrupted'):
                if data['state'] != 'completed':
                    raise DeviceError(f"{args.id} is {data['state']} (exit {data.get('exit_code')}). Use logs; no automatic retry.", 'job_failed')
                return 'wait', data
            if time.monotonic() >= deadline:
                raise DeviceError('Wait timed out. Job was not stopped; inspect jobs/logs or wait again.', 'wait_timeout')
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    if args.action == 'service':
        if args.operation == 'check':
            result = health(entry, conf['profile'], args.name, args.path)
            if not result['healthy']:
                raise DeviceError(f"Service {args.name} is not healthy at {result['endpoint']}: {result.get('error', result.get('http_status'))}", 'service_unhealthy')
            return 'service_check', result
        if args.operation == 'remove':
            confirm(args, 'Remove owned service unit? Its workspace/results will remain.')
        return 'service', call('service_action', name=name(args.name), action=args.operation, approved=True)
    if args.action == 'clean':
        confirm(args, 'Delete this finished owned job including its outputs/logs? Fetch results first.')
        return 'clean', call('clean', id=args.id, approved=True)
    if args.action == 'env':
        if args.operation != 'list' and not args.env:
            raise DeviceError('Provide an env name/path. Use env list DEVICE first.')
        if args.operation in ('create', 'install', 'remove'):
            confirm(args, f'{args.operation} conda env {args.env}? Dependencies may change; inspect/plan first.')
        if args.operation in ('plan', 'install') and not args.package:
            raise DeviceError('Provide --package NAME[=VERSION] (repeatable).')
        return 'env_' + args.operation, call('env_' + args.operation, env=args.env, packages=args.package, python=args.python, pip=args.pip, approved=args.operation in ('create', 'install', 'remove'))
    raise DeviceError('Unknown command.')

def menu():
    ui = UI()
    while True:
        ui.header('DIRECT SSH · CONTROL DESK')
        print('  1  Devices / status\n  2  Register device\n  3  Inspect a device\n  4  Jobs across devices\n  5  Services\n  6  Conda environments\n  7  Live dashboard\n  8  Shared handoff\n  h  Command help\n  q  Exit\n')
        choice = input('Choose: ').strip().lower()
        if choice in ('q', ''):
            return
        if choice == 'h':
            parser().print_help()
            continue
        commands = {'1': ['status'], '2': ['add'], '3': ['inspect'], '4': ['jobs'], '5': ['services'], '6': ['env', 'list'], '7':['dashboard'],'8':['communication','show']}
        if choice not in commands:
            continue
        argv = commands[choice][:]
        if choice in ('3', '5', '6'):
            argv.append(input('Device name: ').strip())
        try:
            if choice=='7':
                from device_dashboard import watch
                board_args=arguments(argv)
                watch(board_args,lambda:execute(board_args)[1],execute,arguments)
                continue
            action, data = execute(arguments(argv))
            ui.render(action, data)
        except DeviceError as exc:
            ui.message(str(exc), False)
        input('\nEnter to return to menu…')

def main(argv=None):
    init_terminal()
    if argv is None and os.environ.get('DEVICE_ARGUMENTS_BASE64'):
        try:
            argv = json.loads(base64.b64decode(os.environ['DEVICE_ARGUMENTS_BASE64'], validate=True).decode('utf-8'))
            if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
                raise ValueError('expected a string array')
        except (ValueError, UnicodeError) as exc:
            UI().message('Invalid launcher arguments: ' + str(exc), False)
            return 1
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        if sys.stdin.isatty():
            try:
                menu()
            except (KeyboardInterrupt,EOFError):
                return 130
        else:
            parser().print_help()
        return 0
    as_json = '--json' in (argv[:argv.index('--')] if '--' in argv else argv)
    try:
        args = arguments(argv)
        if not args.action:
            parser().print_help()
            return 0
        if args.action=='dashboard' and not args.json and not args.once and sys.stdin.isatty() and sys.stdout.isatty():
            from device_dashboard import watch
            watch(args,lambda:execute(args)[1],execute,arguments)
            return 0
        if args.action=='logs' and args.follow:
            from device_dashboard import follow_logs
            follow_logs(args,execute)
            return 0
        action, data = execute(args)
        if args.json:
            print(json.dumps({'schema': SCHEMA, 'ok': True, 'action': action, 'data': data}, ensure_ascii=False))
        else:
            UI(args.color).render(action, data)
        return 0
    except DeviceError as exc:
        if as_json:
            print(json.dumps({'schema': SCHEMA, 'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}, ensure_ascii=False))
        else:
            UI().message(str(exc), False)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        message = 'Cannot complete this step: ' + str(exc)
        if as_json:
            print(json.dumps({'schema': SCHEMA, 'ok': False, 'error': {'code': 'operation_failed', 'message': message}}, ensure_ascii=False))
        else:
            UI().message(message, False)
        return 1
    except KeyboardInterrupt:
        if as_json:
            print(json.dumps({'schema': SCHEMA, 'ok': False, 'error': {'code': 'interrupted', 'message': 'Host interrupted. Submitted jobs/services are not stopped.'}}))
        else:
            print('\nHost interrupted. Submitted jobs/services are not stopped.', file=sys.stderr)
        return 130

if __name__ == '__main__':
    raise SystemExit(main())
