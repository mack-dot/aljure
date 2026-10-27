"""V3 transport regressions: virtual time, real local processes, no provider calls."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.gateway_client import AnthropicMessagesTransport, GatewayClient
from benchmark.line_process import LineProcess
from benchmark.relay_fixture import response
from test_python.test_external_transport import CONFIG, request


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class V3TransportTests(unittest.TestCase):
    def test_long_success_and_remaining_task_deadline_use_distinct_clocks(self):
        for startup, duration, success in [(20, 61, True), (30, 91, False)]:
            with self.subTest(startup=startup, duration=duration), tempfile.TemporaryDirectory() as tmp:
                now = [1000.0]
                clock = SimpleNamespace(monotonic=lambda: now[0], time=time.time)
                raw = response('fixture answer', 'fixture-model')['body'].encode()
                class Headers:
                    def get_content_type(self): return 'application/json'
                class Reply:
                    status, headers, closed = 200, Headers(), False
                    def __enter__(self): return self
                    def __exit__(self, *_): pass
                    def isclosed(self): return self.closed
                    def set_read_timeout(self, _): pass
                    def read1(self, _):
                        self.closed = True
                        now[0] += duration
                        return raw
                calls = []
                def opener(wire, timeout):
                    calls.append(timeout)
                    self.assertEqual(timeout, 120-startup)
                    return Reply()
                out = Path(tmp)/'gateway'
                with patch('benchmark.gateway_client.time', clock), patch.dict('os.environ', {'ANTHROPIC_API_KEY':'FIXTURE-NOT-A-CREDENTIAL'}):
                    gateway = GatewayClient(out, CONFIG, AnthropicMessagesTransport(authorized=True, opener=opener))
                    now[0] += startup
                    try:
                        pending = gateway.submit('prime', request('long response'))
                        if success:
                            self.assertEqual(pending.result(timeout=10)['body'].encode(), raw)
                        else:
                            with self.assertRaises(RuntimeError): pending.result(timeout=10)
                    finally: gateway.close()
                usage = rows(out/'usage.jsonl')[0]
                self.assertEqual(usage['status'], 'complete' if success else 'unknown')
                if not success: self.assertEqual(usage['reserved_usd'], .005)
                self.assertEqual(len(calls), 1)
                self.assertEqual(next((out/'transport-bodies').glob('*')).read_bytes(), raw)
                audit = rows(out/'transport.jsonl')
                self.assertEqual(audit[0]['task_remaining_ms'], (120-startup)*1000)
                self.assertEqual(audit[-1]['elapsed_ms'], duration*1000)
                self.assertEqual(audit[-1]['task_elapsed_ms'], (startup+duration)*1000)
                if not success: self.assertEqual(audit[-1]['category'], 'deadline')
                self.assertIsNotNone(gateway.peer.process.poll())

    def test_missing_or_malformed_terminal_usage_keeps_full_reservation(self):
        for terminal in [None, {}, {'output_tokens':'20'}, {'output_tokens':-1}]:
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory() as tmp:
                reply = response('fixture', 'fixture-model', stream=True)
                frames = [json.loads(frame.split('data: ',1)[1]) for frame in reply['body'].strip().split('\n\n')]
                for event in frames:
                    if event['type']=='message_delta':
                        if terminal is None: event.pop('usage')
                        else: event['usage']=terminal
                reply['body']=''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in frames)
                out=Path(tmp)/'gateway'; calls=[]
                def transport(body, remaining): calls.append(body); return reply
                gateway=GatewayClient(out, CONFIG, transport)
                try:
                    with self.assertRaises(RuntimeError): gateway.submit('prime', request('invalid usage')).result(timeout=10)
                    with self.assertRaises(RuntimeError): gateway.submit('prime', request('no retry')).result(timeout=10)
                finally: gateway.close()
                self.assertEqual(len(calls),1)
                usage=rows(out/'usage.jsonl')[0]
                self.assertEqual((usage['status'],usage['reserved_usd']),('unknown',.005))
                events=rows(out/'events.jsonl')
                self.assertEqual(next(e['payload']['response'] for e in events if e['type']=='gateway-response'),reply)
                self.assertTrue(any(e['type']=='gateway-receipt-rejected' and e['payload']['category']=='terminal-usage' for e in events))

    def test_partial_stream_stall_and_cancellation_preserve_unknown_usage(self):
        partial=b'event: message_start\ndata: {"type":"message_start"}\n\n'
        for cancelled in [False, True]:
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as tmp:
                peers=[]
                source=("import json,time; input(); print(json.dumps({'progress':{'stage':'response','http_status':200}}),flush=True); "
                        "print(json.dumps({'chunk':"+repr(base64.b64encode(partial).decode())+"}),flush=True); time.sleep(20)")
                def worker(args, **kwargs):
                    if args==['python3','-m','benchmark.api_http_worker']:
                        p=LineProcess([sys.executable,'-c',source],**kwargs);peers.append(p);return p
                    return LineProcess(args,**kwargs)
                out=Path(tmp)/'gateway'; transport=AnthropicMessagesTransport(authorized=True)
                with patch('benchmark.gateway_client.LineProcess',side_effect=worker):
                    gateway=GatewayClient(out,CONFIG,transport)
                    # Compress only the test's remaining time; production remains 120s.
                    gateway.deadline=time.monotonic()+(.8 if not cancelled else 10)
                    began=time.monotonic()
                    future=gateway.submit('prime',request('partial'))
                    if cancelled:
                        until=time.monotonic()+5
                        while not list((out/'transport-bodies').glob('*.body')) and time.monotonic()<until:
                            time.sleep(.01)
                        self.assertTrue(list((out/'transport-bodies').glob('*.body')))
                        transport.cancel_pending()
                    try:
                        with self.assertRaises(RuntimeError): future.result(timeout=5)
                    finally: gateway.close()
                self.assertLess(time.monotonic()-began,5)
                self.assertTrue(all(p.process.poll() is not None for p in peers))
                self.assertEqual(next((out/'transport-bodies').glob('*')).read_bytes(),partial)
                self.assertEqual(rows(out/'usage.jsonl')[0]['status'],'unknown')
                self.assertEqual(rows(out/'usage.jsonl')[0]['reserved_usd'],.005)
                audit=rows(out/'transport.jsonl')
                self.assertEqual(audit[-1]['category'],'cancelled' if cancelled else 'deadline')
                self.assertEqual(audit[-1]['response_bytes'],len(partial))

    def test_received_response_survives_http_helper_cleanup_failure(self):
        reply=response('fixture', 'fixture-model'); peers=[]
        source="import json; input(); print(json.dumps({'response':"+repr(reply)+"}),flush=True)"
        def worker(args, **kwargs):
            p=LineProcess([sys.executable,'-c',source],**kwargs) if args==['python3','-m','benchmark.api_http_worker'] else LineProcess(args,**kwargs)
            if args==['python3','-m','benchmark.api_http_worker']:
                close=p.close
                def failed_close(): close(); raise PermissionError('SECRET-DO-NOT-LOG')
                p.close=failed_close; peers.append(p)
            return p
        with tempfile.TemporaryDirectory() as tmp, patch('benchmark.gateway_client.LineProcess',side_effect=worker):
            out=Path(tmp)/'gateway'; gateway=GatewayClient(out,CONFIG,AnthropicMessagesTransport(authorized=True))
            try:
                with self.assertRaises(RuntimeError): gateway.submit('prime',request('complete then cleanup fails')).result(timeout=10)
                with self.assertRaises(RuntimeError): gateway.submit('prime',request('do not dispatch')).result(timeout=10)
            finally:
                with self.assertRaises(RuntimeError): gateway.close()
            usage=rows(out/'usage.jsonl')
            self.assertEqual(len(usage),1)
            self.assertEqual(usage[0]['status'],'complete')
            self.assertEqual((usage[0]['input_tokens'],usage[0]['output_tokens']),(100,20))
            events=rows(out/'events.jsonl')
            self.assertEqual(next(e['payload']['response'] for e in events if e['type']=='gateway-response'),reply)
            self.assertEqual(rows(out/'transport.jsonl')[-1]['category'],'cleanup')
            self.assertTrue(all(p.process.poll() is not None for p in peers))
            self.assertNotIn('SECRET', (out/'transport.jsonl').read_text())

    def test_gateway_cleanup_failure_does_not_discard_settled_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'gateway'
            gateway=GatewayClient(out,CONFIG,lambda body, remaining: response('fixture','fixture-model'))
            gateway.submit('prime',request('settled')).result(timeout=10)
            close=gateway.peer.close
            def failed_close(): close(); raise OSError('SECRET-DO-NOT-LOG')
            with patch.object(gateway.peer,'close',side_effect=failed_close):
                with self.assertRaises(RuntimeError): gateway.close()
            self.assertEqual(rows(out/'usage.jsonl')[0]['status'],'complete')
            cleanup=json.loads((out/'cleanup.json').read_text())
            self.assertFalse(cleanup['ok'])
            self.assertIn('gateway-peer',cleanup['failed_stages'])
            self.assertTrue(cleanup['transport_pool_joined'])
            self.assertIsNotNone(gateway.peer.process.poll())
            self.assertNotIn('SECRET',(out/'cleanup.json').read_text())


if __name__=='__main__': unittest.main()
