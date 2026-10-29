"""Explicit scripted control through the production adapter path. Zero inference.

Run only after actual SCI/native negative isolation tests pass. This fixture is
not OOLONG evidence, learned behavior, or proof of live native caller attribution.
"""
import json
from pathlib import Path
import sys
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
        # Aljure native tool calls: {'tool': name, 'input': {...}, 'text': optional preamble}.
        blocks = [{'type': 'text', 'text': content['text']}] if tool and 'text' in content else []
        blocks += ([{'type': 'tool_use', 'id': 'toolu_' + uuid.uuid4().hex, 'name': content['tool'], 'input': content['input']}]
                   if tool else [{'type': 'text', 'text': content}])
        if signed:
            blocks.insert(0, {'type': 'thinking', 'thinking': 'Scripted transport check.', 'signature': SIGNATURE})
        body = {'type': 'message', 'id': identifier, 'model': model, 'role': 'assistant',
                'content': blocks, 'stop_reason': 'tool_use' if tool else 'end_turn', 'usage': usage}
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
        self.tool_results = 0
        self.history = {}

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
        if self.harness == 'aljure':
            self.check_aljure_tools(body, lane)
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
            script = ([call('repl_eval', source='(count external-context)'), call('done', summary='6')] if child else
                      # A text-only answer is rejected and corrected once; nothing in it runs.
                      ['```edn\n{:op :done :summary "WRONG-REJECTED-FRAGMENT"}\n```',
                       # Code with quoted strings, the shape that broke EDN escaping in V6.
                       call('repl_eval', 'Counting the characters.', source=TOOL_CODE),
                       call('agent_call', id='child', task='child-context-fixture', context=[]),
                       # The answer comes from code in the SCI worker, as Prime's comes from a file.
                       call('done', source='(str (count external-context))')])
        else:
            code = ("from pathlib import Path\nassert len(Path('/work/context.txt').read_text()) == 6\n"
                    "Path('/work/child-answer.txt').write_text('6')\nprint(6)" if child else
                    "from pathlib import Path\nassert len(Path('/work/context.txt').read_text()) == 6\n"
                    "child = await rlm.spawn('child-context-fixture: compute the context length and write /work/child-answer.txt', name='context-child')\n"
                    "results = await rlm.collect([child], timeout_ms=60000)\nassert results[0].settled\n"
                    "Path('/work/answer.txt').write_text(Path('/work/child-answer.txt').read_text())\nprint(6)")
            script = [{'code': code}, 'Fixture complete.']
        require(index < len(script), 'Unexpected extra fixture provider request; preserve failure')
        return response(script[index], body['model'], stream=body.get('stream', False), signed=True)

    def check_aljure_tools(self, body, lane):
        # The provider rejects unanswered or orphaned tool calls, and edited history
        # invalidates thinking blocks. Enforce both here, before any live request.
        require(body.get('tool_choice') == {'type': 'auto', 'disable_parallel_tool_use': True} and
                [tool['name'] for tool in body.get('tools', [])] == ALJURE_TOOLS, 'Aljure native tool contract differs')
        messages = body['messages']
        def blocks(message, kind):
            content = message['content'] if isinstance(message['content'], list) else []
            return [block for block in content if block.get('type') == kind]
        def plain(message):
            # The cache breakpoint moves to the newest block on each call; it is not history.
            content = message['content']
            content = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
            return {**message, 'content': [{k: v for k, v in block.items() if k != 'cache_control'} for block in content]}
        marked = [block for message in messages if isinstance(message['content'], list)
                  for block in message['content'] if 'cache_control' in block]
        require(len(marked) == 1 and isinstance(messages[-1]['content'], list) and 'cache_control' in messages[-1]['content'][-1]
                and [tool for tool in body['tools'] if 'cache_control' in tool] == body['tools'][-1:],
                'Aljure prompt-cache breakpoints differ from the native pattern')
        for i, message in enumerate(messages):
            if message['role'] == 'assistant' and blocks(message, 'tool_use'):
                answer = messages[i + 1] if i + 1 < len(messages) else None
                require(answer is not None and answer['role'] == 'user' and
                        [b['tool_use_id'] for b in blocks(answer, 'tool_result')] == [b['id'] for b in blocks(message, 'tool_use')],
                        'Aljure tool call is not answered by ID in the next message')
            if message['role'] == 'user' and blocks(message, 'tool_result'):
                require(i > 0 and messages[i - 1]['role'] == 'assistant' and blocks(messages[i - 1], 'tool_use'),
                        'Aljure tool result has no preceding tool call')
        with self.lock:
            previous, current = self.history.get(lane, []), [plain(message) for message in messages]
            require(current[:len(previous)] == previous, 'Aljure history was edited instead of appended')
            self.history[lane] = current
            self.tool_results += sum(len(blocks(message, 'tool_result')) for message in messages[len(previous):])


