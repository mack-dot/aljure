"""Step 0 of the thesis test (research/RESEARCH_THESIS_REVIEW.md): do the rules and parsers
that A1c's Aljure arms generated transfer to unseen trec_coarse windows? Each arm's own
recorded code is replayed in the isolated SCI worker against another window's public
text; only the final done expression is replaced so the arm returns one label per item
(the residual analysis's diagnostics). Item gold comes from the pinned validation shard's
label-augmented column and is used offline only. No model calls.

    source var/worker.env && python3 scripts/step0_rule_transfer.py A1C_RUN PARQUET OUT_DIR [--prepare-only]
"""
import glob
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from residual_reasoning_analysis import DIAGNOSTICS, LINE, NAMES  # noqa: E402
from review_replay_ablation import sources  # noqa: E402

A1C_WINDOW = (32768, 0)
# Unexposed validation-split trec_coarse windows (no suite has used them; the sealed
# held-out suite is test-split and holds no trec_coarse window).
TARGETS = [(32768, 1), (65536, 3), (65536, 4)]
UNDECIDED = {'unk', 'ent*'}


def exposed_windows():
    seen = set()
    for path in glob.glob('/Users/mackianni/*/repl-lab/var/official/*/controller/answers.jsonl'):
        if 'heldout' in path:
            continue
        for line in open(path):
            row = json.loads(line)
            seen.add((row['dataset'], row['context_window_id']))
    return seen


def windows(parquet):
    import pyarrow.parquet as pq
    wanted, out = set(TARGETS) | {A1C_WINDOW}, {}
    f = pq.ParquetFile(parquet)
    for group in range(f.num_row_groups):
        meta = f.read_row_group(group, columns=['dataset', 'context_len', 'context_window_id']).to_pylist()
        idx = [i for i, r in enumerate(meta) if r['dataset'] == 'trec_coarse'
               and (r['context_len'], r['context_window_id']) in wanted - set(out)]
        for i in idx:
            r = f.read_row_group(group, columns=['context_len', 'context_window_id', 'context_window_text',
                                                 'context_window_text_with_labels']).take([i]).to_pylist()[0]
            key = (r['context_len'], r['context_window_id'])
            if key in out:
                continue
            items = [m for m in (LINE.match(x) for x in r['context_window_text_with_labels'].splitlines()) if m]
            out[key] = {'public': r['context_window_text'], 'questions': [m[3] for m in items],
                        'gold': [NAMES[m[4]] for m in items]}
    return out


def metrics(pred, gold, new_mask):
    rows = []
    for subset, keep in (('all', [True] * len(gold)), ('new_only', new_mask)):
        p = [x for x, k in zip(pred, keep) if k]
        g = [x for x, k in zip(gold, keep) if k]
        decided = [(a, b) for a, b in zip(p, g) if a not in UNDECIDED]
        per_class = {}
        for cls in sorted(set(NAMES.values())):
            per_class[cls] = {'predicted': sum(a == cls for a, _ in decided),
                              'false_positive': sum(a == cls and b != cls for a, b in decided),
                              'false_negative': sum(b == cls and a != cls for a, b in zip(p, g))}
        rows.append((subset, {'items': len(g), 'decided': len(decided),
                              'coverage': round(len(decided) / len(g), 4) if g else None,
                              'precision': round(sum(a == b for a, b in decided) / len(decided), 4) if decided else None,
                              'default_ent': sum(a == 'ent*' for a in p),
                              'default_ent_precision': round(sum(a == 'ent*' and b == 'ent' for a, b in zip(p, g)) /
                                                             max(1, sum(a == 'ent*' for a in p)), 4),
                              'per_class': per_class}))
    return dict(rows)


