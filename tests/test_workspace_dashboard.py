"""Offline workspace, metadata and interactive dashboard regression checks."""
from contextlib import nullcontext, redirect_stdout
import io
import json
from pathlib import Path
import sys
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import device_workspace as workspace
import device_dashboard as dashboard
import device_cli as cli
import device_common as common
import device_remote as remote
import device_ui as ui
from test_device import Temporary, unit_lock


class WorkspaceTests(Temporary):
    def test_setup_migrates_exact_profile_and_is_idempotent(self):
        legacy = self.path / 'devices.json'
        original = {'schema': 1, 'profile': 'a'*32, 'devices': {}}
        common.atomic_json(legacy, original)
        with patch.object(cli, 'CONFIG', cli.WORKSPACE/'config/devices.json'), patch.object(cli, 'LEGACY_CONFIG', legacy), patch.object(cli.shutil, 'which', return_value='ssh'):
            cli.execute(cli.arguments(['setup']))
            cli.execute(cli.arguments(['setup']))
            self.assertEqual(cli.config(), original)
            self.assertFalse(legacy.exists())

    def test_conflicting_configs_are_preserved(self):
        workspace.initialize(cli.WORKSPACE)
        canonical = cli.WORKSPACE/'config/devices.json'
        legacy = self.path/'devices.json'
        common.atomic_json(canonical, {'schema':1,'profile':'a'*32,'devices':{}})
        common.atomic_json(legacy, {'schema':1,'profile':'b'*32,'devices':{}})
        with patch.object(cli,'CONFIG',canonical), patch.object(cli,'LEGACY_CONFIG',legacy), patch.object(cli.shutil,'which',return_value='ssh'):
            with self.assertRaises(common.DeviceError) as caught:
                cli.execute(cli.arguments(['setup']))
        self.assertEqual(caught.exception.code, 'config_conflict')
        self.assertEqual(common.read_json(canonical)['profile'], 'a'*32)
        self.assertEqual(common.read_json(legacy)['profile'], 'b'*32)

    def test_agent_notes_are_separate_and_append_only(self):
        a = workspace.note(cli.WORKSPACE,'agent-a','A','First')
        b = workspace.note(cli.WORKSPACE,'agent-b','B','Second')
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(len(workspace.show(cli.WORKSPACE)['notes']), 2)
        self.assertEqual(workspace.show(cli.WORKSPACE,'agent-a')['notes'], [a])
        with self.assertRaises(common.DeviceError): workspace.agent(cli.WORKSPACE,'../escape')

    def test_snapshot_preserves_human_summary_and_marks_unknown_counts(self):
        workspace.initialize(cli.WORKSPACE)
        summary = cli.WORKSPACE/'communication/shared/SUMMARY.md'
        summary.write_text('Human context',encoding='utf-8')
        data = {'observed_at':'2026-10-06T00:00:00Z','devices':[{'name':'offline-device','online':False}], 'jobs':[]}
        workspace.snapshot(cli.WORKSPACE,data)
        workspace.initialize(cli.WORKSPACE)
        self.assertEqual(summary.read_text(encoding='utf-8'), 'Human context')
        self.assertEqual(workspace.show(cli.WORKSPACE)['snapshot'], data)
        status = (summary.parent/'STATUS.md').read_text(encoding='utf-8')
        self.assertIn('unknown', status)
        self.assertIn('not a live monitor', status)

    def test_entire_workspace_cannot_be_synced(self):
        workspace.agent(cli.WORKSPACE,'agent-a')
        with self.assertRaises(common.DeviceError): common.pack_directory(cli.WORKSPACE)
        source = cli.WORKSPACE/'communication/agents/agent-a/work/code'
        source.mkdir(); (source/'main.py').write_text('print(42)')
        self.assertTrue(common.pack_directory(source))

    def test_successful_submission_survives_local_receipt_failure(self):
        project=self.path/'project'; project.mkdir()
        workspace.init_project(project,cli.ROOT)
        args = cli.arguments(['run','test','hello','--project-dir',str(project),'--','python','main.py'])
        conf = {'profile':'a'*32,'devices':{'test':{'user':'test','address':'100.64.0.1'}}}
        with patch.object(cli,'config',return_value=conf), patch.object(cli,'remote',return_value={'id':'job-'+'a'*16}), patch.object(workspace,'receipt',side_effect=OSError('disk full')):
            action, result = cli.execute(args)
        self.assertEqual(action,'run')
        self.assertIn('Job submitted',result['warning'])


