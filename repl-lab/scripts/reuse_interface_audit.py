#!/usr/bin/env python3
"""Extract observable evidence from the frozen development run. No inference or edits to inputs."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit(root, output):
    root, output = Path(root), Path(output)
    index = json.loads((root / 'index.json').read_text())
    for name, expected in index['files'].items():
        assert sha((root / name).read_bytes()) == expected, name
    output.mkdir(parents=True, exist_ok=False)
    result = {'evidence': 'FROZEN LIVE OBSERVATIONS; NO NEW INFERENCE',
              'source_commit': 'e6d17fee98bb40ad9119ca0f3b15533f5b76ad67',
              'verified_files': len(index['files']), 'index_sha256': sha((root / 'index.json').read_bytes()),
              'model_calls': 0, 'tasks': []}
    for position in (3, 4, 5):
        task = root / f'runs/ES-s101/{position:02}-aljure'
        gateway = [json.loads(line) for line in (task / 'gateway/events.jsonl').read_text().splitlines()]
        inputs = [e['payload']['input'] for e in gateway if e['type'] == 'gateway-request-intent']
        events = [json.loads(line) for line in (task / 'agent/events.jsonl').read_text().splitlines()]
        # The first request has no assistant response. Do not extract private reasoning.
        first = inputs[0]
        (output / f'task-{position}-first-request.json').write_text(json.dumps(first, indent=2) + '\n')
        observations = [e for e in events if e['type'] in ('tool-call', 'tool-result', 'artifact-library-loaded',
                        'artifact-applicability', 'artifact-preloaded', 'artifact-invocations', 'artifact-reuse-summary')]
        (output / f'task-{position}-observations.json').write_text(json.dumps(observations, indent=2) + '\n')
        errors = []
        for body in inputs:
            for message in body['messages']:
                if isinstance(message['content'], list):
                    for block in message['content']:
                        if block.get('type') == 'tool_result' and block.get('is_error'):
                            if block not in errors:
                                errors.append(block)
        result['tasks'].append({'position': position, 'tool_names': [t['name'] for t in first['tools']],
                                'requests': len(inputs), 'model_visible_errors': errors,
                                'artifact_invocation_events': sum(e['type'] == 'artifact-invocations' for e in events),
                                'tool_calls': [e['payload']['command'] for e in observations if e['type'] == 'tool-call']})
    result['files'] = {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return {k: v for k, v in result.items() if k != 'tasks'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.evidence, args.out), indent=2))