ALJURE_TOOLS = ['context_metadata', 'context_query', 'repl_eval', 'agent_call', 'done']
TOOL_CODE = '(count (re-seq (re-pattern "(?s).") external-context))'


def call(tool, text=None, **fields):
    return {'tool': tool, 'input': fields, **({'text': text} if text else {})}


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
                                  'tool_results': script.tool_results,
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
        checks['native_tool_call'] = any((e['payload'].get('command') or {}).get('source') == TOOL_CODE
                                         for e in events if e['type'] == 'tool-call')
        # Root: eval and child call answered; child: eval answered. Thinking returned unchanged.
        checks['aljure_tool_history'] = (summaries['aljure']['tool_results'] == 3
                                         and summaries['aljure']['signed_round_trips'] > 0)
        checks['answer_from_code'] = any((e['payload'].get('command') or {}).get('op') == 'done/eval'
                                         for e in events if e['type'] == 'tool-call')
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


def raw_response(blocks, stop_reason, model):
    """A non-streamed provider message with exactly these blocks and stop reason."""
    usage = {'input_tokens': 100, 'output_tokens': 20, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0,
             'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0},
             'output_tokens_details': {'thinking_tokens': 0}, 'service_tier': 'standard',
             'inference_geo': 'global', 'speed': 'standard'}
    body = {'type': 'message', 'id': 'fixture-' + uuid.uuid4().hex, 'model': model, 'role': 'assistant',
            'content': blocks, 'stop_reason': stop_reason, 'usage': usage}
    return {'status': 200, 'content-type': 'application/json', 'body': json.dumps(body)}


class ContractScript(Script):
    """Aljure root only: a truncated turn (the Opus imdb shape), a real SCI eval,
    a text-only reply, then a FINAL ANSWER line."""
    def __init__(self, *, provider, config):
        super().__init__('aljure', provider=provider, config=config)
        self.bodies = []

    def __call__(self, body, _):
        if self.provider == 'claude-oauth-subscription':
            from .subscription_protocol import prepare_body
            prepare_body(body, native=True)
        self.check_aljure_tools(body, 'root')
        thinking = {'type': 'thinking', 'thinking': 'Scripted contract check.', 'signature': SIGNATURE}
        with self.lock:
            index = self.counts.get('root', 0)
            self.counts['root'] = index + 1
            self.bodies.append(json.loads(json.dumps(body['messages'])))
        script = [lambda: raw_response([thinking, {'type': 'thinking', 'thinking': 'This part of the response was interrupted before it finished.',
                                                   'signature': SIGNATURE}], 'tool_use', body['model']),
                  lambda: response(call('repl_eval', source=TOOL_CODE), body['model'], signed=True),
                  lambda: raw_response([thinking, {'type': 'text', 'text': 'The context has 6 characters, so the answer is 6.'}],
                                       'end_turn', body['model']),
                  lambda: raw_response([thinking, {'type': 'text', 'text': 'FINAL ANSWER: 6'}], 'end_turn', body['model'])]
        require(index < len(script), 'Unexpected extra contract fixture request; preserve failure')
        return script[index]()


