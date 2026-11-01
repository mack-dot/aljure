#!/usr/bin/env python3
"""Program pilot A/B comparison (research/PROGRAMMATIC_EXECUTION.md section 8). Reads recorded runs
only: per-task metrics come from benchmark.service_benchmark.report, which scores answers and final
service state against the suite's sealed answers. No inference, no Docker. Applies the
preregistered GO/NO-GO rule verbatim and prints both JSON and a Markdown summary."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark import service_benchmark as sb  # noqa: E402

OP_HEAVY = ("read", "cond", "bulk", "verify", "fault", "rate")
RULE = {"success_tolerance": 0.05, "effects_tolerance": 0.05, "request_ratio_max": 0.5, "cost_ratio_max": 0.75}


def percentile(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


def mean(values):
    values = [v for v in values if v is not None]
    return (sum(values) / len(values)) if values else None


def summarize(cases):
    """Pooled metrics over a list of per-task cases."""
    n = len(cases)
    if not n:
        return None
    return {"tasks": n,
            "success": mean([c["score"] for c in cases]),
            "effects_correct": sum(1 for c in cases if c.get("state_ok")) / n,
            "unintended_changes": sum(len(c.get("unintended_changes") or []) for c in cases),
            "missing_changes": sum(len(c.get("missing_changes") or []) for c in cases),
            "failures": sum(1 for c in cases if c["status"] != "completed"),
            "model_requests": mean([c["model_requests"] for c in cases]),
            "input_tokens": mean([c["input_tokens"] for c in cases]),
            "cache_read_tokens": mean([c["cache_read_input_tokens"] for c in cases]),
            "output_tokens": mean([c["output_tokens"] for c in cases]),
            "cost_usd": mean([c["cost_usd"] for c in cases]),
            "cost_usd_total": sum(c["cost_usd"] or 0 for c in cases),
            "wall_ms_p50": percentile([c["wall_ms"] for c in cases], 0.5),
            "wall_ms_p95": percentile([c["wall_ms"] for c in cases], 0.95),
            "tool_operations": mean([c["tool_operations"] for c in cases]),
            "operations_failed": mean([c["operations_failed"] for c in cases]),
            "operations_deduplicated": mean([c["operations_deduplicated"] for c in cases]),
            "operations_denied": mean([c["operations_denied"] for c in cases]),
            "programs": mean([c["programs"] for c in cases]),
            "programs_failed": sum(c["programs_failed"] for c in cases),
            "controller_op_ms": mean([c["controller_op_ms"] for c in cases])}


def task_root(run_dir, row):
    """The task directory in the paired layout: the directory holding answer.txt, agent/ and
    gateway/. The suite's pinned scorer module resolves it from the usage path's parent, which in
    the live layout is the gateway/ subdirectory; the scorer file cannot change without changing
    the suite identity (its hash is pinned), so the resolution is corrected here."""
    run_dir = Path(run_dir)
    candidates = []
    if row.get("answer_path"):
        candidates.append((run_dir / row["answer_path"]).parent)
    usage_parent = (run_dir / row["usage_path"]).parent
    candidates += [usage_parent, usage_parent.parent]
    for c in candidates:
        if (c / "agent").is_dir() or (c / "answer.txt").is_file():
            return c
    return usage_parent


def report(run_dir, suite):
    """benchmark.service_benchmark.report with the task directory resolved by task_root."""
    from benchmark.oolong import read_suite, jsonl
    _, _, answers = read_suite(suite)
    run_dir = Path(run_dir)
    cases = []
    for row in jsonl(run_dir / "results.jsonl"):
        if row.get("harness") not in (None, "aljure"):
            continue
        task_dir = task_root(run_dir, row)
        usage = list(jsonl(run_dir / row["usage_path"])) if (run_dir / row["usage_path"]).is_file() else []
        text = (run_dir / row["answer_path"]).read_text() if row.get("answer_path") and (run_dir / row["answer_path"]).is_file() else ""
        answer = answers[row["task_id"]]
        cases.append({"task_id": row["task_id"], "family": answer["family"], "status": row["status"],
                      **sb.task_metrics(task_dir, usage, row.get("pricing_usd_per_m"), answer, text, row.get("wall_time_ms"))})
    return {"tasks": len(cases), "cases": cases}


def load(runs, suite):
    """{arm: {run_name: report}} with every case tagged by arm and run."""
    arms = {}
    for arm, paths in runs.items():
        arms[arm] = {}
        for path in paths:
            value = report(path, suite)
            for case in value["cases"]:
                case["arm"], case["run"] = arm, Path(path).name
            arms[arm][Path(path).name] = value
    return arms


def pooled(arms):
    out = {}
    for arm, reports in arms.items():
        cases = [c for r in reports.values() for c in r["cases"]]
        out[arm] = {"overall": summarize(cases),
                    "op_heavy": summarize([c for c in cases if c["family"] in OP_HEAVY]),
                    "families": {f: summarize([c for c in cases if c["family"] == f]) for f in sb.FAMILIES},
                    "per_run": {run: {"overall": summarize(r["cases"]),
                                      "families": {f: summarize([c for c in r["cases"] if c["family"] == f]) for f in sb.FAMILIES}}
                                for run, r in reports.items()}}
    return out


def paired(arms, a="A", b="B"):
    """B minus A per task, matched by task id within the same run index, averaged; spread = per-run values."""
    runs_a, runs_b = sorted(arms[a]), sorted(arms[b])
    deltas = {f: {"success": [], "effects": [], "requests": [], "cost": [], "wall_ms": []} for f in sb.FAMILIES}
    for ra, rb in zip(runs_a, runs_b):
        ia = {c["task_id"]: c for c in arms[a][ra]["cases"]}
        ib = {c["task_id"]: c for c in arms[b][rb]["cases"]}
        for task, ca in ia.items():
            cb = ib.get(task)
            if not cb:
                continue
            d = deltas[ca["family"]]
            d["success"].append(cb["score"] - ca["score"])
            d["effects"].append(int(bool(cb.get("state_ok"))) - int(bool(ca.get("state_ok"))))
            d["requests"].append(cb["model_requests"] - ca["model_requests"])
            if cb["cost_usd"] is not None and ca["cost_usd"] is not None:
                d["cost"].append(cb["cost_usd"] - ca["cost_usd"])
            if cb["wall_ms"] is not None and ca["wall_ms"] is not None:
                d["wall_ms"].append(cb["wall_ms"] - ca["wall_ms"])
    return {f: {k: {"mean": mean(v), "n": len(v), "min": min(v) if v else None, "max": max(v) if v else None}
                for k, v in d.items()} for f, d in deltas.items()}


def decide(p, a="A", b="B"):
    """The preregistered rule, applied verbatim. Returns the verdict and every checked condition."""
    A, B = p[a], p[b]
    checks = {}
    checks["success_within_tolerance"] = B["overall"]["success"] >= A["overall"]["success"] - RULE["success_tolerance"]
    checks["effects_within_tolerance"] = B["overall"]["effects_correct"] >= A["overall"]["effects_correct"] - RULE["effects_tolerance"]
    checks["requests_halved_on_op_heavy"] = (A["op_heavy"]["model_requests"] or 0) > 0 and \
        B["op_heavy"]["model_requests"] <= RULE["request_ratio_max"] * A["op_heavy"]["model_requests"]
    checks["cost_per_task_ratio_ok"] = A["overall"]["cost_usd"] is not None and B["overall"]["cost_usd"] is not None and \
        B["overall"]["cost_usd"] <= RULE["cost_ratio_max"] * A["overall"]["cost_usd"]
    family_losses = {f: {"success": B["families"][f]["success"] - A["families"][f]["success"],
                         "effects": B["families"][f]["effects_correct"] - A["families"][f]["effects_correct"]}
                     for f in sb.FAMILIES if A["families"][f] and B["families"][f]}
    checks["no_family_loses_more_than_tolerance"] = all(v["success"] >= -RULE["success_tolerance"] and v["effects"] >= -RULE["effects_tolerance"]
                                                        for v in family_losses.values())
    checks["no_more_unintended_changes"] = B["overall"]["unintended_changes"] <= A["overall"]["unintended_changes"]
    # The request reduction must come from the operation-heavy families, not only from direct/auth.
    reduction_op_heavy = (A["op_heavy"]["model_requests"] or 0) - (B["op_heavy"]["model_requests"] or 0)
    checks["reduction_not_only_direct_auth"] = reduction_op_heavy > 0
    go = all(checks.values())
    return {"verdict": "GO" if go else "NO-GO", "checks": checks, "family_differences_B_minus_A": family_losses,
            "ratios": {"requests_op_heavy_B_over_A": (B["op_heavy"]["model_requests"] / A["op_heavy"]["model_requests"]) if A["op_heavy"]["model_requests"] else None,
                       "cost_B_over_A": (B["overall"]["cost_usd"] / A["overall"]["cost_usd"]) if A["overall"]["cost_usd"] else None},
            "rule": RULE}


def fmt(v, digits=2):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def markdown(p, pairs, verdict, arms):
    lines = []
    keys = [("success", "Success"), ("effects_correct", "Effects correct"), ("failures", "Failures (tasks)"),
            ("unintended_changes", "Unintended changes"), ("model_requests", "Model requests / task"),
            ("input_tokens", "Input tokens / task"), ("cache_read_tokens", "Cache-read tokens / task"),
            ("output_tokens", "Output tokens / task"), ("cost_usd", "Cost USD / task"),
            ("cost_usd_total", "Cost USD total"), ("wall_ms_p50", "Latency p50 ms"), ("wall_ms_p95", "Latency p95 ms"),
            ("tool_operations", "Tool operations / task"), ("operations_failed", "Failed operations / task"),
            ("operations_deduplicated", "Deduplicated operations / task"), ("programs", "Programs / task"),
            ("programs_failed", "Programs failed"), ("controller_op_ms", "Controller op ms / task")]
    lines.append("| Metric (pooled, 2 runs) | A direct tools | A per run | B program_run | B per run |")
    lines.append("| --- | --- | --- | --- | --- |")
    for key, label in keys:
        def spread(arm):
            vals = [fmt(r["overall"][key]) for r in p[arm]["per_run"].values()]
            return " / ".join(vals)
        lines.append(f"| {label} | {fmt(p['A']['overall'][key])} | {spread('A')} | {fmt(p['B']['overall'][key])} | {spread('B')} |")
    lines.append("")
    lines.append("| Family | A success | B success | A effects | B effects | A requests | B requests | A cost | B cost | B−A success (min..max) | B−A requests (min..max) |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for f in sb.FAMILIES:
        a, b, d = p["A"]["families"][f], p["B"]["families"][f], pairs[f]
        lines.append(f"| {f} | {fmt(a['success'])} | {fmt(b['success'])} | {fmt(a['effects_correct'])} | {fmt(b['effects_correct'])} | "
                     f"{fmt(a['model_requests'], 1)} | {fmt(b['model_requests'], 1)} | {fmt(a['cost_usd'], 4)} | {fmt(b['cost_usd'], 4)} | "
                     f"{fmt(d['success']['mean'])} ({fmt(d['success']['min'])}..{fmt(d['success']['max'])}) | "
                     f"{fmt(d['requests']['mean'], 1)} ({fmt(d['requests']['min'], 0)}..{fmt(d['requests']['max'], 0)}) |")
    lines.append("")
    lines.append(f"**Verdict: {verdict['verdict']}**")
    for k, v in verdict["checks"].items():
        lines.append(f"- {k}: {'pass' if v else 'FAIL'}")
    r = verdict["ratios"]
    lines.append(f"- requests on op-heavy families, B/A: {fmt(r['requests_op_heavy_B_over_A'])}; cost per task, B/A: {fmt(r['cost_B_over_A'])}")
    failed = [(c["arm"], c["run"], c["task_id"], c["status"]) for rs in arms.values() for rr in rs.values() for c in rr["cases"] if c["status"] != "completed"]
    if failed:
        lines.append("- non-completed tasks: " + "; ".join(f"{a} {r} {t} ({s})" for a, r, t, s in failed))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--a", nargs="+", required=True, type=Path, help="A run directories")
    parser.add_argument("--b", nargs="+", required=True, type=Path, help="B run directories")
    parser.add_argument("--out", type=Path, help="write JSON here")
    args = parser.parse_args()
    arms = load({"A": args.a, "B": args.b}, args.suite)
    p = pooled(arms)
    pairs = paired(arms)
    verdict = decide(p)
    result = {"pooled": p, "paired_B_minus_A_by_family": pairs, "verdict": verdict,
              "runs": {arm: sorted(r) for arm, r in arms.items()}, "model_calls": 0}
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(markdown(p, pairs, verdict, arms))


if __name__ == "__main__":
    main()
