"""Local source/security checks. Never invokes SSH or a real Kubernetes API."""
from pathlib import Path
import configparser
import importlib.util
import ipaddress
import json
import re
import subprocess
import sys
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cluster_cli', ROOT / 'scripts/cluster_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

def load(path):
    return yaml.load((ROOT / path).read_text(encoding='utf-8'), Loader=cli.UniqueLoader)

def main():
    source_dirs = ('roles', 'playbooks', 'inventory', 'kubernetes', '.github')
    files = [ROOT / 'devices.example.yml']
    for directory in source_dirs:
        files.extend((ROOT / directory).rglob('*.yml'))
    for path in files:
        list(yaml.load_all(path.read_text(encoding='utf-8'), Loader=cli.UniqueLoader))
    for path in (ROOT / 'cluster', ROOT / 'scripts/setup-host.sh', ROOT / 'cluster.ps1'):
        assert b'\r' not in path.read_bytes(), f'CRLF: {path}'
    config = configparser.ConfigParser()
    config.read(ROOT / 'ansible/ansible.cfg')
    assert (ROOT / 'ansible' / config['defaults']['roles_path']).resolve() == ROOT / 'roles'
    assert (ROOT / 'ansible' / config['defaults']['inventory']).resolve().is_file()
    assert config['defaults']['host_key_checking'] == 'True'

    defaults = load('roles/k3s_node/defaults/main.yml')
    assert re.fullmatch(r'v\d+\.\d+\.\d+\+k3s\d+', defaults['k3s_version'])
    tasks = load('roles/k3s_node/tasks/main.yml')
    imports = [task['ansible.builtin.import_tasks'] for task in tasks]
    assert imports[0] == 'preflight.yml' and 'gpu.yml' in imports and 'data.yml' in imports
    for name in imports:
        assert (ROOT / 'roles/k3s_node/tasks' / name).is_file()
    env = Environment(undefined=StrictUndefined)
    env.filters['to_json'] = json.dumps
    template = env.from_string((ROOT / 'roles/k3s_node/templates/config.yaml.j2').read_text(encoding='utf-8'))
    for role in ('server', 'worker'):
        values = dict(cluster_node_name='test-device', cluster_tailscale_ip='100.101.102.103', cluster_role=role, cluster_server_ip='100.101.102.104')
        rendered = yaml.safe_load(template.render(**values))
        assert rendered['node-ip'] == values['cluster_tailscale_ip']
        assert rendered['flannel-iface'] == 'tailscale0'
        assert 'read-only-port=0' in rendered['kubelet-arg']
        if role == 'server':
            for key in ('bind-address', 'advertise-address'):
                assert ipaddress.ip_address(rendered[key]) in ipaddress.ip_network('100.64.0.0/10')
            assert {'traefik', 'servicelb', 'metrics-server'} <= set(rendered['disable'])
        else:
            assert rendered['server'] == 'https://100.101.102.104:6443'
            assert 'token' not in rendered and rendered['token-file'] == '/etc/rancher/k3s/join-token'

    for filename in ('kubeconfig.yml', 'install.yml'):
        for task in load(f'roles/k3s_node/tasks/{filename}'):
            if any(word in task['name'].lower() for word in ('credential', 'token', 'kubeconfig')) and ('ansible.builtin.slurp' in task or 'ansible.builtin.copy' in task):
                assert task.get('no_log') is True, task['name']
    plugin = load('kubernetes/nvidia-device-plugin.yml')
    pod = plugin['spec']['template']['spec']
    assert pod['runtimeClassName'] == 'nvidia'
    assert pod['nodeSelector'] == {'personal-compute/gpu': 'true'}
    assert pod['containers'][0]['env'][0]['value'] == 'true'
    assert pod['volumes'][0]['hostPath']['path'] == '/var/lib/kubelet/device-plugins'
    smoke = list(yaml.safe_load_all((ROOT / 'kubernetes/smoke-test.yml').read_text(encoding='utf-8')))
    assert next(doc for doc in smoke if doc['kind'] == 'Service')['spec']['type'] == 'ClusterIP'

    preflight = load('roles/k3s_node/tasks/preflight.yml')
    route_validator = next(t['ansible.builtin.command']['argv'][2] for t in preflight if t['name'].startswith('Verify default Pod'))
    cases = [([{'dst': 'default', 'dev': 'eth0'}], 'fresh', True),
             ([{'dst': '10.0.0.0/8', 'dev': 'tailscale0'}], 'fresh', False),
             ([{'dst': '10.42.0.0/24', 'dev': 'cni0'}], 'fresh', False),
             ([{'dst': '10.42.0.0/24', 'dev': 'cni0'}], 'owned', True),
             ([{'dst': '10.43.0.9', 'dev': 'tun0'}], 'owned', False)]
    for routes, owner, expected in cases:
        result = subprocess.run([sys.executable, '-c', route_validator, json.dumps(routes), owner], capture_output=True)
        assert (result.returncode == 0) == expected
    install = load('roles/k3s_node/tasks/install.yml')
    guard = next(t['ansible.builtin.replace'] for t in install if 'ansible.builtin.replace' in t)
    before = '    tailscale set --advertise-routes=\n'
    after = re.sub(guard['regexp'], guard['replace'], before, flags=re.MULTILINE)
    assert after != before and 'tailscale set' not in after
    assert re.sub(guard['regexp'], guard['replace'], after, flags=re.MULTILINE) == after
    assert all('cluster_data_root' not in str(t) for t in load('playbooks/reset.yml')[0]['tasks']), 'Reset must never delete dataset directories'
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for command in ('setup', 'add-device', 'check', 'run'):
        assert f'./cluster {command}' in readme and f'.\\cluster.ps1 {command}' in readme
    assert (ROOT / 'AGENTS.md').is_file()
    ignored = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert '/devices.yml' in ignored and '/.cluster/' in ignored
    print(f'PASS: {len(files)} YAML files, server/worker templates, secret handling, GPU/runtime, routes, reset/data separation and documentation paths.')

if __name__ == '__main__':
    main()
