"""Per-arm interaction metrics for the Sonnet and Opus OOLONG-synth 32K dev runs, both harnesses.

Read-only over recorded traces in a clean checkout; no model calls. Reuses the per-arm
decomposition (score, calls, output tokens, cost, wall time) and its trace readers.

    python3 scripts/interaction_metrics.py CLEAN_REPL_LAB DECOMPOSITION.json OUT.json

Every classification is heuristic. RULES (written into the output) names each rule, and
each arm row lists the evidence the rule used, so a reader can audit or overturn it.
Low-confidence rows carry `confidence: low` and the reasons.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark.official import score_answer  # noqa: E402  (pure scorer; reads no data)
from model_harness_decomposition import RUNS, records  # noqa: E402

SUITE = 'var/official/synth32-indep-dev'   # dev only; the held-out suite is never opened
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()

RULES = {
    'relevant_items': "Instances (Date/User/Instance lines of the public context) in the question's subset: "
                      "'in <Month> of any year', 'between <d0> and <d1>, inclusive', 'user IDs <n>', "
                      "'User <a> or User <b>'; otherwise all instances.",
    'items_displayed': "A relevant instance counts as displayed when a 56-character window of its text "
                       "(characters 4-60, or the last 60-4 for texts of 200+ characters) appears in a root "
                       "tool result; texts of 12-63 characters match on text[4:]; texts under 12 characters "
                       "cannot be matched and are left out of the coverage denominator (count reported).",
    'label_rule': "A regex literal (Clojure #\"...\", Python re.* argument) with >=3 alternation branches, "
                  "none naming Date/User/Instance/month/\\d structure; or a vector/list of >=5 quoted "
                  "alphabetic keywords (not month names). Single-label probes are not rules.",
    'judgement_literal': "Model judgements written into code: >=8 integers in one literal run (index sets), "
                         "or a quoted string of >=10 letters drawn from <=3 symbols (e.g. 'TFTF...').",
    'per_batch_count': "A number appended to program state per page: x.append(<int>[+<int>]), x=[<int>], "
                       "or Clojure swap!/conj with an integer.",
    'decision_count': "A non-final call with a counting operation (len/sum/count/frequencies/Counter/distinct) "
                      "whose short (<300 char) result has digits, over a judgement literal, a label rule, "
                      "or a variable defined from one.",
    'algorithm_class': "delegated: child sessions exist. structural-only: question has no 'label' and no "
                       "label rule. R = label rule present; J = judgement literal present or >= min(20, "
                       "relevant) items displayed. R and not J: rules. R and J: rules if no judgement "
                       "literal and the last non-final call holds the rule (rule decided after a look), "
                       "else mixed. J only: read-and-judge.",
    'answer_basis': "From the last decision_count, if no new items were displayed after it: "
                    "computed-from-judgements (over judgement literals), computed-from-rules (over a rule "
                    "only), computed-sum-of-stated-batch-counts (over per-batch numbers only). "
                    "computed-structural: no labels needed. stated: no decision_count, so the count lived "
                    "only in thinking/text; 'stated (code counts preceded further reading)' when the last "
                    "decision_count came before more items were read. For numeric tasks also: does the final "
                    "number appear in a short (<300 char) root tool result.",
    'verification': "reread-selected: a call after the first item display that prints items chosen by an "
                    "explicit index list or single index. label-length-check: len/count of a judgement "
                    "literal by itself. recount: a second decision_count with no new items displayed since "
                    "the previous one. after_pass marks calls after the last call that displayed new items.",
    'errors': "Aljure: tool-result status != ok. Prime: toolResult isError, status != ok, or a traceback; "
              "assistant stopReason 'error'. Recovered: a later successful tool result in the same session.",
    'text_candidates': "Text-only replies (Aljure rejections; Prime replies when no answer file exists). The "
                       "last requested-form line in each is scored with the official scorer, as the "
                       "counterfactual 'if this text had been accepted'.",
    'child_use': "Prime: numbers in agent_message replies from children that reappear inside the root's "
                 "per-batch count expressions (e.g. C.append(11+22)).",
    'end_reason': "model-finished: Aljure session complete via done, or Prime root ended its own turn. "
                  "harness-rejection: Aljure session failed on a rejected response. limit: calls, seconds "
                  "or dollars reached the plan cap.",
}


# ---------- generic helpers ----------

def flat(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return '\n'.join(flat(v) for v in value.values())
    if isinstance(value, list):
        return '\n'.join(flat(v) for v in value)
    return '' if value is None else str(value)


def norm(text):
    return re.sub(r'\s+', ' ', text)


def parse_body(response):
    """Gateway response body (JSON or SSE) -> {content, usage, stop_reason}."""
    body, kind = response.get('body') or '', response.get('content-type') or ''
    if 'event-stream' not in kind:
        try:
            return json.loads(body)
        except ValueError:
            return {'content': [], 'usage': {}, 'stop_reason': None}
    msg, blocks = {'usage': {}, 'stop_reason': None}, {}
    for line in body.split('\n'):
        if not line.startswith('data:'):
            continue
        try:
            d = json.loads(line[5:])
        except ValueError:
            continue
        if d.get('type') == 'message_start':
            msg['usage'].update(d['message'].get('usage') or {})
        elif d.get('type') == 'content_block_start':
            blocks[d['index']] = dict(d['content_block'])
        elif d.get('type') == 'message_delta':
            msg['stop_reason'] = d['delta'].get('stop_reason')
            msg['usage'].update(d.get('usage') or {})
    msg['content'] = [blocks[k] for k in sorted(blocks)]
    return msg


def gateway(arm):
    out = []
    for e in records(arm + '/gateway/events.jsonl'):
        if e['type'] == 'gateway-response':
            r = e['payload']['response']
            m = parse_body(r)
            kinds = sorted({b.get('type') for b in m.get('content') or []})
            out.append({'status': r.get('status'), 'stop_reason': m.get('stop_reason'), 'blocks': kinds,
                        'thinking_tokens': ((m.get('usage') or {}).get('output_tokens_details') or {}).get('thinking_tokens') or 0})
    return out


# ---------- task subset ----------

def instances(context):
    rows = []
    for line in context.split('\n'):
        m = re.match(r'Date: (\w{3} \d{1,2}, \d{4}) \|\| User: (\d+) \|\| Instance: (.*)$', line)
        if m:
            rows.append({'date': datetime.strptime(m[1], '%b %d, %Y'), 'user': m[2], 'text': m[3]})
    return rows


def subset(question, rows):
    q = question
    if m := re.search(r'occur in (\w+) of any year', q):
        mon = m[1][:3]
        return f'month {mon}', [r for r in rows if r['date'].strftime('%b') == mon]
    if m := re.search(r'between (\w{3} \d{1,2}, \d{4}) and (\w{3} \d{1,2}, \d{4}), inclusive', q):
        d0, d1 = (datetime.strptime(x, '%b %d, %Y') for x in (m[1], m[2]))
        return f'dates {m[1]}..{m[2]}', [r for r in rows if d0 <= r['date'] <= d1]
    if m := re.search(r'associated with user IDs ([\d, ]+)', q):
        users = set(re.findall(r'\d+', m[1]))
        return f'users {sorted(users)}', [r for r in rows if r['user'] in users]
    if m := re.search(r'User (\d+) or User (\d+)', q):
        return f'users {m[1]},{m[2]}', [r for r in rows if r['user'] in (m[1], m[2])]
    return 'all', rows


def windows(text):
    """Head and tail windows of an instance; short texts minus 4 leading characters (prints that
    sliced at a fixed offset after 'Instance:' dropped 1-3 characters). Very short texts: none."""
    t = norm(text).strip()
    if len(t) >= 64:
        return (t[4:60], t[-60:-4]) if len(t) >= 200 else (t[4:60],)
    return (t[4:],) if len(t) >= 12 else ()


# ---------- code features ----------

STRUCT = re.compile(r'Date|User|Instance|\\d|\\\|\\\||\|\||->|\b(?:' + '|'.join(MONTHS) + r')\b')


def regex_literals(code):
    pats = re.findall(r'#"((?:[^"\\]|\\.)*)"', code)
    pats += [m[2] for m in re.finditer(r're\.\w+\(\s*r?(["\'])((?:(?!\1).)*)\1', code)]
    pats += [m[1] for m in re.finditer(r're\.\w+\(\s*r?"""(.*?)"""', code, re.S)]
    return pats


def label_rules(code):
    found = []
    for p in regex_literals(code):
        branches = [b for b in re.split(r'(?<!\\)\|', p) if re.search(r'[A-Za-z]{2,}', b)]
        if len(branches) >= 3 and not STRUCT.search(p):
            found.append(p[:120])
    for m in re.finditer(r'[\[\{(]\s*((?:(["\'])[^"\'\n]{1,40}\2[\s,]*){5,})[\]\})]', code):
        words = re.findall(r'["\']([^"\'\n]{1,40})["\']', m[1])
        if all(re.search(r'[A-Za-z]', w) for w in words) and not any(w[:3] in MONTHS and len(w) <= 4 for w in words):
            found.append('keywords: ' + ' '.join(words)[:120])
    return found


def judgement_literals(code):
    code = INDEX_SELECT.sub(' ', code)   # index lists that select items to print are not judgements
    found = [m[0][:60] + ('...' if len(m[0]) > 60 else '') + f' ({len(re.findall(r"[0-9]+", m[0]))} ints)'
             for m in re.finditer(r'(?<![\w.])\d+(?:[ \t,\n]+\d+){7,}', code)]
    for m in re.finditer(r'("""|"|\')((?:(?!\1)[\s\S])*?)\1', code):
        s = re.sub(r'\s+', '', m[2])
        if len(s) >= 10 and s.isalpha() and len(set(s)) <= 3:
            found.append(f'label string len {len(s)} over {"".join(sorted(set(s)))}')
    return found