def run_contract(output, *, provider='claude-oauth-subscription', config_path):
    """Both contract switches through the real gateway and an SCI worker, against the
    original contract on the identical script. Scripted responses only; no inference."""
    import subprocess
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    require(config['provider'] == provider, 'Fixture provider differs from explicit configuration')
    from .paired import aljure_contract
    require(aljure_contract(config) == {'truncated_turn_retries': 1, 'terminal_text_answer': True},
            'The contract fixture needs both switches on, one retry')
    # Aljure only: the SCI proof gates execution; Prime is not involved.
    subprocess.run(['python3', 'scripts/clj.py', '-e', "(require '[repl-lab.isolation :as i]) (i/require-tested!) (shutdown-agents)"],
                   cwd=ROOT, capture_output=True, timeout=25, check=True)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources, runtime_sources = source_snapshot(), runtime_snapshot()
    readiness = {'checks': {}}
    checks, summaries = {}, {}
    try:
        for name, arm_config in (('contract', config), ('original', {k: v for k, v in config.items() if k != 'aljure_contract'})):
            arm = out / name
            arm.mkdir()
            script = ContractScript(provider=provider, config=arm_config)
            gateway = GatewayClient(arm / 'gateway', gateway_config(arm_config, 'aljure'), script)
            try:
                result = run_arm('aljure', {'context': 'abcdef', 'task': {'task_id': 'fixture-only', 'question': 'Return context length.'}},
                                 arm, arm_config, gateway, readiness)
            finally:
                gateway.close()
            usage = [json.loads(line) for line in (arm / 'gateway/usage.jsonl').read_text().splitlines()]
            events = [json.loads(line) for line in (arm / 'agent/events.jsonl').read_text().splitlines()]
            kinds = [e['type'] for e in events]
            summaries[name] = {'requests': script.counts.get('root', 0), 'gateway_receipts': len(usage),
                               'answer': (arm / 'answer.txt').read_text() if (arm / 'answer.txt').exists() else None,
                               'exit_code': result.get('completion', {}).get('native_exit_code'),
                               'retried': [e['payload'] for e in events if e['type'] == 'provider-turn-retried'],
                               'rejected': [e['payload']['reason'] for e in events if e['type'] == 'command-rejected'],
                               'accepted': [e['payload']['answer'] for e in events if e['type'] == 'terminal-text-accepted'],
                               'sci_values': [e['payload']['result']['value'] for e in events if e['type'] == 'tool-result'
                                              and e['payload'].get('status') == 'ok' and e['payload'].get('op') == 'repl/eval'],
                               'event_kinds': sorted(set(kinds))}
            summaries[name]['bodies'] = script.bodies
        on, off = summaries['contract'], summaries['original']
        checks = {
            'contract_answer': on['answer'] == '6' and on['exit_code'] == 0,
            'retry_once_not_executed': [(r['reason'], r['retried'], r['executed']) for r in on['retried']] == [('truncated-tool-turn', True, False)],
            'retry_resends_identical_history': len(on['bodies']) >= 2 and on['bodies'][0] == on['bodies'][1],
            'sci_executed_after_retry': on['sci_values'] == [6],
            'text_correction_then_final_answer': on['rejected'] == ['no-tool-call'] and on['accepted'] == ['6'],
            'final_answer_instruction_sent': len(on['bodies']) == 4 and 'FINAL ANSWER: <the exact final answer>' in json.dumps(on['bodies'][3][-1]),
            'every_call_charged': on['gateway_receipts'] == on['requests'] == 4,
            'original_contract_fails_on_truncation': off['answer'] is None and off['requests'] == 1 and off['gateway_receipts'] == 1
                                                     and off['rejected'] == ['incomplete-turn'] and not off['retried'],
        }
        for name in summaries:
            summaries[name].pop('bodies')
        require(all(checks.values()), 'One or more contract fixture checks failed')
        require(source_snapshot()['sha256'] == sources['sha256'], 'Source changed during fixture')
        require(runtime_snapshot() == runtime_sources, 'Runtime/config inputs changed during fixture')
        report = {'status': 'PASSED', 'evidence': 'FIXTURE', 'checks': checks, 'summaries': summaries,
                  'source_sha256': sources['sha256'], 'runtime_source': runtime_sources,
                  'sci_image': json.loads((ROOT / 'var/isolation-proof.json').read_text())['image'],
                  'transport_contract': transport_contract(config), 'model_calls': 0,
                  'limitations': ['Scripted responses only; live provider behaviour under the new instruction is unverified.']}
    except Exception as error:
        for name in summaries:
            summaries[name].pop('bodies', None)
        report = {'status': 'FAILED', 'evidence': 'FIXTURE', 'model_calls': 0, 'checks': checks,
                  'summaries': summaries, 'failure': f'{type(error).__name__}: {error}'[:500], 'source_sha256': sources['sha256']}
    (out / 'report.json').write_bytes(encoded(report))
    return report


