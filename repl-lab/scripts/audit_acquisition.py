#!/usr/bin/env python3
"""Read recorded development trajectories. No model, Docker, or held-out access."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def audit(runs):
    runs = Path(runs).resolve()
    files, rows, instructions = {}, [], {}
    for trajectory in sorted(runs.iterdir()):
        if not trajectory.is_dir() or not (trajectory / 'results.jsonl').is_file():
            continue
        for result in read_rows(trajectory / 'results.jsonl'):
            task = trajectory / Path(result['usage_path']).parent.parent
            event_path = task / 'agent/events.jsonl'
            events = read_rows(event_path) if event_path.exists() else []
            proposals = [e['payload'] for e in events if e['type'] == 'artifact-proposal']
            inputs = [e['payload'] for e in events if e['type'] == 'provider-input'
                      and e['payload'].get('session') == 'proposal']
            usage_path = task / 'gateway/usage.jsonl'
            usage = read_rows(usage_path)
            proposal = proposals[0] if proposals else {}
            matched = [u for u in usage if u.get('provider_request_id') == proposal.get('provider-id')]
            responses = []
            for path in sorted((task / 'gateway/transport-bodies').glob('*.body')):
                body = json.loads(path.read_text())
                if body.get('id') == proposal.get('provider-id'):
                    responses.append(body)
                    files[str(path.relative_to(runs))] = sha(path)
            if inputs:
                last = inputs[-1]['appended'][-1]
                instruction = '\n'.join(c.get('content', '') for c in last.get('content', [])
                                        if isinstance(c, dict) and c.get('type') == 'tool_result')
                instructions[hashlib.sha256(instruction.encode()).hexdigest()] = {
                    'mentions_later_tasks': 'later tasks' in instruction,
                    'states_shared_format': 'same record format' in instruction,
                    'optional_no_penalty': 'Optional, one turn, no penalty' in instruction,
                    'answer_already_final': 'It is final' in instruction}
            for path in (event_path, usage_path, task / 'agent/proposal.edn', trajectory / 'results.jsonl'):
                if path.is_file():
                    files[str(path.relative_to(runs))] = sha(path)
            content = [c for response in responses for c in response.get('content', [])]
            rows.append({
                'trajectory': trajectory.name, 'arm': result['arm'], 'task_id': result['task_id'],
                'status': result['status'], 'proposal_inputs': len(inputs),
                'decision': proposal.get('decision', 'not-offered'), 'reason': proposal.get('reason'),
                'matched_receipts': len(matched), 'matched_responses': len(responses),
                'proposal_tools': [c['name'] for c in content if c.get('type') == 'tool_use'],
                'visible_thinking_blocks': sum(c.get('type') == 'thinking' for c in content),
                'output_tokens': sum(u.get('output_tokens', 0) for u in matched),
                'proposal_usd': sum(u.get('estimated_usd', 0) for u in matched),
                'unknown_receipts': sum(u.get('status') == 'unknown' for u in usage)})
    if not rows:
        raise ValueError('No recorded task rows found')
    offered = [r for r in rows if r['proposal_inputs']]
    matched = all(r['proposal_inputs'] == r['matched_receipts'] == r['matched_responses'] == 1 for r in offered)
    report = {
        'schema': 'acquisition-audit-v1', 'evidence': 'RECORDED LIVE DEVELOPMENT RUNS; read-only audit',
        'source_runs': str(runs), 'model_calls_in_audit': 0, 'heldout_access': False,
        'task_runs': len(rows), 'offered_turns': len(offered), 'proposal_receipts_reconciled': matched,
        'decisions': dict(Counter(r['decision'] for r in rows)),
        'by_arm': {arm: {'tasks': len(group), 'offered': sum(bool(r['proposal_inputs']) for r in group),
                         'decisions': dict(Counter(r['decision'] for r in group))}
                   for arm in sorted({r['arm'] for r in rows})
                   for group in [[r for r in rows if r['arm'] == arm]]},
        'offered_tool_calls': dict(Counter(t for r in offered for t in r['proposal_tools'])),
        'proposal_output_tokens': dict(Counter(r['output_tokens'] for r in offered)),
        'visible_thinking_blocks': sum(r['visible_thinking_blocks'] for r in offered),
        'thinking_token_count': None,
        'thinking_limit': 'Absence of visible thinking blocks does not establish absence of internal reasoning.',
        'proposal_usd': sum(r['proposal_usd'] for r in rows),
        'unknown_receipts': sum(r['unknown_receipts'] for r in rows),
        'instruction_variants': instructions, 'tasks': rows, 'source_sha256': files}
    report['sources_unchanged_after_read'] = all(sha(runs / name) == digest for name, digest in files.items())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('tasks', 'source_sha256', 'instruction_variants')}, indent=2))
