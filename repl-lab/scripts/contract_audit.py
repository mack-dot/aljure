"""Execution-contract audit of recorded Aljure arms. Read-only; no model calls.

Every provider response the gateway recorded is classified from its raw body.
Aljure's recorded handling of that response is then checked against the
native-tool contract and the arm's aljure_contract switches:
F1 truncated_turn_retries and F2 terminal_text_answer.

    python3 scripts/contract_audit.py RUN_DIR [RUN_DIR ...] [--out OUT.json]
    python3 scripts/contract_audit.py --arm ARM_DIR [--contract JSON] [--out OUT.json]

A run directory's switches come from its plan.json; an arm given alone uses
--contract (default: both off). The exit status is 1 when any violation is found.
"""
import argparse
import glob
import json
import os
from pathlib import Path
import sys

MARKER = 'FINAL ANSWER: '
TERMINAL_INSTRUCTION = 'reply with exactly one line, FINAL ANSWER: <the exact final answer>'
ORIGINAL_INSTRUCTION = 'Call exactly one of the provided tools.'
TEXT_BLOCKS = {'text', 'thinking', 'redacted_thinking'}
OPS = {'context_metadata': {'context/metadata'}, 'context_query': {'context/query'}, 'repl_eval': {'repl/eval'},
       'agent_call': {'agent/call'}, 'done': {'done', 'done/eval'}}
HANDLING = {'tool-call', 'command-rejected', 'provider-turn-retried', 'terminal-text-accepted', 'evidence-gate'}
# The only recorded handlings each response shape may receive.
ALLOWED = {'tool-call': [['tool-call'], ['command-rejected'], ['evidence-gate']],
           'text-only': [['command-rejected'], ['terminal-text-accepted', 'tool-call']],
           'truncated': [['provider-turn-retried'], ['command-rejected']],
           'multiple-commands': [['command-rejected']], 'incomplete-turn': [['command-rejected']],
           'content-blocks': [['command-rejected']]}
REASONS = {'tool-call': {'tool-name', 'tool-input'}, 'text-only': {'no-tool-call'}, 'truncated': {'incomplete-turn'},
           'multiple-commands': {'multiple-commands'}, 'incomplete-turn': {'incomplete-turn'},
           'content-blocks': {'content-blocks'}}


def jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def strip_cache(value):
    """Cache breakpoints move between requests; they are not history content. Placing
    one turns string content into a single text block, which the API reads the same."""
    if isinstance(value, dict):
        out = {k: strip_cache(v) for k, v in value.items() if k != 'cache_control'}
        if 'role' in out and isinstance(out.get('content'), str):
            out['content'] = [{'type': 'text', 'text': out['content']}]
        return out
    if isinstance(value, list):
        return [strip_cache(v) for v in value]
    return value


def classify(body):
    """The provider turn's shape, decided from the raw body alone."""
    blocks, stop = body.get('content'), body.get('stop_reason')
    if not isinstance(blocks, list) or any(b.get('type') not in TEXT_BLOCKS | {'tool_use'} for b in blocks):
        return 'content-blocks'
    calls = [b for b in blocks if b['type'] == 'tool_use']
    if stop == 'tool_use' and len(calls) == 1:
        return 'tool-call'
    if stop == 'end_turn' and not calls:
        return 'text-only'
    if len(calls) > 1:
        return 'multiple-commands'
    if stop == 'tool_use' and not calls:
        return 'truncated'
    return 'incomplete-turn'


def terminal_answer(body):
    """An independent reading of the F2 acceptance rule, or None."""
    blocks = body.get('content')
    if body.get('stop_reason') != 'end_turn' or not isinstance(blocks, list):
        return None
    if any(b.get('type') not in TEXT_BLOCKS for b in blocks) or not any(b['type'] == 'text' for b in blocks):
        return None
    text = ''.join(b['text'] for b in blocks if b['type'] == 'text').strip()
    if '\n' in text or '\r' in text or not text.startswith(MARKER):
        return None
    answer = text[len(MARKER):].strip()
    return answer if answer and len(answer) <= 4096 and MARKER.strip() not in answer else None


def command_matches(command, call):
    name, given = call.get('name'), call.get('input') or {}
    if command.get('op') not in OPS.get(name, set()):
        return False
    if name == 'repl_eval':
        return command.get('source') == given.get('source')
    if name == 'done':
        key = 'summary' if 'summary' in given else 'source'
        return command.get(key) == given.get(key)
    if name == 'context_query':
        return command.get('handle') == given.get('handle')
    return True


