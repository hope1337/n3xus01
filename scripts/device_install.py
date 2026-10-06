"""User-only command registration; no pip, admin, shell eval or network."""
import base64
import json
import ntpath
import os
from pathlib import Path
import shlex
import sys
import uuid

from device_common import DeviceError, atomic_json, clean_text, safe_path

MARKER = 'personal-device-cli launcher v1 '
BEGIN = '# >>> personal-device-cli PATH >>>'
END = '# <<< personal-device-cli PATH <<<'


def platform_name():
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform.startswith('linux'):
        return 'linux'
    raise DeviceError('Command registration supports Windows and Ubuntu/Linux.')


def directory(platform):
    if platform == 'windows':
        location = os.environ.get('LOCALAPPDATA')
        if not location:
            raise DeviceError('LOCALAPPDATA is unavailable; run setup --no-register.')
        return safe_path(Path(location) / 'PersonalDevice/bin')
    return safe_path(Path.home() / '.local/bin')


def windows_path(value=None):
    """Only HKCU user PATH; preserve its type and all unrelated entries."""
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        try:
            current, kind = winreg.QueryValueEx(key, 'Path')
        except FileNotFoundError:
            current, kind = '', winreg.REG_EXPAND_SZ
        if not isinstance(current, str) or kind not in (winreg.REG_SZ,winreg.REG_EXPAND_SZ):
            raise DeviceError('User PATH has an unsupported registry type; nothing replaced.')
        if value is None:
            return current
        if current != value:
            winreg.SetValueEx(key,'Path',0,kind,value)
    # Explorer notices the new user environment; current parent shells keep theirs.
    try:
        import ctypes
        result = ctypes.c_size_t()
        ctypes.windll.user32.SendMessageTimeoutW(0xffff,0x1a,0,'Environment',2,1000,ctypes.byref(result))
    except (AttributeError,OSError):
        pass


def path_key(value):
    return ntpath.normcase(ntpath.normpath(os.path.expandvars(value.strip().strip('"'))))


def templates(platform, metadata, command='n3xus'):
    encoded = base64.b64encode(json.dumps(metadata,ensure_ascii=False,sort_keys=True).encode('utf-8')).decode('ascii')
    repo = clean_text(metadata['repo'])
    python = clean_text(metadata['python'])
    if platform == 'linux':
        text = '#!/bin/sh\n# '+MARKER+encoded+'\nexec '+shlex.quote(python)+' '+shlex.quote(str(Path(repo)/'scripts/device_cli.py'))+' "$@"\n'
        return {command:text.encode('utf-8')}
    quote = lambda value: "'"+value.replace("'","''")+"'"
    script = '# '+MARKER+encoded+'\n$ErrorActionPreference = \'Stop\'\n'
    script += '$previous = $env:DEVICE_PYTHON_EXECUTABLE\ntry {\n'
    script += '    $env:DEVICE_PYTHON_EXECUTABLE = '+quote(python)+'\n'
    script += '    & '+quote(str(Path(repo)/(command+'.ps1')))+' @args\n    $deviceExit = $LASTEXITCODE\n'
    script += '} finally { $env:DEVICE_PYTHON_EXECUTABLE = $previous }\nexit $deviceExit\n'
    # PowerShell 5.1 needs a BOM when paths contain non-ASCII characters.
    cmd = '@echo off\r\nREM '+MARKER+encoded+'\r\nsetlocal DisableDelayedExpansion\r\npowershell.exe -NoProfile -File "%~dp0'+command+'.ps1" %*\r\nexit /b %errorlevel%\r\n'
    return {command+'.ps1':script.encode('utf-8-sig'),command+'.cmd':cmd.encode('ascii')}


def existing(platform, target, command='n3xus'):
    files = (command+'.ps1',command+'.cmd') if platform == 'windows' else (command,)
    metadata = None
    for filename in files:
        path = safe_path(target/filename)
        if not path.exists():
            continue
        if not path.is_file():
            raise DeviceError('Launcher destination is not a regular file: '+str(path))
        raw = path.read_bytes()
        try:
            lines = raw.decode('utf-8-sig').splitlines()
            line = lines[1] if platform == 'linux' or filename.endswith('.cmd') else lines[0]
            prefix = 'REM ' if filename.endswith('.cmd') else '# '
            if not line.startswith(prefix+MARKER):
                raise ValueError('not owned')
            candidate = json.loads(base64.b64decode(line[len(prefix+MARKER):],validate=True).decode('utf-8'))
            if set(candidate) != {'repo','python','path_added'} or type(candidate['path_added']) is not bool:
                raise ValueError('metadata changed')
            if not all(isinstance(candidate[k],str) and Path(candidate[k]).is_absolute() for k in ('repo','python')):
                raise ValueError('invalid paths')
            if templates(platform,candidate,command)[filename] != raw or metadata is not None and candidate != metadata:
                raise ValueError('manual modifications')
        except (ValueError,TypeError,KeyError,IndexError,UnicodeError) as exc:
            raise DeviceError('Refusing to overwrite/remove an unowned or modified launcher: '+str(path),'launcher_conflict') from exc
        metadata = candidate
    return metadata


