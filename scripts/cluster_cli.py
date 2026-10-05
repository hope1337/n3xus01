"""Human/agent CLI. No secrets in config; all provisioning is in Ansible."""
from __future__ import annotations
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid
import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('CLUSTER_STATE_DIR', str(ROOT / '.cluster')))
CONFIG = ROOT / 'devices.yml'
CONTEXT = 'personal-compute-v1'
OWNER = 'personal-compute-v1'
STEP = 'arguments'

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ClusterError('Duplicate field/device in devices.yml; refusing ambiguous configuration.')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

class ClusterError(Exception):
    pass

def say(message):
    print(f'[cluster] {message}', flush=True)

def run_process(argv, *, capture=False, input_text=None, timeout=None, check=True):
    try:
        result = subprocess.run([str(x) for x in argv], input=input_text, text=True,
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClusterError(f'{Path(str(argv[0])).name}: {exc}') from exc
    if check and result.returncode:
        # Never dump Ansible variables/input; modules containing credentials use no_log.
        if capture and result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        raise ClusterError(f'{Path(str(argv[0])).name} failed (exit {result.returncode}). See the error above.')
    return result

def atomic_write(path, content):
    path = Path(path)
    if path.is_symlink():
        raise ClusterError(f'Refusing symlink: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            os.chmod(temporary, 0o600)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

def validate_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
        raise ClusterError('Name must be 1-63 lowercase letters/digits/hyphens, beginning/ending with a letter or digit.')
    return value

def validate_device(name, entry):
    validate_name(name)
    if not isinstance(entry, dict) or set(entry) - {'address', 'user', 'role', 'gpu', 'data_root', 'key'}:
        raise ClusterError(f'{name}: unknown device fields. Do not put passwords/tokens in devices.yml.')
    if not isinstance(entry.get('address'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', entry['address']):
        raise ClusterError(f'{name}: use a Tailscale IPv4 or MagicDNS hostname, without shell characters.')
    try:
        address = ipaddress.ip_address(entry['address'])
    except ValueError:
        address = None
    if address is not None and (address.version != 4 or address not in ipaddress.ip_network('100.64.0.0/10')):
        raise ClusterError(f'{name}: address must be a Tailscale IPv4, not a LAN/public address.')
    if not isinstance(entry.get('user'), str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', entry['user']):
        raise ClusterError(f'{name}: invalid SSH username.')
    if entry.get('role') not in ('server', 'worker') or type(entry.get('gpu')) is not bool:
        raise ClusterError(f'{name}: role must be server/worker and gpu must be true/false.')
    path = entry.get('data_root', '')
    if not isinstance(path, str) or not path.startswith('/') or str(PurePosixPath(path)) != path or '..' in PurePosixPath(path).parts:
        raise ClusterError(f'{name}: data_root must be a normalized absolute Linux directory.')
    allowed = ('/srv/', '/data/', '/mnt/', '/home/')
    if not path.startswith(allowed) or any(x in path for x in ('\n', '\r', '\x00')):
        raise ClusterError(f'{name}: use a data directory below /srv, /data, /mnt or /home; never system/K3s paths.')
    if 'key' in entry and (not isinstance(entry['key'], str) or any(x in entry['key'] for x in ('\n', '\r', '\x00'))):
        raise ClusterError('key must be a local file PATH, never private-key contents.')

def load_config():
    if not CONFIG.exists():
        raise ClusterError('Run setup first; devices.yml is missing.')
    try:
        config = yaml.load(CONFIG.read_text(encoding='utf-8'), Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ClusterError('devices.yml is invalid YAML.') from exc
    if not isinstance(config, dict) or set(config) - {'cluster_id', 'devices'} or not isinstance(config.get('devices'), dict):
        raise ClusterError('devices.yml must contain a devices mapping and optional cluster_id only.')
    devices = config['devices']
    for name, entry in devices.items():
        validate_device(name, entry)
    servers = [name for name, entry in devices.items() if entry['role'] == 'server']
    if devices and len(servers) != 1:
        raise ClusterError('Exactly one device must be server. V1 has no HA or server promotion.')
    addresses = [entry['address'].lower() for entry in devices.values()]
    if len(set(addresses)) != len(addresses):
        raise ClusterError('Two devices have the same address; refusing ambiguous provisioning.')
    if devices and not re.fullmatch(r'[a-f0-9]{32}', str(config.get('cluster_id', ''))):
        raise ClusterError('Invalid/missing cluster_id. Preserve the ID written by add-device.')
    return config

def receipt(name, config):
    path = STATE / 'nodes' / f'{validate_name(name)}.json'
    if not path.exists():
        raise ClusterError(f'{name}: setup not complete on this host. Rerun add-device {name}.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('cluster_id') != config['cluster_id'] or data.get('data_root') != config['devices'][name]['data_root']:
        raise ClusterError(f'{name}: local state differs from devices.yml; rerun add-device with the original config.')
    if type(data.get('uid')) is not int or data['uid'] <= 0 or type(data.get('gid')) is not int:
        raise ClusterError('Invalid workload UID/GID. Rerun add-device; workloads must use a non-root device user.')
    return data

def k(*arguments, capture=False, input_text=None, check=True):
    return run_process(['kubectl', '--kubeconfig', STATE / 'kubeconfig.yaml', '--context', CONTEXT,
                        '--request-timeout=180s', *arguments], capture=capture, input_text=input_text, check=check)

def require_cluster(config):
    if not config['devices']:
        raise ClusterError('No devices. Run add-device first.')
    server = next(name for name, entry in config['devices'].items() if entry['role'] == 'server')
    receipt(server, config)
    if not (STATE / 'kubeconfig.yaml').exists():
        raise ClusterError(f'No access file. Rerun add-device {server} to fetch it.')
    return server

def write_inventory(config):
    hosts = {}
    for name, entry in config['devices'].items():
        hosts[name] = {'ansible_host': entry['address'], 'ansible_user': entry['user'],
                       'cluster_node_name': name, 'cluster_role': entry['role'],
                       'cluster_gpu': entry['gpu'], 'cluster_data_root': entry['data_root']}
        if entry.get('key'):
            hosts[name]['ansible_ssh_private_key_file'] = entry['key']
    server_receipt = next((STATE / 'nodes' / f'{name}.json' for name, entry in config['devices'].items() if entry['role'] == 'server'), None)
    server_ip = ''
    if server_receipt and server_receipt.exists():
        server_ip = json.loads(server_receipt.read_text(encoding='utf-8'))['tailscale_ip']
    inventory = {'all': {'vars': {'cluster_id': config['cluster_id'], 'cluster_state_dir': str(STATE),
                                 'cluster_kubeconfig_path': str(STATE / 'kubeconfig.yaml'),
                                 'cluster_join_token_path': str(STATE / 'join-token'),
                                 'cluster_server_ip': server_ip},
                         'children': {'k3s_nodes': {'hosts': hosts}}}}
    path = STATE / 'inventory.yml'
    atomic_write(path, yaml.safe_dump(inventory, sort_keys=False))
    return path

def ansible(config, name, playbook, no_sudo_prompt=False, extra=None):
    arguments = ['ansible-playbook', '-i', write_inventory(config), ROOT / 'playbooks' / playbook,
                 '--limit', validate_name(name)]
    if not no_sudo_prompt:
        arguments.append('--ask-become-pass')
    if extra:
        arguments.extend(['--extra-vars', json.dumps(extra)])
    run_process(arguments)

def add_device(args):
    global STEP
    STEP = 'register device'
    config = load_config()
    name = validate_name(args.name or input('Device name (e.g. home-4090): ').strip())
    existing = config['devices'].get(name, {})
    address = args.address or existing.get('address') or input('Tailscale IP/hostname: ').strip()
    user = args.user or existing.get('user') or input('SSH user on device: ').strip()
    first = not config['devices']
    gpu = args.gpu if args.gpu is not None else existing.get('gpu', False)
    if args.gpu is None and not existing and sys.stdin.isatty():
        gpu = input('Prepare NVIDIA GPU? [y/N]: ').strip().lower() in ('y', 'yes')
    entry = {'address': address, 'user': user, 'role': existing.get('role', 'server' if first else 'worker'),
             'gpu': gpu, 'data_root': args.data_root or existing.get('data_root', '/srv/personal-compute/data')}
    if args.key or existing.get('key'):
        entry['key'] = args.key or existing['key']
    validate_device(name, entry)
    if existing and any(existing[key] != entry[key] for key in ('address', 'user', 'role', 'data_root')):
        raise ClusterError('Device identity changed. V1 refuses rename/replacement/adoption; restore the original values.')
    if any(other != name and device['address'].lower() == address.lower() for other, device in config['devices'].items()):
        raise ClusterError('Another device already uses this address.')
    if entry['role'] == 'worker':
        require_cluster(config)
        if not (STATE / 'join-token').exists():
            raise ClusterError('Join credentials missing. Rerun add-device on the server first.')
    config.setdefault('cluster_id', uuid.uuid4().hex)
    config['devices'][name] = entry
    atomic_write(CONFIG, yaml.safe_dump(config, sort_keys=False))
    say(f'Recorded {name} as {entry["role"]}' + (' with NVIDIA GPU.' if gpu else '.'))
    STEP = f'SSH to {name}'
    ssh = os.environ.get('CLUSTER_WINDOWS_SSH', 'ssh')
    probe = [ssh, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15']
    if entry.get('key'):
        probe.extend(['-i', entry['key']])
    run_process([*probe, f'{user}@{address}', 'true'], timeout=25)
    STEP = f'provision {name} (Ansible task names show the failing step)'
    ansible(config, name, 'setup.yml', args.no_sudo_prompt)
    STEP = f'confirm {name} Ready from host'
    k('wait', f'node/{name}', '--for=condition=Ready', '--timeout=180s')
    if gpu:
        install_plugin(name)
        wait_gpu(name)
    say(f'{name} ready. Next: cluster check')

def namespace(name, *, host_data=False):
    result = k('get', 'namespace', name, '--ignore-not-found', '-o', 'json', capture=True)
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if data['metadata'].get('labels', {}).get('app.kubernetes.io/managed-by') != OWNER:
            raise ClusterError(f'Namespace {name} is owned by someone else. Refusing to change it.')
        return
    document = {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': name, 'labels': {
        'app.kubernetes.io/managed-by': OWNER,
        'pod-security.kubernetes.io/enforce': 'privileged' if host_data else 'baseline'}}}
    apply(document)

def apply(document):
    k('apply', '-f', '-', input_text=json.dumps(document))

def install_plugin(name):
    k('label', f'node/{name}', 'personal-compute/gpu=true', '--overwrite')
    existing = k('get', 'daemonset', 'personal-compute-nvidia', '-n', 'kube-system', '--ignore-not-found', '-o', 'json', capture=True)
    if existing.stdout.strip() and json.loads(existing.stdout)['metadata'].get('labels', {}).get('app.kubernetes.io/managed-by') != OWNER:
        raise ClusterError('Existing GPU plugin name is unowned; refusing overwrite.')
    k('apply', '-f', ROOT / 'kubernetes/nvidia-device-plugin.yml')
    k('rollout', 'status', 'daemonset/personal-compute-nvidia', '-n', 'kube-system', '--timeout=180s')

def wait_gpu(name):
    for _ in range(36):
        data = json.loads(k('get', 'node', name, '-o', 'json', capture=True).stdout)
        if int(data['status'].get('allocatable', {}).get('nvidia.com/gpu', 0)) > 0:
            return
        time.sleep(5)
    raise ClusterError(f'{name}: GPU is not allocatable. Check driver/runtime/device-plugin logs.')

def make_job(name, device, image, command, *, gpu=False, data=None, namespace_name='personal-compute-jobs', sample_args=None):
    validate_name(name)
    validate_name(device)
    container = {'name': 'task', 'image': image, 'imagePullPolicy': 'IfNotPresent',
                 'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                               'limits': {'cpu': '2', 'memory': '4Gi'}},
                 'securityContext': {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}}}
    if command:
        container['command'] = command
    if sample_args:
        container['args'] = sample_args
    pod = {'restartPolicy': 'Never', 'nodeSelector': {'kubernetes.io/hostname': device},
           'automountServiceAccountToken': False, 'containers': [container],
           'securityContext': {'seccompProfile': {'type': 'RuntimeDefault'}}}
    if gpu:
        pod['runtimeClassName'] = 'nvidia'
        container['resources']['limits']['nvidia.com/gpu'] = 1
        container['env'] = [{'name': 'NVIDIA_DRIVER_CAPABILITIES', 'value': 'compute,utility'}]
    if data:
        pod['securityContext'].update({'runAsUser': data['uid'], 'runAsGroup': data['gid'], 'runAsNonRoot': True})
        pod['volumes'] = []
        container['volumeMounts'] = []
        for directory in ('datasets', 'checkpoints', 'results'):
            pod['volumes'].append({'name': directory, 'hostPath': {'path': f'{data["data_root"]}/{directory}', 'type': 'Directory'}})
            container['volumeMounts'].append({'name': directory, 'mountPath': f'/data/{directory}', 'readOnly': directory == 'datasets'})
    return {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': namespace_name,
            'labels': {'app.kubernetes.io/managed-by': OWNER}}, 'spec': {'backoffLimit': 0,
            'template': {'metadata': {'labels': {'app.kubernetes.io/managed-by': OWNER}}, 'spec': pod}}}

def wait_job(name, ns='personal-compute-jobs', seconds=600):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = json.loads(k('get', 'job', validate_name(name), '-n', ns, '-o', 'json', capture=True).stdout)
        conditions = {item['type']: item['status'] for item in job.get('status', {}).get('conditions', [])}
        if conditions.get('Complete') == 'True':
            k('logs', f'job/{name}', '-n', ns)
            return
        if conditions.get('Failed') == 'True' or job.get('status', {}).get('failed', 0):
            k('logs', f'job/{name}', '-n', ns, check=False)
            raise ClusterError(f'Job {name} failed. Inspect logs/events; no automatic retry of your computation.')
        time.sleep(2)
    k('get', 'pods', '-n', ns, '-o', 'wide', check=False)
    k('get', 'events', '-n', ns, '--sort-by=.lastTimestamp', check=False)
    raise ClusterError(f'Job {name} did not finish within {seconds}s. It was left running; use wait/logs/delete-job.')

def owned_job(name):
    job = json.loads(k('get', 'job', validate_name(name), '-n', 'personal-compute-jobs', '-o', 'json', capture=True).stdout)
    if job['metadata'].get('labels', {}).get('app.kubernetes.io/managed-by') != OWNER:
        raise ClusterError('Refusing to operate on a job not created by this repo.')

def debug_kubectl(arguments):
    protected = {'--context', '--kubeconfig', '--server', '-s', '--user', '--cluster', '--token',
                 '--certificate-authority', '--client-certificate', '--client-key', '--username', '--password',
                 '--insecure-skip-tls-verify', '--tls-server-name'}
    if not arguments or any(value.split('=', 1)[0] in protected or (value.startswith('-s') and not value.startswith('--')) for value in arguments):
        raise ClusterError('Use kubectl arguments without overriding this repo\'s cluster or TLS credentials.')
    k(*arguments)

def check_live(config, gpu_only=None):
    global STEP
    STEP = 'check cluster API and devices'
    server = require_cluster(config)
    k('get', '--raw=/readyz', capture=True)
    say('Cluster API ready.')
    for name in config['devices']:
        receipt(name, config)
        k('wait', f'node/{name}', '--for=condition=Ready', '--timeout=180s')
    namespace('personal-compute-smoke')
    if not gpu_only:
        STEP = 'CPU workload and cross-device Pod networking'
        documents = list(yaml.safe_load_all((ROOT / 'kubernetes/smoke-test.yml').read_text(encoding='utf-8')))
        for document in documents:
            if document['kind'] == 'Deployment':
                document['spec']['template']['spec']['nodeSelector'] = {'kubernetes.io/hostname': server}
            apply(document)
        k('rollout', 'status', 'deployment/nginx', '-n', 'personal-compute-smoke', '--timeout=180s')
        for name in config['devices']:
            job_name = 'cpu-check-' + uuid.uuid4().hex[:12]
            job = make_job(job_name, name, 'busybox:1.37.0', ['wget', '-qO-', 'http://nginx.personal-compute-smoke.svc.cluster.local'], namespace_name='personal-compute-smoke')
            k('create', '-f', '-', input_text=json.dumps(job))
            wait_job(job_name, 'personal-compute-smoke', 180)
            output = k('logs', f'job/{job_name}', '-n', 'personal-compute-smoke', capture=True).stdout
            if 'Welcome to nginx!' not in output:
                raise ClusterError(f'{name}: network test did not return the expected nginx page.')
            k('delete', 'job', job_name, '-n', 'personal-compute-smoke')
    for name, entry in config['devices'].items():
        if (gpu_only and name != gpu_only) or not entry['gpu']:
            continue
        STEP = f'actual CUDA computation on {name}'
        wait_gpu(name)
        job_name = 'gpu-check-' + uuid.uuid4().hex[:12]
        sample = make_job(job_name, name, 'nvcr.io/nvidia/k8s/cuda-sample:nbody', None, gpu=True,
                          namespace_name='personal-compute-smoke', sample_args=['nbody', '-gpu', '-benchmark', '-numbodies=1024'])
        k('create', '-f', '-', input_text=json.dumps(sample))
        wait_job(job_name, 'personal-compute-smoke', 300)
        output = k('logs', f'job/{job_name}', '-n', 'personal-compute-smoke', capture=True).stdout
        if not any(marker in output for marker in ('Performance', 'billion interactions', 'GFLOP')):
            raise ClusterError('GPU container exited but CUDA benchmark output was not recognized; inspect its logs.')
        k('delete', 'job', job_name, '-n', 'personal-compute-smoke')
    say('PASS: selected device checks completed. Dataset/checkpoints/results were not removed.')

def parser():
    cli = argparse.ArgumentParser(description='Personal compute: prepare once, then let your agent submit jobs.')
    commands = cli.add_subparsers(dest='action', required=True)
    commands.add_parser('setup', help='prepare local host tools; never provisions a device')
    add = commands.add_parser('add-device', help='record a device and provision it through SSH')
    add.add_argument('name', nargs='?')
    add.add_argument('--address')
    add.add_argument('--user')
    add.add_argument('--key')
    add.add_argument('--data-root')
    add.add_argument('--gpu', action='store_const', const=True, default=None)
    add.add_argument('--no-sudo-prompt', action='store_true')
    check = commands.add_parser('check', help='live CPU/network/GPU checks')
    check.add_argument('--static', action='store_true')
    test = commands.add_parser('test', help='rerun checks or select one GPU device')
    test.add_argument('--gpu', metavar='DEVICE')
    commands.add_parser('status', help='read-only cluster status')
    commands.add_parser('jobs', help='list agent-submitted jobs')
    debug = commands.add_parser('kubectl', help='advanced troubleshooting in this repo\'s cluster')
    debug.add_argument('arguments', nargs=argparse.REMAINDER)
    for action in ('logs', 'wait', 'delete-job'):
        command = commands.add_parser(action)
        command.add_argument('job')
        if action == 'wait':
            command.add_argument('--timeout', type=int, default=600)
    job = commands.add_parser('run', help='submit a container command to a named device')
    job.add_argument('device')
    job.add_argument('--image', required=True)
    job.add_argument('--gpu', action='store_true')
    reset = commands.add_parser('reset', help='destructive uninstall, preserves the separate data_root')
    reset.add_argument('device')
    reset.add_argument('--yes-delete-cluster', action='store_true')
    reset.add_argument('--no-sudo-prompt', action='store_true')
    return cli

def main(argv=None):
    global STEP
    if argv is None and os.environ.get('CLUSTER_ARGUMENTS_BASE64'):
        try:
            argv = json.loads(base64.b64decode(os.environ['CLUSTER_ARGUMENTS_BASE64'], validate=True).decode('utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise ClusterError('Invalid Windows launcher arguments.') from exc
        if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
            raise ClusterError('Windows launcher arguments must be a string array.')
    argv = list(sys.argv[1:] if argv is None else argv)
    payload = []
    if argv and argv[0] == 'run' and '--' in argv:
        index = argv.index('--')
        payload, argv = argv[index + 1:], argv[:index]
    args = parser().parse_args(argv)
    STATE.mkdir(parents=True, exist_ok=True)
    if STATE.is_symlink():
        raise ClusterError('Refusing symlink state directory.')
    os.chmod(STATE, 0o700)
    if args.action == 'setup':
        if not CONFIG.exists():
            atomic_write(CONFIG, (ROOT / 'devices.example.yml').read_text(encoding='utf-8'))
        load_config()
        say('Host ready. Next: cluster add-device (or provide name/address/user flags).')
        return
    if args.action == 'check' and args.static:
        STEP = 'local static tests (no SSH)'
        run_process([sys.executable, ROOT / 'tests/static_check.py'])
        run_process([sys.executable, '-m', 'unittest', 'discover', '-s', ROOT / 'tests', '-p', 'test_*.py'])
        for script in ('cluster', 'scripts/setup-host.sh'):
            run_process(['bash', '-n', ROOT / script])
        for playbook in ('setup.yml', 'reset.yml'):
            run_process(['ansible-playbook', '-i', ROOT / 'inventory/hosts.example.yml', '--syntax-check', ROOT / 'playbooks' / playbook])
        say('PASS: static checks; no live device was tested.')
        return
    if args.action == 'add-device':
        add_device(args)
        return
    config = load_config()
    if args.action == 'reset':
        STEP = 'destructive reset safety checks'
        name = validate_name(args.device)
        if not args.yes_delete_cluster:
            raise ClusterError('Reset requires --yes-delete-cluster and deletes workloads/K3s local PV data.')
        if name not in config['devices']:
            raise ClusterError('Unknown device.')
        if config['devices'][name]['role'] == 'server' and len(config['devices']) > 1:
            raise ClusterError('Reset workers first; server reset with registered workers is blocked.')
        worker = config['devices'][name]['role'] == 'worker'
        if worker:
            require_cluster(config)
            k('get', '--raw=/readyz')
        ansible(config, name, 'reset.yml', args.no_sudo_prompt, {'cluster_confirm_reset': True})
        if worker:
            # K3s stores the node password in Kubernetes; remove it for clean rejoin.
            k('delete', 'node', name, '--ignore-not-found')
        config['devices'].pop(name)
        atomic_write(CONFIG, yaml.safe_dump(config, sort_keys=False))
        for path in (STATE / 'nodes' / f'{name}.json',):
            path.unlink(missing_ok=True)
        if not config['devices']:
            for path in (STATE / 'kubeconfig.yaml', STATE / 'join-token'):
                path.unlink(missing_ok=True)
        say('Device reset. Separate data_root, NVIDIA driver/toolkit and Tailscale were preserved.')
        return
    require_cluster(config)
    STEP = args.action
    if args.action in ('check', 'test'):
        gpu_only = args.gpu if args.action == 'test' else None
        if gpu_only and (gpu_only not in config['devices'] or not config['devices'][gpu_only]['gpu']):
            raise ClusterError('Select a registered device with gpu: true.')
        check_live(config, gpu_only)
    elif args.action == 'status':
        k('get', 'nodes', '-o', 'wide')
        k('get', 'pods', '-A', '-o', 'wide')
    elif args.action == 'run':
        if args.device not in config['devices'] or not payload:
            raise ClusterError('Use run DEVICE --image IMAGE [--gpu] -- COMMAND ARGUMENTS...')
        if args.gpu and not config['devices'][args.device]['gpu']:
            raise ClusterError('Device has no GPU setup; rerun add-device NAME --gpu.')
        if not args.image or any(x.isspace() for x in args.image):
            raise ClusterError('Invalid image name.')
        data = receipt(args.device, config)
        namespace('personal-compute-jobs', host_data=True)
        name = 'task-' + uuid.uuid4().hex[:12]
        document = make_job(name, args.device, args.image, payload, gpu=args.gpu, data=data)
        k('create', '-f', '-', input_text=json.dumps(document))
        say(f'Submitted {name} on {args.device}. Use logs {name} or wait {name}.')
    elif args.action == 'jobs':
        result = k('get', 'namespace', 'personal-compute-jobs', '--ignore-not-found', '-o', 'name', capture=True)
        if result.stdout.strip():
            k('get', 'jobs', '-n', 'personal-compute-jobs', '-l', 'app.kubernetes.io/managed-by=' + OWNER)
        else:
            say('No user jobs yet.')
    elif args.action == 'kubectl':
        debug_kubectl(args.arguments)
    else:
        owned_job(args.job)
        if args.action == 'logs':
            k('logs', f'job/{args.job}', '-n', 'personal-compute-jobs')
        elif args.action == 'wait':
            if args.timeout <= 0:
                raise ClusterError('Timeout must be positive.')
            wait_job(args.job, seconds=args.timeout)
        elif args.action == 'delete-job':
            k('delete', 'job', args.job, '-n', 'personal-compute-jobs')

if __name__ == '__main__':
    try:
        main()
    except (ClusterError, ValueError, KeyError) as exc:
        print(f'[cluster] ERROR ({STEP}): {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('[cluster] Interrupted. An already-submitted job continues on the device.', file=sys.stderr)
        sys.exit(130)
