"""Six new synthetic development tasks. No download, inference, or held-out input."""
import argparse
import json
from pathlib import Path
import random
import re

from .oolong import digest, encoded, require

VERSION = 'learning-development-v1'
HEADER = ("Routing v1. Classify each Instance as 'hold', 'expedite', or 'retry'. "
          "Apply these rules in order: blocked=yes means hold; otherwise age_minutes>=60 "
          "means expedite; otherwise attempts>=3 means retry; otherwise hold. "
          "The id is an identifier and does not affect the label.")
PARITY = "Parity v1. Labels are 'even' and 'odd'. Classify each Instance by whether code is even or odd."


def score(answer, output):
    match = re.fullmatch(r'\s*Answer:\s*(\d+)\s*', output or '')
    parsed = int(match.group(1)) if match else None
    return {'score': float(parsed == int(answer['answer'])), 'parse_confidence': 'exact-development-count-v1',
            'attempted_parse': parsed}


def bundle():
    """Deterministic disjoint texts AND feature tuples, including the validation panel."""
    rng, used = random.Random(20261102), set()

    def window(name, count, label, parity=False):
        items = []
        for n in range(count):
            if parity:
                code = (20000 if name.startswith('panel') else 10000) + n * 7
                text, gold = f'id={name}-{n} code={code}', 'even' if code % 2 == 0 else 'odd'
            else:
                while True:
                    fields = (rng.choice(('yes', 'no')), rng.randrange(120), rng.randrange(10))
                    if fields not in used:
                        used.add(fields)
                        break
                blocked, age, attempts = fields
                text = f'id={name}-{n} blocked={blocked} age_minutes={age} attempts={attempts}'
                gold = 'hold' if blocked == 'yes' else 'expedite' if age >= 60 else 'retry' if attempts >= 3 else 'hold'
            items.append({'case': f'{name}-{n}', 'text': text, 'label': gold})
        context = '\n'.join([PARITY if parity else HEADER, ''] +
                            [f'Date: Nov 02, 2026 || User: {n} || Instance: {item["text"]}'
                             for n, item in enumerate(items)])
        question = f"In the above data, how many data points should be classified as label '{label}'? Return only Answer: N."
        return {'id': name, 'question': question, 'context': context, 'items': items}

    windows = [window(f'learn-dev-{i}', count, label, i == 6) for i, count, label in
               ((1, 64, 'hold'), (2, 72, 'expedite'), (3, 80, 'retry'),
                (4, 88, 'hold'), (5, 96, 'expedite'), (6, 24, 'even'))]
    panel = {'schema': 'aljure-panel-v1', 'windows': [window('panel-routing', 36, 'hold'),
                                                   window('panel-parity', 12, 'even', True)]}
    files, tasks, answers = {}, [], []
    for w in windows:
        context = w['context'].encode()
        relative = f'contexts/{w["id"]}.txt'
        files['public/' + relative] = context
        task = {'task_id': w['id'], 'question': w['question'], 'context_path': relative,
                'context_sha256': digest(context)}
        task['task_sha256'] = digest(encoded(task))
        tasks.append(task)
        label = w['question'].split("'")[1]
        answers.append({'task_id': w['id'], 'answer': str(sum(i['label'] == label for i in w['items']))})
    files['public/tasks.jsonl'] = b''.join(encoded(t) + b'\n' for t in tasks)
    files['controller/answers.jsonl'] = b''.join(encoded(a) + b'\n' for a in answers)
    files['controller/panel.json'] = encoded(panel) + b'\n'
    files['controller/novelty.json'] = encoded(novelty(windows + panel['windows'])) + b'\n'
    manifest = {'schema_version': 1, 'suite': 'learning-development',
                'dataset': {'generator': 'benchmark/learning_development.py', 'version': VERSION},
                'scorer': {'path': 'benchmark/learning_development.py'},
                'scorer_sha256': digest(Path(__file__).read_bytes()),
                'input_provenance': 'synthetic-development',
                'selection': {'method': VERSION, 'seed': 20261102,
                              'families': {'F1': [w['id'] for w in windows[:5]], 'F2': [windows[5]['id']]}},
                'task_ids': [t['task_id'] for t in tasks],
                'files': {name: digest(data) for name, data in files.items()}}
    manifest['suite_sha256'] = digest(encoded(manifest))
    files['manifest.json'] = encoded(manifest) + b'\n'
    return manifest, files


def novelty(windows):
    seen_text, seen_features = set(), set()
    counts = {}
    for w in windows:
        texts = {i['text'] for i in w['items']}
        features = {re.sub(r'^id=\S+ ', '', t) for t in texts}
        require(len(texts) == len(features) == len(w['items']) and
                not (texts & seen_text) and not (features & seen_features),
                'Development task/panel records overlap, including after identifier removal')
        seen_text |= texts
        seen_features |= features
        counts[w['id']] = len(texts)
    return {'texts_disjoint': True, 'features_disjoint': True, 'records_by_window': counts,
            'meaning': 'New to this live trajectory; synthetic development, not independent held-out evidence.'}


def prepare(output):
    manifest, files = bundle()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        if name.startswith('controller/'):
            path.chmod(0o600)
    return manifest


def verify(root):
    manifest, files = bundle()
    for name, data in files.items():
        path = Path(root) / name
        require(path.is_file() and not path.is_symlink() and path.read_bytes() == data,
                'Synthetic development input differs from frozen generator: ' + name)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out), indent=2))