class ReviewScript(Script):
    """Aljure root only: record labels with one unknown, audit, try done, resolve,
    audit again, done. Exercises the review switches through the real controller."""
    STEPS = [('repl_eval', {'source': '(def labels {0 :c 1 :unknown 2 :n})'}),
             ('repl_eval', {'source': '(select-keys (audit-labels (range 3) labels) [:open :count-range])'}),
             ('done', {'summary': 'Answer: 1'}),
             ('repl_eval', {'source': '(select-keys (audit-labels (range 3) (assoc labels 1 :c)) [:open :counts])'}),
             ('done', {'summary': 'Answer: 2'})]

    def __init__(self, *, provider, config):
        super().__init__('aljure', provider=provider, config=config)
        self.bodies = []

    def __call__(self, body, _):
        if self.provider == 'claude-oauth-subscription':
            from .subscription_protocol import prepare_body
            prepare_body(body, native=True)
        self.check_aljure_tools(body, 'root')
        with self.lock:
            index = self.counts.get('root', 0)
            self.counts['root'] = index + 1
            self.bodies.append(json.loads(json.dumps(body['messages'])))
        require(index < len(self.STEPS), 'Unexpected extra review fixture request; preserve failure')
        tool, fields = self.STEPS[index]
        return response(call(tool, **fields), body['model'], signed=True)