def contract_of(run_dir):
    plan = os.path.join(run_dir, 'plan.json')
    config = json.loads(Path(plan).read_text()).get('config', {}) if os.path.exists(plan) else {}
    return config.get('aljure_contract') or {}


def audit_arm(arm, contract):
    retries = int(contract.get('truncated_turn_retries', 0))
    terminal = bool(contract.get('terminal_text_answer', False))
    gate = bool(contract.get('targeted_review', False))
    gateway, agent = jsonl(arm + '/gateway/events.jsonl'), jsonl(arm + '/agent/events.jsonl')
    usage = jsonl(arm + '/gateway/usage.jsonl')
    intents = [e['payload'] for e in gateway if e['type'] == 'gateway-request-intent']
    responses = {e['payload']['request-id']: e['payload']['response'] for e in gateway if e['type'] == 'gateway-response'}
    violations, counts = [], {}

    def fail(check, detail):
        violations.append({'check': check, 'detail': detail})

    if not intents or 'tools' not in intents[0]['input']:
        return {'arm': arm, 'status': 'not-applicable', 'reason': 'not a native-tool arm'}

    if not agent:
        # Arms ended by a deadline or an error before the runtime exported its log.
        return {'arm': arm, 'status': 'unauditable', 'reason': 'no exported agent event log', 'requests': len(intents)}
    parents = {e['payload']['id']: e['payload']['parent'] for e in agent if e['type'] == 'session-created'}
    inputs = [(i, e) for i, e in enumerate(agent) if e['type'] == 'provider-input']
    if any('message-count' not in e['payload'] for _, e in inputs):
        return {'arm': arm, 'status': 'not-applicable', 'reason': 'event log predates request alignment'}
    # Calls are sequential, so the k-th gateway request is the k-th agent request.
    if len(inputs) != len(intents) or any(len(g['input']['messages']) != e['payload']['message-count']
                                          for g, (_, e) in zip(intents, inputs)):
        fail('alignment', f'{len(inputs)} agent requests against {len(intents)} gateway requests')
        return {'arm': arm, 'status': 'violations', 'violations': violations}

    # Accounting: every request has a response and a complete receipt.
    unknown = [g['request-id'] for g in intents if g['request-id'] not in responses]
    complete = [u for u in usage if u.get('status') == 'complete']
    agent_results = [e for e in agent if e['type'] == 'provider-result']
    if len(complete) != len(responses) or len(agent_results) != len(responses):
        fail('accounting', f'{len(responses)} responses, {len(complete)} complete receipts, {len(agent_results)} agent results')
    if abs(sum(e['payload']['usd'] for e in agent_results) - sum(u.get('estimated_usd') or 0 for u in complete)) > 1e-6:
        fail('accounting', 'agent and gateway costs differ')

    received, last_in_session, corrections, refused = [], {}, [], 0
    root_failed = any(e['type'] == 'session-finished' and parents.get(e['payload']['id'], 'x') is None
                      and e['payload']['status'] == 'failed' for e in agent)
    for k, (g, (at, e)) in enumerate(zip(intents, inputs)):
        session, messages = e['payload']['session'], strip_cache(g['input']['messages'])
        # Append-only history: a session's earlier request is a prefix of its next one.
        prior = last_in_session.get(session)
        if prior is not None and messages[:len(prior)] != prior:
            fail('append-only', f'request {k} rewrote session {session} history')
        last_in_session[session] = messages
        # Every assistant turn in history is a provider response, verbatim.
        for m in messages:
            if m['role'] == 'assistant' and m['content'] not in received:
                fail('verbatim-history', f'request {k} carries an assistant turn no provider returned')
        # The correction a rejected turn receives must match the contract.
        if corrections and corrections[-1]['next'] == k:
            sent = json.dumps(messages[-1])
            expected = TERMINAL_INSTRUCTION if corrections[-1]['terminal'] else ORIGINAL_INSTRUCTION
            other = ORIGINAL_INSTRUCTION if corrections[-1]['terminal'] else TERMINAL_INSTRUCTION
            if expected not in sent or other in sent:
                fail('correction-text', f'request {k} did not carry the expected correction')
        elif TERMINAL_INSTRUCTION in json.dumps(messages[-1]):
            fail('correction-text', f'request {k} carries the terminal instruction without a correction')

        response = responses.get(g['request-id'])
        if response is None:
            continue
        body = json.loads(response['body'])
        kind = classify(body)
        counts[kind] = counts.get(kind, 0) + 1
        end = inputs[k + 1][0] if k + 1 < len(inputs) else len(agent)
        # The window holds this response's handling; events of other sessions are ignored.
        handled = [x for x in agent[at:end] if x['type'] in HANDLING and x['payload'].get('session', session) == session]
        shape = [x['type'] for x in handled]
        if shape not in ALLOWED[kind] and not (kind == 'tool-call' and not shape):
            fail('handling', f'response {k} ({kind}) was handled as {shape}')
        if not handled:
            continue
        h = handled[0]
        p = h['payload']
        if h['type'] == 'tool-call':
            call = next((b for b in body['content'] if b['type'] == 'tool_use'), None)
            if kind != 'tool-call':
                fail('text-never-executed', f'response {k} ({kind}) was executed')
            elif not command_matches(p['command'], call):
                fail('command-provenance', f'response {k}: executed command differs from its tool call')
            received.append(body['content'])
        elif h['type'] == 'command-rejected':
            if p.get('executed') is not False:
                fail('rejection', f'response {k}: rejection not marked unexecuted')
            if p.get('reason') not in REASONS[kind]:
                fail('rejection', f'response {k} ({kind}) rejected for {p.get("reason")}')
            if kind == 'truncated' and retries:
                fail('f1-retry', f'response {k}: truncated turn rejected although retries are enabled')
            if p.get('correction-requested'):
                corrections.append({'next': k + 1, 'terminal': terminal and parents.get(session) is None
                                    and p.get('reason') == 'no-tool-call'})
        elif h['type'] == 'provider-turn-retried':
            if kind != 'truncated':
                fail('f1-retry', f'response {k} ({kind}) was retried but is not a confirmed truncation')
            if not retries:
                fail('f1-retry', f'response {k} was retried with F1 off')
            # retried: true records a granted allowance. The resend itself is the next gateway
            # request; when a cap or the deadline refuses it, none follows and the session fails.
            if p.get('retried') and k + 1 < len(intents):
                if strip_cache(intents[k + 1]['input']) != strip_cache(g['input']):
                    fail('f1-retry', f'response {k}: the retried request differs from the original')
            elif p.get('retried') and not root_failed:
                fail('f1-retry', f'response {k}: a granted retry was neither sent nor refused by a limit')
            elif p.get('retried'):
                refused += 1
        elif h['type'] == 'evidence-gate':
            # The done call stays in history, answered by the notice instead of being run.
            call = next((b for b in body['content'] if b['type'] == 'tool_use'), {})
            if not gate:
                fail('evidence-gate', f'response {k}: gate fired with the switch off')
            if parents.get(session) is not None or call.get('name') != 'done':
                fail('evidence-gate', f'response {k}: gate fired outside a root done')
            if not (p.get('audit') or {}).get('open'):
                fail('evidence-gate', f'response {k}: gate fired without open audit items')
            received.append(body['content'])
        elif h['type'] == 'terminal-text-accepted':
            prior_rejection = [c for c in corrections if c['next'] == k and c['terminal']]
            if not terminal:
                fail('f2-terminal', f'response {k}: terminal answer accepted with F2 off')
            if parents.get(session) is not None:
                fail('f2-terminal', f'response {k}: terminal answer accepted in child session {session}')
            if not prior_rejection or TERMINAL_INSTRUCTION not in json.dumps(messages[-1]):
                fail('f2-terminal', f'response {k}: terminal answer accepted without the instruction')
            if terminal_answer(body) is None or terminal_answer(body) != p.get('answer'):
                fail('f2-terminal', f'response {k}: accepted text fails the strict FINAL ANSWER rule')
            # The only command an accepted answer may produce is done with that answer.
            if [x['payload']['command'] for x in handled[1:]] != [{'op': 'done', 'summary': p.get('answer')}]:
                fail('f2-terminal', f'response {k}: acceptance produced a command other than done')

    events = [e['type'] for e in agent]
    granted = [e for e in agent if e['type'] == 'command-rejected' and e['payload'].get('correction-requested')]
    if len(granted) > 1:
        fail('one-correction', f'{len(granted)} corrections granted')
    issued = [e for e in agent if e['type'] == 'provider-turn-retried' and e['payload'].get('retried')]
    if len(issued) > retries:
        fail('f1-retry', f'{len(issued)} retries against an allowance of {retries}')
    if sum(1 for e in agent if e['type'] == 'evidence-gate') > (1 if gate else 0):
        fail('evidence-gate', 'more evidence gates than the contract allows')
    for rid in unknown:
        same = [g for g in intents if g['request-id'] != rid and g['input-hash'] == next(x for x in intents if x['request-id'] == rid)['input-hash']]
        if same:
            fail('unknown-outcome', f'request {rid} had no recorded outcome and was resent')

    # The answer file holds the root's done summary or its accepted terminal answer, nothing else.
    finished = [e['payload'] for e in agent if e['type'] == 'session-finished' and parents.get(e['payload']['id'], 'x') is None]
    answer_path = arm + '/agent/answer.txt'
    answer = Path(answer_path).read_text() if os.path.exists(answer_path) else None
    sources = [(e['payload'].get('result') or {}).get('summary') for e in agent if e['type'] == 'tool-result'
               and parents.get(e['payload']['session'], 'x') is None and e['payload'].get('op') in ('done', 'done/eval')]
    if finished and finished[-1]['status'] == 'complete':
        if answer is not None and answer.strip() not in [str(s).strip() for s in sources if s is not None]:
            fail('answer-provenance', 'answer file does not match a done summary or accepted terminal answer')
    elif answer:
        fail('answer-provenance', 'failed session left an answer file')

    return {'arm': arm, 'status': 'violations' if violations else 'conformant', 'violations': violations,
            'contract': {'truncated_turn_retries': retries, 'terminal_text_answer': terminal, 'targeted_review': gate},
            'evidence_gates': events.count('evidence-gate'),
            'retries_refused_by_limit': refused,
            'responses': counts, 'requests': len(intents), 'unknown_outcomes': len(unknown),
            'corrections': len(granted), 'retries': len(issued),
            'terminal_accepted': events.count('terminal-text-accepted'),
            'session': finished[-1]['status'] if finished else None}


