"""Dependency-free offline source/document checks."""
import ast
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]
for directory in ('scripts','tests','examples'):
    for path in (ROOT/directory).rglob('*.py'):
        try: ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
        except SyntaxError as exc: errors.append(str(exc))
        if b'\r\n' in path.read_bytes(): errors.append(f'{path.name}: expected LF')
for path in [ROOT/'device',ROOT/'device.ps1']:
    if b'\r\n' in path.read_bytes(): errors.append(f'{path.name}: expected LF')
for required in ('device','device.ps1','scripts/device_cli.py','scripts/device_remote.py','scripts/device_dashboard.py','scripts/device_workspace.py','workspace/README.md','README.md','AGENTS.md','docs/agent-usage.md','docs/validation.md'):
    if not (ROOT/required).is_file(): errors.append('Missing '+required)
for path in [ROOT/'README.md',*(ROOT/'docs').glob('*.md')]:
    for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#') and not (path.parent/target.split('#')[0]).exists(): errors.append(f'{path.name}: broken link {target}')
for obsolete in ('cluster','cluster.ps1','ansible','roles/k3s_node','playbooks/setup.yml','scripts/cluster_cli.py'):
    if (ROOT/obsolete).exists(): errors.append('Obsolete implementation: '+obsolete)
for path in (ROOT/'scripts').glob('*.py'):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Attribute) and node.func.attr=='extractall': errors.append('Unsafe extractall: '+path.name)
            for option in node.keywords:
                if option.arg=='shell' and isinstance(option.value,ast.Constant) and option.value.value: errors.append('shell=True: '+path.name)
json.loads((ROOT/'devices.example.json').read_text(encoding='utf-8'))
if '/devices.json' not in (ROOT/'.gitignore').read_text(): errors.append('Config must be ignored')
if '/workspace/*' not in (ROOT/'.gitignore').read_text(): errors.append('Workspace runtime must be ignored')
if errors:
    print('\n'.join(errors)); sys.exit(1)
print('PASS: Python syntax, launchers LF, document links, obsolete-source removal, config ignore, unsafe API checks')
