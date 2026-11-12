"""Equivalence check for a paired run: do both harnesses receive the same task, the same model settings, the same
caps and deadline, and the same output semantics? Read-only over a run directory written by benchmark.headtohead
(pilot 1 or later) plus its plan; no inference.

    python3 -m benchmark.equivalence --out var/h2h-20261104/run-1 [--write research/evidence/.../equivalence.json]

Observed, per task pair: the public input delivered to each arm (sha256 of the identical context and question), and
every provider request's model, max_tokens, thinking and output_config as recorded in the gateway ledger
(gateway-request-intent events, written before dispatch and validated by gateway.clj validate-request!). Declared,
from the frozen plan: calls, dollars and tokens per arm, deadline, request and output bounds, container limits, and
the answer rule in force for each harness."""
import argparse
import json
from pathlib import Path

from .oolong import digest, jsonl

SETTINGS = ('model', 'max_tokens', 'thinking', 'output_config', 'temperature', 'top_p', 'top_k', 'stream')


def requests_of(task_out):
    path = task_out / 'gateway/events.jsonl'
    if not path.exists():
        return []
    out = []
    for e in jsonl(path):
        if e.get('type') == 'gateway-request-intent':
            body = e['payload'].get('input') or {}
            out.append({k: body.get(k) for k in SETTINGS} | {'tools': len(body.get('tools') or []),
                                                               'tools_bytes': len(json.dumps(body.get('tools') or [])),
                                                               'system_bytes': len(json.dumps(body.get('system') or ''))})
    return out


def check(out):
    out = Path(out)
    plan = json.loads((out / 'plan.json').read_text())
    configs = plan['configs']
    config = configs.get('aljure') or next(iter(configs.values()))
    rows = list(jsonl(out / 'results.jsonl'))
    by_item = {}
    for r in rows:
        # A two-harness run labels arms by harness; a multi-arm ablation labels them by arm name.
        by_item.setdefault((r['suite'], r['task_id'], r['trial']), {})[r.get('arm') or r['harness']] = r
    expected = set(plan.get('arms') or {'aljure', 'prime'})
    pairs, mismatches = [], []
    for key, arms in sorted(by_item.items()):
        if set(arms) != expected:
            mismatches.append({'item': key, 'problem': 'missing arm'})
            continue
        inputs, settings = {}, {}
        for h, r in arms.items():
            task_out = out / f"{r['index']:03}-{r['suite']}-{h}"
            data = task_out / 'public-input.json'
            inputs[h] = digest(data.read_bytes()) if data.exists() else None
            reqs = requests_of(task_out)
            settings[h] = {k: sorted({json.dumps(q[k], sort_keys=True) for q in reqs}) for k in SETTINGS} | {'requests': len(reqs)}
        first = next(iter(arms))
        same_input = all(inputs[h] == inputs[first] and inputs[h] is not None for h in arms)
        same_settings = all(settings[h][k] == settings[first][k] for h in arms for k in ('model', 'max_tokens', 'thinking', 'output_config', 'temperature', 'top_p', 'top_k'))
        single_valued = all(len(settings[h][k]) <= 1 for h in settings for k in ('model', 'max_tokens', 'thinking', 'output_config'))
        pairs.append({'item': key, 'same_public_input': same_input, 'same_model_settings': same_settings, 'single_valued_settings': single_valued,
                      'settings': settings, 'input_sha256': inputs})
        if not (same_input and same_settings and single_valued):
            mismatches.append({'item': key, 'problem': 'input or settings differ', 'detail': {'inputs': inputs, 'settings': settings}})
    from .paired import task_limits
    limits = {k: config.get(k) for k in ('calls_per_arm', 'usd_per_arm', 'tokens_per_arm', 'max_output_tokens')} | task_limits(config)
    contract = config.get('aljure_contract') or {}
    return {'run': str(out), 'plan_sha256': plan['plan_sha256'], 'pairs': len(pairs), 'mismatches': mismatches,
            'all_pairs_equivalent': not mismatches,
            'declared_identical_for_both_arms': {**limits, 'model_settings_enforced_by': 'src/repl_lab/gateway.clj validate-request! on every request',
                                                 'context_delivery': 'Prime /work/context.txt; Aljure external-context binding; identical bytes (public-input sha256 per pair above)',
                                                 'container': '256 MiB, 1 CPU, 32 PIDs, no network, read-only root; Aljure controller runs on the host (PRIME_PARITY_MATRIX row 4, disclosed)'},
            'answer_semantics': {'aljure': ('done call or terminal text under ' + str(contract.get('terminal_text_answer'))) if contract.get('terminal_text_answer') else 'done call only',
                                 'prime': '/work/answer.txt' + (' or final assistant text under the identical text-answer-v2 rule' if contract.get('terminal_text_answer') == 'text-answer-v2' else ' only'),
                                 'scorer': 'same official scorer on answer.txt, blind to harness'},
            'disclosed_differences': ['streaming (Prime) against non-streaming (Aljure) requests', 'harness prompt and tool schemas differ by design',
                                      'Prime per-call output truncation against Aljure bounded surface; Aljure 10 s per expression'],
            'example_settings': pairs[0]['settings'] if pairs else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--write')
    args = parser.parse_args(argv)
    report = check(args.out)
    if args.write:
        Path(args.write).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('pairs', 'all_pairs_equivalent', 'mismatches', 'declared_identical_for_both_arms', 'answer_semantics', 'example_settings')}, indent=1))
    return 0 if report['all_pairs_equivalent'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