def per_batch_counts(code):
    return re.findall(r'\.append\(\s*\d+(?:\s*\+\s*\d+)*\s*\)|\b\w+\s*=\s*\[\d+\]|\((?:swap!|conj)[^()]*\b\d+\)', code)


def assigned_names(code):
    names = set(re.findall(r'^\s*(\w+)\s*(?:[+|]?=)(?!=)', code, re.M))
    names |= set(re.findall(r'\b(\w+)\.append\(', code)) | set(re.findall(r'\bdef\s+(\w+)\(', code))
    names |= set(re.findall(r'\(def(?:n)?\s+([\w\-?!*]+)', code))
    return names


def numeric_leaf(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(numeric_leaf(v) for v in value.values())
    if isinstance(value, list):
        return any(numeric_leaf(v) for v in value)
    return False


COUNT_OP = re.compile(r'\b(len|sum|count|frequencies|Counter|distinct)\b|\.count\(')
INDEX_SELECT = re.compile(r'for \w+ in \[(?:\s*\d+\s*,){1,29}\s*\d+\s*\]|print\(\w+\[\d+\]|'
                          r'\(map [^\n]*\[(?:\d+\s+){1,29}\d+\]\)')


# ---------- trajectories ----------

def aljure_trajectory(arm):
    ev = records(arm + '/agent/events.jsonl')
    results = {e['payload']['call-sequence']: e['payload'] for e in ev if e['type'] == 'tool-result'}
    steps, rejections, finished = [], [], None
    for e in ev:
        p = e['payload']
        if e['type'] == 'tool-call':
            c, r = p['command'], results.get(e['sequence'], {})
            ok = r.get('status') == 'ok'
            steps.append({'op': c.get('op'), 'code': c.get('source') if 'source' in c else json.dumps(c),
                          'result': flat(r.get('result') if ok else r.get('error') or r.get('result')),
                          'numeric': ok and numeric_leaf(r.get('result')),
                          'ok': ok, 'final': c.get('op') == 'done', 'session': p.get('session')})
        elif e['type'] == 'command-rejected':
            rejections.append({'reason': p.get('reason'), 'recoverable': p.get('recoverable', True),
                               'text': (p.get('text') or '')[:4000], 'after_step': len(steps)})
        elif e['type'] == 'session-finished' and p.get('id') == 'root':
            finished = p
    children = sum(1 for e in ev if e['type'] == 'session-created') - 1
    return {'steps': steps, 'rejections': rejections, 'finished': finished, 'children': children,
            'texts': [], 'provider_errors': []}


def prime_session(path):
    calls, results, texts, perrs, custom, out_tokens, last_stop = {}, {}, [], [], [], 0, None
    order = []
    for line in open(path):
        if not line.strip():
            continue
        x = json.loads(line)
        m = x.get('message') or {}
        if x.get('type') == 'custom_message':
            custom.append({'type': x.get('customType'), 'content': (x.get('content') or '')[:300]})
        elif m.get('role') == 'assistant':
            out_tokens += (m.get('usage') or {}).get('output') or 0
            last_stop = m.get('stopReason')
            if m.get('stopReason') == 'error':
                perrs.append(m.get('errorMessage'))
            for b in m.get('content') or []:
                if b.get('type') in ('toolCall', 'tool_use'):
                    args = b.get('arguments') or b.get('input') or {}
                    calls[b['id']] = args.get('code') or json.dumps(args)
                    order.append(b['id'])
                elif b.get('type') == 'text':
                    texts.append({'after_step': len(order), 'text': b['text'][:4000]})
        elif m.get('role') == 'toolResult':
            c = m.get('content')
            txt = ' '.join(b.get('text', '') for b in c) if isinstance(c, list) else str(c)
            ok = not m.get('isError') and (m.get('details') or {}).get('status', 'ok') == 'ok' and 'Traceback' not in txt
            results[m.get('toolCallId')] = (txt, ok)
    steps = [{'op': 'python_repl', 'code': calls[i], 'result': results.get(i, ('', False))[0],
              'ok': results.get(i, ('', False))[1], 'final': '/work/answer.txt' in calls[i] and 'write' in calls[i]}
             for i in order]
    return {'steps': steps, 'texts': texts, 'provider_errors': perrs, 'custom': custom,
            'output_tokens': out_tokens, 'last_stop': last_stop}


def prime_trajectory(arm):
    roots = sorted(glob.glob(arm + '/native/sessions/*.jsonl'))
    root = prime_session(roots[0])
    for extra in roots[1:]:
        more = prime_session(extra)
        root['steps'] += more['steps']
    subs = [prime_session(f) for f in sorted(glob.glob(arm + '/native/agent/session-artifacts/**/sub-*/*.jsonl', recursive=True))
            if not f.endswith('semantic-edges.jsonl')]
    root.update(children=len(subs), subs=subs, rejections=[], finished=None)
    return root


# ---------- per-arm metrics ----------

def arm_metrics(root, run, model, row, task, answer_row, limits, decomp):
    arm = os.path.join(root, run, (row.get('trace_path') or row.get('usage_path')).split('/')[0])
    harness, question = row['harness'], task['question']
    tr = aljure_trajectory(arm) if harness == 'aljure' else prime_trajectory(arm)
    steps = [s for s in tr['steps'] if s.get('session', 'root') == 'root']
    rows = instances(json.load(open(arm + '/public-input.json'))['context'])
    subset_name, rel = subset(question, rows)
    wins = [windows(r['text']) for r in rel]
    unmatchable = sum(1 for w in wins if not w)
    needs_label = 'label' in question.lower()
    numeric = answer_row['answer_type'].endswith('NUMERIC')
    answer = (open(arm + '/answer.txt').read().strip() if os.path.exists(arm + '/answer.txt') else '')

    shown, rule_vars, lit_kinds, plain_vars = set(), set(), {}, set()
    feats, last_new, decisions, verification = [], -1, [], []
    rules_all, lits_all, batch_all = [], [], []
    for i, s in enumerate(steps):
        code, res = s['code'] or '', norm(s['result'] or '')
        f = {'i': i, 'final': s['final'], 'ok': s['ok']}
        echo = harness == 'aljure' and s['final']   # done echoes the summary; it displays nothing new
        disp = set() if echo else {k for k, ws in enumerate(wins) if any(w in res for w in ws)}
        new = disp - shown
        f.update(displayed=len(disp), new=len(new))
        had_display = bool(shown)
        if new:
            last_new = i
        shown |= disp
        f['rules'], f['literals'], f['batch'] = label_rules(code), judgement_literals(code), per_batch_counts(code)
        rules_all += f['rules']
        lits_all += f['literals']
        batch_all += f['batch']
        kinds = ({'string'} if any('label string' in x for x in f['literals']) else set()) | \
                ({'index'} if any(' ints)' in x for x in f['literals']) else set()) | ({'batch'} if f['batch'] else set())
        for v, k in lit_kinds.items():
            if re.search(r'(?<![\w\-])%s(?![\w\-])' % re.escape(v), code):
                kinds |= k
        uses_rule = bool(f['rules']) or any(re.search(r'(?<![\w\-])%s(?![\w\-])' % re.escape(v), code) for v in rule_vars)
        length_only = kinds and kinds <= {'string'} and re.search(r'\blen\(|\(count ', code) \
            and not re.search(r'\.count\(|\bsum\(|frequencies|Counter', code)
        countable = (len(s['result'] or '') < 300 and re.search(r'\d', s['result'] or '')) or s.get('numeric')
        if not echo:
            if countable and COUNT_OP.search(code) and (kinds or uses_rule) and not length_only:
                kind = 'batch-sums' if kinds == {'batch'} else 'judgements' if kinds else 'rules'
                if decisions and steps_since_new(feats, decisions[-1]['i']) == 0 and f['new'] == 0 \
                        and not f['literals'] and not f['batch']:
                    verification.append({'i': i, 'kind': 'recount', 'after_pass': None, 'evidence': code[:120]})
                decisions.append({'i': i, 'kind': kind, 'result': norm(s['result'] or '')[:120]})
            if length_only:
                verification.append({'i': i, 'kind': 'label-length-check', 'after_pass': None,
                                     'evidence': norm(s['result'] or '')[:40]})
            if had_display and INDEX_SELECT.search(code) and len(s['result'] or '') > 100:
                verification.append({'i': i, 'kind': 'reread-selected', 'after_pass': None,
                                     'evidence': INDEX_SELECT.search(code)[0][:100]})
        names = assigned_names(code)
        if f['literals'] or f['batch']:
            here = ({'string'} if any('label string' in x for x in f['literals']) else set()) | \
                   ({'index'} if any(' ints)' in x for x in f['literals']) else set()) | ({'batch'} if f['batch'] else set())
            for n in names - plain_vars:
                lit_kinds[n] = lit_kinds.get(n, set()) | here
        elif f['rules']:
            rule_vars |= names - plain_vars
        else:
            plain_vars |= names - set(lit_kinds) - rule_vars
        feats.append(f)
    for v in verification:
        v['after_pass'] = v['i'] >= last_new

    # algorithm class
    n_rel = len(rel) - unmatchable
    J = bool(lits_all) or len(shown) >= min(20, max(1, n_rel))
    R = bool(rules_all)
    nonfinal = [f for f in feats if not f['final']]
    reasons = []
    if tr['children'] > 0:
        cls = 'delegated'
    elif not needs_label and not R:
        cls = 'structural-only'
    elif R and not J:
        cls = 'rules'
    elif R and J:
        cls = 'rules' if (not lits_all and nonfinal and nonfinal[-1]['rules']) else 'mixed'
    elif J:
        cls = 'read-and-judge'
    else:
        cls, _ = 'unclassified', reasons.append('no rule, no literal, <10 items displayed')
    eff = cls
    if cls == 'delegated':
        eff = 'mixed' if (R and J) else 'rules' if R else 'read-and-judge'
    coverage = round(len(shown) / n_rel, 3) if n_rel else None
    if cls == 'read-and-judge' and coverage is not None and coverage < 0.5:
        reasons.append(f'only {coverage:.0%} of the {subset_name} subset displayed'
                       + (' (top-user shortcut)' if subset_name == 'all' and 'user' in question.lower() else ''))
    if cls == 'rules' and J:
        reasons.append('rule decided the answer, but items were also displayed')
    if cls in ('read-and-judge', 'mixed', 'rules') and not lits_all and unmatchable > 0.1 * len(rel):
        reasons.append(f'{unmatchable} of {len(rel)} relevant instances too short to match')

    # answer basis
    num = re.findall(r'-?\d+', answer)
    value = num[-1] if (numeric and num) else None
    in_result = None
    if value is not None:
        in_result = any(len(s['result'] or '') < 300 and re.search(r'(?<!\d)%s(?!\d)' % value, s['result'] or '')
                        for s in steps if not (harness == 'aljure' and s['final']))
    if not needs_label:
        basis = 'computed-structural'
    elif not decisions:
        basis = 'stated'
    elif decisions[-1]['i'] < last_new:
        basis = 'stated (code counts preceded further reading)'
    else:
        basis = {'judgements': 'computed-from-judgements', 'rules': 'computed-from-rules',
                 'batch-sums': 'computed-sum-of-stated-batch-counts'}[decisions[-1]['kind']]
    if numeric and needs_label:
        lit_calls = sum(1 for f in feats if f['literals'])
        batch_state = ('per-batch-counts' if batch_all else 'per-batch-judgements' if lit_calls >= 2
                       else 'single-judgement-literal' if lit_calls == 1 else 'none')
    else:
        batch_state = None

    # errors and provider/protocol events
    errors = [{'i': i, 'message': (s['result'] or '')[:160],
               'recovered': any(t['ok'] for t in steps[i + 1:])} for i, s in enumerate(steps) if not s['ok']]
    gw = gateway(arm)
    protocol = [f"rejected:{r['reason']}" for r in tr['rejections']]
    protocol += [f"gateway:{g['status']}:{g['stop_reason']}:{'+'.join(g['blocks'])}" for g in gw
                 if g['status'] != 200 or g['stop_reason'] == 'max_tokens'
                 or (g['stop_reason'] == 'tool_use' and 'tool_use' not in g['blocks'])]
    protocol += [f'root-stream-error:{e}' for e in tr['provider_errors']]
    child = None
    if harness == 'prime' and tr['children']:
        child = {'sessions': tr['children'],
                 'calls': sum(len(c['steps']) for c in tr['subs']),
                 'tool_errors': [s['result'][:100] for c in tr['subs'] for s in c['steps'] if not s['ok']],
                 'stream_errors': [e for c in tr['subs'] for e in c['provider_errors']],
                 'output_tokens': sum(c['output_tokens'] for c in tr['subs']),
                 'messages_to_root': [c['content'] for c in tr['custom'] if c['type'] == 'agent_message'],
                 'failures_reported_to_root': [c['type'] + ': ' + c['content'][:120] for c in tr['custom']
                                               if c['type'] in ('rlm_child_failure', 'rlm_child_terminal_notice')],
                 'child_verification': [s['code'][:80] for c in tr['subs'] for s in c['steps'] if 'assert' in s['code']]}
        # did a number a child reported reach the root's per-batch program state?
        reported = {n for c in tr['custom'] if c['type'] == 'agent_message' for n in re.findall(r'\d+', c['content'].split(']')[-1])}
        child['child_numbers_in_root_batch_state'] = sorted(
            {n for f in feats for b in f['batch'] for n in re.findall(r'\d+', b) if n in reported}, key=int)
        protocol += [f'child-stream-error:{e}' for e in child['stream_errors']]

    # text candidates (before the final answer) and finalization
    texts = [r['text'] for r in tr['rejections'] if r['text']]
    if harness == 'prime' and not answer:
        texts += [t['text'] for t in tr['texts']]
    candidates = [c for c in map(answer_line, texts) if c]
    cand_scores = [round(score_answer('oolong-synth', answer_row, c)['score'], 3) for c in candidates]
    if harness == 'aljure':
        fin = tr['finished'] or {}
        reasons_rej = [r['reason'] for r in tr['rejections']]
        if fin.get('status') == 'complete':
            final = 'done' if not reasons_rej else 'text-only-correction->done' if set(reasons_rej) == {'no-tool-call'} else 'correction->done'
            end = 'model-finished'
        else:
            final = 'failure: ' + ('text-only x%d, correction exhausted' % reasons_rej.count('no-tool-call')
                                   if 'no-tool-call' in reasons_rej and 'incomplete-turn' not in reasons_rej
                                   else 'incomplete turn (thinking-only response), not recoverable'
                                   if 'incomplete-turn' in reasons_rej else str(fin.get('summary')))
            end = 'harness-rejection'
        changed = None
        if candidates and answer:
            changed = norm(candidates[-1]).strip() != norm(answer).strip()
    else:
        final = 'answer-file' if answer else 'failure: text-only answer, no answer file'
        end = 'model-finished' if tr['last_stop'] == 'stop' else f"stop:{tr['last_stop']}"
        changed = None

    calls, cap_calls = decomp['model_calls'], limits['calls']
    wall, cap_s = decomp['wall_s'], limits['seconds']
    cost, cap_usd = decomp['cost_usd'], limits['usd']
    if calls >= cap_calls or wall >= cap_s or cost >= cap_usd:
        end = 'limit'
    usage = records(arm + '/gateway/usage.jsonl')
    per_call = [u.get('output_tokens') or 0 for u in usage]

    out = {
        'model': model, 'harness': harness, 'task_id': row['task_id'], 'dataset': answer_row['dataset'],
        'answer_type': answer_row['answer_type'].split('.')[-1], 'status': row['status'], 'score': decomp['score'],
        'answer': answer[:80], 'subset': subset_name, 'relevant_items': len(rel),
        'unmatchable_short_items': unmatchable, 'needs_label': needs_label,
        'algorithm': {'class': cls, 'effective_root_class': eff, 'confidence': 'low' if reasons else 'high',
                      'low_confidence_reasons': reasons, 'label_rules': sorted(set(rules_all))[:6],
                      'judgement_literals': lits_all[:6], 'items_displayed': len(shown),
                      'coverage': coverage, 'tool_calls': len(steps)},
        'answer_basis': {'basis': basis, 'decision_counts': decisions, 'numeric_value_in_tool_result': in_result,
                         'count_task_batch_state': batch_state},
        'verification': {'any': bool(verification), 'events': verification,
                         'text_candidates': len(candidates), 'text_candidate_scores': cand_scores,
                         'final_differs_from_text_candidate': changed},
        'errors': {'tool_errors': errors, 'unrecovered': sum(1 for e in errors if not e['recovered']),
                   'protocol_events': protocol, 'child': child},
        'compute': {'calls': calls, 'output_tokens': decomp['output_tokens'], 'cost_usd': cost, 'wall_s': wall,
                    'thinking_tokens': sum(g['thinking_tokens'] for g in gw),
                    'max_call_output_tokens': max(per_call or [0]), 'final_call_output_tokens': (per_call or [0])[-1],
                    'root_output_tokens': tr.get('output_tokens') if harness == 'prime' else None},
        'budget': {'calls': f'{calls}/{cap_calls}', 'calls_frac': round(calls / cap_calls, 4),
                   'seconds': f'{wall}/{cap_s}', 'seconds_frac': round(wall / cap_s, 4),
                   'usd': f'{cost}/{cap_usd}', 'usd_frac': round(cost / cap_usd, 5), 'end_reason': end},
        'finalization': final,
    }
    return out


def answer_line(text):
    """Last line in a requested answer form ('Answer: ...', 'Label: ...', 'User: ...'); the official
    scorer misparses multi-line replies, so only this line is scored."""
    lines = re.findall(r'(?:Answer|Label|User):[ \t]*[^\n*]+', text.replace('**', ''))
    return lines[-1].strip() if lines else None


def steps_since_new(feats, since):
    return sum(f.get('new', 0) for f in feats[since + 1:])


# ---------- summaries ----------

def mean(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 3) if xs else None


def tally(xs):
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))


