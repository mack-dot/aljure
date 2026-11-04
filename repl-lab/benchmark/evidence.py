"""Evidence-sufficiency detector, specification evidence-v1 (research/ALJURE_SELECTIVE_VERIFICATION_PLAN.md). Offline analysis tool only.

A deterministic, model-free check over TRUSTED execution metadata: the task question and the controller's
ordered ledger of what the root session executed and what the isolated worker returned. It never reads the
answer for keywords and never claims the answer is right. It establishes only whether the answer about to be
committed rests on the kind of evidence its task class requires.

States (one per assessment):
  supported       an item-level record covering the displayed items exists and a count follows it, or (for a
                  structural count) a computed number exists
  incomplete      an item-level record exists but covers fewer items than were displayed or enumerated
  approximation   the only counts came from keyword or regex matching over the context (no item-level record)
  contradictory   two successive count results disagree in direction and nothing reconciled them
  missing         the task needs an item-level tally and the ledger holds no record and no count at all
  undeterminable  the task class is not one the detector understands, or the ledger could not be read
                  (fail-safe: never triggers)

A corrective step is requested only when one of the four pre-registered observables holds (trigger v1,
research/EVIDENCE_TRIGGER_V1.md); `approximation` alone does not trigger. This module is the reference detector,
the replay tool over recorded runs, and the analyzer for native Prime's Python cells. It is NOT wired into the
Clojure controller: trigger v1 failed its pre-registered disjoint evaluation (precision 0.46, recall 0.39,
false-trigger rate 0.84; research/evidence/evidence-trigger-v1-disjoint-20261104/), so no controller hook was built.
"""
import json
import re

VERSION = 'evidence-v1'
MIN_RECORD = 8            # fewer recorded labels than this is not an item-level record
COVERAGE = 0.9            # a record must cover this share of the displayed items
MARGIN = 0.30             # a two-way count closer than this, |a-b|/(a+b), is a narrow margin
# Trigger v1 (pre-registered in research/EVIDENCE_TRIGGER_V1.md before any disjoint evaluation): four interpretable
# pre-answer observables, label-judgement tasks only. No gold answer or score is ever an input.
OBSERVABLES = ('O1-contradiction', 'O2-narrow-margin', 'O3-missing-aggregation', 'O4-incomplete-coverage')

LABEL_COMPARISON = re.compile(r"(?:is|was) label '[^']+' (?:more common, less common, or the same frequency|more common)", re.I)
LABEL_COUNT = re.compile(r"how many (?:data points|instances|items|records)[^?]*\blabel", re.I)
STRUCTURAL_COUNT = re.compile(r"how many (?:dates|users|user ids|months|days|years)\b|which (?:date|user|month)\b", re.I)
PAIRS = re.compile(r"list all pairs of user ids", re.I)


def task_class(question):
    """What kind of evidence the question needs, from the trusted task text alone."""
    q = str(question or '')
    if PAIRS.search(q):
        return 'pairs'
    if LABEL_COMPARISON.search(q):
        return 'label-comparison'
    if LABEL_COUNT.search(q):
        return 'label-count'
    if STRUCTURAL_COUNT.search(q):
        return 'structural-count'
    return 'unknown'


NEEDS_TALLY = ('label-comparison', 'label-count', 'pairs')

# ---- source analyzers (language-specific): how many per-item labels a step's SOURCE records as literals

_INT_COLLECTION = {'clojure': re.compile(r'#\{([\d\s]+)\}|\[([\d\s]+)\]'), 'python': re.compile(r'\{([\d,\s]+)\}|\[([\d,\s]+)\]')}
_LABEL_STRING = re.compile(r'"([A-Za-z01?]{12,})"')
_MAP_ENTRY = {'clojure': re.compile(r'\{((?:\s*\d+\s+(?::[\w-]+|"[^"]{1,24}")\s*,?)+)\}'),
              'python': re.compile(r"\{((?:\s*\d+\s*:\s*(?:'[^']{1,24}'|\"[^\"]{1,24}\"|\d)\s*,?)+)\}")}
