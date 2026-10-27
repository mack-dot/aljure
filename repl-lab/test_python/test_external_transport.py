"""Scripted transport controls. No Docker, network, API keys or model inference."""
import copy
from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from benchmark.gateway_client import AnthropicMessagesTransport, GatewayClient, Relay
from benchmark.prime.isolation import denied
from benchmark.paired import validate_config, runtime_snapshot
from benchmark.relay_fixture import response

CONFIG = {'model': 'fixture-model', 'context-window': 1000, 'max-output': 100,
          'pinned-settings': {}, 'routes': ['prime'],
          'rates': {'input': 2, 'output': 10, 'cache-read': .2, 'cache-write-5m': 2.5, 'cache-write-1h': 4},
          'limits': {'calls': 8, 'tokens': 100000, 'usd': .02, 'wall-ms': 120000, 'concurrent-subagents': 8}}


def request(name):
    return {'model': 'fixture-model', 'messages': [{'role': 'user', 'content': name}], 'max_tokens': 100}


class ExternalTransportTests(unittest.TestCase):
    def test_attestation_ignores_evidence_but_rejects_runtime_config_and_locks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ['src/repl_lab/runtime.clj', 'scripts/isolation.py', 'worker/deps.edn',
                     'benchmark/vendor/scorer.py', 'benchmark/upstream.lock.json',
                     'resources/base-instructions.txt', 'config/experiment.edn', 'Makefile']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('original')
            baseline = runtime_snapshot(root)
            for name in ['research/results.md', 'research/evidence/raw.json', 'test_python/test_new.py',
                         'var/new-plan.json', 'benchmark/__pycache__/module.pyc']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('new evidence')
            self.assertEqual(runtime_snapshot(root), baseline)
            for name in names:
                path = root / name
                path.write_text('changed')
                self.assertNotEqual(runtime_snapshot(root)['sha256'], baseline['sha256'], name)
                path.write_text('original')
            (root / 'scripts/new_executable.py').write_text('new')
            self.assertNotEqual(runtime_snapshot(root)['sha256'], baseline['sha256'])

    def test_parallel_requests_share_global_reservations(self):
        release, entered, lock = threading.Event(), [], threading.Lock()
        def transport(body, _):
            with lock:
                entered.append(body['messages'][0]['content'])
            self.assertTrue(release.wait(10))
            return response('fixture', 'fixture-model')
        with tempfile.TemporaryDirectory() as tmp:
            gateway = GatewayClient(Path(tmp) / 'gateway', CONFIG, transport)
            try:
                # Names describe scripted request intents, not inferred native attribution.
                futures = [gateway.submit('prime', request(name)) for name in ('root', 'child', 'refinement', 'compaction')]
                rejected = gateway.submit('prime', request('over-budget'))
                with self.assertRaises(RuntimeError):
                    rejected.result(timeout=10)
                with lock:
                    self.assertEqual(set(entered), {'root', 'child', 'refinement', 'compaction'})
                release.set()
                self.assertTrue(all(f.result(timeout=10)['status'] == 200 for f in futures))
            finally:
                release.set()
                gateway.close()
            usage = [json.loads(line) for line in (Path(tmp) / 'gateway/usage.jsonl').read_text().splitlines()]
            self.assertEqual(len(usage), 4)
            self.assertTrue(all(row['status'] == 'complete' for row in usage))
            self.assertTrue(all('unverified' in row['session_identity'] for row in usage))

    def test_transport_failure_retains_reservation_and_stops_next_call(self):
        calls = []
        def failed(body, _):
            calls.append(body)
            raise RuntimeError('Synthetic error that must not enter the ledger')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'gateway'
            gateway = GatewayClient(out, CONFIG, failed)
            try:
                with self.assertRaises(RuntimeError):
                    gateway.submit('prime', request('first')).result(timeout=10)
                with self.assertRaises(RuntimeError):
                    gateway.submit('prime', request('second')).result(timeout=10)
            finally:
                gateway.close()
            self.assertEqual(len(calls), 1)
            rows = [json.loads(line) for line in (out / 'usage.jsonl').read_text().splitlines()]
            self.assertEqual([(row['status'], row['reserved_usd']) for row in rows], [('unknown', .005)])
            self.assertNotIn('Synthetic error', (out / 'events.jsonl').read_text())

    def test_subscription_or_missing_authorization_never_reads_credentials(self):
        with patch('benchmark.gateway_client.os.environ', {}) as environment:
            with self.assertRaises(ValueError):
                AnthropicMessagesTransport()
            with self.assertRaises(ValueError):
                validate_config({'provider': 'claude-subscription'})
            self.assertEqual(dict(environment), {})

    def test_http_body_and_sse_preserved_and_errors_sanitized(self):
        class Headers:
            def get_content_type(self):
                return 'text/event-stream'
        class FakeResponse:
            status, headers = 200, Headers()
            def __enter__(self):
                self.parts = iter([b'event: ping\ndata: {}\n\n', b''])
                return self
            def __exit__(self, *args):
                pass
            def read(self, _):
                return next(self.parts)
        seen = []
        def opener(wire, timeout):
            seen.append(json.loads(wire.data))
            self.assertEqual(wire.full_url, 'https://api.anthropic.com/v1/messages')
            return FakeResponse()
        body = {**request('native'), 'stream': True, 'tools': [{'name': 'ipython', 'input_schema': {}}]}
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'FAKE-TEST-ONLY'}):
            transport = AnthropicMessagesTransport(authorized=True, opener=opener)
            self.assertEqual(transport(body, 10)['body'], 'event: ping\ndata: {}\n\n')
            self.assertEqual(seen, [body])
            transport.opener = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('FAKE-TEST-ONLY'))
            with self.assertRaises(RuntimeError) as caught:
                transport(body, 10)
            self.assertNotIn('FAKE-TEST-ONLY', str(caught.exception))

    def test_relay_does_not_serialize_children_and_rejects_duplicate_ids(self):
        class FakeGateway:
            def __init__(self):
                self.futures = []
            def submit(self, route, body):
                result = Future()
                self.futures.append(result)
                return result
        gateway = FakeGateway()
        relay = Relay(gateway, 'prime')
        for identifier in ('root', 'child'):
            relay({'type': 'external_provider_request', 'id': identifier, 'body': request(identifier)}, 10)
        gateway.futures[1].set_result(response('child', 'fixture-model'))
        self.assertEqual(json.loads(relay.poll())['id'], 'child')
        self.assertEqual(len(relay.pending), 1)
        with self.assertRaises(ValueError):
            relay({'type': 'external_provider_request', 'id': 'root', 'body': request('root')}, 10)

    def test_startup_failure_never_counts_as_security_restriction(self):
        for name in ('loop', 'allocation', 'oversized-output', 'host-read', 'root-write', 'network', 'evaluator'):
            self.assertFalse(denied(name, {'startup_ready': False, 'exit_code': 137,
                                         'failure': 'wall-time-limit', 'stderr': 'MemoryError'}))
        self.assertFalse(denied('root-write', {'startup_ready': True, 'exit_code': 1,
                                              'failure': None, 'stderr': 'SyntaxError'}))


if __name__ == '__main__':
    unittest.main()
