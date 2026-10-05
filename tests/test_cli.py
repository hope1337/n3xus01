"""Regression tests for the human/agent interface, isolated from real devices."""
import argparse
import base64
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cluster_test_module', ROOT / 'scripts/cluster_cli.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

def entry(address='100.101.102.103', role='server', gpu=False):
    return dict(address=address, user='student', role=role, gpu=gpu, data_root='/srv/personal-compute/data')

class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='personal-compute-test-')
        self.root = Path(self.temp.name)
        self.patch = patch.multiple(c, STATE=self.root / 'private', CONFIG=self.root / 'devices.yml')
        self.patch.start()
        c.STATE.mkdir()
        c.atomic_write(c.CONFIG, 'devices: {}\n')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def seed(self, worker=False, gpu=False):
        config = {'cluster_id': 'a' * 32, 'devices': {'home': entry(gpu=gpu)}}
        if worker:
            config['devices']['lab'] = entry('100.101.102.104', 'worker')
        c.atomic_write(c.CONFIG, yaml.safe_dump(config))
        for name, device in config['devices'].items():
            data = dict(cluster_id='a' * 32, tailscale_ip=device['address'], data_root=device['data_root'], uid=1000, gid=1000)
            c.atomic_write(c.STATE / 'nodes' / f'{name}.json', json.dumps(data))
        c.atomic_write(c.STATE / 'kubeconfig.yaml', 'offline fixture, no credentials\n')
        c.atomic_write(c.STATE / 'join-token', 'offline fixture, not a real token\n')
        return config

    def test_reject_bad_addresses_names_and_secrets(self):
        for name in ('../device', '-option', 'UPPER', 'a;rm', ''):
            with self.assertRaises(c.ClusterError):
                c.validate_name(name)
        for address in ('8.8.8.8', '192.168.1.5', '100.1.2.3', 'host;whoami', 'host\nother'):
            with self.assertRaises(c.ClusterError):
                c.validate_device('home', entry(address))
        device = entry()
        device['password'] = 'should-never-be-accepted'
        with self.assertRaises(c.ClusterError):
            c.validate_device('home', device)

    def test_data_path_cannot_be_system_or_traversal(self):
        for path in ('/', '/etc/data', '/var/lib/rancher/k3s', '/srv/../etc', '/data', '/srv/data/../../root'):
            device = entry()
            device['data_root'] = path
            with self.assertRaises(c.ClusterError):
                c.validate_device('home', device)

    def test_duplicate_yaml_and_two_servers_rejected(self):
        c.atomic_write(c.CONFIG, 'devices: {}\ndevices: {}\n')
        with self.assertRaises(c.ClusterError):
            c.load_config()
        config = self.seed(worker=True)
        config['devices']['lab']['role'] = 'server'
        c.atomic_write(c.CONFIG, yaml.safe_dump(config))
        with self.assertRaises(c.ClusterError):
            c.load_config()

    def test_inventory_uses_paths_not_token_contents(self):
        config = self.seed(worker=True)
        inventory = c.write_inventory(config)
        text = inventory.read_text()
        self.assertNotIn('offline fixture', text)
        parsed = yaml.safe_load(text)['all']
        self.assertEqual(parsed['vars']['cluster_server_ip'], '100.101.102.103')
        self.assertEqual(parsed['children']['k3s_nodes']['hosts']['lab']['cluster_role'], 'worker')

    def test_job_is_pinned_nonroot_and_dataset_readonly(self):
        config = self.seed(gpu=True)
        data = c.receipt('home', config)
        command = ['python', '-c', 'print("literal $HOME; not a shell")']
        job = c.make_job('task-test', 'home', 'example/image:1', command, gpu=True, data=data)
        pod = job['spec']['template']['spec']
        self.assertEqual(pod['nodeSelector'], {'kubernetes.io/hostname': 'home'})
        self.assertEqual(pod['runtimeClassName'], 'nvidia')
        self.assertEqual(pod['containers'][0]['resources']['limits']['nvidia.com/gpu'], 1)
        self.assertEqual(pod['containers'][0]['command'], command)
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        mounts = {m['name']: m for m in pod['containers'][0]['volumeMounts']}
        self.assertTrue(mounts['datasets']['readOnly'])
        self.assertFalse(mounts['results']['readOnly'])
        self.assertFalse(pod.get('hostNetwork', False))

    def test_kubectl_ignores_external_context(self):
        with patch.object(c, 'run_process', return_value=subprocess.CompletedProcess([], 0)) as invoke:
            c.k('get', 'nodes')
        args = invoke.call_args.args[0]
        self.assertEqual(args[1:5], ['--kubeconfig', c.STATE / 'kubeconfig.yaml', '--context', c.CONTEXT])

    def test_namespace_not_owned_is_never_overwritten(self):
        response = subprocess.CompletedProcess([], 0, json.dumps({'metadata': {'labels': {'app.kubernetes.io/managed-by': 'someone-else'}}}), '')
        with patch.object(c, 'k', return_value=response), patch.object(c, 'apply') as apply:
            with self.assertRaises(c.ClusterError):
                c.namespace('personal-compute-jobs')
            apply.assert_not_called()

    def test_reset_without_confirmation_cannot_call_ansible(self):
        self.seed()
        with patch.object(c, 'ansible') as provision:
            with self.assertRaises(c.ClusterError):
                c.main(['reset', 'home'])
            provision.assert_not_called()

    def test_server_reset_blocked_while_workers_registered(self):
        self.seed(worker=True)
        with patch.object(c, 'ansible') as provision:
            with self.assertRaises(c.ClusterError):
                c.main(['reset', 'home', '--yes-delete-cluster'])
            provision.assert_not_called()

    def test_worker_reset_removes_node_for_clean_rejoin(self):
        self.seed(worker=True)
        with patch.object(c, 'ansible'), patch.object(c, 'k') as kubectl:
            c.main(['reset', 'lab', '--yes-delete-cluster', '--no-sudo-prompt'])
            kubectl.assert_any_call('delete', 'node', 'lab', '--ignore-not-found')
        self.assertNotIn('lab', c.load_config()['devices'])
        self.assertTrue((c.STATE / 'kubeconfig.yaml').exists())

    def test_failed_provision_keeps_device_for_retry_and_never_waits(self):
        with patch.object(c, 'run_process', return_value=subprocess.CompletedProcess([], 0)), patch.object(c, 'ansible', side_effect=c.ClusterError('failed')), patch.object(c, 'k') as kubectl:
            with self.assertRaises(c.ClusterError):
                c.main(['add-device', 'home', '--address', '100.101.102.103', '--user', 'student', '--gpu'])
            kubectl.assert_not_called()
        config = c.load_config()
        self.assertEqual(config['devices']['home']['role'], 'server')
        self.assertTrue(config['devices']['home']['gpu'])

    def test_identity_change_does_not_write_config_or_contact_device(self):
        self.seed()
        before = c.CONFIG.read_bytes()
        with patch.object(c, 'run_process') as invoke:
            with self.assertRaises(c.ClusterError):
                c.main(['add-device', 'home', '--address', '100.101.102.105'])
            invoke.assert_not_called()
        self.assertEqual(before, c.CONFIG.read_bytes())

    def test_run_submits_literal_command_and_does_not_wait(self):
        self.seed(gpu=True)
        with patch.object(c, 'namespace'), patch.object(c, 'k') as kubectl:
            c.main(['run', 'home', '--image', 'sample:1', '--gpu', '--', 'python', '-c', 'print("hello")'])
            document = json.loads(kubectl.call_args.kwargs['input_text'])
        self.assertEqual(document['spec']['template']['spec']['containers'][0]['command'], ['python', '-c', 'print("hello")'])

    def test_failed_job_reports_immediately(self):
        job = {'status': {'failed': 1}}
        with patch.object(c, 'k', return_value=subprocess.CompletedProcess([], 0, json.dumps(job), '')), patch.object(c.time, 'sleep') as sleep:
            with self.assertRaises(c.ClusterError):
                c.wait_job('task-failed')
            sleep.assert_not_called()

    def test_new_device_joins_as_worker(self):
        self.seed()
        with patch.object(c, 'run_process', return_value=subprocess.CompletedProcess([], 0)), patch.object(c, 'ansible') as provision, patch.object(c, 'k'):
            c.main(['add-device', 'lab', '--address', '100.101.102.104', '--user', 'student', '--no-sudo-prompt'])
        self.assertEqual(c.load_config()['devices']['lab']['role'], 'worker')
        self.assertEqual(provision.call_args.args[1:3], ('lab', 'setup.yml'))

    def test_jobs_before_first_submission_is_read_only(self):
        self.seed()
        with patch.object(c, 'k', return_value=subprocess.CompletedProcess([], 0, '', '')) as kubectl:
            c.main(['jobs'])
        self.assertEqual(kubectl.call_count, 1)
        self.assertEqual(kubectl.call_args.args[:2], ('get', 'namespace'))

    def test_debug_cannot_override_cluster_credentials(self):
        for arguments in (['--context=other', 'get', 'nodes'], ['get', 'nodes', '--insecure-skip-tls-verify'], ['get', 'nodes', '-shttps://other'], []):
            with patch.object(c, 'k') as kubectl:
                with self.assertRaises(c.ClusterError):
                    c.debug_kubectl(arguments)
                kubectl.assert_not_called()
        with patch.object(c, 'k') as kubectl:
            c.debug_kubectl(['get', 'events', '-A'])
            kubectl.assert_called_once_with('get', 'events', '-A')

    def test_windows_payload_preserves_literal_container_arguments(self):
        self.seed()
        command = ['python', '-c', 'print("Xin chào $HOME")']
        arguments = ['run', 'home', '--image', 'sample:1', '--', *command]
        encoded = base64.b64encode(json.dumps(arguments).encode()).decode()
        with patch.dict(c.os.environ, {'CLUSTER_ARGUMENTS_BASE64': encoded}), patch.object(c, 'namespace'), patch.object(c, 'k') as kubectl:
            c.main()
        document = json.loads(kubectl.call_args.kwargs['input_text'])
        self.assertEqual(document['spec']['template']['spec']['containers'][0]['command'], command)

    def test_check_submits_network_job_per_device_and_actual_cuda_job(self):
        config = self.seed(worker=True, gpu=True)
        def response(*arguments, **kwargs):
            output = ''
            if arguments[0] == 'logs':
                output = 'Performance = 1 billion interactions' if arguments[1].startswith('job/gpu-check-') else 'Welcome to nginx!'
            return subprocess.CompletedProcess([], 0, output, '')
        with patch.object(c, 'namespace'), patch.object(c, 'wait_gpu'), patch.object(c, 'wait_job'), patch.object(c, 'k', side_effect=response) as kubectl:
            c.check_live(config)
        jobs = [json.loads(call.kwargs['input_text']) for call in kubectl.call_args_list if call.args[:2] == ('create', '-f')]
        cpu_jobs = [job for job in jobs if job['metadata']['name'].startswith('cpu-check-')]
        gpu_jobs = [job for job in jobs if job['metadata']['name'].startswith('gpu-check-')]
        self.assertEqual({job['spec']['template']['spec']['nodeSelector']['kubernetes.io/hostname'] for job in cpu_jobs}, {'home', 'lab'})
        self.assertEqual(len(gpu_jobs), 1)
        self.assertIn('-benchmark', gpu_jobs[0]['spec']['template']['spec']['containers'][0]['args'])
        self.assertEqual(gpu_jobs[0]['spec']['template']['spec']['runtimeClassName'], 'nvidia')

if __name__ == '__main__':
    unittest.main()