_REGEX_COUNT = {'clojure': re.compile(r're-(?:find|seq|matches)|includes\?|\.contains'), 'python': re.compile(r're\.(?:findall|search|compile|match)|\bin\s+\w+\.lower\(\)|\.count\(')}
_COUNTING = {'clojure': re.compile(r'\bcount\b|\bfrequencies\b'), 'python': re.compile(r'\blen\(|Counter\(|\bsum\(|\.count\(')}


def record_parts(source, language):
    """Per-item labels written as literals in one step, by kind. `index`: integers in literal index collections
    (a record of the positives only, e.g. the indices judged False). `per_item`: characters of label strings over
    a small alphabet and entries of literal id->label maps (one label for every item). Literals are what a model
    types when it records its own judgements; computed collections are not counted."""
    source = str(source or '')
    index = per_item = 0
    for m in _INT_COLLECTION[language].finditer(source):
        ints = re.findall(r'\d+', m.group(1) or m.group(2) or '')
        if len(ints) >= 3:
            index += len(set(ints))
    for m in _LABEL_STRING.finditer(source):
        text = m.group(1)
        if len(set(text)) <= 6:   # a label alphabet, not prose
            per_item += len(text)
    for m in _MAP_ENTRY[language].finditer(source):
        per_item += len(re.findall(r'\d+\s*(?::|\s)', m.group(1)))
    return {'index': index, 'per_item': per_item}


def record_size(source, language):
    parts = record_parts(source, language)
    return parts['index'] + parts['per_item']


def displayed_items(text):
    """Distinct numbered item lines the worker returned to the model: '12 text', '12. text', '12: text'."""
    return {int(m) for m in re.findall(r'(?:^|\n|\| )\s*(\d{1,5})[.:)]?\s+\S', str(text or ''))}


def numbers_vector(text):
    """A result that is a short vector/list of numbers (a count result), else None."""
    t = str(text or '').strip()
    if re.fullmatch(r'[\[(]\s*\d+(?:[\s,]+\d+){1,5}\s*[\])]', t):
        return [int(x) for x in re.findall(r'\d+', t)]
    return None


def assess(question, steps, language='clojure'):
    """steps: [{'source': str, 'ok': bool, 'result': str}] in execution order, root session only.
    Returns {'version', 'class', 'state', 'trigger', 'facts'}; never raises."""
    try:
        cls = task_class(question)
        if not isinstance(steps, (list, tuple)):
            raise TypeError('ledger is not a list of steps')
        steps = [s for s in steps if isinstance(s, dict)]
        ok = [s for s in steps if s.get('ok')]
        index = sum(record_parts(s.get('source'), language)['index'] for s in ok)
        per_item = sum(record_parts(s.get('source'), language)['per_item'] for s in ok)
        record = index + per_item
        displayed = set()
        for s in ok:
            displayed |= displayed_items(s.get('result'))
        regex_counts = [s for s in ok if _REGEX_COUNT[language].search(str(s.get('source') or '')) and _COUNTING[language].search(str(s.get('source') or ''))]
        vectors = [v for v in (numbers_vector(s.get('result')) for s in ok) if v]
        computed_number = any(re.fullmatch(r'\s*\d+(?:\.\d+)?\s*', str(s.get('result') or '')) or numbers_vector(s.get('result')) for s in ok)
        flips = 0
        for a, b in zip(vectors, vectors[1:]):
            if len(a) >= 2 and len(b) >= 2 and (a[0] - a[1]) * (b[0] - b[1]) < 0:
                flips += 1
        last_error = bool(steps) and not steps[-1].get('ok')
        facts = {'steps': len(steps), 'ok_steps': len(ok), 'record': record, 'record_index': index, 'record_per_item': per_item,
                 'displayed': len(displayed), 'regex_count_steps': len(regex_counts), 'count_vectors': len(vectors),
                 'direction_flips': flips, 'last_step_error': last_error}
        observables = []
        if cls == 'unknown':
            state = 'undeterminable'
        elif cls == 'structural-count':
            state = 'supported' if computed_number else 'missing'
            if not computed_number:
                observables.append('O3-missing-aggregation')
        else:
            # Label-judgement tasks (comparison, count, pairs).
            margin = None
            if cls == 'label-comparison' and vectors:
                a, b = vectors[-1][-2], vectors[-1][-1]
                margin = abs(a - b) / max(1, a + b)
            facts['margin'] = margin
            short = bool(per_item) and len(displayed) >= MIN_RECORD and per_item < COVERAGE * len(displayed) and not index
            if (0 < record < MIN_RECORD) or (record >= MIN_RECORD and short) or (last_error and (record or computed_number)):
                state = 'incomplete'
                observables.append('O4-incomplete-coverage')
            elif record >= MIN_RECORD:
                state = 'supported'
            elif flips:
                state = 'contradictory'
                observables.append('O1-contradiction')
            elif computed_number:
                state = 'approximation'      # a count exists but no item-level record; not a trigger by itself
                if margin is not None and margin < MARGIN:
                    observables.append('O2-narrow-margin')
            else:
                state = 'missing'
                observables.append('O3-missing-aggregation')
        facts['observables'] = observables
        return {'version': VERSION, 'class': cls, 'state': state, 'trigger': bool(observables), 'facts': facts}
    except Exception as error:  # fail-safe: an unreadable ledger never blocks an answer
        return {'version': VERSION, 'class': 'unknown', 'state': 'undeterminable', 'trigger': False, 'facts': {'error': type(error).__name__}}