def group(rows):
    return {
        'tasks': len(rows), 'completed': sum(r['status'] == 'completed' for r in rows),
        'mean_score': mean(r['score'] for r in rows),
        'calls_total': sum(r['compute']['calls'] for r in rows), 'calls_mean': mean(r['compute']['calls'] for r in rows),
        'output_tokens_total': sum(r['compute']['output_tokens'] for r in rows),
        'thinking_tokens_total': sum(r['compute']['thinking_tokens'] for r in rows),
        'cost_usd_total': round(sum(r['compute']['cost_usd'] for r in rows), 3),
        'wall_s_total': round(sum(r['compute']['wall_s'] for r in rows), 1),
        'max_calls_frac': max(r['budget']['calls_frac'] for r in rows),
        'max_seconds_frac': max(r['budget']['seconds_frac'] for r in rows),
        'algorithm_class': tally(r['algorithm']['class'] for r in rows),
        'answer_basis': tally(r['answer_basis']['basis'] for r in rows),
        'arms_with_verification': sum(r['verification']['any'] for r in rows),
        'verification_kinds': tally(v['kind'] for r in rows for v in r['verification']['events']),
        'mean_coverage_label_tasks': mean(r['algorithm']['coverage'] for r in rows
                                          if r['algorithm']['class'] != 'structural-only'),
        'tool_errors': sum(len(r['errors']['tool_errors']) for r in rows),
        'unrecovered_tool_errors': sum(r['errors']['unrecovered'] for r in rows),
        'arms_with_protocol_events': sum(bool(r['errors']['protocol_events']) for r in rows),
        'finalization': tally(r['finalization'] for r in rows),
        'text_candidates': "Text-only replies (Aljure rejections; Prime replies when no answer file exists). The "
                       "last requested-form line in each is scored with the official scorer, as the "
                       "counterfactual 'if this text had been accepted'.",
    'end_reason': tally(r['budget']['end_reason'] for r in rows),
    }


