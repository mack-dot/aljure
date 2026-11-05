"""Context coverage: what share of the records a question concerns reached the model as tool output.

A measurement over public inputs and recorded traces only (the question, the context, and the tool results a
harness returned to its model, root and child sessions). No gold answer is read. Two levels per record:
  seen  the start of the record's text appears in some tool output (the item was displayed, perhaps cut short)
  full  the record's whole text appears in some tool output
The relevant records are all records, or the subset the question's own filter names (a month, user ids). A
before/after date question concerns every record. Coverage says what was displayed, not what was understood.
"""
import glob
import json
import re

RECORD = re.compile(r'^Date: (\w+) (\d+), (\d{4}) \|\| User: (\d+) \|\| Instance: (.*)$')
MONTH = re.compile(r'only consider the subset of instances that occur in (\w+) of any year')
USERS = re.compile(r'only consider the subset of instances that are associated with user IDs ([\d, ]+)')
SEEN_CHARS = 24


def normalize(text):
    return re.sub(r'[^0-9a-z]+', '', str(text or '').lower())


def records(context):
    """[(month, user, instance text)] for every record line of an OOLONG-synth context."""
    out = []
    for line in str(context or '').splitlines():
        m = RECORD.match(line.strip())
        if m:
            out.append((m.group(1), m.group(4), m.group(5)))
    return out


def relevant(question, context):
    """The records the question concerns, by its own filter."""
    rows = records(context)
    month, users = MONTH.search(str(question or '')), USERS.search(str(question or ''))
    if month:
        return [r for r in rows if r[0][:3].lower() == month.group(1)[:3].lower()]
    if users:
        ids = set(re.findall(r'\d+', users.group(1)))
        return [r for r in rows if r[1] in ids]
    return rows


def coverage(question, context, outputs):
    """outputs: the tool-result texts returned to the model. Returns counts and fractions over the relevant records."""
    rows = relevant(question, context)
    seen_text = normalize(' '.join(str(o) for o in outputs))
    seen = full = 0
    for _, _, instance in rows:
        key = normalize(instance)
        if not key:
            continue
        seen += key[:SEEN_CHARS] in seen_text
        full += key in seen_text
    n = len(rows)
    return {'records': len(records(context)), 'relevant': n, 'seen': seen, 'full': full,
            'seen_fraction': seen / n if n else None, 'full_fraction': full / n if n else None,
            'output_chars': sum(len(str(o)) for o in outputs)}


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def aljure_outputs(task_out):
    """Every tool result any session of the arm received (root and children)."""
    path = task_out / 'agent/events.jsonl'
    out = []
    if path.exists():
        for line in path.open(encoding='utf-8', errors='replace'):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'tool-result':
                out.append(_text((event.get('payload') or {}).get('result')))
    return out


def prime_outputs(task_out):
    """Every tool result in the native session logs, root and subagents."""
    out = []
    paths = glob.glob(str(task_out / 'native/sessions/*.jsonl')) + glob.glob(str(task_out / 'native/agent/session-artifacts/*/sub-*/*.jsonl'))
    for path in sorted(paths):
        if path.endswith('semantic-edges.jsonl'):
            continue
        for line in open(path, encoding='utf-8', errors='replace'):
            try:
                message = json.loads(line).get('message') or {}
            except ValueError:
                continue
            if message.get('role') == 'toolResult':
                content = message.get('content')
                out.append(' '.join(b.get('text', '') for b in content if isinstance(b, dict)) if isinstance(content, list) else _text(content))
    return out


def measure(task_out, harness):
    """Coverage of one recorded arm from its own directory (public-input.json and traces)."""
    path = task_out / 'public-input.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    outputs = aljure_outputs(task_out) if harness == 'aljure' else prime_outputs(task_out)
    return coverage(data['task']['question'], data['context'], outputs)