REQUESTS = {
    'supported': None,
    'missing': ('Not submitted yet. This answer needs a count over individual items, and the worker has no item-level record or '
                'count for it. Show the relevant items, record one label per item in the worker, compute the count from that '
                'record, then answer. This check is made once.'),
    'approximation': ('Not submitted yet. The only counts so far come from keyword or pattern matching, which does not decide '
                      'each item. Check the pattern against the items it matched and the ones it missed, or record one label per '
                      'item in the worker and count from that record, then answer. This check is made once.'),
    'contradictory': ('Not submitted yet. Two of your counts point in opposite directions and nothing reconciled them. Inspect the '
                      'items the two counts disagree on, record a label for each, recompute, then answer. This check is made once.'),
    'incomplete': ('Not submitted yet. Your item-level record covers fewer items than were shown. Complete the record for the '
                   'remaining items, recompute from the whole record, then answer. This check is made once.'),
}


def corrective_request(assessment):
    """The one corrective message for a triggering assessment, or None. Names the condition, not the answer."""
    if not assessment.get('trigger'):
        return None
    state = assessment.get('state')
    return REQUESTS.get('approximation' if state == 'approximation' else state)


# ---- ledgers of recorded runs (replay)

def aljure_steps(events):
    steps, pending = [], {}
    for e in events:
        p = e.get('payload') or {}
        if e.get('type') == 'tool-call' and p.get('session') == 'root':
            command = p.get('command') or {}
            if command.get('op') in ('repl/eval', 'done/eval'):
                pending[e.get('sequence')] = str(command.get('source') or '')
        elif e.get('type') == 'tool-result' and p.get('session') == 'root' and p.get('call-sequence') in pending:
            result = p.get('result')
            value = result.get('value') if isinstance(result, dict) and 'value' in result else result
            steps.append({'source': pending.pop(p['call-sequence']), 'ok': p.get('status') == 'ok',
                          'result': value if isinstance(value, str) else json.dumps(value)})
    return steps


def prime_steps(session_lines):
    steps, calls = [], {}
    for raw in session_lines:
        try:
            m = (json.loads(raw).get('message') or {})
        except ValueError:
            continue
        if m.get('role') == 'assistant':
            for b in m.get('content') or []:
                if isinstance(b, dict) and b.get('type') in ('toolCall', 'tool_use'):
                    args = b.get('arguments') or b.get('input') or {}
                    calls[b.get('id')] = str(args.get('code') or '')
        elif m.get('role') == 'toolResult' and m.get('toolCallId') in calls:
            content = m.get('content')
            text = ' '.join(x.get('text', '') for x in content if isinstance(x, dict)) if isinstance(content, list) else str(content)
            ok = not m.get('isError') and (m.get('details') or {}).get('status', 'ok') == 'ok' and 'Traceback' not in text
            steps.append({'source': calls.pop(m['toolCallId']), 'ok': ok, 'result': text})
    return steps
