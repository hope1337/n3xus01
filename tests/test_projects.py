"""Isolated project routing and preflight tests; never SSH to a device."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import device_cli as cli
import device_workspace as workspace
from device_common import DeviceError, archive_payload, pack_directory, read_json
from test_device import Temporary

class ProjectTests(Temporary):
    def setUp(self):
        super().setUp()
        self.a=self.path/'project A ü'; self.a.mkdir()
        self.b=self.path/'project-b'; self.b.mkdir()
        self.conf={'profile':'a'*32,'devices':{'test':{'address':'100.64.0.1','user':'user'}}}

    def init(self,root):
        return cli.execute(cli.arguments(['project','init','--project-dir',str(root)]))[1]

    def test_initialize_discover_override_and_preserve_project_identity(self):
        (self.a/'.gitignore').write_text('# user rules\ndata/\n',encoding='utf-8')
        first=self.init(self.a); self.init(self.b)
        self.assertEqual(self.init(self.a)['project_id'],first['project_id'])
        nested=self.a/'src'/'nested'; nested.mkdir(parents=True)
        with patch.object(Path,'cwd',return_value=nested):
            self.assertEqual(workspace.find_project(None,cli.ROOT),self.a)
            self.assertEqual(workspace.find_project(str(self.b),cli.ROOT),self.b)
        self.assertEqual((self.a/'.gitignore').read_text(encoding='utf-8'),'# user rules\ndata/\n/communication/\n')
        self.assertFalse((self.a/'config').exists())

    def test_communication_is_separate_and_relative_message_uses_selected_root(self):
        self.init(self.a); self.init(self.b)
        (self.a/'handoff.txt').write_text('Only project A',encoding='utf-8')
        cli.execute(cli.arguments(['communication','note','agent-a','--title','A','--message-file','handoff.txt','--project-dir',str(self.a)]))
        cli.execute(cli.arguments(['communication','init','agent-b','--project-dir',str(self.b)]))
        self.assertEqual(workspace.show(self.a)['notes'][0]['message'],'Only project A')
        self.assertEqual(workspace.show(self.b)['notes'],[])
        self.assertFalse((cli.WORKSPACE/'communication').exists())

    def test_missing_project_and_tool_repo_are_rejected_before_remote_mutations(self):
        with patch.object(cli,'config',return_value=self.conf),patch.object(cli,'remote') as remote,patch.object(Path,'cwd',return_value=self.a):
            for command in (['run','test','hello','--','python','main.py'],['sync','test','src','--project','hello'],['fetch','test','job-'+'a'*16],['job-note','test','job-'+'a'*16,'--agent','agent-a']):
                with self.subTest(command=command),self.assertRaises(DeviceError): cli.execute(cli.arguments(command))
        remote.assert_not_called()
        with self.assertRaises(DeviceError) as caught: self.init(cli.ROOT)
        self.assertEqual(caught.exception.code,'project_in_tool')

    def test_invalid_marker_is_not_overwritten(self):
        marker=self.a/workspace.PROJECT_MARKER
        marker.write_text('{"schema":true,"project_id":"bad"}',encoding='utf-8')
        original=marker.read_bytes()
        with self.assertRaises(DeviceError): self.init(self.a)
        self.assertEqual(marker.read_bytes(),original)
        self.assertFalse((self.a/'communication').exists())

    def test_paths_cannot_escape_project_and_payload_options_are_literal(self):
        self.init(self.a)
        for value in ('../outside',str(self.b/'output')):
            with self.subTest(value=value),self.assertRaises(DeviceError): workspace.project_path(self.a,value)
        args=cli.arguments(['run','test','hello','--project-dir',str(self.a),'--','python','--project-dir','literal'])
        self.assertEqual(args.project_dir,str(self.a))
        self.assertEqual(args.command,['python','--project-dir','literal'])

    def test_job_receipts_and_snapshot_only_include_this_project_jobs(self):
        self.init(self.a); self.init(self.b)
        one={'id':'job-'+'a'*16,'state':'running','project':'hello'}
        two={'id':'job-'+'b'*16,'state':'running','project':'other'}
        workspace.receipt(self.a,'test',one); workspace.receipt(self.b,'test',two)
        data={'observed_at':'now','devices':[{'name':'test','online':True,'active_jobs':2}],
              'jobs':[{'device':'test',**one},{'device':'test',**two}]}
        workspace.project_snapshot(self.a,data)
        saved=workspace.show(self.a)['snapshot']
        self.assertEqual([r['id'] for r in saved['jobs']],[one['id']])
        self.assertEqual(saved['devices'][0]['active_jobs'],2)
        self.assertFalse((self.a/'runs').exists())

    def test_default_fetch_uses_agent_downloads_and_duplicate_is_refused_before_ssh(self):
        self.init(self.a)
        args=cli.arguments(['fetch','test','job-'+'a'*16,'--agent','agent-a','--project-dir',str(self.a)])
        (self.b/'hello.txt').write_text('Fetched result',encoding='utf-8')
        with patch.object(cli,'remote',return_value=archive_payload(pack_directory(self.b))):
            result=cli.fetch_files(args,{},'a'*32)
        destination=self.a/'communication/agents/agent-a/downloads'/('test-'+args.id)
        self.assertEqual(Path(result['downloaded_to']),destination)
        self.assertEqual((destination/'hello.txt').read_text(encoding='utf-8'),'Fetched result')
        with patch.object(cli,'remote') as remote,self.assertRaises(DeviceError): cli.fetch_files(args,{},'a'*32)
        remote.assert_not_called()

    def test_global_readonly_commands_and_setup_need_no_project(self):
        with patch.object(cli,'config',return_value={'profile':'a'*32,'devices':{}}),patch.object(Path,'cwd',return_value=self.a):
            self.assertEqual(cli.execute(cli.arguments(['status']))[1],{'devices':[]})
        with patch.object(cli,'CONFIG',cli.WORKSPACE/'config/devices.json'),patch.object(cli.shutil,'which',return_value='ssh'):
            cli.execute(cli.arguments(['setup']))
        self.assertTrue((cli.WORKSPACE/'config/devices.json').exists())
        self.assertFalse((cli.WORKSPACE/'communication').exists())
        self.assertFalse((self.a/workspace.PROJECT_MARKER).exists())

    def test_successful_submit_writes_receipt_in_selected_project(self):
        self.init(self.a)
        record={'id':'job-'+'a'*16,'name':'test-run','state':'running'}
        with patch.object(cli,'config',return_value=self.conf),patch.object(cli,'remote',return_value=record):
            cli.execute(cli.arguments(['run','test','hello','--agent','agent-a','--name','test-run','--description','test','--project-dir',str(self.a),'--','python','main.py']))
        files=list((self.a/'communication/runs').glob('*.json'))
        self.assertEqual(len(files),1)
        self.assertEqual(read_json(files[0])['id'],record['id'])
        self.assertFalse((cli.WORKSPACE/'communication').exists())
