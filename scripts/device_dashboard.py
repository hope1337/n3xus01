"""Native terminal dashboard: polls SSH, never runs a background host server."""
from contextlib import contextmanager
import os
import select
import shutil
import sys
import time
from device_common import DeviceError
from device_ui import UI

@contextmanager
def keyboard():
    previous = None
    if os.name != 'nt':
        import termios
        import tty
        previous = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
    try:
        yield
    finally:
        if previous is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,previous)

def read_key(timeout=0.1):
    if os.name=='nt':
        import msvcrt
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if msvcrt.kbhit():
                value=msvcrt.getwch()
                if value in ('\x00','\xe0'):
                    return {'H':'k','P':'j'}.get(msvcrt.getwch(),'')
                return value.lower()
            time.sleep(.03)
        return ''
    descriptor=sys.stdin.fileno()
    ready,_,_=select.select([descriptor],[],[],timeout)
    if not ready: return ''
    value=os.read(descriptor,1).decode('ascii',errors='ignore')
    if value=='\x1b':
        ready,_,_=select.select([descriptor],[],[],.03)
        if ready:
            rest=os.read(descriptor,1).decode('ascii',errors='ignore')
            ready,_,_=select.select([descriptor],[],[],.03)
            if rest=='[' and ready: return {'A':'k','B':'j'}.get(os.read(descriptor,1).decode('ascii',errors='ignore'),'')
    return value.lower()

class Selection:
    def __init__(self): self.identity=None
    def index(self,jobs):
        return next((i for i,r in enumerate(jobs) if (r['device'],r['id'])==self.identity),0)
    def choose(self,jobs,delta=0):
        if not jobs:
            self.identity=None
            return None
        index=(self.index(jobs)+delta)%len(jobs)
        record=jobs[index]
        self.identity=(record['device'],record['id'])
        return record

def draw(data,selection,ui):
    print('\033[H\033[2J',end='')
    ui.header('LIVE DEVICES / JOBS')
    print(ui.paint('Observed '+data['observed_at']+' · SSH polling, not cached state','2'))
    ui.table(['DEVICE','SSH','RAM AVAILABLE','GPU VRAM USED / TOTAL','ACTIVE JOBS'],[[d['name'],'online' if d.get('online') else 'offline',f"{d.get('memory_available_gib','?')} / {d.get('memory_total_gib','?')} GiB",', '.join(f"{(g['total_mib']-g['free_mib'])/1024:.1f}/{g['total_mib']/1024:.1f} GiB" for g in d.get('gpus',[])) or '—', d.get('active_jobs','unknown')] for d in data['devices'][:6]])
    jobs=data['jobs']; selection.choose(jobs)
    current=selection.index(jobs)
    budget=max(1,shutil.get_terminal_size((110,24)).lines-14-min(6,len(data['devices'])))
    start=max(0,current-budget+1)
    print('\n'+ui.paint('JOBS · '+('including history' if data['include_history'] else 'active only'),'1;36'))
    ui.table(['','DEVICE','NAME','STATE','PHASE / PURPOSE'],[['›' if selection.identity==(r['device'],r['id']) else '',r['device'],r.get('name',r['id']),r['state'],(r.get('phase','')+' · ' if r.get('phase') else '')+(r.get('summary') or r.get('description') or 'No description (legacy job)')] for r in jobs[start:start+budget]])
    print('\n'+ui.paint('j/k select · i details · l logs · s stop · d delete · h history · r refresh · q quit','2'))
    print(ui.paint('Notes/progress are reported by agents, not automatic execution status.','2'))
    for device in data['devices']:
        if device.get('jobs_error'): ui.message(device['name']+': '+device['jobs_error'],False)
    sys.stdout.flush()

def watch(args,fetch,execute,parse):
    if args.interval<1: raise DeviceError('Dashboard interval must be >=1 second.')
    ui=UI(args.color); selection=Selection()
    print('\033[?1049h\033[?25l',end='',flush=True)
    try:
        with keyboard():
            refresh=True; data=None; deadline=0
            while True:
                if refresh or time.monotonic()>=deadline:
                    data=fetch(); deadline=time.monotonic()+args.interval; refresh=False
                    draw(data,selection,ui)
                key=read_key(min(.2,max(.01,deadline-time.monotonic())))
                if key in ('q','\x03'): return
                if key=='r': refresh=True
                elif key=='h': args.all=not args.all; refresh=True
                elif key in ('j','k'):
                    selection.choose(data['jobs'],1 if key=='j' else -1); draw(data,selection,ui)
                elif key in ('i','l','s','d'):
                    chosen=selection.choose(data['jobs'])
                    if chosen is None: continue
                    action={'i':'job','l':'logs','s':'stop','d':'clean'}[key]
                    command=[action,chosen['device'],chosen['id']]
                    print('\033[H\033[2J',end='')
                    ui.header(chosen['device']+' / '+chosen.get('name',chosen['id']))
                    if key in ('s','d'):
                        ui.message('Stop this job?' if key=='s' else 'Delete its workspace, outputs and logs? Fetch results first.',False)
                        print('Press y to confirm; any other key cancels.',flush=True)
                        if read_key(3600)!='y': refresh=True; continue
                        if key=='d': command.append('--yes')
                    try:
                        action,result=execute(parse(command)); ui.render(action,result)
                    except DeviceError as exc: ui.message(str(exc),False)
                    print('\nPress any key to return.',flush=True); read_key(3600); refresh=True
    finally:
        print('\033[?25h\033[?1049l',end='',flush=True)

def follow_logs(args,execute):
    if args.json: raise DeviceError('--follow is a terminal view, not JSON.')
    if not sys.stdout.isatty(): raise DeviceError('--follow requires a terminal. Use logs snapshots when redirecting output.')
    ui=UI(args.color); previous=None
    while True:
        _,data=execute(args)
        if data['log']!=previous:
            if sys.stdout.isatty(): print('\033[H\033[2J',end='')
            ui.render('logs',data); previous=data['log']
        time.sleep(2)
