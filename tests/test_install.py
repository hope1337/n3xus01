"""Isolated command registration tests; never write real PATH/startup files."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import device_install as installation
import device_cli as cli
import device_common as common
from test_device import Temporary, ROOT


class InstallTests(Temporary):
    def setUp(self):
        super().setUp()
        self.install_patch.stop()
        self.original_path=os.environ.get('PATH','')
        self.home=self.path/'home'; self.home.mkdir()
        self.repo=self.path/"repo with space $ ü '"; self.repo.mkdir()
        self.registry='C:\\ExistingTools;%USERPROFILE%\\Other'
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(Path,'home',return_value=self.home))
        self.stack.enter_context(patch.dict(os.environ,{'LOCALAPPDATA':str(self.home/'AppData'),'PATH':''}))

    def registry_access(self,value=None):
        if value is None: return self.registry
        self.registry=value

    def register(self,platform):
        # Temporary base fixture mocks CLI registration, not this installer.
        with patch.object(installation,'platform_name',return_value=platform), patch.object(installation,'windows_path',side_effect=self.registry_access):
            return installation.register(self.repo,cli.WORKSPACE)

    def unregister(self,platform):
        with patch.object(installation,'platform_name',return_value=platform), patch.object(installation,'windows_path',side_effect=self.registry_access):
            return installation.unregister(self.repo,cli.WORKSPACE)

    def test_linux_idempotent_preserves_profiles_and_unregister_keeps_config(self):
        profile=self.home/'.profile'; profile.write_text('# my settings\nexport MY_SETTING=yes\n')
        first=self.register('linux')
        launcher=Path(first['bin'])/'device'
        before=launcher.read_bytes()
        self.register('linux')
        self.assertEqual(launcher.read_bytes(),before)
        content=profile.read_text(encoding='utf-8')
        self.assertEqual(content.count(installation.BEGIN),1)
        self.assertIn('MY_SETTING=yes',content)
        config=cli.WORKSPACE/'config/devices.json'; common.atomic_json(config,{'profile':'kept'})
        self.unregister('linux')
        self.assertFalse(launcher.exists())
        self.assertEqual(profile.read_text(encoding='utf-8'),'# my settings\nexport MY_SETTING=yes\n')
        self.assertEqual(common.read_json(config),{'profile':'kept'})
        self.assertFalse(self.unregister('linux')['registered'])

    def test_windows_only_adds_and_removes_owned_path_entry(self):
        original=self.registry
        receipt=self.register('windows')
        added=self.registry
        self.assertTrue(added.startswith(original+';'))
        self.register('windows')
        self.assertEqual(self.registry,added)
        self.registry+=';C:\\LaterUserChange'
        self.unregister('windows')
        self.assertEqual(self.registry,original+';C:\\LaterUserChange')
        self.assertFalse((Path(receipt['bin'])/'device.cmd').exists())

    def test_windows_preexisting_user_path_is_kept(self):
        target=installation.directory('windows')
        self.registry+=';'+str(target)
        original=self.registry
        self.register('windows'); self.unregister('windows')
        self.assertEqual(self.registry,original)

    def test_unknown_launcher_is_not_overwritten(self):
        target=installation.directory('linux'); target.mkdir(parents=True)
        launcher=target/'device'; launcher.write_text('personal unrelated command')
        with self.assertRaises(common.DeviceError): self.register('linux')
        self.assertEqual(launcher.read_text(),'personal unrelated command')
        self.assertFalse((self.home/'.profile').exists())

    def test_modified_launcher_cannot_be_replaced_or_removed(self):
        result=self.register('windows')
        launcher=Path(result['bin'])/'device.ps1'
        launcher.write_bytes(launcher.read_bytes()+b'# user modification\n')
        before=self.registry
        for operation in (self.register,self.unregister):
            with self.assertRaises(common.DeviceError): operation('windows')
        self.assertTrue(launcher.exists())
        self.assertEqual(self.registry,before)

    def test_edited_startup_block_refuses_all_writes(self):
        result=self.register('linux')
        profile=self.home/'.profile'
        profile.write_text(profile.read_text().replace('export PATH','export CUSTOM'))
        launcher=Path(result['bin'])/'device'; before=launcher.read_bytes()
        with self.assertRaises(common.DeviceError): self.register('linux')
        with self.assertRaises(common.DeviceError): self.unregister('linux')
        self.assertEqual(launcher.read_bytes(),before)

    def test_another_checkout_cannot_unregister_current_command(self):
        self.register('windows')
        with patch.object(installation,'platform_name',return_value='windows'):
            with self.assertRaises(common.DeviceError): installation.unregister(self.path/'different',cli.WORKSPACE)

    def test_setup_no_register_never_touches_host_registration(self):
        with patch.object(cli.installation,'register') as register, patch.object(cli,'CONFIG',cli.WORKSPACE/'config/devices.json'), patch.object(cli,'LEGACY_CONFIG',self.path/'absent.json'), patch.object(cli.shutil,'which',return_value='ssh'):
            action,data=cli.execute(cli.arguments(['setup','--no-register']))
        register.assert_not_called()
        self.assertEqual(action,'setup')
        self.assertFalse(data['registered'])

    def test_setup_registers_by_default(self):
        with patch.object(cli.installation,'register',return_value={'registered':True,'note':'test'}) as register, patch.object(cli,'CONFIG',cli.WORKSPACE/'config/devices.json'), patch.object(cli,'LEGACY_CONFIG',self.path/'absent.json'), patch.object(cli.shutil,'which',return_value='ssh'):
            action,data=cli.execute(cli.arguments(['setup']))
        register.assert_called_once_with(cli.ROOT,cli.WORKSPACE)
        self.assertTrue(data['registered'])

    @unittest.skipUnless(sys.platform.startswith('linux'),'real Linux global launcher')
    def test_linux_command_from_unrelated_folder_preserves_literal_argv(self):
        (self.repo/'scripts').mkdir()
        (self.repo/'scripts/device_cli.py').write_text('import sys,json; print(json.dumps(sys.argv[1:]))',encoding='utf-8')
        result=self.register('linux')
        payload=['run','--','python','-c','print("$HOME; ü")','a b']
        execution=subprocess.run([str(Path(result['bin'])/'device'),*payload],cwd=self.home,capture_output=True,text=True,timeout=20)
        self.assertEqual(execution.returncode,0,execution.stderr)
        self.assertEqual(json.loads(execution.stdout),payload)

    @unittest.skipUnless(os.name=='nt','real Windows global launcher')
    def test_windows_global_command_from_unrelated_folder_preserves_argv(self):
        shutil.copy2(ROOT/'device.ps1',self.repo/'device.ps1')
        (self.repo/'scripts').mkdir()
        (self.repo/'scripts/device_cli.py').write_text("import os,base64,json; print(json.dumps(json.loads(base64.b64decode(os.environ['DEVICE_ARGUMENTS_BASE64']).decode('utf-8'))))",encoding='utf-8')
        result=self.register('windows')
        for executable in filter(None,(shutil.which('powershell.exe',path=self.original_path),shutil.which('pwsh.exe',path=self.original_path))):
            script="$env:PATH = '"+result['bin'].replace("'","''")+";' + $env:PATH; device --json run sekiro hello --name test --description 'test $HOME; ü' --gpu 0 -- python -c 'print(\"$HOME; ü\")' 'a b'"
            response=subprocess.run([executable,'-NoProfile','-Command',script],cwd=self.home,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
            self.assertEqual(response.returncode,0,response.stderr)
            self.assertEqual(json.loads(response.stdout),['--json','run','sekiro','hello','--name','test','--description','test $HOME; ü','--gpu','0','--','python','-c','print("$HOME; ü")','a b'])