class MetadataTests(Temporary):
    def setUp(self):
        super().setUp()
        self.uid_patch = patch.object(remote.os,'getuid',return_value=1000,create=True)
        self.uid_patch.start()

    def tearDown(self):
        self.uid_patch.stop()
        super().tearDown()

    def records(self):
        root = self.owned()
        records = []
        for suffix,state in (('a','completed'),('b','running')):
            record = {'owner':common.OWNER,'id':'job-'+suffix*16,'name':'training','state':state,'pid':123,'created_at':'2026-10-06T00:00:00+00:00'}
            directory = root/'jobs'/record['id']; directory.mkdir()
            common.atomic_json(directory/'job.json',record)
            records.append(record)
        return root,records

    def test_active_name_wins_and_ambiguous_history_requires_id(self):
        root,records = self.records()
        with patch.object(remote,'alive',return_value=True):
            self.assertEqual(remote.resolve_job(root,'training'),records[1]['id'])
        records[1]['state']='completed'
        common.atomic_json(root/'jobs'/records[1]['id']/'job.json',records[1])
        with self.assertRaises(common.DeviceError): remote.resolve_job(root,'training')
        self.assertEqual(remote.resolve_job(root,records[0]['id']), records[0]['id'])

    def test_note_preserves_execution_identity_and_has_author_timestamp(self):
        root,records = self.records()
        with patch.object(remote,'root_for',return_value=root), patch.object(remote,'locked',unit_lock), patch.object(remote,'alive',return_value=True):
            result = remote.job_note({'id':records[1]['id'],'summary':'Epoch 3 completed','phase':'training','progress':25,'agent':'agent-a'})
        self.assertEqual(result['pid'],123)
        self.assertEqual(result['state'],'running')
        self.assertEqual(result['note_author'],'agent-a')
        self.assertIn('note_updated_at',result)

    def test_invalid_progress_does_not_write(self):
        root,records = self.records()
        for value in (101,-1,True,float('nan')):
            with patch.object(remote,'root_for',return_value=root), patch.object(remote,'locked',unit_lock):
                with self.assertRaises(common.DeviceError): remote.job_note({'id':records[1]['id'],'progress':value})
        self.assertNotIn('progress',common.read_json(root/'jobs'/records[1]['id']/'job.json'))


class DashboardTests(Temporary):
    def test_posix_arrow_keys_use_unbuffered_descriptor(self):
        with patch.object(dashboard.os,'name','posix'), patch.object(dashboard.sys,'stdin',Mock(fileno=Mock(return_value=9))), patch.object(dashboard.select,'select',return_value=([9],[],[])), patch.object(dashboard.os,'read',side_effect=[b'\x1b',b'[',b'B']):
            self.assertEqual(dashboard.read_key(),'j')

    def data(self):
        return {'observed_at':'2026-10-06','include_history':False,'devices':[{'name':'test','online':True,'active_jobs':1}], 'jobs':[{'device':'test','id':'job-'+'a'*16,'name':'test-run','state':'running','description':'Compute useful result'}]}

    def test_overview_queries_each_device_once_and_reports_offline(self):
        conf = {'profile':'a'*32,'devices':{'online':{'user':'user','address':'100.64.0.1'},'offline':{'user':'user','address':'100.64.0.2'}}}
        def reply(entry,profile,operation,**kwargs):
            self.assertEqual(operation,'overview'); self.assertTrue(kwargs['all'])
            if entry['address'].endswith('.2'): raise common.DeviceError('timeout','ssh_timeout')
            return {'device':{'online':True,'active_jobs':0},'jobs':[]}
        with patch.object(cli,'remote',side_effect=reply) as call:
            result = cli.overview(conf,include_all=True)
        self.assertEqual(call.call_count,2)
        self.assertFalse(result['devices'][1]['online'])
        self.assertNotIn('active_jobs',result['devices'][1])

    def test_selection_survives_reordered_refresh(self):
        selection = dashboard.Selection()
        rows = self.data()['jobs']; rows.append({'device':'other','id':'job-'+'b'*16})
        chosen = selection.choose(rows,1)
        self.assertEqual(selection.choose(list(reversed(rows))),chosen)

    def test_cancel_stop_and_delete_never_execute(self):
        args = cli.arguments(['dashboard'])
        execute = Mock()
        output = io.StringIO()
        with patch.object(dashboard,'keyboard',return_value=nullcontext()), patch.object(dashboard,'read_key',side_effect=['s','n','d','n','q']), redirect_stdout(output):
            dashboard.watch(args,self.data,execute,cli.arguments)
        execute.assert_not_called()
        self.assertTrue(output.getvalue().endswith('\033[?25h\033[?1049l'))

    def test_confirmed_stop_uses_selected_exact_id(self):
        args = cli.arguments(['dashboard'])
        execute = Mock(return_value=('stop',{'state':'stopped'}))
        with patch.object(dashboard,'keyboard',return_value=nullcontext()), patch.object(dashboard,'read_key',side_effect=['s','y','x','q']), redirect_stdout(io.StringIO()):
            dashboard.watch(args,self.data,execute,cli.arguments)
        request = execute.call_args.args[0]
        self.assertEqual((request.action,request.device,request.id),('stop','test','job-'+'a'*16))

    def test_cursor_restored_on_fetch_error(self):
        output = io.StringIO()
        with patch.object(dashboard,'keyboard',return_value=nullcontext()), redirect_stdout(output):
            with self.assertRaises(common.DeviceError):
                dashboard.watch(cli.arguments(['dashboard']),Mock(side_effect=common.DeviceError('bad config')),Mock(),cli.arguments)
        self.assertTrue(output.getvalue().endswith('\033[?25h\033[?1049l'))

    def test_json_dashboard_never_enters_interactive_mode(self):
        output = io.StringIO()
        with patch.object(cli,'execute',return_value=('dashboard',self.data())), patch.object(dashboard,'watch') as watch, redirect_stdout(output):
            self.assertEqual(cli.main(['dashboard','--json']),0)
        watch.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())['ok'])

    def test_job_output_sanitizes_remote_escape_sequences(self):
        output = io.StringIO()
        with redirect_stdout(output): ui.UI('never').render('job',{'name':'example','summary':'\033[2Junsafe','command':['python','main.py']})
        self.assertNotIn('\033',output.getvalue())