def audit_run(run_dir):
    contract = contract_of(run_dir)
    arms = sorted(glob.glob(os.path.join(run_dir, '*-aljure'))) or sorted(
        d for d in glob.glob(os.path.join(run_dir, '*')) if os.path.isdir(d + '/agent'))
    return {'run': run_dir, 'contract': contract, 'arms': [audit_arm(a, contract) for a in arms]}


def summary(runs):
    rows = []
    for run in runs:
        arms = [a for a in run['arms'] if a['status'] in ('conformant', 'violations')]
        unauditable = [os.path.basename(a['arm']) for a in run['arms'] if a['status'] == 'unauditable']
        bad = [a for a in arms if a['status'] == 'violations']
        responses = {}
        for a in arms:
            for k, v in a.get('responses', {}).items():
                responses[k] = responses.get(k, 0) + v
        rows.append({'run': os.path.basename(run['run'].rstrip('/')), 'contract': run['contract'], 'arms': len(arms),
                     'conformant': len(arms) - len(bad), 'unauditable': unauditable, 'responses': responses,
                     'corrections': sum(a.get('corrections', 0) for a in arms),
                     'retries': sum(a.get('retries', 0) for a in arms),
                     'terminal_accepted': sum(a.get('terminal_accepted', 0) for a in arms),
                     'failed_sessions': sum(1 for a in arms if a.get('session') == 'failed'),
                     'violations': [v | {'arm': os.path.basename(a['arm'])} for a in bad for v in a['violations']]})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', nargs='*')
    parser.add_argument('--arm', action='append', default=[])
    parser.add_argument('--contract', default='{}')
    parser.add_argument('--out')
    args = parser.parse_args()
    runs = [audit_run(r) for r in args.runs]
    if args.arm:
        contract = json.loads(args.contract)
        runs.append({'run': 'arms', 'contract': contract, 'arms': [audit_arm(a, contract) for a in args.arm]})
    rows = summary(runs)
    if args.out:
        Path(args.out).write_text(json.dumps({'model_calls': 0, 'summary': rows, 'runs': runs}, indent=1))
    print(json.dumps(rows, indent=1))
    sys.exit(1 if any(r['violations'] for r in rows) else 0)


if __name__ == '__main__':
    main()
