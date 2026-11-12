"""The execution-contract auditor on synthetic arms. Recorded shapes only; no model calls."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from contract_audit import audit_arm  # noqa: E402

TOOLS = [{'name': n} for n in ('context_metadata', 'context_query', 'repl_eval', 'agent_call', 'done')]
CORRECTION = ('Call exactly one of the provided tools. Text outside a tool call is never executed; to finish, call done. '
              "No rejected call was executed. This is the task's only formatting correction; normal budgets still apply.")
TERMINAL = ('Your response had no tool call, so nothing was executed. Call done with the exact final answer as summary. '
            'If you are finished but cannot call a tool, reply with exactly one line, FINAL ANSWER: <the exact final answer>, '
            "and nothing else; any other text is rejected. This is the task's only formatting correction; normal budgets still apply.")
THINK = {'type': 'thinking', 'thinking': 'Working.', 'signature': 'sig'}
BOTH = {'truncated_turn_retries': 1, 'terminal_text_answer': True}


def tool(name, **given):
    return {'content': [THINK, {'type': 'tool_use', 'id': f'toolu_{name}_{len(json.dumps(given))}', 'name': name,
                                'input': given}], 'stop_reason': 'tool_use'}


def text(value, stop='end_turn'):
    return {'content': [THINK, {'type': 'text', 'text': value}], 'stop_reason': stop}


TRUNCATED = {'content': [THINK, {'type': 'thinking', 'thinking': 'This part of the response was interrupted before it finished.',
                                 'signature': 'sig'}], 'stop_reason': 'tool_use'}


class Arm:
    """Writes the gateway and agent records Aljure's runtime produces for a root session."""

    def __init__(self):
        self.messages = [{'role': 'user', 'content': 'base'}, {'role': 'user', 'content': 'task'}]
        self.requests, self.agent, self.answer = [], [self._event('session-created', id='root', parent=None)], None
        self.pending_correction = None

    def _event(self, kind, **payload):
        return {'type': kind, 'payload': payload}

    def turn(self, body, handling, *, session='root', command=None, reason=None, correction=None):
        """Records one request and response, then Aljure's handling of it."""
        k = len(self.requests)
        self.requests.append((copy.deepcopy(self.messages), body))
        self.agent += [self._event('provider-reserved', session=session), self._event('provider-input', session=session,
                       **{'request-id': f'a{k}', 'message-count': len(self.messages)}),
                       self._event('provider-result', usd=0.01)]
        if handling == 'execute':
            call = next((b for b in body['content'] if b['type'] == 'tool_use'), {'id': 'none', 'name': None})
            command = command or {'op': {'repl_eval': 'repl/eval', 'done': 'done'}[call['name']], **call['input']}
            self.agent.append(self._event('tool-call', session=session, command=command))
            result = {'summary': command['summary']} if command['op'] == 'done' else {'value': 1}
            self.agent.append(self._event('tool-result', session=session, op=command['op'], status='ok', result=result))
            self.messages += [{'role': 'assistant', 'content': body['content']},
                              {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': call['id'], 'content': '1'}]}]
            if command['op'] == 'done':
                self.finish(command['summary'])
        elif handling == 'reject':
            granted = correction is not None
            self.agent.append(self._event('command-rejected', session=session, reason=reason, executed=False,
                                          **{'correction-requested': granted}))
            if granted:
                self.messages.append({'role': 'user', 'content': [{'type': 'text', 'text': correction}]})
            else:
                self.agent.append(self._event('session-finished', id='root', status='failed', summary={}))
        elif handling == 'retry':
            self.agent.append(self._event('provider-turn-retried', session=session, reason='truncated-tool-turn',
                                          executed=False, retried=True))
        elif handling == 'format':
            self.agent.append(self._event('answer-format-notice', session=session, executed=False))
            call = next(b for b in body['content'] if b['type'] == 'tool_use')
            self.messages += [{'role': 'assistant', 'content': body['content']},
                              {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': call['id'], 'content': 'Not submitted.'}]}]
        elif handling == 'gate':
            self.agent.append(self._event('evidence-gate', session=session, audit={'open': 2}, executed=False))
            call = next(b for b in body['content'] if b['type'] == 'tool_use')
            self.messages += [{'role': 'assistant', 'content': body['content']},
                              {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': call['id'], 'content': 'Not submitted.'}]}]
        elif handling == 'accept':
            answer = body['content'][-1]['text'][len('FINAL ANSWER: '):].strip()
            self.agent += [self._event('terminal-text-accepted', session=session, answer=answer),
                           self._event('tool-call', session=session, command={'op': 'done', 'summary': answer}),
                           self._event('tool-result', session=session, op='done', status='ok', result={'summary': answer})]
            self.finish(answer)
        return self

    def finish(self, answer):
        self.answer = answer
        self.agent.append(self._event('session-finished', id='root', status='complete', summary={'summary': answer}))

    def write(self, root):
        root = Path(root)
        (root / 'gateway').mkdir(parents=True)
        (root / 'agent').mkdir()
        gateway, usage = [], []
        for k, (messages, body) in enumerate(self.requests):
            given = {'messages': messages, 'tools': TOOLS}
            gateway.append({'type': 'gateway-request-intent', 'payload': {
                'request-id': f'g{k}', 'input': given,
                'input-hash': hashlib.sha256(json.dumps(given, sort_keys=True).encode()).hexdigest()}})
            gateway.append({'type': 'gateway-response', 'payload': {'request-id': f'g{k}', 'response': {
                'status': 200, 'body': json.dumps(body)}}})
            usage.append({'status': 'complete', 'estimated_usd': 0.01})
        (root / 'gateway/events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in gateway))
        (root / 'gateway/usage.jsonl').write_text(''.join(json.dumps(u) + '\n' for u in usage))
        (root / 'agent/events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in self.agent))
        if self.answer is not None:
            (root / 'agent/answer.txt').write_text(self.answer)
        return str(root)


def recovered():
    """The fixture's shape: truncation, retry, an eval, a text reply, then FINAL ANSWER."""
    return (Arm().turn(TRUNCATED, 'retry').turn(tool('repl_eval', source='(count x)'), 'execute')
            .turn(text('The answer is 6.'), 'reject', reason='no-tool-call', correction=TERMINAL)
            .turn(text('FINAL ANSWER: 6'), 'accept'))


class ContractAuditTests(unittest.TestCase):
    def audit(self, arm, contract):
        with tempfile.TemporaryDirectory() as d:
            return audit_arm(arm.write(Path(d) / 'arm'), contract)

    def checks(self, arm, contract):
        return {v['check'] for v in self.audit(arm, contract).get('violations', [])}

    def test_conformant_arms_pass(self):
        original = (Arm().turn(tool('repl_eval', source='(count x)'), 'execute')
                    .turn(text('Answer: 6'), 'reject', reason='no-tool-call', correction=CORRECTION)
                    .turn(tool('done', summary='Answer: 6'), 'execute'))
        self.assertEqual(self.audit(original, {})['status'], 'conformant')
        result = self.audit(recovered(), BOTH)
        self.assertEqual(result['status'], 'conformant', result.get('violations'))
        self.assertEqual((result['retries'], result['corrections'], result['terminal_accepted']), (1, 1, 1))

    def test_switches_must_match_the_plan(self):
        self.assertTrue({'f1-retry', 'f2-terminal', 'correction-text'} <= self.checks(recovered(), {}))
        failed = Arm().turn(TRUNCATED, 'reject', reason='incomplete-turn')
        self.assertEqual(self.checks(failed, {}), set())
        self.assertIn('f1-retry', self.checks(failed, BOTH))

    def test_the_proposal_turn_after_the_recorded_answer_is_not_a_task_command(self):
        # aljure_contract.acquisition: one optional turn in session "proposal", after the root's done.
        def arm(replies):
            built = Arm().turn(tool('done', summary='Answer: 6'), 'execute')
            for reply in replies:
                built.turn(reply, 'none', session='proposal')
            built.agent.append(built._event('artifact-proposal', decision='declined'))
            return built
        result = self.audit(arm([text('No proposal.')]), {})
        self.assertEqual(result['status'], 'conformant', result.get('violations'))
        self.assertEqual(self.checks(arm([tool('skip_proposal')]), {}), set())
        # A second proposal request means the first was not the last request.
        self.assertIn('proposal', self.checks(arm([text('a'), text('b')]), {}))

    def test_text_is_never_executed(self):
        arm = Arm().turn(text('(count x)'), 'execute', command={'op': 'repl/eval', 'source': '(count x)'})
        self.assertIn('text-never-executed', self.checks(arm, {}))

    def test_executed_command_must_be_the_tool_call(self):
        arm = Arm().turn(tool('repl_eval', source='(count x)'), 'execute', command={'op': 'repl/eval', 'source': '(slurp "/etc")'})
        self.assertIn('command-provenance', self.checks(arm, {}))

    def test_one_correction_per_task(self):
        arm = (Arm().turn(text('a'), 'reject', reason='no-tool-call', correction=CORRECTION)
               .turn(text('b'), 'reject', reason='no-tool-call', correction=CORRECTION))
        self.assertIn('one-correction', self.checks(arm, {}))

    def test_only_confirmed_truncation_is_retried_with_the_same_request(self):
        arm = Arm().turn(text('partial', stop='max_tokens'), 'retry')
        self.assertIn('f1-retry', self.checks(arm, BOTH))
        changed = Arm().turn(TRUNCATED, 'retry')
        changed.messages.append({'role': 'user', 'content': 'extra'})
        changed.turn(tool('done', summary='x'), 'execute')
        self.assertIn('f1-retry', self.checks(changed, BOTH))
        twice = Arm().turn(TRUNCATED, 'retry').turn(TRUNCATED, 'retry')
        self.assertIn('f1-retry', self.checks(twice, BOTH))

    def test_a_retry_refused_by_a_limit_is_not_a_violation(self):
        refused = Arm().turn(TRUNCATED, 'retry')
        refused.agent.append(refused._event('session-finished', id='root', status='failed', summary={}))
        result = self.audit(refused, BOTH)
        self.assertEqual(result['status'], 'conformant', result.get('violations'))
        self.assertEqual(result['retries_refused_by_limit'], 1)
        self.assertIn('f1-retry', self.checks(Arm().turn(TRUNCATED, 'retry'), BOTH))

    def test_terminal_answer_needs_the_instruction_and_the_strict_line(self):
        early = Arm().turn(text('FINAL ANSWER: 6'), 'accept')
        self.assertIn('f2-terminal', self.checks(early, BOTH))
        loose = (Arm().turn(text('I think 6.'), 'reject', reason='no-tool-call', correction=TERMINAL)
                 .turn(text('FINAL ANSWER: 6\nBecause the context has six characters.'), 'accept'))
        self.assertIn('f2-terminal', self.checks(loose, BOTH))
        wrong_text = (Arm().turn(text('I think 6.'), 'reject', reason='no-tool-call', correction=CORRECTION)
                      .turn(text('FINAL ANSWER: 6'), 'accept'))
        self.assertTrue({'f2-terminal', 'correction-text'} <= self.checks(wrong_text, BOTH))

    def test_history_is_append_only_and_verbatim(self):
        arm = recovered()
        arm.requests[3][0][1] = {'role': 'user', 'content': 'a different task'}
        self.assertIn('append-only', self.checks(arm, BOTH))
        forged = recovered()
        messages, body = forged.requests[3]
        messages[2] = {'role': 'assistant', 'content': [{'type': 'text', 'text': 'invented'}]}
        self.assertIn('verbatim-history', self.checks(forged, BOTH))

    def test_evidence_gate_only_with_its_switch_and_once(self):
        gated = (Arm().turn(tool('repl_eval', source='(audit-labels ids labels)'), 'execute')
                 .turn(tool('done', summary='Answer: 120'), 'gate').turn(tool('done', summary='Answer: 122'), 'execute'))
        result = self.audit(gated, {'structured_labels': True, 'uncertainty_audit': True, 'targeted_review': True})
        self.assertEqual(result['status'], 'conformant', result.get('violations'))
        self.assertEqual(result['evidence_gates'], 1)
        self.assertIn('evidence-gate', self.checks(gated, {}))
        twice = (Arm().turn(tool('done', summary='a'), 'gate').turn(tool('done', summary='b'), 'gate')
                 .turn(tool('done', summary='c'), 'execute'))
        self.assertIn('evidence-gate', self.checks(twice, {'structured_labels': True, 'uncertainty_audit': True, 'targeted_review': True}))

    def test_format_notice_only_on_a_real_violation_with_its_switch_once(self):
        form = {'answer_format': {'max_lines': 1, 'max_chars': 64}}
        good = (Arm().turn(tool('done', summary='Answer: 285\n\nAn estimate.'), 'format')
                .turn(tool('done', summary='Answer: 285'), 'execute'))
        result = self.audit(good, form)
        self.assertEqual(result['status'], 'conformant', result.get('violations'))
        self.assertEqual(result['format_notices'], 1)
        self.assertIn('answer-format', self.checks(good, {}))
        spurious = Arm().turn(tool('done', summary='Answer: 285'), 'format').turn(tool('done', summary='Answer: 285'), 'execute')
        self.assertIn('answer-format', self.checks(spurious, form))

    def test_answer_and_accounting(self):
        arm = recovered()
        arm.answer = '7'
        self.assertIn('answer-provenance', self.checks(arm, BOTH))
        with tempfile.TemporaryDirectory() as d:
            path = recovered().write(Path(d) / 'arm')
            usage = Path(path) / 'gateway/usage.jsonl'
            usage.write_text(''.join(usage.read_text().splitlines(keepends=True)[:-1]))
            self.assertIn('accounting', {v['check'] for v in audit_arm(path, BOTH)['violations']})


if __name__ == '__main__':
    unittest.main()
