"""Native Prime headless fixture under external isolation. Never live inference."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

from benchmark.language import evaluate_case, compare_languages
from benchmark.oolong import checked_file
from .container import container, execute, regular_files, snapshot
from .isolation import require_tested
from .usage import audit_transcripts

ROOT = Path(__file__).resolve().parents[2]


def source_snapshot():
    files = list(Path(__file__).parent.glob('*.py')) + [Path(__file__).parent / 'Dockerfile',
            Path(__file__).parent / 'default-packages.lock', ROOT / 'benchmark/language.py', ROOT / 'benchmark/oolong.py',
            ROOT / 'scripts/isolation.py', ROOT / 'research/capabilities.json']
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}


def matched_task(aljure_run):
    if not aljure_run:
        raise ValueError('Set --aljure-run to a passing shared-language pilot')
    root = Path(aljure_run).resolve()
    comparison = compare_languages(root)
    report = json.loads((root / 'report.json').read_text())
    rows = [row for row in report['rows'] if row['case-id'] == 'aggregate-0']
    if {row['language'] for row in rows} != {'clojure', 'python'}:
        raise ValueError('Expected both Aljure languages for aggregate-0')
    inputs = None
    evidence = {}
    for row in rows:
        trace = checked_file(root, row['trace-path'], row['trace-sha256'])
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        query = next(event['payload']['result']['records'] for event in events
                     if event['type'] == 'tool-result' and event['payload'].get('op') == 'context/query')
        answer = next(event['payload']['result']['value'] for event in events
                      if event['type'] == 'tool-result' and event['payload'].get('op') == 'repl/eval'
                      and isinstance(event['payload']['result'].get('value'), dict)
                      and set(event['payload']['result']['value']) == {'ids', 'total'})
        if not evaluate_case('aggregate', query, answer) or (inputs is not None and inputs != query):
            raise ValueError('Aljure integration task differs or its permitted-input answer is wrong')
        inputs = query
        evidence[row['language']] = {'answer': answer, 'trace_sha256': row['trace-sha256'],
                                     'task_sha256': row['task-sha256']}
    return inputs, {'run': str(root), 'case_id': 'aggregate-0', 'report_sha256': comparison['report_sha256'], 'arms': evidence}


def recursive_script():
    child_code = ("import json\nfrom pathlib import Path\n"
                  "records = json.loads(Path('/work/child-context.json').read_text())\n"
                  "answer = {'ids': sorted(r['id'] for r in records), 'total': sum(r['weight'] for r in records)}\n"
                  "Path('/work/child-answer.json').write_text(json.dumps(answer))\n"
                  "await agent_message.send(json.dumps(answer), receiver_role='parent')\nprint(answer)")
    parent_code = ("import json\nfrom pathlib import Path\n"
                   "records = json.loads(Path('/work/context.json').read_text())\n"
                   "selected = [r for r in records if r['ready']]\n"
                   "Path('/work/child-context.json').write_text(json.dumps(selected))\n"
                   "child = await rlm.spawn('Aggregate /work/child-context.json into /work/child-answer.json and reply.', name='aggregate')\n"
                   "results = await rlm.collect([child], timeout_ms=60000)\n"
                   "assert results[0].settled\n"
                   "answer = json.loads(Path('/work/child-answer.json').read_text())\n"
                   "Path('/work/answer.json').write_text(json.dumps(answer))\nprint(answer)")
    return {"responses": [{"content": [{"type": "toolCall", "name": "ipython", "arguments": {"code": parent_code}}]},
                           "Fixture child result consumed. Inspect the independently scored file."],
            "repeatLastResponse": True,
            "children": {"aggregate": {"responses": [
                {"content": [{"type": "toolCall", "name": "ipython", "arguments": {"code": child_code}}]},
                "Fixture aggregate written and sent to parent."]}}}


def run_fixture(output, aljure_run, recursive=False):
    check = require_tested()
    context, matched = matched_task(aljure_run)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    # The same aggregate family and independent evaluator used by Aljure's pilot.
    prompt = ("Read the external records in /work/context.json. Write /work/answer.json with exactly "
              "ids (sorted IDs of ready records) and total (sum of their weights). Use the Python REPL. "
              "This is a developer-scripted integration fixture, not an inference experiment.")
    code = ("import json\nfrom pathlib import Path\n"
            "records = json.loads(Path('/work/context.json').read_text())\n"
            "ready = [record for record in records if record['ready']]\n"
            "answer = {'ids': sorted(record['id'] for record in ready), 'total': sum(record['weight'] for record in ready)}\n"
            "Path('/work/answer.json').write_text(json.dumps(answer))\nprint(answer)")
    script = {"responses": [{"content": [{"type": "toolCall", "name": "ipython", "arguments": {"code": code}}]},
                             "Fixture task complete. Inspect the independently scored artifact."]}
    if recursive:
        script = recursive_script()
    request = {"mode": "fixture", "prompt": prompt, "context": context, "script": script}
    bootstrap = (Path(__file__).with_name("bootstrap.py")).read_text()
    started = time.monotonic()
    sources = source_snapshot()
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    manifest = {"evidence": "FIXTURE", "image": check["image"], "prime_commit": check["commit"],
                "aljure_commit": revision, "aljure_dirty": bool(dirty), "source_files": sources,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "context": context,
                "script": script, "limits": check["limits"], "model_calls": 0, "recursive_fixture": recursive,
                "matched_aljure_fixture": matched,
                "usage_type": "Prime faux-provider tokenizer estimates; not measured model usage or billing",
                "limitations": ["Native built-in faux provider; no inference or learning evidence",
                                "Whole-task watchdog; per-expression timeout parity is unverified",
                                "No provider credentials or network; external provider gateway is missing"]}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    report = {"evidence": "FIXTURE", "passed": False, "model_calls": 0, "learning_claim": False,
              "matched_aljure_fixture": matched}
    try:
        with container(check['image'], ['-c', bootstrap], entrypoint='/opt/venv/bin/python') as (name, inspection):
            (root / 'container-inspection.json').write_text(json.dumps(inspection, indent=2))
            result = execute(name, json.dumps(request).encode() + b'\n', completion_type='aljure_fixture_complete')
            (root / 'events.jsonl').write_bytes(result['stdout'])
            (root / 'stderr.log').write_bytes(result['stderr'])
            report.update({k: result[k] for k in ('failure', 'wall_ms')})
            report['attach_exit_code'] = result['exit_code']
            completion = result.get('completion') or {}
            report['native_exit_code'] = completion.get('native_exit_code')
            report['exit_code'] = completion.get('native_exit_code')
            if result['failure'] or completion.get('native_exit_code') != 0:
                raise RuntimeError('Native Prime process failed; inspect preserved stderr/events')
            archive = snapshot(name)
            (root / 'native-state.tar').write_bytes(archive)
            files = regular_files(archive)
            if 'answer.json' not in files:
                raise RuntimeError('Prime did not produce the required answer artifact')
            answer = json.loads(files['answer.json'])
            (root / 'answer.json').write_bytes(files['answer.json'])
            events = [json.loads(line) for line in result['stdout'].splitlines() if line.strip()]
            event_types = sorted({event.get('type', '') for event in events})
            passed = evaluate_case('aggregate', context, answer)
            usage_audit = audit_transcripts(files)
            (root / 'transcript-usage.json').write_text(json.dumps(usage_audit, indent=2))
            if recursive:
                selected = json.loads(files['child-context.json'])
                child_answer = json.loads(files['child-answer.json'])
                parent_rows = [json.loads(line) for path, data in files.items()
                               if path.startswith('sessions/') and path.endswith('.jsonl')
                               for line in data.splitlines() if line.strip()]
                delivered = [row for row in parent_rows if row.get('customType') == 'agent_message'
                             and json.dumps(answer) in str(row.get('content', ''))]
                if (selected != [record for record in context if record['ready']] or child_answer != answer
                        or len(usage_audit['sessions']) < 2 or not delivered
                        or len({row['session_id'] for row in usage_audit['assistant_rows']}) < 2):
                    raise RuntimeError('Native child context, result, or usage evidence is incomplete')
                # Pinned print_runtime/faux.rs explicitly sets rlm_usage_store:
                # None. Do not claim that this scripted path tested native
                # aggregate attribution or the real provider's billing path.
                report['recursive_checks'] = {'selected_context': True, 'child_result': True,
                    'parent_consumed_child': True, 'child_message_delivered': True,
                    'root_and_child_transcripts': True, 'native_billing_attribution_verified': False}
            # Final assistant prose is never the correctness oracle.
            report.update(passed=passed, answer=answer, event_types=event_types, transcript_usage=usage_audit,
                          native_files={p: {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
                                        for p, body in files.items()},
                          usage_evidence=[event for event in events
                                          if event.get('type') == 'message_end' and event.get('message', {}).get('role') == 'assistant'])
            if not passed:
                raise RuntimeError('Independent aggregate evaluator rejected the native answer')
            if sources != source_snapshot():
                raise RuntimeError('Adapter or evaluator source changed during the fixture')
            report['trace_sha256'] = hashlib.sha256(result['stdout']).hexdigest()
            report['native_state_sha256'] = hashlib.sha256(archive).hexdigest()
    except Exception as error:
        report['error'] = str(error)
        report['passed'] = False
        raise
    finally:
        report['total_wall_ms'] = (time.monotonic() - started) * 1000
        (root / 'report.json').write_text(json.dumps(report, indent=2))
    receipt = {'evidence': 'FIXTURE', 'passed': True, 'image': check['image'], 'source_files': sources,
               'run': str(root.resolve()), 'report_sha256': hashlib.sha256((root / 'report.json').read_bytes()).hexdigest(),
               'model_calls': 0}
    (ROOT / 'var/prime-adapter-proof.json').write_text(json.dumps(receipt, indent=2))
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--aljure-run', required=True)
    parser.add_argument('--recursive', action='store_true', help='Exercise a native child, message, collect and usage attribution')
    args = parser.parse_args()
    value = run_fixture(args.out, args.aljure_run, args.recursive)
    print(json.dumps({key: value[key] for key in ('evidence', 'passed', 'model_calls', 'answer')}))