def summarise(rows, order):
    key = {(r['model'], r['harness'], r['task_id']): r for r in rows}
    all4 = [t for t in order if all(key[(m, h, t)]['status'] == 'completed' for m in RUNS for h in ('aljure', 'prime'))]
    out = {'subset_all4_tasks': [order.index(t) + 1 for t in all4]}
    for name, tids in (('all_21', order), ('completed_by_all_4', all4)):
        g = {f'{m}/{h}': group([key[(m, h, t)] for t in tids]) for m in RUNS for h in ('aljure', 'prime')}
        d = lambda a, b, k: round(g[a][k] - g[b][k], 3)  # noqa: E731
        g['deltas'] = {
            'opus_minus_sonnet': {h: {k: d(f'opus/{h}', f'sonnet/{h}', k) for k in ('mean_score', 'calls_total', 'output_tokens_total', 'thinking_tokens_total')}
                                  for h in ('aljure', 'prime')},
            'aljure_minus_prime': {m: {k: d(f'{m}/aljure', f'{m}/prime', k) for k in ('mean_score', 'calls_total', 'output_tokens_total', 'thinking_tokens_total')}
                                   for m in RUNS},
        }
        g['deltas']['difference_in_differences_prime_minus_aljure'] = round(
            g['deltas']['opus_minus_sonnet']['prime']['mean_score'] - g['deltas']['opus_minus_sonnet']['aljure']['mean_score'], 3)
        out[name] = g
    # attribute the difference in differences to task buckets (rule recorded in the output)
    buckets = {}
    for t in order:
        r = {(m, h): key[(m, h, t)] for m in RUNS for h in ('aljure', 'prime')}
        did = ((r[('opus', 'prime')]['score'] - r[('sonnet', 'prime')]['score'])
               - (r[('opus', 'aljure')]['score'] - r[('sonnet', 'aljure')]['score'])) / len(order)
        if any(x['status'] != 'completed' for x in r.values()):
            b = 'answer delivery (an arm did not deliver)'
        elif any(r[('sonnet', h)]['algorithm']['effective_root_class'] != r[('opus', h)]['algorithm']['effective_root_class']
                 and abs(r[('opus', h)]['score'] - r[('sonnet', h)]['score']) > 0.5 for h in ('aljure', 'prime')):
            b = 'algorithm class changed with a score change > 0.5'
        elif r[('opus', 'aljure')]['answer_type'] == 'NUMERIC' and r[('opus', 'aljure')]['needs_label']:
            b = 'judged counts (accumulated semantic judgement)'
        else:
            b = 'other'
        buckets.setdefault(b, {'tasks': [], 'did_contribution': 0.0, 'per_task': {}})
        buckets[b]['tasks'].append(order.index(t) + 1)
        buckets[b]['did_contribution'] = round(buckets[b]['did_contribution'] + did, 4)
        if abs(did) > 1e-9:
            buckets[b]['per_task'][order.index(t) + 1] = round(did, 4)
    # counterfactual: an undelivered arm scored by its last text candidate (0 when it had none)
    cf = {}
    for (m, h, t), r in key.items():
        if r['status'] != 'completed':
            sc = r['verification']['text_candidate_scores']
            cf[(m, h, t)] = sc[-1] if sc else 0.0
    def cf_mean(m, h):
        return sum(cf.get((m, h, t), key[(m, h, t)]['score']) for t in order) / len(order)
    did_cf = (cf_mean('opus', 'prime') - cf_mean('sonnet', 'prime')) - (cf_mean('opus', 'aljure') - cf_mean('sonnet', 'aljure'))
    out['did_attribution'] = {
        'rule': "Per task: ((Prime Opus - Prime Sonnet) - (Aljure Opus - Aljure Sonnet)) / 21. Bucket order: "
                "any arm undelivered; else an arm's effective root algorithm class changed between models with "
                "|score change| > 0.5; else a numeric judged count; else other.",
        'buckets': buckets,
        'undelivered_arms_text_candidate_scores': {f'{m}/{h}/task{order.index(t) + 1}': v for (m, h, t), v in cf.items()},
        'did_if_text_candidates_had_been_accepted': round(did_cf, 3)}
    return out


