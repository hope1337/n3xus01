"""Offline safety/transport tests: never SSH or mutate a real device."""
import base64
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import device_cli as cli
import device_common as common
import device_remote as remote
import device_ui as ui

@contextmanager
def unit_lock(root):
    remote.require_owned(root)
    yield

class Temporary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='device-test-')
        self.path = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def owned(self):
        root = self.path / ('a' * 32)
        root.mkdir()
        common.atomic_json(root / 'owner.json', {'owner': common.OWNER, 'schema': 1, 'profile': root.name, 'uid': 1000})
        for part in ('jobs', 'services', 'envs', 'projects'):
            (root / part).mkdir()
        common.atomic_json(root / 'envs.json', {})
        return root

class ArchiveTests(Temporary):
    def test_sync_excludes_secrets_and_dataset_not_source(self):
        source = self.path / 'source'; source.mkdir()
        for item in ('main.py', '.env', 'devices.json', 'private.pem'):
            (source / item).write_text('data')
        (source / 'datasets').mkdir(); (source / 'datasets/a').write_text('data')
        raw = common.pack_directory(source)
        self.assertEqual(raw, common.pack_directory(source))
        destination = self.path / 'dest'; common.unpack(raw, destination)
        self.assertEqual([p.name for p in destination.iterdir()], ['main.py'])
        self.assertTrue((source / '.env').exists())
    def test_dangerous_tar_rejected_before_destination_created(self):
        for filename, kind in (('../escape', tarfile.REGTYPE), ('C:/escape', tarfile.REGTYPE), ('NUL.txt', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            with self.subTest(filename=filename):
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode='w') as archive:
                    item = tarfile.TarInfo(filename); item.type = kind; item.size = 1 if kind == tarfile.REGTYPE else 0
                    archive.addfile(item, io.BytesIO(b'x'))
                destination = self.path / 'dest'
                with self.assertRaises(common.DeviceError): common.unpack(buffer.getvalue(), destination)
                self.assertFalse(destination.exists())
    def test_download_refuses_existing_files(self):
        source = self.path / 'source'; source.mkdir(); (source / 'main.py').write_text('x')
        with self.assertRaises(FileExistsError): common.unpack(common.pack_directory(source), source)
        self.assertEqual((source / 'main.py').read_text(), 'x')
    def test_limits(self):
        with patch.object(common, 'MAX_ARCHIVE', 1):
            source = self.path / 'source'; source.mkdir(); (source / 'file').write_text('too big')
            with self.assertRaises(common.DeviceError): common.pack_directory(source)
    def test_symlink_refused(self):
        source = self.path / 'source'; source.mkdir(); (source / 'real').write_text('x')
        try: (source / 'link').symlink_to(source / 'real')
        except OSError: self.skipTest('OS does not grant symlink creation')
        with self.assertRaises(common.DeviceError): common.pack_directory(source)
    def test_duplicate_metadata(self):
        path = self.path / 'bad.json'; path.write_text('{"x":1,"x":2}')
        with self.assertRaises(common.DeviceError): common.read_json(path)
    def test_public_ip_root_and_password_refused(self):
        for entry in ({'address':'8.8.8.8','user':'hope'}, {'address':'100.71.182.15','user':'root'}, {'address':'sekiro','user':'hope','password':'x'}):
            with self.assertRaises(common.DeviceError): common.validate_device(entry)

class HostTests(Temporary):
    def test_setup_idempotent_preserves_profile(self):
        with patch.object(cli, 'CONFIG', self.path / 'devices.json'), patch.object(cli.shutil, 'which', return_value='ssh'):
            cli.execute(cli.arguments(['setup'])); first = cli.config()
            cli.execute(cli.arguments(['setup'])); self.assertEqual(first, cli.config())
    def test_transport_literal_argv_and_strict_ssh(self):
        response = subprocess.CompletedProcess([], 0, json.dumps({'schema':1,'ok':True,'data':{'id':'ok'}}).encode(), b'')
        payload = ['python', '-c', 'print("$HOME; ü")', 'space argument', '--json']
        with patch.object(cli.shutil, 'which', return_value='ssh.exe'), patch.object(cli.subprocess, 'run', return_value=response) as run:
            cli.remote({'address':'sekiro','user':'hope'}, 'a'*32, 'run', command=payload)
        arguments = run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=yes', arguments)
        self.assertIn('BatchMode=yes', arguments)
        self.assertNotIn(payload[2], arguments[-1])
        envelope = json.loads(run.call_args.kwargs['input'])
        self.assertEqual(envelope['request']['command'], payload)
        self.assertNotIn('shell', run.call_args.kwargs)
    def test_payload_json_flag_is_not_cli_flag(self):
        args = cli.arguments(['run','sekiro','hello','--env','ml','--json','--','python','--json'])
        self.assertTrue(args.json); self.assertEqual(args.command, ['python','--json'])
    def test_json_errors_no_traceback_or_prompt(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer): code = cli.main(['does-not-exist','--json'])
        self.assertEqual(code, 1); self.assertEqual(json.loads(buffer.getvalue())['error']['code'], 'invalid_argument')
    def test_noninteractive_mutation_requires_explicit_approval(self):
        args = cli.arguments(['env','create','sekiro','new-env','--json'])
        with self.assertRaises(common.DeviceError) as caught: cli.confirm(args, 'create?')
        self.assertEqual(caught.exception.code, 'confirmation_required')
    def test_timeout_does_not_auto_retry(self):
        with patch.object(cli.shutil, 'which', return_value='ssh'), patch.object(cli.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ssh', 35)) as run:
            with self.assertRaises(common.DeviceError) as caught: cli.remote({'address':'sekiro','user':'hope'}, 'a'*32, 'run')
        self.assertEqual(caught.exception.code, 'ssh_timeout'); self.assertEqual(run.call_count, 1)
    def test_real_bootstrap_protocol_without_ssh(self):
        body = {'common':(ROOT/'scripts/device_common.py').read_text(encoding='utf-8'), 'helper':(ROOT/'scripts/device_remote.py').read_text(encoding='utf-8'), 'request':{'operation':'probe','profile':'a'*32}}
        with tempfile.TemporaryDirectory() as home:
            environment = dict(os.environ, HOME=home, USERPROFILE=home)
            result = subprocess.run([sys.executable,'-c',cli.BOOTSTRAP], input=json.dumps(body).encode(), capture_output=True,env=environment,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        response=json.loads(result.stdout); self.assertFalse(response['ok'])
        # No SSH_CONNECTION/device mutation; Linux rejects non-tailnet, Windows rejects OS.
        self.assertIn(response['error']['code'], ('unsupported_device','not_tailnet'))
    def test_status_retains_offline_device(self):
        conf = {'profile':'a'*32,'devices':{'offline':{'address':'sekiro','user':'hope'}}}
        with patch.object(cli, 'remote', side_effect=common.DeviceError('unreachable','ssh_failed')):
            self.assertFalse(cli.status(conf)['devices'][0]['online'])
    def test_fetch_existing_target_does_not_contact_device(self):
        args = cli.arguments(['fetch','sekiro','job-'+'a'*16,'--output', str(self.path)])
        with patch.object(cli, 'remote') as call:
            with self.assertRaises(common.DeviceError): cli.fetch_files(args, {}, 'a'*32)
            call.assert_not_called()

class RemoteSafetyTests(Temporary):
    def setUp(self):
        super().setUp()
        self.uid = patch.object(remote.os, 'getuid', return_value=1000, create=True); self.uid.start()
        self.root = self.owned()
        self.root_patch = patch.object(remote, 'root_for', return_value=self.root); self.root_patch.start()
        self.lock_patch = patch.object(remote, 'locked', unit_lock); self.lock_patch.start()
    def tearDown(self):
        self.lock_patch.stop(); self.root_patch.stop(); self.uid.stop(); super().tearDown()
    def test_conda_create_failure_remains_owned_for_cleanup(self):
        request = {'operation':'env_create','env':'ml','approved':True,'python':'3.11'}
        with patch.object(remote, 'conda_json', side_effect=common.DeviceError('channel failed')):
            with self.assertRaises(common.DeviceError): remote.env_change(request)
        self.assertIn('ml', common.read_json(self.root / 'envs.json'))
        with patch.object(remote, 'active_env_users', return_value=[]):
            remote.env_change({'operation':'env_remove','env':'ml','approved':True})
        self.assertEqual(common.read_json(self.root / 'envs.json'), {})
    def test_no_env_mutation_without_confirmation(self):
        with patch.object(remote, 'conda_json') as conda:
            with self.assertRaises(common.DeviceError): remote.env_change({'operation':'env_create','env':'ml'})
            conda.assert_not_called()
    def test_external_env_cannot_be_removed(self):
        outside = self.path / 'external'; outside.mkdir(); (outside / 'valuable').write_text('keep')
        with self.assertRaises(common.DeviceError): remote.env_change({'operation':'env_remove','env':str(outside),'approved':True})
        self.assertEqual((outside / 'valuable').read_text(), 'keep')
    def test_tampered_managed_prefix_cannot_delete_outside(self):
        common.atomic_json(self.root / 'envs.json', {'ml':str(self.path)})
        with self.assertRaises(common.DeviceError): remote.env_change({'operation':'env_remove','env':'ml','approved':True})
        self.assertTrue(self.path.exists())
    def test_busy_env_protected(self):
        with patch.object(remote, 'resolve_env', return_value='/env/ml'), patch.object(remote, 'conda_json', return_value={'root_prefix':'/base'}), patch.object(remote, 'active_env_users', return_value=['job-running']):
            with self.assertRaises(common.DeviceError) as caught:
                remote.env_change({'operation':'env_install','env':'ml','approved':True,'packages':['numpy']})
        self.assertEqual(caught.exception.code, 'env_busy')
    def test_base_protected(self):
        with patch.object(remote, 'resolve_env', return_value='/base'), patch.object(remote, 'conda_json', return_value={'root_prefix':'/base'}):
            with self.assertRaises(common.DeviceError) as caught:
                remote.env_change({'operation':'env_install','env':'base','approved':True,'packages':['numpy']})
        self.assertEqual(caught.exception.code, 'base_protected')
    def test_pid_reuse_and_reboot_do_not_signal(self):
        identifier = 'job-' + 'b'*16; directory = self.root / 'jobs' / identifier; directory.mkdir()
        common.atomic_json(directory / 'job.json', {'owner':common.OWNER,'id':identifier,'state':'running','pid':42,'pid_start':'old','boot_id':'oldboot'})
        with patch.object(remote, 'boot_id', return_value='newboot'), patch.object(remote.os, 'killpg', create=True) as kill:
            remote.stop_job({'id':identifier}); kill.assert_not_called()
        record = {'boot_id':'same','pid':42,'pid_start':'old'}
        with patch.object(remote, 'boot_id', return_value='same'), patch.object(remote, 'pid_start', return_value='new'):
            self.assertFalse(remote.alive(record))
    def test_service_requires_tailnet_placeholders(self):
        with self.assertRaises(common.DeviceError) as caught:
            remote.serve({'name':'api','command':['python','main.py','--host','0.0.0.0'],'port':8088})
        self.assertEqual(caught.exception.code, 'unsafe_bind')
    def test_ssh_destination_verified_not_hostname_only(self):
        with patch.dict(os.environ, {'SSH_CONNECTION':'1.2.3.4 2222 192.168.1.5 22'}):
            with self.assertRaises(common.DeviceError): remote.tailnet_ip()
    def test_gpu_validation(self):
        result = subprocess.CompletedProcess([],0,'0\n1\n','')
        with patch.object(remote,'command', return_value=result):
            self.assertEqual(remote.gpu_selection({'gpu':1}),1)
            with self.assertRaises(common.DeviceError): remote.gpu_selection({'gpu':2})
    def test_unit_quote_and_literal_command(self):
        self.assertEqual(remote.validate_argv(['python','-c','print("$HOME")']), ['python','-c','print("$HOME")'])
        quoted = remote.systemd_quote('/home/a $HOME/%/"path')
        self.assertIn('$$HOME', quoted); self.assertIn('%%', quoted); self.assertIn('\\"', quoted)
    def test_immutable_revisions_do_not_replace_running_workspace(self):
        source = self.path / 'code'; source.mkdir(); (source / 'main.py').write_text('old')
        remote.sync_project({'project':'hello', **common.archive_payload(common.pack_directory(source))})
        remote.project_snapshot(self.root, 'hello', self.path / 'snapshot')
        (source / 'main.py').write_text('new')
        remote.sync_project({'project':'hello', **common.archive_payload(common.pack_directory(source))})
        self.assertEqual((self.path / 'snapshot/main.py').read_text(), 'old')
    def test_modified_service_unit_cannot_be_stopped_or_deleted(self):
        service = 'api'; directory = self.root / 'services' / service; directory.mkdir()
        unit = remote.unit_name(self.root,service); path = self.path / unit; path.write_text('changed')
        common.atomic_json(directory / 'service.json', {'owner':common.OWNER,'name':service,'unit':unit,'unit_path':str(path),'unit_sha256':'wrong'})
        with patch.object(remote, 'user_systemctl') as control:
            with self.assertRaises(common.DeviceError): remote.service_action({'name':service,'action':'remove','approved':True})
            control.assert_not_called()
        self.assertTrue(path.exists())

class UITests(unittest.TestCase):
    def test_escape_sanitization(self):
        self.assertEqual(ui.sanitize('\x1b[31mred\x1b[0m'), 'red')
        self.assertNotIn('\x1b',ui.sanitize('\x1b]0;bad title\x07hello'))
    def test_color_and_plain_modes(self):
        for mode in ('always','never'):
            with self.subTest(mode=mode):
                output = io.StringIO()
                with redirect_stdout(output): ui.UI(mode).render('status',{'devices':[{'name':'lab','online':False}]})
                self.assertEqual('\x1b[' in output.getvalue(), mode=='always')
                self.assertIn('offline',output.getvalue())
    def test_narrow_table_fits(self):
        screen = ui.UI('never'); screen.columns = 48
        output = io.StringIO()
        with redirect_stdout(output): screen.table(['DEVICE','SSH','STATE','RAM','GPU'], [['long-device-name','online','ready','123GiB','Very long GPU name']])
        self.assertTrue(all(ui.width(line)<=48 for line in output.getvalue().splitlines()))

@unittest.skipUnless(os.name == 'nt', 'native Windows launcher')
class WindowsLauncherTests(Temporary):
    def test_native_powershell_preserves_argv(self):
        shutil.copy2(ROOT / 'device.ps1', self.path / 'device.ps1')
        (self.path / 'scripts').mkdir()
        (self.path / 'scripts/device_cli.py').write_text("import os,base64,json; print(json.dumps(json.loads(base64.b64decode(os.environ['DEVICE_ARGUMENTS_BASE64']).decode('utf-8'))))",encoding='utf-8')
        candidates = [shutil.which('powershell.exe'), shutil.which('pwsh.exe')]
        for executable in filter(None, candidates):
            with self.subTest(executable=executable):
                script = "& '" + str(self.path / 'device.ps1').replace("'","''") + "' --json run sekiro hello --env ml -- python -c 'print(\"$HOME; ü\")' 'a b'"
                result = subprocess.run([executable,'-NoProfile','-Command',script],capture_output=True, text=True, encoding='utf-8',errors='replace',timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload, ['--json','run','sekiro','hello','--env','ml','--','python','-c','print("$HOME; ü")','a b'])

@unittest.skipUnless(sys.platform == 'linux', 'real Linux runner integration')
class LinuxRunnerTests(Temporary):
    def setUp(self):
        super().setUp()
        self.root = self.path / ('c'*32); self.root.mkdir()
        common.atomic_json(self.root / 'owner.json',{'owner':common.OWNER,'schema':1,'profile':self.root.name,'uid':os.getuid()})
        for directory in ('jobs','projects','envs','services'): (self.root / directory).mkdir()
        common.atomic_json(self.root / 'envs.json',{})
        for filename in ('device_common.py','device_remote.py'): shutil.copy2(ROOT / 'scripts' / filename,self.root / filename)
        self.root_patch = patch.object(remote,'root_for',return_value=self.root); self.root_patch.start()
        self.runners = []
    def tearDown(self):
        for process in self.runners:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=10)
        self.root_patch.stop(); super().tearDown()
    def record(self, program):
        identifier='job-'+'d'*16; directory=self.root / 'jobs' / identifier; directory.mkdir()
        (directory / 'workspace').mkdir(); (directory / 'outputs').mkdir()
        common.atomic_json(directory / 'job.json', {'owner':common.OWNER,'id':identifier,'state':'queued','boot_id':remote.boot_id(),'command':[sys.executable,'-u','-c',program], 'workspace':str(directory / 'workspace'),'outputs':str(directory / 'outputs'),'env_path':None})
        return identifier,directory
    def runner(self, identifier):
        process=subprocess.Popen([sys.executable,str(self.root / 'device_remote.py'),'run-job',str(self.root),identifier],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        self.runners.append(process); return process
    def test_real_runner_output_exit_and_live_logs(self):
        identifier,directory=self.record("import os,time,pathlib; print('started',flush=True); time.sleep(1); pathlib.Path(os.environ['DEVICE_OUTPUT_DIR'],'answer.txt').write_text('42')")
        process=self.runner(identifier)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and not (directory/'task.log').exists(): time.sleep(.05)
        self.assertIn('started',(directory/'task.log').read_text())
        self.assertIsNone(process.poll(), 'log should be visible before job exits')
        stdout,stderr=process.communicate(timeout=10); self.assertEqual(process.returncode,0,stderr)
        record=common.read_json(directory/'job.json'); self.assertEqual(record['state'],'completed'); self.assertEqual(record['exit_code'],0)
        self.assertEqual((directory/'outputs/answer.txt').read_text(),'42')
    def test_real_failed_exit(self):
        identifier,directory=self.record('raise SystemExit(7)'); process=self.runner(identifier); process.communicate(timeout=10)
        record=common.read_json(directory/'job.json'); self.assertEqual(record['state'],'failed'); self.assertEqual(record['exit_code'],7)
    def test_real_stop_uses_process_group(self):
        identifier,directory=self.record("import time; print('running',flush=True); time.sleep(60)"); process=self.runner(identifier)
        for _ in range(100):
            if common.read_json(directory/'job.json')['state']=='running': break
            time.sleep(.05)
        remote.stop_job({'id':identifier}); process.communicate(timeout=10)
        self.assertEqual(common.read_json(directory/'job.json')['state'],'stopped')
    @unittest.skipUnless(shutil.which('tmux'),'tmux not installed')
    def test_real_tmux_launch_and_owned_cleanup(self):
        remote.sync_project({'project':'hello',**common.archive_payload(common.pack_directory(ROOT/'examples/hello'))})
        result=remote.launch_job({'project':'hello','command':[sys.executable,'-u','main.py']})
        identifier=result['id']
        for _ in range(150):
            record=remote.job_file(self.root,identifier)[1]
            if record['state'] in ('completed','failed'): break
            time.sleep(.05)
        self.assertEqual(record['state'],'completed')
        self.assertTrue((Path(record['outputs'])/'hello.txt').exists())
        for _ in range(30):
            if remote.tmux(self.root,'has-session','-t',identifier,check=False).returncode: break
            time.sleep(.05)
        remote.clean_job({'id':identifier,'approved':True})
        self.assertFalse((self.root/'jobs'/identifier).exists())

if __name__ == '__main__': unittest.main()
