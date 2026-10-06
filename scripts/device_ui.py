"""Terminal presentation. JSON callers never use this module's rendering."""
import ctypes
import json
import os
import re
import shutil
import sys
import unicodedata

def init_terminal():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if os.name == 'nt':
        try:
            kernel = ctypes.windll.kernel32
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 4)
        except (AttributeError, OSError):
            pass

def sanitize(value):
    text = str(value)
    text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return ''.join(c if c == '\n' or ord(c) >= 32 and ord(c) != 127 else '?' for c in text)

def width(value):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 0 if unicodedata.combining(c) else 1 for c in value)

def crop(value, maximum):
    text = sanitize(value).replace('\n', ' ')
    if width(text) <= maximum:
        return text
    result = ''
    for character in text:
        if width(result + character) > maximum - 1:
            break
        result += character
    return result + '…'

class UI:
    def __init__(self, color='auto'):
        self.color = color == 'always' or color == 'auto' and sys.stdout.isatty() and not os.environ.get('NO_COLOR')
        self.columns = max(48, min(shutil.get_terminal_size((110, 24)).columns, 150))

    def paint(self, text, code='36'):
        text = sanitize(text)
        return f'\033[{code}m{text}\033[0m' if self.color else text

    def header(self, subtitle='Your devices · Your code · Direct SSH'):
        print(self.paint('╭─ DEVICE ', '1;36') + self.paint('─' * (self.columns - 10), '2;36'))
        print('│ ' + self.paint(crop(subtitle, self.columns - 2), '2'))
        print(self.paint('╰' + '─' * (self.columns - 1), '2;36'))

    def message(self, text, good=True):
        print(self.paint('✓ ' if good else '! ', '32' if good else '33') + sanitize(text))

    def table(self, headers, rows):
        if not rows:
            self.message('Nothing here yet.', False)
            return
        widths = [min(48, max(width(str(h)), *(width(sanitize(r[i])) for r in rows))) for i, h in enumerate(headers)]
        while sum(widths) + 3 * (len(headers) - 1) > self.columns:
            largest = max(range(len(widths)), key=widths.__getitem__)
            widths[largest] -= 1
        def line(row, heading=False):
            cells = []
            for value, size in zip(row, widths):
                text = crop(value, size)
                padded = text + ' ' * max(0, size - width(text))
                code = '1;36' if heading else '32' if text in ('online', 'ready', 'running', 'completed', 'active') else '31' if text in ('offline', 'failed', 'interrupted', 'blocked') else '33' if text in ('queued', 'starting', 'stopped', 'needs prepare', 'needs add') else '0'
                cells.append(self.paint(padded, code))
            print(' │ '.join(cells))
        line(headers, True)
        print(self.paint('─┼─'.join('─' * size for size in widths), '2'))
        for row in rows:
            line(row)

    def render(self, action, data):
        self.header(action.replace('_', ' ').upper())
        entry = '.\\device.ps1' if os.name == 'nt' else './device'
        if action in ('setup', 'add', 'run', 'serve', 'fetch'):
            keys = {'setup': ('ready', 'config', 'next'), 'add': ('device', 'ready', 'conda', 'next'), 'run': ('id', 'name', 'description', 'state', 'project', 'outputs', 'note'), 'serve': ('name', 'state', 'endpoint', 'listening', 'note'), 'fetch': ('id', 'downloaded_to')}[action]
            for key in keys:
                if key in data:
                    value = data[key]
                    if key == 'next':
                        value = str(value).replace('device ', entry + ' ', 1)
                    print(self.paint(key.replace('_', ' ') + ': ', '36') + sanitize(value))
            if action == 'run':
                print('\n' + self.paint('Use jobs / logs / wait to follow this ID. Host may disconnect.', '2'))
            if action == 'serve' and not data.get('listening'):
                self.message('Service is not listening yet. Read logs and check before using its endpoint.', False)
        elif action == 'env_inspect':
            for key in ('env', 'path', 'size_gib', 'size_is_partial'):
                print(self.paint(key + ': ', '36') + sanitize(data[key]))
            packages = data['packages']
            print('\n' + self.paint(f'{len(packages)} packages · showing first 20', '1;36'))
            self.table(['PACKAGE', 'VERSION', 'CHANNEL'], [[p.get('name', ''), p.get('version', ''), p.get('channel', '')] for p in packages[:20]])
            print('\n' + self.paint('Add --json for the full package inventory.', '2'))
        elif action == 'status':
            self.table(['DEVICE', 'SSH', 'READY FOR JOBS', 'RAM FREE', 'GPU'], [[d['name'], 'online' if d.get('online') else 'offline', 'ready' if d.get('ready') else 'blocked' if d.get('blocked') else ('needs prepare' if d.get('prepared') else 'needs add') if d.get('online') else '—', f"{d['memory_available_gib']:.1f} GiB" if 'memory_available_gib' in d else '—', ', '.join(g['name'] for g in d.get('gpus', [])) or '—'] for d in data['devices']])
            for d in data['devices']:
                if d.get('error'):
                    self.message(f"{d['name']}: {d['error']}", False)
            print('\n' + self.paint('SSH online ≠ free GPU. Use inspect DEVICE before running heavy work.', '2'))
        elif action in ('jobs','dashboard'):
            records=data['jobs']
            self.table(['DEVICE','NAME','STATE','PHASE','PURPOSE'],[[r.get('device',''),r.get('name',r['id']),r['state'],r.get('phase') or '—',r.get('summary') or r.get('description') or 'No description (legacy job)'] for r in records])
            if action=='dashboard':
                print('\n'+self.paint('DEVICES','1;36'))
                self.table(['DEVICE','SSH','RAM AVAILABLE','GPU VRAM USED / TOTAL','ACTIVE JOBS'],[[d['name'],'online' if d.get('online') else 'offline',f"{d.get('memory_available_gib','?')} / {d.get('memory_total_gib','?')} GiB",', '.join(f"{(g['total_mib']-g['free_mib'])/1024:.1f}/{g['total_mib']/1024:.1f} GiB" for g in d.get('gpus',[])) or '—',d.get('active_jobs','unknown')] for d in data['devices']])
            for device in data.get('devices',[]):
                if device.get('jobs_error'): self.message(device['name']+': '+device['jobs_error'],False)
            print('\n'+self.paint('Observed '+data['observed_at']+' · '+('history included' if data['include_history'] else 'active jobs only; use --all for history'),'2'))
            print(self.paint('Use job DEVICE NAME for the full ID, command, notes and recent log.','2'))
            if data['include_history']:
                print('\n'+self.paint('FULL IDS (use these when historical names repeat)','1;36'))
                for record in records:
                    print(sanitize(record['device']+' / '+record['id']+' / '+record.get('name',record['id'])))
        elif action=='job':
            for key in ('id','name','description','state','phase','progress','agent','project','env_name','gpu','elapsed_seconds','exit_code','summary','note_author','note_updated_at','observed_at','workspace','outputs'):
                if key in data: print(self.paint(key.replace('_',' ')+': ','36')+sanitize(data[key]))
            if 'command' in data: print(self.paint('command: ','36')+sanitize(json.dumps(data['command'],ensure_ascii=False)))
            if 'recent_log' in data:
                print('\n'+self.paint('RECENT LOG','1;36')); print(sanitize(data['recent_log']) or '(no output)')
            if data.get('note_updated_at'): print(self.paint('Summary/phase/progress are dated agent notes; state is checked live.','2'))
        elif action=='communication':
            print(sanitize(data['summary']))
            if data.get('snapshot'):
                snapshot=data['snapshot']
                print('\n'+self.paint('SAVED SNAPSHOT · '+snapshot['observed_at']+' · historical','1;33'))
                self.table(['DEVICE','LAST SSH','LAST ACTIVE JOBS'],[[d['name'],'online' if d.get('online') else 'offline',d.get('active_jobs','unknown')] for d in snapshot['devices']])
            self.table(['UPDATED','AGENT','TITLE'],[[n['updated_at'],n['agent'],n['title']] for n in data['notes']])
            for note in data['notes'][:10]:
                print('\n'+self.paint(note['title']+' · '+note['agent'],'1;36')); print(sanitize(note['message']))
            self.message(data['warning'],False)
        elif action == 'services':
            records = data[action]
            self.table(['ID / NAME', 'PROJECT', 'STATE', 'ENV', 'EXIT / ENDPOINT'], [[r.get('id', r.get('name', '')), r.get('project', ''), r.get('state', ''), r.get('env_name') or 'system', r.get('endpoint') or str(r.get('exit_code', '—'))] for r in records])
        elif action == 'env_list':
            self.table(['ENV', 'PATH', 'MANAGED'], [[r['name'], r['path'], 'yes' if r['managed'] else 'no'] for r in data['envs']])
            print('\n' + self.paint('Use env inspect DEVICE ENV to see packages and disk size.', '2'))
        elif action == 'logs':
            print(sanitize(data['log']) or '(no output yet)')
        elif action == 'inspect':
            self.table(['PROPERTY', 'VALUE'], [[k, data.get(k, '—')] for k in ('hostname', 'os', 'python', 'cpu_count', 'memory_available_gib', 'disk_free_gib', 'conda', 'tmux', 'linger')])
            if data.get('gpus'):
                print('\n' + self.paint('GPU', '1;36'))
                self.table(['NAME', 'VRAM FREE / TOTAL', 'UTILIZATION'], [[g['name'], f"{g['free_mib']} / {g['total_mib']} MiB", f"{g['utilization']}%"] for g in data['gpus']])
            for warning in data.get('warnings', []):
                self.message(warning, False)
        else:
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    print(self.paint(key.upper(), '1;36'))
                    print(sanitize(json.dumps(value, ensure_ascii=False, indent=2)))
                else:
                    print(self.paint(key.replace('_', ' ') + ': ', '36') + sanitize(value))
        if data.get('warning') and action not in ('communication',):
            self.message(data['warning'],False)
