"""Scripted proof of the reuse-economics arms through the real gateway, adapter and SCI. Zero inference."""
import argparse
import json
from pathlib import Path
import re

from . import paired
from .gateway_client import GatewayClient
from .oolong import encoded, jsonl, require
from .reuse_economics import CONFIGS, PROOF, ROOT, attribution, files, first_request, prompt_measure, verify_suite, write
from .reuse_interface_fixture import InterfaceScript, tool_results

SIX_CLAUSES = ('(count (filter (fn [l] (when-let [m (re-find #"blocked=(\\w+) age_minutes=(\\d+) attempts=(\\d+)" l)] '
               '(let [b (m 1) a (parse-long (m 2)) t (parse-long (m 3))] (= "{label}" (cond (= b "yes") "hold" (>= a 60) "expedite" '
               '(and (>= a 30) (>= t 3)) "retry" (and (>= a 30) (< t 3)) "hold" (and (< a 30) (>= t 3)) "retry" :else "hold"))))) context-lines))')


def eval_values(events):
    return [e['payload'].get('result', {}).get('value') for e in events
            if e['type'] == 'tool-result' and e['payload'].get('op') == 'repl/eval' and e['payload'].get('status') == 'ok']


def run(suite, out):
    manifest, cases = verify_suite(suite)
    suite, out = Path(suite), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    configs = {name: json.loads((suite / (name + '.json')).read_text()) for name in CONFIGS}
    by_id = {c['task_id']: c for c in cases}
    runtime = paired.runtime_snapshot()
    image = json.loads((ROOT / 'var/isolation-proof.json').read_text())['image']
    require(image == configs['library']['execution_images']['sci'], 'Wrong worker image')
    checks, records, measures, texts = {}, [], {}, {}

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
        texts[name] = json.dumps((first_request(dest) or {}).get('messages', [])).replace('\\"', '"')
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

    def page_of(results, index):
        return results[index]['content'] if not results[index].get('is_error', False) else ''

    # Arm A: the long rule implemented fresh as one six-clause expression returns the gold; no library at all.
    case = by_id['reuse-economics-1']
    public = json.loads((suite / 'public' / (case['task_id'] + '.json')).read_text())
    instance = next(l for l in public['context'].splitlines() if 'Instance: ' in l).split('Instance: ', 1)[1]
    script, events, result, answer = task('A-long-stateless', case['task_id'], 'stateless', [
        ('repl_eval', {'source': SIX_CLAUSES.format(label=case['label'])}),
        ('done', {'summary': 'Answer: ' + case['answer']})])
    checks.update(A_five_tools=measures['A-long-stateless']['tools'] == 5,
                  A_no_inventory=not measures['A-long-stateless']['inventory_in_prompt'],
                  A_no_library_events=result['level'] == 'no-library' and not any(e['type'].startswith('artifact-') for e in events),
                  A_six_clause_expression_returns_gold=eval_values(events) == [int(case['answer'])],
                  A_answer_correct=answer.strip() == 'Answer: ' + case['answer'],
                  long_rule_in_text=public['context'].startswith('Routing v1, full statement.') and '(6) otherwise' in public['context'])

    # Arm B: the same case; the inventory carries the model-authored summary; the retained skill, called once, returns the gold.
    script, events, result, answer = task('B-long-library', case['task_id'], 'library', [
        inspect_first,
        lambda b: ('repl_eval', {'source': count_source(case['label'])}),
        lambda b: ('done', {'summary': 'Answer: ' + case['answer']})])
    results = tool_results(script.bodies[-1])
    counted = [x for x in result['executions'] if x['path'] == 'preloaded' and x['calls'] == case['records'] + 2]
    checks.update(B_seven_tools=measures['B-long-library']['tools'] == 7,
                  B_inventory_with_summary=result['flags']['exposed'] and ':summary "Routing rules' in texts['B-long-library']
                  and ':summary-withheld' not in texts['B-long-library'],
                  B_admitted=result['flags']['admitted'],
                  B_inspection_page_has_summary=':summary "Routing rules' in page_of(results, 0),
                  B_skill_counts_to_gold=len(counted) == 1 and counted[0]['useful'] and eval_values(events) == [int(case['answer'])],
                  B_decision_use=result['level'] == 'used' and result['useful_reuse'],
                  B_answer_correct=answer.strip() == 'Answer: ' + case['answer'])

    # Arm BN: names, hashes and call syntax only; no summary in the inventory or on any page; execution still works.
    script, events, result, answer = task('BN-long-library-names', case['task_id'], 'library-names', [
        inspect_first,
        lambda b: ('artifact_inspect', {'hash': selected['hash'], 'section': 'applicability'}),
        lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': [instance]}),
        lambda b: ('repl_eval', {'source': count_source(case['label'])}),
        lambda b: ('done', {'summary': 'Answer: ' + case['answer']})])
    results = tool_results(script.bodies[-1])
    via_call = [x for x in result['executions'] if x['path'] == 'artifact_call']
    text = texts['BN-long-library-names']
    checks.update(BN_seven_tools=measures['BN-long-library-names']['tools'] == 7,
                  BN_inventory_without_summary=result['flags']['exposed'] and ':summary "' not in text and ':summary-withheld true' in text
                  and 'Summaries are withheld on this task' in text and 'attempts>=3' not in text.split('Routing v1, full statement.')[0],
                  BN_names_hashes_and_call_syntax_shown=':name "route-hold-rules"' in text and selected['hash'] in text
                  and ':call "(route-hold-rules arg1)"' in text,
                  BN_admitted=result['flags']['admitted'],
                  BN_function_page_without_summary=':summary "' not in page_of(results, 0) and ':summary-withheld true' in page_of(results, 0)
                  and ':source "(fn [text]' in page_of(results, 0),
                  BN_applicability_page_without_summary=':section "applicability"' in page_of(results, 1) and ':summary "' not in page_of(results, 1),
                  BN_artifact_call_executes=len(via_call) == 1 and via_call[0]['useful'] and not results[2].get('is_error', False),
                  BN_skill_counts_to_gold=eval_values(events) == [int(case['answer'])],
                  BN_decision_use=result['level'] == 'used' and result['useful_reuse'],
                  BN_answer_correct=answer.strip() == 'Answer: ' + case['answer'],
                  BN_same_tools_smaller_prompt_than_B=measures['BN-long-library-names']['tools_bytes'] == measures['B-long-library']['tools_bytes']
                  and measures['BN-long-library-names']['messages_bytes'] < measures['B-long-library']['messages_bytes'],
                  B_prompt_larger_than_A=measures['B-long-library']['tools_bytes'] > measures['A-long-stateless']['tools_bytes'])

    # Negative controls: parity refuses the artifact in the names-only configuration; the long changed rules admit the
    # artifact, and the retained skill then counts the legacy answer, which the scorer marks wrong.
    parity = by_id['reuse-economics-7']
    script, events, result, answer = task('BN-parity', parity['task_id'], 'library-names', [
        inspect_first,
        lambda b: ('artifact_call', {'hash': selected['hash'], 'arguments': [instance]}),
        ('done', {'summary': 'Answer: ' + parity['answer']})])
    results = tool_results(script.bodies[-1])
    checks.update(parity_refused_not_admitted=not result['flags']['admitted'] and result['flags']['exposed'],
                  parity_inspectable=not results[0].get('is_error', False),
                  parity_call_denied=results[1].get('is_error') is True and not result['flags']['executed'],
                  parity_answer_correct=answer.strip() == 'Answer: ' + parity['answer'])
    changed = by_id['reuse-economics-8']
    script, events, result, answer = task('B-changed-long', changed['task_id'], 'library', [
        inspect_first,
        lambda b: ('repl_eval', {'source': count_source(changed['label'])}),
        lambda b: ('done', {'summary': 'Answer: ' + changed['legacy_answer']})])
    checks.update(changed_rules_admitted=result['flags']['admitted'],
                  changed_rules_skill_counts_legacy_answer=eval_values(events) == [int(changed['legacy_answer'])] and changed['legacy_answer'] != changed['answer'],
                  changed_rules_skill_answer_scored_wrong=answer.strip() != 'Answer: ' + changed['answer'] and result['level'] == 'used')
    require(paired.runtime_snapshot() == runtime, 'Runtime changed during proof')
    proof = {'evidence': 'FIXTURE', 'status': 'PASSED' if all(checks.values()) else 'FAILED', 'model_calls': 0,
             'checks': checks, 'records': records, 'runtime_source': runtime, 'sci_image': image,
             'suite_sha256': manifest['suite_sha256'], 'transport_contract': paired.transport_contract(configs['library'])}
    write(out / 'proof.json', proof)
    require(all(checks.values()), 'Economics fixture checks failed; preserve this attempt')
    PROOF.write_bytes(encoded(proof) + b'\n')
    return {k: v for k, v in proof.items() if k not in ('records', 'runtime_source')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.suite, args.out), indent=2))