def run_review(output, *, provider='claude-oauth-subscription', config_path):
    """The review switches (helpers, uncertainty review, evidence gate) through the real
    gateway and SCI worker, against a no-review control on the identical script.
    Scripted responses only; no inference."""
    import subprocess
    sys.path.insert(0, str(ROOT / 'scripts'))
    from contract_audit import audit_arm
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    require(config['provider'] == provider, 'Fixture provider differs from explicit configuration')
    from .paired import aljure_contract
    contract = aljure_contract(config)
    require(contract['structured_labels'] and contract['uncertainty_audit'] and contract['targeted_review'],
            'The review fixture needs all three review levels on')
    subprocess.run(['python3', 'scripts/clj.py', '-e', "(require '[repl-lab.isolation :as i]) (i/require-tested!) (shutdown-agents)"],
                   cwd=ROOT, capture_output=True, timeout=25, check=True)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources, runtime_sources = source_snapshot(), runtime_snapshot()
    readiness, summaries, checks = {'checks': {}}, {}, {}
    off = {**contract, 'structured_labels': False, 'uncertainty_audit': False, 'targeted_review': False}
    try:
        for name, arm_config in (('review', config), ('control', {**config, 'aljure_contract': off})):
            arm = out / name
            arm.mkdir()
            script = ReviewScript(provider=provider, config=arm_config)
            gateway = GatewayClient(arm / 'gateway', gateway_config(arm_config, 'aljure'), script)
            try:
                result = run_arm('aljure', {'context': 'abcdef', 'task': {'task_id': 'fixture-only', 'question': 'Count label c.'}},
                                 arm, arm_config, gateway, readiness)
            finally:
                gateway.close()
            usage = [json.loads(line) for line in (arm / 'gateway/usage.jsonl').read_text().splitlines()]
            events = [json.loads(line) for line in (arm / 'agent/events.jsonl').read_text().splitlines()]
            results = [e['payload'] for e in events if e['type'] == 'tool-result' and e['payload'].get('op') == 'repl/eval']
            audit = audit_arm(str(arm), aljure_contract(arm_config))
            summaries[name] = {'requests': script.counts.get('root', 0), 'gateway_receipts': len(usage),
                               'answer': (arm / 'answer.txt').read_text() if (arm / 'answer.txt').exists() else None,
                               'exit_code': result.get('completion', {}).get('native_exit_code'),
                               'finalization': json.loads((arm / 'agent/result.json').read_text()).get('finalization'),
                               'audits': [r.get('result', {}).get('value') if r.get('status') == 'ok' else r.get('error')
                                          for r in results[1:]],
                               'gates': [e['payload']['audit'] for e in events if e['type'] == 'evidence-gate'],
                               'contract_audit': audit['status'], 'violations': audit.get('violations', [])}
            summaries[name]['bodies'] = script.bodies
        on, base = summaries['review'], summaries['control']
        checks = {
            'review_answer_after_resolution': on['answer'] == 'Answer: 2' and on['exit_code'] == 0,
            'audit_reports_the_open_item': on['audits'][0] == {'open': 1, 'count-range': {'c': [1, 2], 'n': [1, 2]}},
            'gate_fired_once_on_the_open_audit': [g['open'] for g in on['gates']] == [1],
            'gate_notice_reached_the_model': len(on['bodies']) == 5 and 'Not submitted' in json.dumps(on['bodies'][3][-1]),
            'reaudit_closes_the_item': on['audits'][1] == {'open': 0, 'counts': {'c': 2, 'n': 1}},
            'every_call_charged': on['gateway_receipts'] == on['requests'] == 5 and base['gateway_receipts'] == base['requests'] == 3,
            'control_has_no_helpers_and_no_gate': base['answer'] == 'Answer: 1' and not base['gates']
                                                  and 'audit-labels' in str(base['audits'][0]),
            'both_arms_conformant': on['contract_audit'] == base['contract_audit'] == 'conformant',
            'finalization_recorded': on['finalization'] == base['finalization'] == 'done',
        }
        for name in summaries:
            summaries[name].pop('bodies')
        require(all(checks.values()), 'One or more review fixture checks failed')
        require(source_snapshot()['sha256'] == sources['sha256'], 'Source changed during fixture')
        require(runtime_snapshot() == runtime_sources, 'Runtime/config inputs changed during fixture')
        report = {'status': 'PASSED', 'evidence': 'FIXTURE', 'checks': checks, 'summaries': summaries,
                  'source_sha256': sources['sha256'], 'runtime_source': runtime_sources,
                  'sci_image': json.loads((ROOT / 'var/isolation-proof.json').read_text())['image'],
                  'transport_contract': transport_contract(config), 'model_calls': 0,
                  'limitations': ['Scripted responses only; whether a live model records labels and unknowns is unverified.']}
    except Exception as error:
        for name in summaries:
            summaries[name].pop('bodies', None)
        report = {'status': 'FAILED', 'evidence': 'FIXTURE', 'model_calls': 0, 'checks': checks,
                  'summaries': summaries, 'failure': f'{type(error).__name__}: {error}'[:500], 'source_sha256': sources['sha256']}
    (out / 'report.json').write_bytes(encoded(report))
    return report


# ---------------------------------------------------------------------------------------
# Thesis pilot acquisition (aljure_contract.acquisition) through the real gateway, the real
# SCI worker and the real promotion JVM. Scripted responses only; no inference. FIXTURE: it
# proves the plumbing, not that a model proposes useful code.

PROPOSAL_TOOLS = ['propose_artifact', 'skip_proposal']
TREC_FIXTURE = ("Each question can be described as one of: 'numeric value', 'human being', 'location', 'abbreviation'.\n\n"
                "Date: Jan 01, 2023 || User: 1 || Instance: Where is city 1 ?\n"
                "Date: Jan 02, 2023 || User: 2 || Instance: Who wrote book 2 ?\n\nCalculate the exact answer.")
SPAM_FIXTURE = ("Each text message can be classified as spam or ham.\n\n"
                "Date: Jan 01, 2023 || User: 1 || Instance: WIN a free prize now\n\nCalculate the exact answer.")


