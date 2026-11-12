"""Scripted transport controls. Local HTTP only; no provider calls or credentials."""
import base64
import copy
from concurrent.futures import Future
import json
from pathlib import Path
import tempfile
import threading
import time
import sys
import socket
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch

from benchmark.gateway_client import (AnthropicMessagesTransport, GatewayClient, Relay,
                                      ProviderTransportFailure, transport_detail)
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
    def test_frozen_command_contract_cannot_claim_a_different_correction_limit(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / 'config/external-subscription-proposal-native-tools.json').read_text())
        validate_config(config)
        for field, value in [('version', 'guess-a-command'), ('corrections_per_task', 2),
                             ('corrections_per_task', True), ('rejected_fragment_execution', True)]:
            changed = copy.deepcopy(config)
            changed['command_contract'][field] = value
            with self.assertRaises(ValueError):
                validate_config(changed)

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
            diagnostics = [json.loads(line) for line in (out / 'transport.jsonl').read_text().splitlines()]
            self.assertEqual([row['event'] for row in diagnostics], ['started', 'failed'])
            self.assertEqual(diagnostics[-1]['gateway_request_id'], rows[0]['call_id'])
            self.assertNotIn('Synthetic error', (out / 'transport.jsonl').read_text())

    def test_requests_near_the_deadline_are_released_not_left_unknown(self):
        # The SCI ablation's control stopped when a request started 3.2 s before
        # the deadline was cut off: an unknown outcome stops the whole pilot.
        calls = []
        def transport(body, _):
            calls.append(body)
            return response('fixture', 'fixture-model')
        with tempfile.TemporaryDirectory() as tmp, patch('benchmark.gateway_client.DISPATCH_FLOOR_SECONDS', 10**6):
            out = Path(tmp) / 'gateway'
            gateway = GatewayClient(out, CONFIG, transport)
            try:
                for name in ('late', 'later'):
                    with self.assertRaises(RuntimeError):
                        gateway.submit('prime', request(name)).result(timeout=10)
            finally:
                gateway.close()
            self.assertEqual(calls, [])
            self.assertEqual((out / 'usage.jsonl').read_text().strip(), '')
            report = json.loads((out / 'report.json').read_text())
            self.assertEqual(report['uncertain_requests'], 0)
            events = (out / 'events.jsonl').read_text()
            self.assertEqual(events.count('provider-not-dispatched'), 2)
            diagnostics = [json.loads(line)['event'] for line in (out / 'transport.jsonl').read_text().splitlines()]
            self.assertEqual(diagnostics, ['not-dispatched', 'not-dispatched'])

    def test_a_sent_request_may_finish_after_the_deadline_so_its_cost_is_known(self):
        seen = []
        def slow(body, allowed):
            seen.append(allowed)
            time.sleep(4.0)
            return response('fixture', 'fixture-model')
        with tempfile.TemporaryDirectory() as tmp, patch('benchmark.gateway_client.DISPATCH_FLOOR_SECONDS', 0), \
             patch('benchmark.gateway_client.IN_FLIGHT_GRACE_SECONDS', 5):
            out = Path(tmp) / 'gateway'
            gateway = GatewayClient(out, CONFIG, slow)
            # Compress only this test's remaining time: 1 s left, a 4 s reply.
            gateway.deadline = time.monotonic() + 1
            future = gateway.submit('prime', request('in-flight'))
            # Close before the reply: close waits for the sent request.
            gateway.close()
            self.assertEqual(future.result(timeout=10)['status'], 200)
            self.assertTrue(5 < seen[0] < 6.1)
            rows = [json.loads(line) for line in (out / 'usage.jsonl').read_text().splitlines()]
            self.assertEqual([row['status'] for row in rows], ['complete'])
            self.assertEqual(json.loads((out / 'report.json').read_text())['uncertain_requests'], 0)

    def test_request_can_use_remaining_task_time_but_cannot_extend_it(self):
        # Advance a fake clock, not a 61-second sleep. The old hidden 45-second
        # limit rejects this healthy reply before the 90-second task deadline.
        clock = [100.0]
        class Headers:
            def get_content_type(self): return 'application/json'
        class Response:
            status, headers, closed = 200, Headers(), False
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def isclosed(self): return self.closed
            def set_read_timeout(self, remaining):
                self.remaining = remaining
            def read1(self, _):
                self.closed = True
                return b'{"ok":true}'
        def opener(wire, timeout):
            self.assertEqual(timeout, 90)
            clock[0] += 61
            return Response()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'FAKE-LOCAL-TEST-ONLY'}), \
             patch('benchmark.gateway_client.time.monotonic', side_effect=lambda: clock[0]):
            transport = AnthropicMessagesTransport(authorized=True, opener=opener)
            self.assertEqual(transport(request('delayed'), 90)['body'], '{"ok":true}')
            def too_late(wire, timeout):
                clock[0] += 91
                return Response()
            transport.opener = too_late
            with self.assertRaises(ProviderTransportFailure) as caught:
                transport(request('late'), 90)
            self.assertEqual(caught.exception.detail['category'], 'deadline')

    def test_host_timeout_keeps_partial_stream_and_request_stage(self):
        from benchmark.line_process import LineProcess
        peers = []
        partial = b'event: message_start\ndata: {"type":"message_start"}\n\n'
        def fake_worker(*args, **kwargs):
            source = ("import json,sys,time; input(); "
                      "print(json.dumps({'progress':{'stage':'response','http_status':200,'provider_request_id':'req_fixture'}}),flush=True); "
                      "print(json.dumps({'chunk':" + repr(base64.b64encode(partial).decode()) + "}),flush=True); time.sleep(10)")
            peer = LineProcess([sys.executable, '-c', source]); peers.append(peer)
            return peer
        frames, chunks = [], []
        with patch('benchmark.gateway_client.LineProcess', side_effect=fake_worker):
            transport = AnthropicMessagesTransport(authorized=True)
            with self.assertRaises(ProviderTransportFailure) as caught:
                transport.request(request('partial'), .3,
                                  observer=lambda detail, chunk: chunks.append(chunk) if chunk is not None else frames.append(detail))
        self.assertEqual(b''.join(chunks), partial)
        self.assertEqual(caught.exception.detail['stage'], 'response')
        self.assertEqual(caught.exception.detail['category'], 'deadline')
        self.assertEqual(caught.exception.detail['provider_request_id'], 'req_fixture')
        self.assertIsNotNone(peers[0].process.poll())

    def test_network_categories_never_copy_exception_text(self):
        cases = [(socket.gaierror('SECRET'), 'dns'), (ssl.SSLError('SECRET'), 'tls'),
                 (TimeoutError('SECRET'), 'deadline'), (ConnectionResetError('SECRET'), 'network')]
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'FAKE-LOCAL-TEST-ONLY'}):
            for error, expected in cases:
                def fail(*args, **kwargs): raise urllib.error.URLError(error)
                transport = AnthropicMessagesTransport(authorized=True, opener=fail)
                with self.assertRaises(ProviderTransportFailure) as caught:
                    transport(request('fail'), 2)
                self.assertEqual(caught.exception.detail['category'], expected)
                self.assertEqual(caught.exception.detail['stage'], 'connect')
                self.assertNotIn('SECRET', str(caught.exception) + json.dumps(caught.exception.detail))
        self.assertEqual(transport_detail({'stage':'SECRET', 'category':'SECRET', 'http_status':'SECRET',
                                           'provider_request_id':'sk-ant-oat-SECRET', 'elapsed_ms':float('nan'),
                                           'Authorization':'SECRET'}), {})

    def test_http_errors_are_recorded_without_secret_messages_or_retries(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                requests.append(self.path)
                raw = json.dumps({'type':'error','error':{'type':'rate_limit_error','message':'SECRET-TEST-CREDENTIAL'}}).encode()
                self.send_response(429)
                self.send_header('Content-Type','application/json')
                self.send_header('request-id','req_rate_limit_fixture')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01),daemon=True); thread.start()
        try:
            def opener(wire, timeout):
                return urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port),timeout=timeout)
            with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ',{'ANTHROPIC_API_KEY':'FAKE-LOCAL-TEST-ONLY'}):
                out=Path(tmp)/'gateway'
                gateway=GatewayClient(out,CONFIG,AnthropicMessagesTransport(authorized=True,opener=opener))
                try:
                    with self.assertRaises(RuntimeError): gateway.submit('prime',request('rate limit')).result(timeout=10)
                    with self.assertRaises(RuntimeError): gateway.submit('prime',request('must not retry')).result(timeout=10)
                finally: gateway.close()
                self.assertEqual(len(requests),1)
                evidence=(out/'events.jsonl').read_text()+(out/'transport.jsonl').read_text()
                self.assertNotIn('SECRET',evidence)
                self.assertIn('rate_limit_error',evidence)
                self.assertIn('req_rate_limit_fixture',evidence)
                self.assertIn('429',evidence)
                usage=json.loads((out/'usage.jsonl').read_text())
                self.assertEqual((usage['status'],usage['reserved_usd']),('unknown',.005))
                self.assertFalse((out/'transport-bodies').exists())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_real_http_worker_preserves_signed_stream_and_truncated_evidence(self):
        from benchmark.line_process import LineProcess
        complete = response({'code': 'print(6)'}, 'fixture-model', stream=True, signed=True)['body'].encode()
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                partial = self.path == '/truncated'
                raw = complete[:len(complete)//2] if partial else complete
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('request-id', 'req_real_worker_fixture')
                self.send_header('Content-Length', str(len(complete)))
                self.end_headers(); self.wfile.write(raw); self.wfile.flush()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True); thread.start()
        try:
            for suffix in ('/complete', '/truncated'):
                with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                    peers = []
                    def worker(arguments, **kwargs):
                        if arguments == ['python3', '-m', 'benchmark.api_http_worker']:
                            # Local fixture endpoint only. The production worker,
                            # framing, gateway and HTTP reader remain executable.
                            source = ("from benchmark.gateway_client import AnthropicMessagesTransport as T; "
                                      "T.endpoint=" + repr('http://127.0.0.1:'+str(server.server_port)+suffix) + "; "
                                      "T.request_headers=lambda self: {'Content-Type':'application/json'}; "
                                      "from benchmark.api_http_worker import main; main()")
                            peer = LineProcess([sys.executable, '-c', source], **kwargs)
                            peers.append(peer); return peer
                        return LineProcess(arguments, **kwargs)
                    out = Path(tmp)/'gateway'
                    body = {**request('native content'), 'stream': True,
                            'tools': [{'name':'ipython','input_schema':{'type':'object'}}]}
                    with patch('benchmark.gateway_client.LineProcess', side_effect=worker):
                        gateway = GatewayClient(out, CONFIG, AnthropicMessagesTransport(authorized=True))
                        try:
                            future = gateway.submit('prime', body)
                            if suffix == '/complete':
                                self.assertEqual(future.result(timeout=10)['body'].encode(), complete)
                            else:
                                with self.assertRaises(RuntimeError): future.result(timeout=10)
                        finally: gateway.close()
                    saved = list((out/'transport-bodies').glob('*.body'))
                    self.assertEqual(len(saved),1)
                    self.assertEqual(saved[0].read_bytes(), complete if suffix == '/complete' else complete[:len(complete)//2])
                    usage = json.loads((out/'usage.jsonl').read_text())
                    audit = [json.loads(x) for x in (out/'transport.jsonl').read_text().splitlines()]
                    self.assertTrue(all(x['gateway_request_id']==usage['call_id'] for x in audit))
                    self.assertEqual(usage['status'], 'complete' if suffix == '/complete' else 'unknown')
                    if suffix == '/truncated':
                        self.assertEqual(audit[-1]['category'], 'incomplete')
                        self.assertEqual(audit[-1]['http_status'],200)
                        self.assertEqual(usage['reserved_usd'],.005)
                    self.assertTrue(all(peer.process.poll() is not None for peer in peers))
                    self.assertEqual(requests[-1],body)
            self.assertEqual(len(requests),2)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

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
            def set_read_timeout(self, _):
                pass
            def read1(self, _):
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

    def test_slow_response_has_total_deadline_and_no_orphan_transport(self):
        from benchmark.line_process import LineProcess
        peers = []
        def fake_worker(*args, **kwargs):
            source = "import sys,time; input();\nwhile True:\n sys.stdout.write('x');sys.stdout.flush();time.sleep(.01)"
            peer = LineProcess([sys.executable, '-c', source])
            peers.append(peer)
            return peer
        with patch('benchmark.gateway_client.LineProcess', side_effect=fake_worker):
            transport = AnthropicMessagesTransport(authorized=True)
            started = time.monotonic()
            with self.assertRaises(RuntimeError):
                transport(request('drip'), .2)
            self.assertLess(time.monotonic() - started, 2)
            self.assertIsNotNone(peers[0].process.poll())
            errors = []
            def call():
                try:
                    transport(request('cancel'), 30)
                except RuntimeError:
                    errors.append(True)
            thread = threading.Thread(target=call)
            thread.start()
            time.sleep(.1)
            transport.cancel_pending()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [True])
            self.assertIsNotNone(peers[1].process.poll())

    def test_real_http_content_length_and_chunked_eof(self):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                data = b'{"ok":true}'
                if self.path == '/chunked':
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    for piece in (data[:4], data[4:]):
                        self.wfile.write(('%x\r\n' % len(piece)).encode() + piece + b'\r\n')
                    self.wfile.write(b'0\r\n\r\n')
                else:
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                self.wfile.flush()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
        thread.start()
        try:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'FAKE-LOCAL-TEST-ONLY'}):
                for suffix in ('/length', '/chunked'):
                    def local_opener(wire, timeout):
                        return urllib.request.urlopen('http://127.0.0.1:' + str(server.server_port) + suffix, timeout=timeout)
                    transport = AnthropicMessagesTransport(authorized=True, opener=local_opener)
                    self.assertEqual(transport(request('local only'), 2)['body'], '{"ok":true}')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

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
        killed = {'startup_ready': True, 'exit_code': 137, 'failure': None, 'stderr': '',
                  'container_state': {'OOMKilled': False}}
        self.assertFalse(denied('allocation', killed))
        self.assertTrue(denied('allocation', {**killed, 'container_state': {'OOMKilled': True}}))


if __name__ == '__main__':
    unittest.main()