def main(root, decomposition, out_path):
    suite = Path(root) / SUITE
    order = json.load(open(suite / 'manifest.json'))['task_ids']
    tasks = {r['task_id']: r for r in map(json.loads, open(suite / 'public/tasks.jsonl'))}
    answers = {r['task_id']: r for r in map(json.loads, open(suite / 'controller/answers.jsonl'))}
    decomp = {(r['model'], r['harness'], r['task_id']): r for r in json.load(open(decomposition))}
    rows = []
    for model, run in RUNS.items():
        plan = json.load(open(os.path.join(root, run, 'plan.json')))
        cfg = plan['config']
        limits = {'calls': cfg['calls_per_arm'], 'usd': cfg['usd_per_arm'],
                  'seconds': cfg.get('task_seconds') or plan['capabilities']['shared']['task_seconds']}
        for r in records(os.path.join(root, run, 'results.jsonl')):
            m = arm_metrics(root, run, model, r, tasks[r['task_id']], answers[r['task_id']], limits,
                            decomp[(model, r['harness'], r['task_id'])])
            m['task'] = order.index(r['task_id']) + 1
            m['limits'] = limits
            rows.append(m)
    rows.sort(key=lambda r: (r['model'] != 'sonnet', r['task'], r['harness']))
    result = {'rules': RULES, 'source': {'clean_checkout': root, 'runs': RUNS, 'decomposition': decomposition},
              'summary': summarise(rows, order), 'arms': rows}
    Path(out_path).write_text(json.dumps(result, indent=1, default=str) + '\n')
    for r in rows:
        a, b, v = r['algorithm'], r['answer_basis'], r['verification']
        print(f"{r['model'][:1]} {r['task']:2} {r['harness'][:1]} {r['score']:4.2f} {a['class']:15} "
              f"{a['items_displayed']:3}/{r['relevant_items'] - r['unmatchable_short_items']:<3} {b['basis']:25} "
              f"{','.join(sorted({e['kind'] for e in v['events']})) or '-':28} {r['budget']['calls']:7} "
              f"{r['budget']['seconds']:10} {r['finalization'][:40]} {a['confidence']}")


if __name__ == '__main__':
    main(*sys.argv[1:4])