class AcquisitionScript(Script):
    """Root steps, then exactly one proposal request carrying the task tools plus the two
    proposal tools, no cache marker, and the 'Answer recorded' tool result last."""
    def __init__(self, *, provider, config, steps, proposal):
        super().__init__('aljure', provider=provider, config=config)
        self.steps, self.proposal, self.proposal_bodies = steps, proposal, []

    def __call__(self, body, _):
        if self.provider == 'claude-oauth-subscription':
            from .subscription_protocol import prepare_body
            prepare_body(body, native=True)
        names = [tool['name'] for tool in body.get('tools', [])]
        if names == ALJURE_TOOLS + PROPOSAL_TOOLS:
            require('cache_control' not in json.dumps(body), 'The proposal turn wrote a cache entry')
            require('Answer recorded' in json.dumps(body['messages'][-1]), 'The proposal instruction is missing')
            with self.lock:
                self.proposal_bodies.append(body)
            require(len(self.proposal_bodies) == 1, 'More than one proposal request')
            return self.proposal(body['model'])
        self.check_aljure_tools(body, 'root')
        with self.lock:
            index = self.counts.get('root', 0)
            self.counts['root'] = index + 1
        require(index < len(self.steps), 'Unexpected extra acquisition fixture request; preserve failure')
        tool, fields = self.steps[index]
        return response(call(tool, **fields), body['model'], signed=True)