def main(a1c_run, parquet, out, prepare_only=False):
    a1c_run, out = Path(a1c_run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    seen = exposed_windows()
    for length, window in TARGETS:
        assert ('trec_coarse', window) not in seen, f'window {window} was exposed by a prepared suite'
    data = windows(parquet)
    a1c_questions = set(data[A1C_WINDOW]['questions'])
    runs = []
    # Control: the override path on A1c's own window must reproduce the recorded diagnostic labels.
    own = out / f'context-{A1C_WINDOW[0]}-{A1C_WINDOW[1]}.txt'
    own.write_text(data[A1C_WINDOW]['public'])
    for arm, (step, expr) in DIAGNOSTICS.items():
        runs.append({'name': f'{arm}@control', 'arm': str(a1c_run / arm),
                     'edits': {str(step): [[sources(a1c_run / arm)[step], expr]]}, 'context': str(own)})
    for length, window in TARGETS:
        ctx = out / f'context-{length}-{window}.txt'
        ctx.write_text(data[(length, window)]['public'])
        for arm, (step, expr) in DIAGNOSTICS.items():
            done = sources(a1c_run / arm)[step]
            runs.append({'name': f'{arm}@{length}-{window}', 'arm': str(a1c_run / arm),
                         'edits': {str(step): [[done, expr]]}, 'context': str(ctx)})
    spec = out / 'step0-spec.json'
    spec.write_text(json.dumps({'out': str(out / 'labels'), 'runs': runs}, indent=1))
    if prepare_only:
        print('prepared', len(runs), 'replays over', TARGETS)
        return
    log = subprocess.run([sys.executable, 'scripts/clj.py', '-m', 'repl-lab.replay', '--spec', str(spec)],
                         capture_output=True, text=True, timeout=3600)
    (out / 'replay.log').write_text(log.stdout + log.stderr)
    statuses = {json.loads(line)['name']: json.loads(line) for line in log.stdout.splitlines() if line.startswith('{')}
    report = {'model_calls': 0, 'a1c_run': str(a1c_run), 'targets': TARGETS, 'arms': list(DIAGNOSTICS), 'windows': {}}
    recorded = Path(__file__).resolve().parent.parent / 'research/evidence/a1c-review-replay/labels'
    report['override_control'] = {
        arm: (out / 'labels' / f'{arm}@control.txt').exists() and (recorded / f'diag-{arm}.txt').exists()
        and (out / 'labels' / f'{arm}@control.txt').read_text() == (recorded / f'diag-{arm}.txt').read_text()
        for arm in DIAGNOSTICS}
    print('override control reproduces recorded labels:', report['override_control'])
    for length, window in TARGETS:
        w = data[(length, window)]
        new_mask = [q not in a1c_questions for q in w['questions']]
        per_arm, votes = {}, [Counter() for _ in w['gold']]
        for arm in DIAGNOSTICS:
            name = f'{arm}@{length}-{window}'
            path = out / 'labels' / f'{name}.txt'
            status = statuses.get(name, {})
            if not path.exists():
                per_arm[arm] = {'applicable': False, 'reason': status.get('error') or 'no answer'}
                continue
            labels = [x.split(',')[0].strip() for x in path.read_text().split('\n')]
            if len(labels) != len(w['gold']):
                per_arm[arm] = {'applicable': False, 'reason': f'{len(labels)} labels for {len(w["gold"])} items',
                                'eval_errors': status.get('errors')}
                continue
            per_arm[arm] = {'applicable': True, 'eval_errors': status.get('errors'), **metrics(labels, w['gold'], new_mask)}
            for i, lab in enumerate(labels):
                if lab not in UNDECIDED:
                    votes[i][lab] += 1
        majority = []
        for c in votes:
            top = c.most_common(2)
            majority.append(top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else 'unk')
        report['windows'][f'{length}-{window}'] = {
            'items': len(w['gold']), 'new_items': sum(new_mask), 'gold_counts': Counter(w['gold']),
            'arms': per_arm, 'majority_vote': metrics(majority, w['gold'], new_mask),
            'conflicted_items': sum(1 for c in votes if len(c) > 1)}
    (out / 'step0-report.json').write_text(json.dumps(report, indent=1))
    for key, wr in report['windows'].items():
        print(key, 'items', wr['items'], 'new', wr['new_items'], 'conflicted', wr['conflicted_items'])
        for arm, m in wr['arms'].items():
            if not m['applicable']:
                print('  ', arm, 'NOT APPLICABLE:', m['reason'][:120])
                continue
            a, n = m['all'], m['new_only']
            print('  ', arm, 'coverage %.3f precision %s | new-only coverage %.3f precision %s' % (a['coverage'], a['precision'], n['coverage'], n['precision']))
        mv = wr['majority_vote']
        print('   VOTE coverage %.3f precision %s | new-only coverage %.3f precision %s' % (mv['all']['coverage'], mv['all']['precision'], mv['new_only']['coverage'], mv['new_only']['precision']))


if __name__ == '__main__':
    main(*sys.argv[1:4], prepare_only='--prepare-only' in sys.argv)
