"""Small, dependency-free primitives shared by host and device."""
from __future__ import annotations
import base64
import fnmatch
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
import uuid

SCHEMA = 1
OWNER = 'personal-device-cli'
MAX_ARCHIVE = 64 * 1024 * 1024
EXCLUDE = {'.git', '.cluster', '.cache', '.venv', 'venv', 'node_modules', '__pycache__', '.ssh', '.aws', '.codex', '.agents', 'datasets', 'checkpoints'}
SECRET_PATTERNS = ('.env', '.env.*', '*.pem', '*.key', 'id_rsa*', 'id_ed25519*', 'devices.json', 'devices.yml', 'kubeconfig*')

class DeviceError(Exception):
    def __init__(self, message, code='operation_failed'):
        super().__init__(message)
        self.code = code

def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', value):
        raise DeviceError('Use 1-48 lowercase letters, digits and hyphens for names.', 'invalid_name')
    return value

def clean_text(value):
    if not isinstance(value, str) or any(c in value for c in ('\0', '\r', '\n')):
        raise DeviceError('Invalid text/path: line breaks and NUL are not allowed.', 'invalid_argument')
    return value

def relative_path(value):
    clean_text(value)
    path = PurePosixPath(value)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or str(path) != value or any(':' in p or p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved for p in path.parts):
        raise DeviceError('Use a normalized relative path without .. or symlinks.', 'invalid_path')
    return path

def validate_device(value):
    if not isinstance(value, dict) or set(value) - {'address', 'user', 'port', 'key', 'conda'}:
        raise DeviceError('Device fields: address, user, port, optional key PATH and conda PATH. No passwords.', 'invalid_config')
    address = value.get('address', '')
    if not isinstance(address, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', address):
        raise DeviceError('Use a Tailscale IPv4 or MagicDNS hostname.', 'invalid_config')
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        ip = None
    if ip is not None and (ip.version != 4 or ip not in ipaddress.ip_network('100.64.0.0/10')):
        raise DeviceError('Use a Tailscale IPv4; LAN/public IPs are refused.', 'invalid_config')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', value.get('user', '')) or value['user'] == 'root':
        raise DeviceError('Use a non-root Ubuntu SSH user.', 'invalid_config')
    if type(value.get('port', 22)) is not int or not 1 <= value.get('port', 22) <= 65535:
        raise DeviceError('Invalid SSH port.', 'invalid_config')
    for key in ('key', 'conda'):
        if key in value:
            clean_text(value[key])
            if not value[key]:
                raise DeviceError(f'{key} must be a file path.', 'invalid_config')

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeviceError(f'Duplicate JSON field: {key}', 'invalid_config')
        result[key] = value
    return result

def read_json(path):
    try:
        if Path(path).is_symlink():
            raise DeviceError(f'Refusing symlink metadata: {path}', 'unsafe_path')
        return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (OSError, ValueError) as exc:
        raise DeviceError(f'Cannot read metadata {Path(path).name}: {exc}', 'invalid_metadata') from exc

def safe_path(path):
    path = Path(path).absolute()
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            raise DeviceError(f'Refusing symlink path: {candidate}', 'unsafe_path')
    return path

def atomic_json(path, value):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def pack_directory(source, *, exclusions=True):
    source = safe_path(source)
    if not source.is_dir():
        raise DeviceError('Source must be a directory.', 'invalid_path')
    stream = io.BytesIO()
    total = 0
    count = 0
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for directory, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (exclusions and d in EXCLUDE))
            for directory_name in dirs:
                if (Path(directory) / directory_name).is_symlink():
                    raise DeviceError('Sync/fetch refuses symlinks; copy real files instead.', 'unsafe_path')
            for filename in sorted(files):
                if exclusions and any(fnmatch.fnmatch(filename.lower(), pattern) for pattern in SECRET_PATTERNS):
                    continue
                path = Path(directory) / filename
                if path.is_symlink() or not path.is_file():
                    raise DeviceError('Sync/fetch accepts regular files only.', 'unsafe_path')
                total += path.stat().st_size
                count += 1
                if total > MAX_ARCHIVE or count > 20000:
                    raise DeviceError('Transfer limit: 64MiB / 20,000 files. Keep datasets/model weights on device.', 'transfer_limit')
                info = tarfile.TarInfo(path.relative_to(source).as_posix())
                info.size = path.stat().st_size
                info.mode = 0o700 if path.stat().st_mode & 0o111 else 0o600
                info.mtime = 0
                with path.open('rb') as handle:
                    archive.addfile(info, handle)
    raw = stream.getvalue()
    if len(raw) > MAX_ARCHIVE:
        raise DeviceError('Archive exceeds 64MiB. Split the transfer.', 'transfer_limit')
    return raw

def unpack(raw, destination):
    if len(raw) > MAX_ARCHIVE:
        raise DeviceError('Archive exceeds transfer limit.', 'transfer_limit')
    destination = safe_path(destination)
    total = 0
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        members = archive.getmembers()
        for member in members:
            relative_path(member.name)
            if member.name in seen or not member.isfile():
                raise DeviceError('Archive must contain unique regular files only.', 'unsafe_archive')
            seen.add(member.name)
            total += member.size
            if total > MAX_ARCHIVE or len(seen) > 20000:
                raise DeviceError('Archive exceeds unpack limit.', 'transfer_limit')
        # Validate the complete archive before creating any destination files.
        for member in members:
            if any(str(parent) in seen for parent in PurePosixPath(member.name).parents if str(parent) != '.'):
                raise DeviceError('File/directory collision in archive.', 'unsafe_archive')
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        for member in members:
            target = safe_path(destination / member.name)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.extractfile(member) as source, target.open('xb') as output:
                while chunk := source.read(65536):
                    output.write(chunk)
            os.chmod(target, 0o700 if member.mode & 0o111 else 0o600)

def archive_payload(raw):
    return {'archive': base64.b64encode(raw).decode('ascii'), 'sha256': hashlib.sha256(raw).hexdigest()}