def run_acquisition(output, *, provider='claude-oauth-subscription', config_path):
    """Arm E and arm C, three scripted tasks each, through run_arm, the gateway and the real
    worker; promotion through `clj -m repl-lab.acquisition promote` in a fresh JVM. Checks that
    the answer is recorded before the proposal turn, that the turn is charged apart, that the
    next task gets exactly the committed pin and runs the promoted code in SCI, and that an
    incompatible task refuses it. Writes var/acquisition-relay-proof.json on success."""
    import subprocess
    from .paired import (EMPTY_LIBRARY, EMPTY_LIBRARY_SHA256, PARENT, aljure_sci, promote_process, trajectory_contract,
                         trajectory_spec)
    config = json.loads(Path(config_path).read_text())
    validate_config(config)
    spec = trajectory_spec(config)
    require(config['provider'] == provider, 'Fixture provider differs from explicit configuration')
    subprocess.run(['python3', 'scripts/clj.py', '-e', "(require '[repl-lab.isolation :as i]) (i/require-tested!) (shutdown-agents)"],
                   cwd=ROOT, capture_output=True, timeout=25, check=True)
    out = Path(output).resolve()
    require(out.is_relative_to(ROOT), 'Fixture output must be under repl-lab (libraries are pinned by relative path)')
    out.mkdir(parents=True, exist_ok=False)
    sources, runtime_sources = source_snapshot(), runtime_snapshot()
    sci_image = json.loads((ROOT / 'var/isolation-proof.json').read_text())['image']
    panel = {'schema': 'aljure-panel-v1', 'windows': [
        {'id': 'trec-fixture', 'question': 'Which label is most common?', 'context': TREC_FIXTURE,
         'items': [{'case': f't{i}', 'text': (f'Where is city {i} ?' if i % 2 else f'Who wrote book {i} ?'),
                    'label': 'location' if i % 2 else 'human being'} for i in range(10)]},
        {'id': 'spam-fixture', 'question': 'How many are spam?', 'context': SPAM_FIXTURE,
         'items': [{'case': 's0', 'text': 'WIN a free prize now', 'label': 'spam'}]}]}
    panel_path = out / 'panel.json'
    panel_path.write_bytes(encoded(panel))
    environment = {k: v for k, v in __import__('os').environ.items()
                   if 'API_KEY' not in k and 'TOKEN' not in k and not k.startswith('REPL_LAB_CLAUDE_')}
    environment['REPL_LAB_WORKER_OUTPUT_BYTES'] = str(aljure_sci(config)['worker_output_bytes'])
    rules = '(fn [text] (cond (re-find #"^Where " text) "location" :else nil))'
    predicate = "(fn [input] (clojure.string/includes? (:context input) \"'abbreviation'\"))"
    propose = {'E': lambda model: response(call('propose_artifact', name='trec-rules', description='Where-questions are locations.',
                                                function_source=rules, applicability_source=predicate), model, signed=True),
               'C': lambda model: response(call('propose_artifact', name='this-answer', description='Exact labels from this task.',
                                                memo_source='labels'), model, signed=True)}
    tasks = {'E': [(TREC_FIXTURE, [('repl_eval', {'source': '(count context-lines)'}), ('done', {'summary': 'Answer: 1'})], propose['E']),
                   (TREC_FIXTURE, [('repl_eval', {'source': '(trec-rules "Where is city 1 ?")'}), ('done', {'summary': 'Answer: 1'})],
                    lambda model: response(call('skip_proposal'), model, signed=True)),
                   (SPAM_FIXTURE, [('done', {'summary': 'Answer: 1'})], lambda model: response('No proposal.', model, signed=True))],
             'C': [(TREC_FIXTURE, [('repl_eval', {'source': '(def labels {"Where is city 1 ?" "location"})'}),
                                   ('done', {'summary': 'Answer: 1'})], propose['C']),
                   (TREC_FIXTURE, [('repl_eval', {'source': '(exact-label "Where is city 1 ?")'}), ('done', {'summary': 'Answer: 1'})],
                    lambda model: response(call('skip_proposal'), model, signed=True)),
                   (SPAM_FIXTURE, [('done', {'summary': 'Answer: 1'})], lambda model: response(call('skip_proposal'), model, signed=True))]}
    checks, summaries = {}, {}
    try:
        for arm, steps in tasks.items():
            library = out / arm / 'library'
            (library / 'libraries').mkdir(parents=True)
            (library / 'libraries' / f'{EMPTY_LIBRARY_SHA256}.edn').write_bytes(EMPTY_LIBRARY)
            pin, rows = EMPTY_LIBRARY_SHA256, []
            for position, (context, script_steps, reply) in enumerate(steps, 1):
                task_out = out / arm / f'{position:02}-aljure'
                task_out.mkdir(parents=True)
                task_config = trajectory_contract(config, arm, str(library.relative_to(ROOT)), pin)
                script = AcquisitionScript(provider=provider, config=task_config, steps=script_steps, proposal=reply)
                gateway = GatewayClient(task_out / 'gateway', gateway_config(task_config, 'aljure'), script)
                try:
                    result = run_arm('aljure', {'context': context, 'task': {'task_id': f'fixture-{arm}-{position}',
                                                                            'question': 'How many questions ask for a location?'}},
                                     task_out, task_config, gateway, {'checks': {}})
                finally:
                    gateway.close()
                usage = [json.loads(line) for line in (task_out / 'gateway/usage.jsonl').read_text().splitlines()]
                events = [json.loads(line) for line in (task_out / 'agent/events.jsonl').read_text().splitlines()]
                agent = json.loads((task_out / 'agent/result.json').read_text())
                row = {'pin_seen': pin, 'answer': (task_out / 'answer.txt').read_text() if (task_out / 'answer.txt').exists() else None,
                       'recorded_first': (task_out / 'agent/answer-recorded.json').is_file(),
                       'exit_code': result.get('completion', {}).get('native_exit_code'),
                       'receipts': len(usage), 'proposal_requests': len(script.proposal_bodies),
                       'acquisition': agent.get('acquisition'),
                       'acquisition_receipts': sum(u.get('provider_request_id') in set(agent.get('acquisition', {}).get('spend', {}).get('provider-ids', []))
                                                   for u in usage),
                       'applicability': [(e['payload'].get('name'), e['payload'].get('decision'), e['payload'].get('reason'))
                                         for e in events if e['type'] == 'artifact-applicability'],
                       'invocations': [i for e in events if e['type'] == 'artifact-invocations' for i in e['payload'].get('invocations', [])],
                       'sci_values': [e['payload']['result']['value'] for e in events if e['type'] == 'tool-result'
                                      and e['payload'].get('status') == 'ok' and e['payload'].get('op') == 'repl/eval']}
                proposal = task_out / 'agent/proposal.edn'
                if proposal.is_file() and (agent.get('acquisition') or {}).get('decision') == 'proposed':
                    request = {'arm': arm, 'library': str(library), 'pin': pin, 'proposal': str(proposal),
                               'proposal_sha256': digest(proposal.read_bytes()), 'task_id': f'fixture-{arm}-{position}',
                               'position': position, 'rule': spec['promotion_rule'], 'panel': str(panel_path),
                               'panel_sha256': digest(panel_path.read_bytes()), 'assisted': aljure_sci(config)['surface'] == 'assisted',
                               'structured_labels': False, 'seconds': 300}
                    (task_out / 'promotion-request.json').write_bytes(encoded(request))
                    environment['REPL_LAB_WORKER_AUDIT_DIR'] = str(task_out / 'promotion-worker-audit')
                    completed = promote_process(task_out / 'promotion-request.json', environment, 300)
                    (task_out / 'promotion-stdout.txt').write_bytes(completed.stdout or b'')
                    reply_json = json.loads((completed.stdout or b'{}').decode().strip().splitlines()[-1])
                    receipt = json.loads((library / 'receipts' / f"{reply_json['receipt-sha256']}.json").read_text())
                    row['promotion'] = {'decision': receipt.get('decision'), 'reasons': receipt.get('reasons'),
                                        'model_calls': receipt.get('model-calls'), 'validation_ms': receipt.get('validation-ms'),
                                        'candidate_panel': receipt.get('candidate-panel')}
                    if receipt.get('decision') == 'approved':
                        data = (library / 'libraries' / f"{receipt['pin-after']}.edn").read_bytes()
                        parent = PARENT.search(data)
                        require(digest(data) == receipt['pin-after'] and parent and parent.group(2).decode() == pin,
                                'Promoted version does not verify')
                        pin = receipt['pin-after']
                rows.append(row)
            summaries[arm] = rows
        e, c = summaries['E'], summaries['C']
        checks = {
            'answers_recorded_before_the_turn': all(r['answer'] == 'Answer: 1' and r['recorded_first'] and r['exit_code'] == 0
                                                    for rows in summaries.values() for r in rows),
            'one_proposal_request_per_task_charged_apart': all(r['proposal_requests'] == 1 and r['acquisition_receipts'] == 1
                                                              for rows in summaries.values() for r in rows),
            'e_promoted_on_the_panel_without_model_calls': e[0].get('promotion', {}).get('decision') == 'approved'
                                                          and e[0]['promotion']['model_calls'] == 0,
            'next_task_gets_the_committed_pin': e[1]['pin_seen'] != e[0]['pin_seen'] and c[1]['pin_seen'] != c[0]['pin_seen']
                                                and e[2]['pin_seen'] == e[1]['pin_seen'],
            'promoted_code_runs_in_sci': 'location' in json.dumps(e[1]['sci_values']) and
                                         [i['name'] for i in e[1]['invocations']] == ['trec-rules'],
            'incompatible_task_refuses': e[2]['applicability'] == [['trec-rules', 'refuse', 'inapplicable']] or
                                         e[2]['applicability'] == [('trec-rules', 'refuse', 'inapplicable')],
            'decline_by_text_is_recorded': (e[2]['acquisition'] or {}).get('decision') == 'declined',
            'c_exact_memo_reused': c[0].get('promotion', {}).get('decision') == 'approved' and 'location' in json.dumps(c[1]['sci_values'])
                                   and ['exact-label', 'preload', 'exact-match'] in [list(a) for a in c[1]['applicability']],
            'c_memo_refused_without_exact_match': ['exact-label', 'refuse', 'no-exact-match'] in [list(a) for a in c[2]['applicability']]}
        require(all(checks.values()), 'One or more acquisition fixture checks failed')
        require(source_snapshot()['sha256'] == sources['sha256'], 'Source changed during fixture')
        require(runtime_snapshot() == runtime_sources, 'Runtime/config inputs changed during fixture')
        report = {'status': 'PASSED', 'evidence': 'FIXTURE', 'checks': checks, 'summaries': summaries,
                  'source_sha256': sources['sha256'], 'runtime_source': runtime_sources, 'sci_image': sci_image,
                  'transport_contract': transport_contract(config), 'provider': provider, 'model_calls': 0,
                  'limitations': ['Scripted responses only; whether a model proposes useful code is not tested here.']}
        (ROOT / 'var/acquisition-relay-proof.json').write_bytes(encoded(report))
    except Exception as error:
        report = {'status': 'FAILED', 'evidence': 'FIXTURE', 'model_calls': 0, 'checks': checks, 'summaries': summaries,
                  'failure': f'{type(error).__name__}: {error}'[:500], 'source_sha256': sources['sha256']}
    (out / 'report.json').write_bytes(encoded(report))
    return report
