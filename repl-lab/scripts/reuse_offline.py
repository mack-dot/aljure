"""Offline seeded-library results for Pilot 1 (research/UNBLOCK_ACQUISITION.md). No model call.

1. Faithfulness: the seeded version, run in a fresh isolated worker on A1c's own window, must
   reproduce arm 08's recorded Step 0 labels exactly: it decides every record the recording
   decided, with the same label, and nothing the recording left to the :ent default. Labels the
   promotion receipt abstained on (rule v2) count as left undecided.
2. Coverage and precision of the seeded version on every Pilot 1 window, on all records and on
   records that neither A1c's window nor the panel held (new records). Spam windows must refuse.
Gold is the suite's controller-only item gold; results hold counts only.

    source var/worker.env && python3 scripts/reuse_offline.py LIBRARY PIN SUITE A1C_LABELS OUT.json
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from benchmark.oolong import digest, encoded, read_suite, require  # noqa: E402

SHORT = {'abb': 'abbreviation', 'num': 'numeric value', 'hum': 'human being', 'loc': 'location',
         'desc': 'description and abstract concept'}
UNDECIDED = '(left to the default)'


def score(library, pin, panel, out_dir):
    path = out_dir / 'offline-panel.json'
    path.write_bytes(encoded(panel))
    request = {'library': str(library), 'pin': pin, 'panel': str(path), 'panel_sha256': digest(path.read_bytes()),
               'assisted': True, 'structured_labels': False, 'seconds': 1500}
    (out_dir / 'offline-request.json').write_bytes(encoded(request))
    env = {k: v for k, v in os.environ.items() if 'API_KEY' not in k and 'TOKEN' not in k}
    done = subprocess.run(['python3', 'scripts/clj.py', '-m', 'repl-lab.acquisition', 'score', str(out_dir / 'offline-request.json')],
                          cwd=ROOT, capture_output=True, timeout=1700, env=env)
    reply = json.loads((done.stdout or b'{}').decode().strip().splitlines()[-1])
    require(done.returncode == 0 and reply.get('model-calls') == 0, f"score failed: {reply.get('error')}")
    return {w['window']: w for w in reply['windows']}


def main(library, pin, suite, a1c_labels, out):
    library, suite, out = ROOT / library, Path(suite), Path(out)
    out_dir = out.parent / (out.stem + '-work')
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest, tasks, _ = read_suite(suite)
    panel = json.loads((suite / 'controller/panel.json').read_text())
    require(digest((suite / 'controller/panel.json').read_bytes()) == manifest['files']['controller/panel.json'], 'Panel changed')
    items = json.loads((suite / 'controller/task-items.json').read_text())
    a1c = next(w for w in panel['windows'] if w['id'] == 'trec_coarse-32768-0')
    receipt = next(r for r in (json.loads(f.read_text()) for f in (library / 'receipts').glob('*.json'))
                   if r.get('decision') == 'approved' and r.get('pin-after') == pin)
    abstained = set((receipt['candidate'].get('abstention') or {}).get('labels', []))
    recorded = [line.split(',')[0].strip() for line in Path(a1c_labels).read_text().split('\n')]
    recorded = [lab if SHORT.get(lab) not in abstained else 'ent*' for lab in recorded]
    require(len(recorded) == len(a1c['items']), 'Recorded labels and A1c window records differ in number')
    windows = [{'id': 'faithfulness', 'question': a1c['question'], 'context': a1c['context'],
                'items': [{'case': f'f-{i}', 'text': item['text'], 'label': SHORT.get(lab, UNDECIDED)}
                          for i, (item, lab) in enumerate(zip(a1c['items'], recorded))]}]
    seen = {i['text'].strip() for w in panel['windows'] for i in w['items']}
    question = {t['context_sha256']: t['question'] for t in tasks.values()}
    for w in items['windows']:
        for subset, keep in (('all', lambda i: True), ('new', lambda i: i['text'].strip() not in seen)):
            chosen = [i for i in w['items'] if keep(i)]
            if chosen:
                windows.append({'id': f"{w['id']}:{subset}", 'question': question[w['context_sha256']],
                                'context': (suite / 'public' / f"contexts/{w['context_sha256']}.txt").read_text(),
                                'items': [{'case': f"{w['id']}:{subset}:{n}", 'text': i['text'], 'label': i['label']}
                                          for n, i in enumerate(chosen)]})
    scored = score(library, pin, {'schema': 'aljure-panel-v1', 'windows': windows}, out_dir)
    f = scored['faithfulness']
    expected = sum(lab in SHORT for lab in recorded)
    report = {'model_calls': 0, 'library_pin': pin, 'suite_sha256': manifest['suite_sha256'], 'abstained': sorted(abstained),
              'faithfulness': {'records': len(recorded), 'recorded_decisions': expected, 'decided': f['decided'],
                               'agreeing': f['correct'],
                               'exact': f['decided'] == expected and f['correct'] == expected},
              'windows': {}}
    for key, w in scored.items():
        if key == 'faithfulness':
            continue
        report['windows'][key] = {'admitted': w['admitted'], 'errors': w['errors'], 'items': w['items'],
                                  'decided': w['decided'], 'correct': w['correct'],
                                  'coverage': round(w['decided'] / w['items'], 4) if w['items'] else None,
                                  'precision': round(w['correct'] / w['decided'], 4) if w['decided'] else None}
    for subset in ('all', 'new'):
        trec = [w for k, w in report['windows'].items() if k.startswith('trec') and k.endswith(subset)]
        n, d, c = (sum(w[x] for w in trec) for x in ('items', 'decided', 'correct'))
        report[f'trec_{subset}'] = {'items': n, 'decided': d, 'correct': c, 'coverage': round(d / n, 4) if n else None,
                                    'precision': round(c / d, 4) if d else None}
    report['spam_refused'] = all(w['admitted'] == 0 and w['decided'] == 0 for k, w in report['windows'].items() if k.startswith('spam'))
    out.write_bytes(encoded(report) + b'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'windows'}, indent=1))
    for k, w in report['windows'].items():
        print(k, w)


if __name__ == '__main__':
    main(*sys.argv[1:6])
