"""Scripted interface proof through the real gateway, external adapter and SCI. Zero inference."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from . import paired
from .gateway_client import GatewayClient
from .oolong import digest, encoded, jsonl, require
from .relay_fixture import ALJURE_TOOLS, Script, call, response
from .reuse_interface import HISTORY, ROOT, files, observations, verify_suite, write


class InterfaceScript(Script):
    def __init__(self, config, steps):
        super().__init__('aljure', provider=config['provider'], config=config)
        self.steps, self.bodies = steps, []

    def __call__(self, body, _):
        expected = ALJURE_TOOLS + (['artifact_inspect', 'artifact_call'] if self.config['aljure_contract'].get('skill_interface') else [])
        require([t['name'] for t in body['tools']] == expected, 'Wrong external tool inventory')
        # Reuse the existing strict append-only history and signed-thinking checks.
        self.check_aljure_tools({**body, 'tools': body['tools'][:5]}, 'root')
        self.bodies.append(body)
        require(len(self.bodies) <= len(self.steps), 'Unexpected fixture request')
        step = self.steps[len(self.bodies) - 1]
        if callable(step):
            step = step(body)
        return response(call(step[0], **step[1]), body['model'], signed=True)


def original_input(position):
    path = HISTORY / f'runs/ES-s101/{position:02}-aljure/gateway/events.jsonl'
    return next(e['payload']['input'] for e in jsonl(path) if e['type'] == 'gateway-request-intent')


def tool_results(body):
    return [b for m in body['messages'] if isinstance(m['content'], list) for b in m['content'] if b['type'] == 'tool_result']


def run(suite, out):
    manifest, _ = verify_suite(suite)
    suite, out = Path(suite), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    configs = {arm: json.loads((suite / (arm + '.json')).read_text()) for arm in ('baseline', 'repaired')}
    checks, records = {}, []
    runtime = paired.runtime_snapshot()
    image = json.loads((ROOT / 'var/isolation-proof.json').read_text())['image']
    require(image == configs['baseline']['execution_images']['sci'], 'Wrong worker image')

    def task(name, data, arm, steps):
        dest = out / name
        dest.mkdir()
        script = InterfaceScript(configs[arm], steps)
        with GatewayClient(dest / 'gateway', paired.gateway_config(configs[arm], 'aljure'), script,
                           evidence='FIXTURE') as gateway:
            execution = paired.run_arm('aljure', data, dest, configs[arm], gateway, {})
        require(execution.get('completion') and (dest / 'answer.txt').exists(), 'Fixture task failed: ' + name)
        events = list(jsonl(dest / 'agent/events.jsonl'))
        cleanup = json.loads((dest / 'gateway/cleanup.json').read_text())
        require(cleanup['ok'] and not paired.worker_isolation_refused(dest), 'Fixture cleanup/isolation failed')
        records.append({'name': name, 'observation': observations(events), 'files': files(dest)})
        return script, events

    for position in (3, 4, 5):
        prior = HISTORY / f'runs/ES-s101/{position:02}-aljure'
        commands = [e['payload']['command'] for e in jsonl(prior / 'agent/events.jsonl') if e['type'] == 'tool-call']
        steps = [('repl_eval', {'source': c['source']}) if c['op'] == 'repl/eval' else ('done', {'summary': c['summary']}) for c in commands]
        script, events = task(f'baseline-{position}', json.loads((prior / 'public-input.json').read_text()), 'baseline', steps)
        # Compare the full provider request, not just the five tool names.
        actual = next(e['payload']['input'] for e in jsonl(out / f'baseline-{position}/gateway/events.jsonl') if e['type'] == 'gateway-request-intent')
        checks[f'baseline_first_request_{position}_byte_content_equal'] = actual == original_input(position)
        require(checks[f'baseline_first_request_{position}_byte_content_equal'], 'Baseline provider request changed')
        checks[f'baseline_no_invocations_{position}'] = not observations(events)['source_attributed_invocation']

    # Identity is read from the inventory, never hardcoded in the adapter or fixture.
    selected = {}
    def inspect_first(body):
        root_task = json.dumps(body['messages'][0])
        # Inventory is an EDN string in the user message; the only artifact hash there is the verified export.
        hashes = re.findall(r':hash "([0-9a-f]{64})"', json.dumps(body['messages']).replace('\\"', '"'))
        require(hashes, 'No approved artifact inventory')
        selected['hash'] = hashes[0]
        names = re.findall(r':name "([a-zA-Z0-9?!_-]+)"', json.dumps(body['messages']).replace('\\"', '"'))
        require(names, 'No export name')
        selected['name'] = names[0]
        return 'artifact_inspect', {'hash': selected['hash']}

    data = json.loads((suite / 'public/reuse-dev-1.json').read_text())
    record = data['context'].split('Instance: ', 1)[1].splitlines()[0]
    steps = [inspect_first,
             lambda b: ('artifact_inspect', {'hash': selected['hash'], 'section': 'applicability'}),
             lambda b: ('repl_eval', {'source': '(source ' + selected['name'] + ')'}),
             lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': [record]}),
             lambda b: ('repl_eval', {'source': '(' + selected['name'] + ' ' + json.dumps(record) + ')'}),
             ('repl_eval', {'source': '(slurp "/etc/passwd")'}),
             ('artifact_inspect', {'hash': '../../etc/passwd'}),
             ('artifact_call', {'hash': '0' * 64, 'arguments': [record]}),
             lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': []}),
             ('done', {'summary': 'fixture complete'})]
    script, events = task('repaired-cold-process', data, 'repaired', steps)
    observation = observations(events)
    results = tool_results(script.bodies[-1])
    checks.update(inspection_reads_source=':source ' in results[0]['content'],
                  inspection_reads_applicability=':section "applicability"' in results[1]['content'],
                  inspection_receipt=':candidate-panel' in results[0]['content'],
                  source_error_points_to_supported_route='artifact_inspect' in results[2]['content'],
                  explicit_call_succeeds=not results[3].get('is_error', False),
                  preloaded_call_succeeds=not results[4].get('is_error', False),
                  filesystem_denied=results[5].get('is_error') is True,
                  invalid_inspection_denied=results[6].get('is_error') is True,
                  unapproved_invocation_denied=results[7].get('is_error') is True,
                  wrong_arity_denied=results[8].get('is_error') is True,
                  both_invocation_paths_attributed={c['path'] for c in observation['invocations']} == {'artifact_call', 'preloaded'},
                  inspection_did_not_count_as_reuse=sum(c['calls'] for c in observation['invocations']) == 2)
    negative = json.loads((suite / 'public/reuse-dev-4.json').read_text())
    script, events = task('inapplicable-cold-process', negative, 'repaired', [
        ('artifact_inspect', {'hash': selected['hash']}),
        ('artifact_call', {'hash': selected['hash'], 'arguments': [record]}),
        ('done', {'summary': 'negative fixture complete'})])
    results = tool_results(script.bodies[-1])
    checks.update(inapplicable_approved_inspectable=not results[0].get('is_error', False),
                  inapplicable_invocation_denied=results[1].get('is_error') is True,
                  negative_no_invocation=not observations(events)['source_attributed_invocation'])
    changed = json.loads((suite / 'public/reuse-dev-5.json').read_text())
    script, events = task('changed-rules-cold-process', changed, 'repaired', [
        ('artifact_inspect', {'hash': selected['hash'], 'section': 'applicability'}),
        ('done', {'summary': 'changed-rules fixture complete'})])
    checks['changed_rules_are_admitted_despite_semantic_mismatch'] = any(
        e['type'] == 'artifact-applicability' and e['payload']['decision'] == 'preload' for e in events)
    checks['inspection_alone_never_counts'] = not observations(events)['source_attributed_invocation']
    for kind in ('corrupt', 'missing', 'quarantined', 'unknown'):
        dest = out / ('adversarial-' + kind)
        dest.mkdir()
        library = dest / 'library'
        shutil.copytree(suite / 'library', library)
        config = json.loads(json.dumps(configs['repaired']))
        config['aljure_contract']['artifacts']['library'] = str(library.relative_to(ROOT))
        target = library / 'artifacts' / (selected['hash'] + '.edn')
        if kind == 'corrupt':
            target.write_text(target.read_text() + 'CORRUPT')
        elif kind == 'missing':
            target.rename(target.with_suffix('.missing'))
        else:
            spec = config['aljure_contract']['artifacts']
            code = ("(require '[repl-lab.skills :as s]) (println (s/set-status! " + json.dumps(str(library)) + ' ' +
                    json.dumps(spec['library_sha256']) + ' ' + json.dumps(selected['hash']) + ' :' + kind + ')) (shutdown-agents)')
            spec['library_sha256'] = subprocess.check_output(['python3', 'scripts/clj.py', '-e', code], cwd=ROOT, text=True).strip()
        steps = [] if kind in ('corrupt', 'missing') else [('artifact_inspect', {'hash': selected['hash']}),
                    ('artifact_call', {'hash': selected['hash'], 'arguments': [record]}), ('done', {'summary': 'denied'})]
        script = InterfaceScript(config, steps)
        with GatewayClient(dest / 'gateway', paired.gateway_config(config, 'aljure'), script, evidence='FIXTURE') as gateway:
            paired.run_arm('aljure', data, dest, config, gateway, {})
        if kind in ('corrupt', 'missing'):
            checks[kind + '_library_fails_before_provider'] = not script.bodies and not (dest / 'answer.txt').exists()
        else:
            errors = tool_results(script.bodies[-1])
            checks[kind + '_inspection_and_call_denied'] = len(errors) == 2 and all(r.get('is_error') for r in errors)
        require(json.loads((dest / 'gateway/cleanup.json').read_text())['ok'], 'Adversarial cleanup failed')
        records.append({'name': 'adversarial-' + kind, 'files': files(dest)})
    require(paired.runtime_snapshot() == runtime, 'Runtime changed during proof')
    proof = {'evidence': 'FIXTURE', 'status': 'PASSED' if all(checks.values()) else 'FAILED',
             'model_calls': 0, 'checks': checks, 'records': records, 'runtime_source': runtime,
             'sci_image': image, 'suite_sha256': manifest['suite_sha256'],
             'transport_contract': paired.transport_contract(configs['baseline'])}
    write(out / 'proof.json', proof)
    require(all(checks.values()), 'Interface checks failed; preserve this attempt')
    (ROOT / 'var/reuse-interface-proof.json').write_bytes(encoded(proof) + b'\n')
    return {k: v for k, v in proof.items() if k not in ('records', 'runtime_source')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.suite, args.out), indent=2))