def legacy_registration(platform,target,repo):
    """Migrate only exact owned device launchers from this checkout."""
    files = ('device.ps1','device.cmd') if platform == 'windows' else ('device',)
    for filename in files:
        path=target/filename
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
            return None
        path=safe_path(path)
        if path.exists():
            if not path.is_file(): return None
            text=path.read_bytes().decode('utf-8-sig',errors='replace').splitlines()
            position=1 if platform=='linux' or filename.endswith('.cmd') else 0
            prefix='REM ' if filename.endswith('.cmd') else '# '
            if len(text)<=position or not text[position].startswith(prefix+MARKER):
                return None  # Unrelated commands are never adopted/deleted.
    legacy=existing(platform,target,'device')
    return legacy if legacy and safe_path(legacy['repo'])==safe_path(repo) else None


def profile_block(target):
    return BEGIN+'\ncase ":$PATH:" in\n  *:'+shlex.quote(str(target))+':*) ;;\n  *) export PATH='+shlex.quote(str(target))+':"$PATH" ;;\nesac\n'+END+'\n'


def profiles(target):
    block = profile_block(target).encode('utf-8')
    result = []
    for filename in ('.profile','.bashrc'):
        path = safe_path(Path.home()/filename)
        content = path.read_bytes() if path.exists() else b''
        if BEGIN.encode() in content or END.encode() in content:
            if content.count(block) != 1 or content.count(BEGIN.encode()) != 1 or content.count(END.encode()) != 1:
                raise DeviceError('Managed PATH block was edited; preserve it and resolve manually: '+str(path),'launcher_conflict')
        result.append((path,content,block))
    return result


def write_file(path, content, mode):
    path = safe_path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary = safe_path(path.with_name(path.name+'.tmp-'+uuid.uuid4().hex))
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def register(repo, workspace):
    platform = platform_name()
    target = directory(platform)
    old = existing(platform,target)
    legacy = legacy_registration(platform,target,repo)
    current = windows_path() if platform == 'windows' else os.environ.get('PATH','')
    normalize = path_key if platform == 'windows' else lambda p: os.path.normpath(os.path.expandvars(p))
    missing = normalize(str(target)) not in [normalize(p) for p in current.split(';' if platform == 'windows' else ':') if p]
    metadata = {'repo':str(safe_path(repo)), 'python':str(safe_path(Path(sys.executable).resolve())), 'path_added':missing or bool(old and old['path_added']) or bool(legacy and legacy['path_added'])}
    changes = profiles(target) if platform == 'linux' else []
    # Complete conflict/symlink checks before writing any launchers or startup files.
    for filename,content in templates(platform,metadata).items():
        path = safe_path(target/filename)
        if not path.exists() or path.read_bytes() != content:
            write_file(path,content,0o755)
    if platform == 'windows' and missing:
        windows_path(current+(';' if current and not current.endswith(';') else '')+str(target))
    elif platform == 'linux' and missing:
        for path,content,block in changes:
            if block not in content:
                mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
                write_file(path,content+(b'\n' if content and not content.endswith(b'\n') else b'')+block,mode)
    if legacy:
        for filename in templates(platform,legacy,'device'):
            safe_path(target/filename).unlink(missing_ok=True)
    receipt = {'registered':True,'command':'n3xus','migrated_device_command':bool(legacy),'platform':platform,'bin':str(target),'repo':metadata['repo'],'python':metadata['python'],
               'note':'Use n3xus from any folder. New terminals load user PATH; existing Ubuntu terminals: source ~/.bashrc.'}
    atomic_json(workspace/'config'/('cli-registration-'+platform+'.json'),receipt)
    return receipt


def unregister(repo, workspace):
    platform = platform_name()
    target = directory(platform)
    old = existing(platform,target)
    if old is None:
        return {'registered':False,'note':'No owned command launcher is installed. Device config and remote work were kept.'}
    if safe_path(old['repo']) != safe_path(repo):
        raise DeviceError('The global command belongs to another checkout; run unregister there.','launcher_conflict')
    current = windows_path() if platform == 'windows' else ''
    changes = profiles(target) if platform == 'linux' else []
    receipt = safe_path(workspace/'config'/('cli-registration-'+platform+'.json'))
    for filename in templates(platform,old):
        safe_path(target/filename).unlink(missing_ok=True)
    if platform == 'windows' and old['path_added']:
        windows_path(';'.join(p for p in current.split(';') if path_key(p) != path_key(str(target))))
    elif platform == 'linux':
        for path,content,block in changes:
            if block in content:
                write_file(path,content.replace(block,b'',1),path.stat().st_mode & 0o777)
    receipt.unlink(missing_ok=True)
    return {'registered':False,'bin':str(target),'note':'Command unregistered. Config, datasets and remote jobs/services were kept; existing shells may still have the old PATH.'}
