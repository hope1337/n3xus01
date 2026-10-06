"""Progress ordering and pipe/timeout safety; never contact SSH or devices."""
from contextlib import redirect_stdout, nullcontext
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import device_cli as cli
import device_progress as progress
import device_dashboard as dashboard
from device_common import DeviceError
from device_ui import UI


class ProgressTests(unittest.TestCase):
    def test_cpu_arrives_before_final_and_stderr_pipe_is_drained(self):
        script = """
import json,sys,time
sys.stdin.buffer.read()
print(json.dumps({'schema':1,'event':'probe_progress','data':{'cpu_count':24}}),flush=True)
sys.stderr.write('x'*100000); sys.stderr.flush()
time.sleep(.25)
print(json.dumps({'schema':1,'ok':True,'data':{'cpu_count':24,'gpus':[]}}),flush=True)
"""
        events=[]
        start=time.monotonic()
        result=cli.streamed_rpc([sys.executable,'-c',script],b'{}',5,lambda data:events.append((time.monotonic(),data)))
        self.assertEqual(result.returncode,0)
        self.assertEqual(events[0][1],{'cpu_count':24})
        self.assertLess(events[0][0],time.monotonic()-.15)
        self.assertLess(time.monotonic()-start,5)
        self.assertEqual(len(result.stderr),100000)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_timeout_includes_blocked_stdin_and_reaps_process(self):
        start=time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            cli.streamed_rpc([sys.executable,'-c','import time; time.sleep(30)'],b'x'*1000000,.2,lambda _:None)
        self.assertLess(time.monotonic()-start,3)

    def test_invalid_stream_and_missing_final_are_errors(self):
        for script in ("print('not-json',flush=True)","print('{\"schema\":1,\"event\":\"probe_progress\",\"data\":{}}',flush=True)"):
            with self.subTest(script=script), self.assertRaises(DeviceError) as caught:
                cli.streamed_rpc([sys.executable,'-c',script],b'{}',5,lambda _:None)
            self.assertEqual(caught.exception.code,'protocol_error')

    def test_fast_device_and_partial_fields_render_before_slow_device(self):
        conf={'profile':'a'*32,'devices':{'slow':{'address':'slow','user':'user'},'fast':{'address':'fast','user':'user'}}}
        ready=threading.Event(); frames=[]
        def publish(action,data):
            frames.append(copy.deepcopy(data))
            if data['devices'][1].get('online'): ready.set()
        def remote(entry,profile,operation,**kwargs):
            if entry['address']=='slow':
                self.assertTrue(ready.wait(2),'Fast device was not published while slow device waited')
            else:
                kwargs['_on_progress']({'online':True,'cpu_count':24,'loading_fields':['gpus']})
            return {'online':True,'ready':True,'gpus':[]}
        with patch.object(cli,'remote',side_effect=remote),patch.object(progress,'publish',side_effect=publish):
            data=cli.status(conf)
        partial=next(frame for frame in frames if frame['devices'][1].get('loading_fields'))
        self.assertTrue(partial['devices'][0]['loading'])
        self.assertEqual(partial['devices'][1]['cpu_count'],24)
        self.assertEqual([d['name'] for d in data['devices']],['slow','fast'])
        self.assertFalse(any(d.get('loading') for d in data['devices']))

    def test_json_never_streams_or_emits_loading_even_on_terminal(self):
        response=subprocess.CompletedProcess([],0,b'{"schema":1,"ok":true,"data":{"online":true,"cpu_count":24}}',b'')
        out=io.StringIO()
        conf={'profile':'a'*32,'devices':{'fast':{'address':'fast','user':'user'}}}
        with redirect_stdout(out),patch.object(sys.stdout,'isatty',return_value=True),patch.object(cli,'config',return_value=conf),patch.object(cli,'streamed_rpc') as stream,patch.object(cli.shutil,'which',return_value='ssh'),patch.object(cli.subprocess,'run',return_value=response) as run:
            self.assertEqual(cli.main(['status','--json']),0)
        stream.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['data'],{'devices':[{'name':'fast','online':True,'cpu_count':24}]})
        self.assertNotIn('_progress',json.loads(run.call_args.kwargs['input'])['request'])
        self.assertNotIn('\033',out.getvalue())

    def test_loading_cleanup_on_exception_and_partial_table(self):
        out=io.StringIO()
        with redirect_stdout(out),patch.object(sys.stdout,'isatty',return_value=True):
            with self.assertRaises(DeviceError):
                with progress.terminal('never'):
                    with progress.operation('Read resources'):
                        raise DeviceError('fail')
        self.assertIsNone(progress._active)
        self.assertIn('Read resources',out.getvalue())
        self.assertTrue(out.getvalue().endswith('\033[1F\033[J'))
        table=io.StringIO()
        with redirect_stdout(table):
            UI('never').resources([{'name':'fast','online':True,'cpu_count':24,'memory_available_gib':16,'memory_total_gib':32,'loading_fields':['gpus']},{'name':'slow','loading':True}])
        self.assertIn('16.0/32.0',table.getvalue())
        self.assertIn('loading',table.getvalue())

    def dashboard_data(self):
        return {'observed_at':'previous','include_history':False,'devices':[{'name':'fast','online':True,'ready':True,'cpu_count':24,'memory_available_gib':24,'memory_total_gib':32,'active_jobs':1,'gpus':[{'name':'TEST GPU','free_mib':6144,'total_mib':24576}]}],
                'jobs':[{'device':'fast','id':'job-'+'a'*16,'name':'keep-job','state':'running'}]}

    def test_refresh_retains_pending_fields_and_jobs_but_final_errors_replace_cache(self):
        previous=self.dashboard_data(); unchanged=copy.deepcopy(previous)
        partial={'observed_at':'new','include_history':False,'devices':[{'name':'fast','online':True,'ready':True,'cpu_count':24,'memory_available_gib':20,'memory_total_gib':32,'loading_fields':['gpus'],'jobs_loading':True}],'jobs':[]}
        view=dashboard.refreshing_snapshot(previous,partial)
        self.assertEqual(view['devices'][0]['memory_available_gib'],20)
        self.assertEqual(view['devices'][0]['gpus'],previous['devices'][0]['gpus'])
        self.assertEqual(view['devices'][0]['active_jobs'],1)
        self.assertEqual(view['jobs'],previous['jobs'])
        self.assertTrue(view['devices'][0]['refreshing'])
        self.assertEqual(view['devices'][0]['loading_fields'],[])
        final={**partial,'devices':[{'name':'fast','online':False,'error':'timeout'}]}
        failed=dashboard.refreshing_snapshot(previous,final)
        self.assertFalse(failed['devices'][0]['refreshing'])
        self.assertNotIn('gpus',failed['devices'][0])
        self.assertEqual(failed['jobs'],[])
        self.assertEqual(previous,unchanged)

    def test_dashboard_refresh_replaces_one_screen_without_generic_loading_table(self):
        previous=self.dashboard_data(); calls=[]
        partial={**previous,'devices':[{'name':'fast','loading':True,'jobs_loading':True}],'jobs':[]}
        def fetch():
            calls.append(True)
            if len(calls)>1: progress.publish('dashboard',partial)
            return previous
        out=io.StringIO()
        with redirect_stdout(out),patch.object(sys.stdout,'isatty',return_value=True),patch.object(dashboard,'keyboard',return_value=nullcontext()),patch.object(dashboard,'read_key',side_effect=['r','q']):
            dashboard.watch(cli.arguments(['dashboard','--color','never']),fetch,cli.terminal_execute,cli.arguments)
        self.assertEqual(len(calls),2)
        self.assertNotIn('│ DASHBOARD',out.getvalue())
        self.assertNotIn('loading…',out.getvalue())
        frames=[frame for frame in out.getvalue().split('\033[H\033[2J') if 'Refreshing' in frame]
        self.assertTrue(frames)
        for frame in frames:
            self.assertIn('24.0/32.0',frame)
            self.assertIn('TEST GPU',frame)
            self.assertIn('keep-job',frame)
        self.assertTrue(out.getvalue().endswith('\033[?25h\033[?1049l'))
        self.assertIsNone(progress._active)

if __name__=='__main__':
    unittest.main()
