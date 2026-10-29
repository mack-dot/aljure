"""MultiNLI exact-count task (dev window 70016): both harnesses against per-pair gold.
Read-only over recorded traces and the pinned dev shard; no model calls.

The gold labels come from the dataset's label-augmented column, decoded for the dev
window only, and only after checking (metadata columns alone) that none of its row
groups holds a held-out row. Held-out windows are never decoded.

    python3 scripts/multinli_count_analysis.py CLEAN_REPL_LAB OUT_DIR
"""
import json
from pathlib import Path
import re
import sys

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
SHARD = 'var/official-cache/582c630afc2b64f3f48d84925eaf6948c6fe9f035b089e4bdfe10b57f7dd13f8-test-00024-of-00041.parquet'
WINDOW = ('multinli', 70016)
TASK = 'oolong-synth-test-32768-715070023'

# Per-page numbers stated in Aljure Opus's summarized thinking (31-aljure, responses 3-7);
# pages are the (show a b) ranges it executed. Page 2 and 4 follow from the running totals.
ALJURE_OPUS_PAGES = [(0, 80, 20), (80, 165, 27), (165, 250, 25), (250, 340, 20), (340, 438, 28)]
ALJURE_OPUS_PAGE1 = [1, 3, 6, 7, 10, 11, 17, 21, 22, 24, 26, 28, 39, 45, 55, 62, 69, 76, 77, 78]
# Items Aljure Opus called uncertain, and how its summaries say it resolved them.
ALJURE_OPUS_UNCERTAIN = {1: 'C', 9: 'not C', 22: 'C', 45: 'C', 48: 'not C', 64: 'not C', 128: 'leaning C',
                         134: 'not C', 135: 'not C', 152: 'not C', 191: 'C', 195: 'set aside', 199: 'open',
                         220: 'open', 226: 'C', 251: 'left out', 275: 'open', 298: 'left out', 334: 'left out', 354: 'not C'}
# Prime Opus root: python_repl calls C=[36]; C.append(11+22); C.append(28); C.append(32).
PRIME_OPUS_SEGMENTS = [('root', [(0, 110)], 36), ('root', [(110, 146), (219, 220)], 11), ('child nli2', [(146, 219)], 22),
                       ('root', [(220, 330)], 28), ('root', [(330, 438)], 32)]


def heldout_windows():
    lock = json.loads((ROOT / 'benchmark/upstream.lock.json').read_text())
    return {tuple(w) for w in lock['official_profiles']['oolong-synth:independent-heldout:32768']['windows']}


def dev_gold():
    parquet, held = pq.ParquetFile(ROOT / SHARD), heldout_windows()
    for group in range(parquet.num_row_groups):
        meta = parquet.read_row_group(group, columns=['dataset', 'context_len', 'context_window_id']).to_pylist()
        rows = [i for i, r in enumerate(meta) if (r['dataset'], r['context_window_id']) == WINDOW and r['context_len'] == 32768]
        if not rows:
            continue
        # Metadata only up to here: refuse a group that also holds a held-out row.
        if any((r['dataset'], r['context_window_id']) in held for r in meta):
            sys.exit(f'Row group {group} also holds held-out rows; refusing to decode labels')
        text = parquet.read_row_group(group, columns=['context_window_text_with_labels']).take(rows[:1]).to_pylist()[0]
        lines = [x for x in text['context_window_text_with_labels'].splitlines() if x.startswith('Date:')]
        return [re.search(r'Label: (\w+)\s*$', x).group(1) for x in lines]
    sys.exit('Dev window not found')


def expected_score(fn_rate, fp_rate, positives, negatives, trials=400000):
    """Count error and expected 0.75^|error| score when each item errs independently."""
    rng = np.random.default_rng(0)
    error = rng.binomial(negatives, fp_rate, trials) - rng.binomial(positives, fn_rate, trials)
    return {'mean_error': round(float(error.mean()), 2), 'sd': round(float(error.std()), 2),
            'p_exact': round(float((error == 0).mean()), 3), 'expected_score': round(float((0.75 ** np.abs(error)).mean()), 3)}


def main(clean, out):
    gold = dev_gold()
    contradiction = {i for i, label in enumerate(gold) if label == 'contradiction'}
    count = lambda spans: sum(1 for a, b in spans for i in range(a, b) if i in contradiction)
    opus = Path(clean) / 'var/benchmarks/synth-indep-32k-dev-opus'
    child = [line.split('\t') for line in (opus / '30-prime/native/chunks/l2.txt').read_text().splitlines() if line.strip()]
    child = {int(i): label.strip() for i, label in child}
    sonnet_prime = set(json.loads((ROOT / 'research/evidence/multinli-count/sonnet-prime-predicted.json').read_text())['sonnet_prime_predicted'])
    tp1 = set(ALJURE_OPUS_PAGE1) & contradiction
    report = {
        'model_calls': 0, 'task': TASK, 'gold': {'items': len(gold), 'contradiction': len(contradiction),
                                                  'entailment': gold.count('entailment'), 'neutral': gold.count('neutral')},
        'prime_opus_segments': [{'by': by, 'items': spans, 'stated': said, 'gold': count(spans), 'error': said - count(spans)}
                                for by, spans, said in PRIME_OPUS_SEGMENTS],
        'prime_opus_child_items': {'n': len(child), 'accuracy': round(sum(gold[i] == l for i, l in child.items()) / len(child), 3),
                                   'false_positive': sum(1 for i, l in child.items() if l == 'contradiction' and i not in contradiction),
                                   'false_negative': sum(1 for i, l in child.items() if l != 'contradiction' and i in contradiction)},
        'aljure_opus_pages': [{'items': [a, b - 1], 'stated': said, 'gold': count([(a, b)]), 'error': said - count([(a, b)])}
                              for a, b, said in ALJURE_OPUS_PAGES],
        'aljure_opus_page1_items': {'listed': len(ALJURE_OPUS_PAGE1), 'true_positive': len(tp1),
                                    'false_positive': sorted(set(ALJURE_OPUS_PAGE1) - contradiction),
                                    'false_negative': sorted(i for i in contradiction if i < 80 and i not in ALJURE_OPUS_PAGE1)},
        'aljure_opus_uncertain': [{'item': i, 'resolved': how, 'gold': gold[i]} for i, how in sorted(ALJURE_OPUS_UNCERTAIN.items())],
        'sonnet_prime_items': {'predicted': len(sonnet_prime), 'true_positive': len(sonnet_prime & contradiction),
                               'false_positive': len(sonnet_prime - contradiction), 'false_negative': len(contradiction - sonnet_prime)},
        'expected_score_models': {
            'unbiased (Opus child rates: FN 1/22, FP 1/51)': expected_score(1 / 22, 1 / 51, 129, 309),
            'biased (Aljure Opus page 1: FN 4/23, FP 1/57)': expected_score(4 / 23, 1 / 57, 129, 309),
            'biased (Sonnet Prime: FN 22/129, FP 4/309)': expected_score(22 / 129, 4 / 309, 129, 309)},
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'dev-gold-labels.json').write_text(json.dumps({'window': list(WINDOW), 'labels': gold}))
    (out / 'analysis.json').write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
