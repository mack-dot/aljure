"""Provider-transport failure modes. Scripted frames and fakes only: no network,
credentials, model calls or Docker. The gateway is the real Clojure process."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from benchmark import paired
from benchmark.gateway_client import AnthropicMessagesTransport, GatewayClient, ProviderTransportFailure
from benchmark.line_process import LineProcess
from benchmark.relay_fixture import response
from test_python.test_external_transport import CONFIG, request

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class TransportFailureTests(unittest.TestCase):
    def test_cancel_before_dispatch_never_opens_a_connection_or_retries(self):
        opened = []
        def opener(wire, timeout):
            opened.append(timeout)
            raise AssertionError('A cancelled transport must not connect')
        transport = AnthropicMessagesTransport(authorized=True, opener=opener)
        transport.cancel_pending()
        # No credential is configured: a cancelled request must stop before reading one.
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ProviderTransportFailure) as caught:
            transport.request(request('cancelled'), 30)
        self.assertEqual(caught.exception.detail, {'stage': 'host', 'category': 'cancelled'})
        self.assertIsNone(caught.exception.response)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'gateway'
            gateway = GatewayClient(out, CONFIG, transport)
            try:
                with self.assertRaises(RuntimeError):
                    gateway.submit('prime', request('cancelled before dispatch')).result(timeout=20)
                with self.assertRaises(RuntimeError):
                    gateway.submit('prime', request('must not be sent')).result(timeout=20)
            finally:
                gateway.close()
            self.assertEqual(opened, [])
            # Never charged as complete. Holding the reservation as unknown is the
            # current, conservative outcome; a not-dispatched release would also be safe.
            usage = [(row['status'], row.get('reserved_usd')) for row in rows(out / 'usage.jsonl')]
            self.assertIn(usage, ([('unknown', .005)], []))
            audit = rows(out / 'transport.jsonl')
            self.assertEqual((audit[-1]['stage'], audit[-1]['category']), ('host', 'cancelled'))
            self.assertEqual([row['event'] for row in audit], ['started', 'failed'])

    def test_bridge_rejects_duplicate_late_and_reused_transport_frames(self):
        config = {**CONFIG, 'routes': ['prime/task']}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            peer = LineProcess([sys.executable, 'scripts/clj.py', '-m', 'repl-lab.gateway-stdio', str(out), 'v2'], cwd=ROOT)
            def frame(**command):
                peer.send(command)
                return peer.read(seconds=30)
            def answer(identifier, **fields):
                return frame(op='provider_response', transport_id=identifier, transport_error=False,
                             cleanup_failure=False, not_dispatched=False, **fields)
            try:
                peer.send({'evidence': 'FIXTURE', 'config': config})
                self.assertEqual(peer.read(seconds=60)['type'], 'gateway_ready')
                receipt = response('fixture', 'fixture-model')
                invoke = {'op': 'invoke', 'route': 'prime/task', 'body': request('fixture')}
                self.assertEqual(frame(transport_id='t1', **invoke)['type'], 'provider_request')
                self.assertEqual(answer('t1', response=receipt)['type'], 'gateway_result')
                # The same delivery twice: no second settlement.
                self.assertEqual(answer('t1', response=receipt)['type'], 'gateway_error')
                # A reused transport ID is not admitted again.
                self.assertEqual(frame(transport_id='t1', **invoke)['type'], 'gateway_error')
                self.assertEqual(frame(transport_id='t2', **invoke)['type'], 'provider_request')
                lost = frame(op='provider_response', transport_id='t2', response=None, transport_error=True,
                             cleanup_failure=False, not_dispatched=False)
                self.assertEqual((lost['type'], lost['message']), ('gateway_error', 'Provider outcome uncertain'))
                # A response that arrives after the request was abandoned is refused.
                self.assertEqual(answer('t2', response=response('late', 'fixture-model'))['type'], 'gateway_error')
                # An unknown outcome stops all further dispatch.
                self.assertEqual(frame(transport_id='t3', **invoke)['type'], 'gateway_error')
                closed = frame(op='close')
                self.assertEqual(closed['type'], 'gateway_closed')
            finally:
                peer.close()
            report = closed['report']
            self.assertEqual(report['status'], 'gateway-stopped')
            self.assertEqual((report['spent']['calls'], report['reserved']['calls']), (1, 1))
            self.assertEqual((report['spent']['tokens'], report['reserved']['usd']), (120, .005))
            self.assertEqual(sorted(row['status'] for row in rows(out / 'usage.jsonl')), ['complete', 'unknown'])
            events = rows(out / 'events.jsonl')
            # The duplicate and late frames never reached the receipt path.
            self.assertEqual(sum(e['type'] == 'gateway-response' for e in events), 1)
            self.assertEqual(sum(e['type'] == 'gateway-request-intent' for e in events), 2)

    def test_an_unknown_receipt_stops_the_pilot_before_the_next_arm(self):
        config = {'provider': 'anthropic-api', 'model': 'fixture-model', 'context_window': 1000, 'max_output_tokens': 100,
                  'pinned_settings': {}, 'rates': CONFIG['rates'], 'calls_per_arm': 8, 'tokens_per_arm': 100000,
                  'usd_per_arm': .02, 'concurrent_requests': 8}
        value = {'plan_sha256': 'fixture-plan', 'config': config, 'capability_sha256': 'fixture',
                 'source': {'commit': 'fixture', 'sha256': 'fixture'},
                 'sequence': [{'task_id': 't1', 'harness': 'aljure'}, {'task_id': 't1', 'harness': 'prime'}]}
        ready = {'ready': True, 'blockers': [], 'checks': {'prime_isolation': {'image': 'p'}, 'sci_isolation': {'image': 's'}}}
        gateways, arms = [], []

        class Gateway:
            """Settles the arm's only request as an unknown outcome."""
            def __init__(self, output, gateway_config, transport, *, evidence):
                self.output = Path(output)
                gateways.append(evidence)
            def close(self):
                self.output.mkdir(parents=True, exist_ok=True)
                (self.output / 'usage.jsonl').write_text(json.dumps({'status': 'unknown', 'reserved_usd': .005}) + '\n')

        def run_arm(harness, data, out, config, gateway, readiness):
            arms.append(harness)
            (out / 'answer.txt').write_text('6')  # Even an answered arm cannot hide the unknown outcome.
            return {'completion': {'native_exit_code': 0}}

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(paired, 'read_plan', return_value=(value, {'suite_sha256': 'suite'}, {'t1': {'task_sha256': 'task'}})), \
             patch.object(paired, 'preflight', return_value=ready), \
             patch.object(paired, 'docker_state', return_value={'session': 'fixed', 'restart_pending': False, 'images': {}}), \
             patch.object(paired, 'public_input', return_value={'task': {}, 'context': ''}), \
             patch.object(paired, 'GatewayClient', Gateway), patch.object(paired, 'run_arm', run_arm), \
             patch.object(paired, 'compare', return_value={}):
            paired.run('plan.json', 'suite', Path(tmp) / 'out', authorize_api_plan='fixture-plan')
            results = rows(Path(tmp) / 'out/results.jsonl')
        self.assertEqual((arms, gateways), (['aljure'], ['LIVE MODEL RUN']))
        self.assertEqual([(r['status'], r['failure']) for r in results],
                         [('error', 'ProviderOutcomeUnknown'), ('error', 'ValueError')])
        self.assertNotIn('answer_path', results[0])

    def test_a_refused_worker_isolation_preflight_stops_the_pilot(self):
        config = {'provider': 'anthropic-api', 'model': 'fixture-model', 'context_window': 1000, 'max_output_tokens': 100,
                  'pinned_settings': {}, 'rates': CONFIG['rates'], 'calls_per_arm': 8, 'tokens_per_arm': 100000,
                  'usd_per_arm': .02, 'concurrent_requests': 8}
        value = {'plan_sha256': 'fixture-plan', 'config': config, 'capability_sha256': 'fixture',
                 'source': {'commit': 'fixture', 'sha256': 'fixture'},
                 'sequence': [{'task_id': 't1', 'harness': 'aljure'}, {'task_id': 't1', 'harness': 'prime'}]}
        ready = {'ready': True, 'blockers': [], 'checks': {'prime_isolation': {'image': 'p'}, 'sci_isolation': {'image': 's'}}}
        arms = []

        class Gateway:
            def __init__(self, output, gateway_config, transport, *, evidence):
                self.output = Path(output)
            def close(self):
                self.output.mkdir(parents=True, exist_ok=True)
                (self.output / 'usage.jsonl').write_text('')

        def run_arm(harness, data, out, config, gateway, readiness):
            # The F2 MultiNLI shape: docker info timed out, the worker was refused, no call was made.
            arms.append(harness)
            (out / 'worker-audit/preflight').mkdir(parents=True)
            (out / 'worker-audit/preflight/w.json').write_text(json.dumps(
                {'ready': False, 'reason': 'Isolation preflight failed at docker-info: TimeoutExpired'}))
            return {'completion': {'native_exit_code': 2}}

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(paired, 'read_plan', return_value=(value, {'suite_sha256': 'suite'}, {'t1': {'task_sha256': 'task'}})), \
             patch.object(paired, 'preflight', return_value=ready), \
             patch.object(paired, 'docker_state', return_value={'session': 'fixed', 'restart_pending': False, 'images': {}}), \
             patch.object(paired, 'public_input', return_value={'task': {}, 'context': ''}), \
             patch.object(paired, 'GatewayClient', Gateway), patch.object(paired, 'run_arm', run_arm), \
             patch.object(paired, 'compare', return_value={}):
            paired.run('plan.json', 'suite', Path(tmp) / 'out', authorize_api_plan='fixture-plan')
            results = rows(Path(tmp) / 'out/results.jsonl')
        self.assertEqual(arms, ['aljure'])
        self.assertEqual([(r['status'], r['failure']) for r in results],
                         [('error', 'IsolationPreflightFailed'), ('error', 'ValueError')])


if __name__ == '__main__':
    unittest.main()
