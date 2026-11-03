"""Scripted proof of the causal protocol's four arms through the real gateway, adapter and SCI. Zero inference."""
import argparse
import json
from pathlib import Path
import re

from . import paired
from .gateway_client import GatewayClient
from .oolong import encoded, jsonl, require
from .relay_fixture import call, response
from .reuse_causal import ARMS, PROOF, ROOT, attribution, files, first_request, prompt_measure, verify_suite, write
from .reuse_interface_fixture import InterfaceScript, tool_results


def run(suite, out):
    manifest, cases = verify_suite(suite)
    suite, out = Path(suite), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    configs = {name: json.loads((suite / (name + '.json')).read_text()) for name in ('stateless', 'library')}
    by_id = {c['task_id']: c for c in cases}
    runtime = paired.runtime_snapshot()
    image = json.loads((ROOT / 'var/isolation-proof.json').read_text())['image']
    require(image == configs['library']['execution_images']['sci'], 'Wrong worker image')
    checks, records, measures = {}, [], {}

    def task(name, task_id, configuration, steps):
        dest = out / name
        dest.mkdir()
        data = json.loads((suite / 'public' / (task_id + '.json')).read_text())
        script = InterfaceScript(configs[configuration], steps)
        gateway = GatewayClient(dest / 'gateway', paired.gateway_config(configs[configuration], 'aljure'), script, evidence='FIXTURE')
        try:
            execution = paired.run_arm('aljure', data, dest, configs[configuration], gateway, {})
        finally:
            gateway.close()
        require(execution.get('completion') and (dest / 'answer.txt').exists(), 'Fixture task failed: ' + name)
        events = list(jsonl(dest / 'agent/events.jsonl'))
        cleanup = json.loads((dest / 'gateway/cleanup.json').read_text())
        require(cleanup['ok'] and not paired.worker_isolation_refused(dest), 'Fixture cleanup/isolation failed')
        answer = (dest / 'answer.txt').read_text()
        result = attribution(events, answer, data['task']['question'], first_request(dest))
        measures[name] = prompt_measure(dest)
        records.append({'name': name, 'attribution': result, 'prompt': measures[name], 'answer': answer, 'files': files(dest)})
        return script, events, result, answer

    selected = {}
    def inspect_first(body):
        text = json.dumps(body['messages']).replace('\\"', '"')
        hashes, names = re.findall(r':hash "([0-9a-f]{64})"', text), re.findall(r':name "([a-zA-Z0-9?!_-]+)"', text)
        require(hashes and names, 'No approved artifact inventory')
        selected.update(hash=hashes[0], name=names[0])
        return 'artifact_inspect', {'hash': selected['hash']}

    def count_source(label):
        return '(count (filter #(= "' + label + '" (' + selected['name'] + ' %)) context-lines))'

    # Arm A: stateless, five tools, no inventory. Run 3's first action, a subs past the text's end, is now
    # bounded by the prelude (Q-SUBSTRATE Phase 3) and returns the text instead of a range error.
    ab = by_id['reuse-causal-1']
    script, events, result, answer = task('A-full-information', ab['task_id'], 'stateless', [
        ('repl_eval', {'source': '(subs (apply str (interpose "\\n" (take 15 context-lines))) 0 3000)'}),
        ('repl_eval', {'source': '(count (filter (fn [l] (when-let [m (re-find #"blocked=(\\w+) age_minutes=(\\d+) attempts=(\\d+)" l)] '
                                  '(and (= "no" (m 1)) (< (parse-long (m 2)) 60) (>= (parse-long (m 3)) 3)))) context-lines))'}),
        ('done', {'summary': 'Answer: ' + ab['answer']})])
    results = tool_results(script.bodies[-1])
    checks.update(A_five_tools=measures['A-full-information']['tools'] == 5,
                  A_no_inventory=not measures['A-full-information']['inventory_in_prompt'],
                  A_no_library_events=result['level'] == 'no-library' and not any(e['type'].startswith('artifact-') for e in events),
                  A_answer_correct=answer.strip() == 'Answer: ' + ab['answer'],
                  run3_first_action_subs_now_bounded=not results[0].get('is_error', False) and isinstance(results[0]['content'], str)
                  and 0 < len(results[0]['content']) <= 3000 and results[0]['content'].startswith('Routing v1.'))

    # Arm B: same case, library admitted, inventory shown; probe (nil), inspect, then a counted computation that returns the answer.
    record = ab['input'] if 'input' in ab else None
    script, events, result, answer = task('B-library', ab['task_id'], 'library', [
        inspect_first,
        lambda b: ('repl_eval', {'source': '(' + selected['name'] + ' (first context-lines))'}),
        lambda b: ('repl_eval', {'source': count_source(ab['label'])}),
        lambda b: ('done', {'summary': 'Answer: ' + ab['answer']})])
    results = tool_results(script.bodies[-1])
    nil_probe = [x for x in result['executions'] if x['path'] == 'preloaded' and x['calls'] == 1]
    # context-lines holds the header and blank line too: those two calls return nil and are counted apart.
    counted = [x for x in result['executions'] if x['path'] == 'preloaded' and x['calls'] == ab['records'] + 2]
    checks.update(B_seven_tools=measures['B-library']['tools'] == 7,
                  B_inventory_shown=measures['B-library']['inventory_in_prompt'] and result['flags']['exposed'],
                  B_admitted=result['flags']['admitted'],
                  B_inspection_counted=len(result['inspections']) == 1 and not results[0].get('is_error', False),
                  B_nil_probe_executed_not_useful=len(nil_probe) == 1 and nil_probe[0]['nils'] == 1 and not nil_probe[0]['useful'],
                  B_counted_execution_useful=len(counted) == 1 and counted[0]['useful'] and counted[0]['nils'] == 2 and counted[0]['returns'] == ab['records'] + 2,
                  B_decision_use=result['level'] == 'used' and result['useful_reuse'],
                  B_answer_correct=answer.strip() == 'Answer: ' + ab['answer'],
                  B_prompt_larger_than_A=(measures['B-library']['tools_bytes'] > measures['A-full-information']['tools_bytes'] and
                                          measures['B-library']['messages_bytes'] > measures['A-full-information']['messages_bytes']))

    # Arm C: the withheld case admits the artifact through the unchanged predicate; artifact_call and the
    # preloaded name both execute; a wrong delivered number is not decision use.
    c = by_id['reuse-causal-6']
    line = next(l for l in c['input']['context'].splitlines() if 'Instance: ' in l) if 'input' in c else None
    public = json.loads((suite / 'public' / (c['task_id'] + '.json')).read_text())
    instance = next(l for l in public['context'].splitlines() if 'Instance: ' in l).split('Instance: ', 1)[1]
    script, events, result, answer = task('C-withheld-library', c['task_id'], 'library', [
        inspect_first,
        lambda b: ('artifact_inspect', {'hash': selected['hash'], 'section': 'applicability'}),
        lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': [instance]}),
        lambda b: ('repl_eval', {'source': count_source(c['label'])}),
        ('done', {'summary': 'Answer: 0'})])
    results = tool_results(script.bodies[-1])
    via_call = [x for x in result['executions'] if x['path'] == 'artifact_call']
    checks.update(C_withheld_text_lacks_rule='attempts>=3' not in public['context'],
                  C_admitted_by_unchanged_predicate=result['flags']['admitted'] and any(
                      e['type'] == 'artifact-applicability' and e['payload']['decision'] == 'preload' for e in events),
                  C_applicability_inspectable=not results[1].get('is_error', False) and ':section "applicability"' in results[1]['content'],
                  C_artifact_call_executes=len(via_call) == 1 and via_call[0]['useful'] and not results[2].get('is_error', False),
                  C_wrong_number_is_not_decision_use=result['flags']['useful'] and not result['useful_reuse'] and result['level'] == 'useful',
                  C_answer_scored_wrong=answer.strip() != 'Answer: ' + c['answer'])

    # Arm C0: the withheld text with no library; an inline guess of "no third rule" is wrong by construction.
    script, events, result, answer = task('C0-withheld-stateless', c['task_id'], 'stateless', [
        ('repl_eval', {'source': '(count (filter (fn [l] (when-let [m (re-find #"blocked=(\\w+) age_minutes=(\\d+)" l)] '
                                  '(and (= "no" (m 1)) (< (parse-long (m 2)) 60)))) context-lines))'}),
        ('done', {'summary': 'Answer: ' + c['without_rule_answers'][-1]})])
    checks.update(C0_no_library=result['level'] == 'no-library' and measures['C0-withheld-stateless']['tools'] == 5,
                  C0_guess_without_rule_is_wrong=answer.strip() != 'Answer: ' + c['answer'])

    # Negative controls in the library configuration: parity refuses execution; changed rules admit but inspection alone counts nothing.
    parity = by_id['reuse-causal-9']
    script, events, result, answer = task('C-parity-library', parity['task_id'], 'library', [
        inspect_first,
        lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': [instance]}),
        ('done', {'summary': 'Answer: ' + parity['answer']})])
    results = tool_results(script.bodies[-1])
    checks.update(parity_refused_not_admitted=not result['flags']['admitted'] and result['flags']['exposed'],
                  parity_inspectable=not results[0].get('is_error', False),
                  parity_call_denied=results[1].get('is_error') is True and not result['flags']['executed'])
    changed = by_id['reuse-causal-10']
    script, events, result, answer = task('C-changed-rules-library', changed['task_id'], 'library', [
        inspect_first,
        ('done', {'summary': 'Answer: ' + changed['answer']})])
    checks.update(changed_rules_admitted=result['flags']['admitted'],
                  changed_rules_inspection_alone_is_not_reuse=result['level'] == 'inspected' and not result['flags']['executed'])
    require(paired.runtime_snapshot() == runtime, 'Runtime changed during proof')
    proof = {'evidence': 'FIXTURE', 'status': 'PASSED' if all(checks.values()) else 'FAILED', 'model_calls': 0,
             'checks': checks, 'records': records, 'runtime_source': runtime, 'sci_image': image,
             'suite_sha256': manifest['suite_sha256'], 'transport_contract': paired.transport_contract(configs['library'])}
    write(out / 'proof.json', proof)
    require(all(checks.values()), 'Causal fixture checks failed; preserve this attempt')
    PROOF.write_bytes(encoded(proof) + b'\n')
    return {k: v for k, v in proof.items() if k not in ('records', 'runtime_source')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.suite, args.out), indent=2))
