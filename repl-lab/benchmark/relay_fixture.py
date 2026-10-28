"""Explicit scripted control through the production adapter path. Zero inference.

Run only after actual SCI/native negative isolation tests pass. This fixture is
not OOLONG evidence, learned behavior, or proof of live native caller attribution.
"""
import json
from pathlib import Path
import threading
import uuid

from .gateway_client import GatewayClient
from .oolong import digest, encoded, require
from .paired import ROOT, gateway_config, run_arm, source_snapshot, runtime_snapshot, validate_config, transport_contract

CONFIG = {'model': 'claude-sonnet-5-5', 'context_window': 1000000, 'max_output_tokens': 32768,
          'pinned_settings': {'thinking': {'type': 'adaptive', 'display': 'summarized'}, 'output_config': {'effort': 'medium'}}, 'calls_per_arm': 12,
          'tokens_per_arm': 12000000, 'concurrent_requests': 8, 'usd_per_arm': 12,
          'rates': {'input': 2, 'output': 10, 'cache-read': .1, 'cache-write-5m': 2.5, 'cache-write-1h': 4}}


SIGNATURE = 'FIXTURE-SIGNATURE-NOT-PROVIDER-ISSUED'


def response(content, model, *, stream=False, signed=False, input_tokens=100):
    identifier = 'fixture-' + uuid.uuid4().hex
    usage = {'input_tokens': input_tokens, 'output_tokens': 20, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0,
             'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0},
             'output_tokens_details': {'thinking_tokens': 0}, 'service_tier': 'standard',
             'inference_geo': 'global', 'speed': 'standard'}
    tool = isinstance(content, dict)
    if not stream:
        body = {'type': 'message', 'id': identifier, 'model': model, 'role': 'assistant',
                'content': [{'type': 'text', 'text': content}], 'stop_reason': 'end_turn', 'usage': usage}
        return {'status': 200, 'content-type': 'application/json', 'body': json.dumps(body)}
    block = {'type': 'tool_use', 'id': 'tool-' + identifier, 'name': 'ipython', 'input': {}} if tool else {'type': 'text', 'text': ''}
    delta = {'type': 'input_json_delta', 'partial_json': json.dumps(content)} if tool else {'type': 'text_delta', 'text': content}
    events = [{'type': 'message_start', 'message': {'id': identifier, 'type': 'message', 'role': 'assistant',
                 'model': model, 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {**usage, 'output_tokens': 1}}},
              {'type': 'content_block_start', 'index': 0, 'content_block': block},
              {'type': 'content_block_delta', 'index': 0, 'delta': delta},
              {'type': 'content_block_stop', 'index': 0},
              {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use' if tool else 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 20}},
              {'type': 'message_stop'}]
    if signed:
        for event in events:
            if 'index' in event:
                event['index'] += 1
        events[1:1] = [
            {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': ''}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': 'Scripted transport check.'}},
            {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': SIGNATURE}},
            {'type': 'content_block_stop', 'index': 0}]
    return {'status': 200, 'content-type': 'text/event-stream',
            'body': ''.join('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n' for event in events)}


class Script:
    def __init__(self, harness, *, provider='anthropic-api', config=None):
        self.harness, self.counts, self.lock = harness, {}, threading.Lock()
        self.config = CONFIG if config is None else config
        self.provider = provider
        self.oauth_requests = 0
        self.signed_round_trips = 0
        self.request_settings = []

    def __call__(self, body, _):
        if self.provider == 'claude-oauth-subscription':
            from .subscription_protocol import prepare_body
            prepare_body(body, native=True)
            with self.lock:
                self.oauth_requests += 1
        actual = {k: body[k] for k in ('thinking', 'output_config', 'temperature', 'top_p', 'top_k') if k in body}
        require(body.get('model') == self.config['model'], 'Native or Aljure requested model differs from the control')
        require(actual == self.config['pinned_settings'], 'Native or Aljure call settings differ from the pinned API contract')
        first = json.dumps([m['content'] for m in body['messages'] if m['role'] == 'user'][:2])
        child = 'child-context-fixture' in first
        lane = 'child' if child else 'root'
        system = json.dumps(body.get('system', ''))
        if self.harness == 'prime':
            if 'You are a context summarization assistant.' in system:
                lane = 'compaction'
            elif 'shouldRefine' in system:
                lane = 'refinement-review'
            elif "You are Prime Agent's /refine continual harness subsystem." in system:
                lane = 'refinement'
        with self.lock:
            index = self.counts.get(lane, 0)
            self.counts[lane] = index + 1
            self.request_settings.append({'fixture_lane': lane, 'settings': actual, 'max_tokens': body['max_tokens']})
            signatures = [block.get('signature') for message in body['messages'] if message['role'] == 'assistant'
                          and isinstance(message.get('content'), list) for block in message['content']
                          if block.get('type') == 'thinking']
            if signatures:
                require(SIGNATURE in signatures, 'Native signed thinking did not round-trip unchanged')
                self.signed_round_trips += 1
        if lane == 'compaction':
            return response('## Goal\nReturn context length.\n## Progress\nPython computed 6 and wrote /work/answer.txt.\n## Next\nFinish.', body['model'], stream=True, signed=True)
        if lane == 'refinement-review':
            return response(json.dumps({'shouldRefine': True, 'rationale': 'Scripted fixture only', 'instructions': 'Return an empty valid plan.'}), body['model'], stream=True, signed=True)
        if lane == 'refinement':
            return response(json.dumps({'summary': 'Scripted fixture; no learned improvement', 'rationale': 'Transport validation',
                                        'expectedOutcome': 'No changes', 'edits': []}), body['model'], stream=True, signed=True)
        if self.harness == 'aljure':
            script = (['{:op :repl/eval :source "(count external-context)" :bindings {}}', '{:op :done :summary "6"}'] if child else
                      ['```edn\n{:op :done :summary "WRONG-REJECTED-FRAGMENT"}\n```',
                       # V7: the root eval uses the verbatim source block with a regex
                       # literal, the code shape that broke EDN string escaping in V6.
                       BLOCK_EVAL,
                       '{:op :agent/call :id "child" :task "child-context-fixture" :context {}}',
                       '{:op :done :summary "6"}'])
        else:
            code = ("from pathlib import Path\nassert len(Path('/work/context.txt').read_text()) == 6\n"
                    "Path('/work/child-answer.txt').write_text('6')\nprint(6)" if child else
                    "from pathlib import Path\nassert len(Path('/work/context.txt').read_text()) == 6\n"
                    "child = await rlm.spawn('child-context-fixture: compute the context length and write /work/child-answer.txt', name='context-child')\n"
                    "results = await rlm.collect([child], timeout_ms=60000)\nassert results[0].settled\n"
                    "Path('/work/answer.txt').write_text(Path('/work/child-answer.txt').read_text())\nprint(6)")
            script = [{'code': code}, 'Fixture complete.']
        require(index < len(script), 'Unexpected extra fixture provider request; preserve failure')
        return response(script[index], body['model'], stream=body.get('stream', False), signed=self.harness == 'prime')


BLOCK_CODE = '(count (re-seq #"(?s)." external-context))'
BLOCK_EVAL = '{:op :repl/eval :source :block :bindings {}}\n<<<SOURCE\n' + BLOCK_CODE + '\nSOURCE>>>'


def run(output, *, provider='anthropic-api', config_path=None):
    from .prime.isolation import require_tested
    from .subscription_protocol import PROVIDER, VERSION, PUBLIC_HEADERS
    import subprocess
    require(provider in ('anthropic-api', PROVIDER), 'Unsupported fixture transport')
    config = json.loads(Path(config_path).read_text()) if config_path else {**CONFIG, 'provider': provider}
    if config_path:
        validate_config(config)
        require(config['provider'] == provider, 'Fixture provider differs from explicit configuration')
    native = require_tested()
    subprocess.run(['python3', 'scripts/clj.py', '-e', "(require '[repl-lab.isolation :as i]) (i/require-tested!) (shutdown-agents)"],
                   cwd=ROOT, capture_output=True, timeout=25, check=True)
    sci = json.loads((ROOT / 'var/isolation-proof.json').read_text())
    require(sci.get('gate_version', sci.get('gate-version', 0)) >= 2, 'Same-worker SCI readiness proof required')
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = source_snapshot()
    runtime_sources = runtime_snapshot()
    readiness = {'checks': {'prime_isolation': native}}
    checks, summaries = {}, {}
    try:
        for harness in ('aljure', 'prime'):
            arm = out / harness
            arm.mkdir()
            script = Script(harness, provider=provider, config=config)
            gateway = GatewayClient(arm / 'gateway', gateway_config(config, harness), script)
            try:
                result = run_arm(harness, {'context': 'abcdef', 'task': {'task_id': 'fixture-only', 'question': 'Return context length.'}},
                                 arm, config, gateway, readiness, fixture_native_commands=True)
            finally:
                gateway.close()
            require(result.get('completion', {}).get('native_exit_code') == 0, 'Scripted arm failed')
            require((arm / 'answer.txt').read_text().strip() == '6', 'Independent context-length check failed')
            usage = [json.loads(line) for line in (arm / 'gateway/usage.jsonl').read_text().splitlines()]
            require(len(usage) == sum(script.counts.values()) and all(row['status'] == 'complete' for row in usage), 'Gateway calls missing')
            summaries[harness] = {'counts': script.counts, 'gateway_receipts': len(usage), 'answer_sha256': digest(b'6'),
                                  'signed_round_trips': script.signed_round_trips, 'request_settings': script.request_settings,
                                  'oauth_requests': script.oauth_requests}
            if harness == 'aljure':
                events = [json.loads(line) for line in (arm / 'agent/events.jsonl').read_text().splitlines()]
                values = [e['payload']['result']['value'] for e in events if e['type'] == 'tool-result'
                          and e['payload'].get('op') == 'repl/eval' and e['payload'].get('status') == 'ok']
                require(values == [6, 6], 'SCI initialization/execution failed; stop before another arm')
        events = [json.loads(line) for line in (out / 'aljure/agent/events.jsonl').read_text().splitlines()]
        sci_values = [e['payload']['result']['value'] for e in events if e['type'] == 'tool-result'
                      and e['payload'].get('op') == 'repl/eval' and e['payload'].get('status') == 'ok']
        checks = {'native_root': summaries['prime']['counts'].get('root') == 2,
                  'native_child': summaries['prime']['counts'].get('child') == 2,
                  'native_tool': (out / 'prime/native/child-answer.txt').read_text().strip() == '6',
                  'sci_context': sci_values == [6, 6],
                  'native_compaction': summaries['prime']['counts'].get('compaction', 0) > 0,
                  'native_refinement': summaries['prime']['counts'].get('refinement', 0) > 0,
                  'native_signed_thinking': summaries['prime']['signed_round_trips'] > 0,
                  'shared_budget': all(v['gateway_receipts'] == sum(v['counts'].values()) for v in summaries.values()),
                  'cleanup': True}
        checks['source_block'] = any(BLOCK_CODE in json.dumps(e['payload']) for e in events if e['type'] == 'tool-call')
        rejected = [e['payload'] for e in events if e['type'] == 'command-rejected']
        checks['command_correction'] = (len(rejected) == 1 and rejected[0]['executed'] is False
                                        and rejected[0]['correction-requested'] is True
                                        and summaries['aljure']['counts'] == {'root': 4, 'child': 2}
                                        and summaries['aljure']['gateway_receipts'] == 6)
        checks['rejected_fragment_not_executed'] = not any(
            'WRONG-REJECTED-FRAGMENT' in json.dumps(e['payload'])
            for e in events if e['type'] in ('tool-call', 'tool-result'))
        if provider == PROVIDER:
            frames = [json.loads(line) for line in (out / 'prime/stdout.jsonl').read_text().splitlines()]
            public = [e['public_headers'] for e in frames if e.get('type') == 'external_provider_request']
            checks['oauth_protocol'] = (len(public) == summaries['prime']['gateway_receipts'] and
                                       all(headers == PUBLIC_HEADERS for headers in public) and
                                       all(v['oauth_requests'] == v['gateway_receipts'] for v in summaries.values()))
        require(all(checks.values()), 'One or more relay fixture checks failed')
        require(source_snapshot()['sha256'] == sources['sha256'], 'Source changed during fixture')
        require(runtime_snapshot() == runtime_sources, 'Runtime/config inputs changed during fixture')
        report = {'status': 'PASSED', 'evidence': 'FIXTURE', 'checks': checks, 'summaries': summaries,
                  'source_sha256': sources['sha256'], 'prime_image': native['image'], 'sci_image': sci['image'],
                  'runtime_source': runtime_sources, 'provider': provider,
                  'transport_contract': transport_contract(config),
                  'subscription_protocol': VERSION if provider == PROVIDER else None,
                  'model_calls': 0, 'learning_claim': False, 'limitations':
                  ['Scripted responses only; native live provider parity remains unverified.',
                   'Fixture identifies scripted lanes; live native parent/refine/compaction attribution remains unknown.',
                   'Native /compact and /refine are explicitly invoked after the fixture task; no autonomous improvement or live inference is demonstrated.',
                   'Only this short fixture sets native keepRecentTokens=1 to exercise manual compaction; production task settings remain native defaults.',
                   'Pinned Prime misreads message_start input usage, so automatic context-pressure triggering remains unverified; the gateway does not rewrite native messages.']}
    except Exception as error:
        report = {'status': 'FAILED', 'evidence': 'FIXTURE', 'model_calls': 0, 'checks': checks,
                  'summaries': summaries, 'failure': type(error).__name__, 'source_sha256': sources['sha256']}
    (out / 'report.json').write_bytes(encoded(report))
    if report['status'] == 'PASSED':
        proof = ROOT / ('var/subscription-relay-proof.json' if provider == PROVIDER else 'var/external-relay-proof.json')
        if proof.exists():
            proof.rename(proof.with_name(proof.stem + '-before-' + uuid.uuid4().hex + '.json'))
        proof.write_bytes(encoded(report))
    return report
