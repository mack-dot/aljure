"""The programmatic-execution development benchmark (research/PROGRAMMATIC_EXECUTION.md, Phase 4):
seeded synthetic service workflows with deterministic expected answers and expected final states.

A suite ("service-sim") is a directory in the official layout: public/tasks.jsonl (each task names
its pinned fixture), public/fixtures/<sha>.json, controller/answers.jsonl (expected answer and
expected final state, controller-only), manifest.json. This file is the suite's scorer, pinned by
its own sha256 in the manifest, so a change here invalidates every suite made before it.

Nothing here calls a model, Docker or the network. No real third-party service exists: every
effect is on the in-memory service the controller seeds from the fixture (src/repl_lab/service_fixture.clj).
"""
import argparse
import json
import math
import random
import re
import statistics
from pathlib import Path

from .oolong import digest, encoded, jsonl, require, write_jsonl

VERSION = "service-sim-v1"
SUITE = "service-sim"
PROVENANCE = "synthetic-service-fixture"
TEAMS = {"u1": "core", "u2": "core", "u3": "web", "u4": "web", "u5": "ops"}
FAMILIES = ("read", "seq", "cond", "bulk", "verify", "fault", "rate", "auth", "direct")
UNSUPPORTED = "unsupported"


# ---- fixtures ---------------------------------------------------------------------------------

def _issues(rng, n):
    issues = {}
    for i in range(1, n + 1):
        issues[f"i{i}"] = {"status": rng.choice(["open", "open", "stale", "closed", "blocked"]),
                           "priority": rng.choice(["low", "medium", "high"]),
                           "assignee": rng.choice(sorted(TEAMS)), "age_days": rng.randint(1, 120),
                           "parent": (f"i{rng.randint(1, i - 1)}" if i > 1 and rng.random() < 0.6 else None)}
    return issues


def _fixture(rng, n, faults=None):
    return {"collections": {"issues": _issues(rng, n),
                            "users": {u: {"name": f"User {u[1]}", "team": team} for u, team in TEAMS.items()}},
            "faults": faults or {}}


def _updated(issues, ids, fields):
    return {i: ({**r, **fields} if i in ids else r) for i, r in issues.items()}


# ---- families: question, expected answer, expected final state, optimum operations ----------------

def _read(rng, n):
    f = _fixture(rng, n)
    issues = f["collections"]["issues"]
    priority, status = rng.choice(["low", "medium", "high"]), rng.choice(["open", "stale"])
    count = sum(1 for r in issues.values() if r["priority"] == priority and r["status"] == status)
    return {"fixture": f, "question": f"How many issues have priority '{priority}' and status '{status}'? Answer with the number.",
            "answer": str(count), "expected_state": f["collections"], "effects_expected": False,
            "optimum_ops": math.ceil(n / 50)}


def _seq(rng, n):
    f = _fixture(rng, n)
    issues = f["collections"]["issues"]
    start = max(issues, key=lambda i: _depth(issues, i))
    chain = [start]
    while issues[chain[-1]]["parent"]:
        chain.append(issues[chain[-1]]["parent"])
    return {"fixture": f, "question": f"Follow the parent links from issue '{start}' to the issue with no parent. Answer with that issue's id.",
            "answer": chain[-1], "expected_state": f["collections"], "effects_expected": False, "optimum_ops": len(chain)}


def _depth(issues, i):
    d = 0
    while issues[i]["parent"]:
        i, d = issues[i]["parent"], d + 1
    return d


def _cond(rng, n):
    f = _fixture(rng, n)
    issues = f["collections"]["issues"]
    team, threshold = rng.choice(["core", "web"]), rng.choice([30, 45, 60])
    members = {u for u, t in TEAMS.items() if t == team}
    targets = {i: r for i, r in issues.items() if r["status"] == "stale" and r["assignee"] in members}
    close = {i for i, r in targets.items() if r["age_days"] > threshold}
    reopen = set(targets) - close
    final = _updated(_updated(issues, close, {"status": "closed"}), reopen, {"status": "open"})
    return {"fixture": f, "question": (f"For every stale issue assigned to a member of team '{team}': close it (status 'closed') if its "
                                       f"age_days is greater than {threshold}, otherwise set its status to 'open'. Answer with the "
                                       "number of issues you closed."),
            "answer": str(len(close)), "expected_state": {**f["collections"], "issues": final}, "effects_expected": True,
            "optimum_ops": 1 + math.ceil(n / 50) + len(targets)}


def _bulk(rng, n, faults=None):
    f = _fixture(rng, n, faults)
    issues = f["collections"]["issues"]
    user, priority = rng.choice(sorted(TEAMS)), "high"
    targets = {i for i, r in issues.items() if r["status"] == "open" and r["assignee"] == user}
    failing = set(f["faults"].get("fail_ids", [])) & targets
    final = _updated(issues, targets - failing, {"priority": priority})
    return {"fixture": f, "targets": sorted(targets), "failing": sorted(failing),
            "question": f"Set priority '{priority}' on every open issue assigned to '{user}'. Answer with the number of issues you updated.",
            "answer": str(len(targets - failing)), "expected_state": {**f["collections"], "issues": final},
            "effects_expected": True, "optimum_ops": math.ceil(n / 50) + len(targets)}


def _verify(rng, n):
    f = _fixture(rng, n)
    issues = f["collections"]["issues"]
    stale = {i for i, r in issues.items() if r["status"] == "stale"}
    final = _updated(issues, stale, {"status": "closed"})
    remaining = sum(1 for r in final.values() if r["status"] != "closed")
    return {"fixture": f, "question": ("Close every stale issue (status 'closed'). Then verify by reading the service again and answer "
                                       "with the number of issues whose status is not 'closed' after your work."),
            "answer": str(remaining), "expected_state": {**f["collections"], "issues": final}, "effects_expected": True,
            "optimum_ops": 2 * math.ceil(n / 50) + len(stale)}


def _fault(rng, n):
    f = _fixture(rng, n)
    issues = f["collections"]["issues"]
    user = rng.choice(sorted(TEAMS))
    targets = sorted(i for i, r in issues.items() if r["status"] == "open" and r["assignee"] == user)
    failing = sorted(rng.sample(targets, min(2, len(targets)))) if targets else []
    f["faults"] = {"fail_ids": failing}
    final = _updated(issues, set(targets) - set(failing), {"priority": "high"})
    return {"fixture": f, "question": (f"Set priority 'high' on every open issue assigned to '{user}'. Some updates may fail with a "
                                       "service error; do not retry a failed id. Answer with the ids you could not update, "
                                       "comma-separated in ascending order, or 'none'."),
            "answer": ", ".join(failing) if failing else "none", "expected_state": {**f["collections"], "issues": final},
            "effects_expected": True, "optimum_ops": math.ceil(n / 50) + len(targets)}


def _rate(rng, n):
    case = _read(rng, n)
    case["fixture"]["faults"] = {"rate_limit_every": 7}
    case["question"] = case["question"] + " The service rate-limits some calls; a rate-limited read may be retried."
    return case


def _auth(rng, n):
    f = _fixture(rng, n)
    return {"fixture": f, "question": ("Delete every closed issue from the service. If the available tools cannot delete, change "
                                       f"nothing and answer exactly '{UNSUPPORTED}'."),
            "answer": UNSUPPORTED, "expected_state": f["collections"], "effects_expected": False, "optimum_ops": 0}


def _direct(rng, n):
    f = _fixture(rng, n)
    a, b = rng.randint(10, 99), rng.randint(10, 99)
    return {"fixture": f, "question": f"No service access is needed for this task. What is {a} times {b}? Answer with the number.",
            "answer": str(a * b), "expected_state": f["collections"], "effects_expected": False, "optimum_ops": 0}


GENERATORS = {"read": _read, "seq": _seq, "cond": _cond, "bulk": _bulk, "verify": _verify, "fault": _fault,
              "rate": _rate, "auth": _auth, "direct": _direct}


def instances(seed, per_family, sizes=(120, 240)):
    """Deterministic workflow instances: per_family of each family, sizes cycling."""
    rows = []
    for family in FAMILIES:
        for k in range(per_family):
            rng = random.Random(f"{VERSION}:{seed}:{family}:{k}")
            n = sizes[k % len(sizes)]
            case = GENERATORS[family](rng, n)
            rows.append({"family": family, "instance": k, "size": n, **case})
    return rows


# ---- suite ------------------------------------------------------------------------------------

def write_suite(output, *, seed, per_family, sizes=(120, 240)):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "public/fixtures").mkdir(parents=True)
    (output / "public/contexts").mkdir()
    (output / "controller").mkdir(mode=0o700)
    tasks, answers = [], []
    for row in instances(seed, per_family, sizes):
        fixture = encoded(row["fixture"])
        fixture_hash = digest(fixture)
        fixture_path = f"fixtures/{fixture_hash}.json"
        (output / "public" / fixture_path).write_bytes(fixture)
        # The public context is a short description of the service; the data is reachable only through tools.
        context = (f"Service collections: issues ({len(row['fixture']['collections']['issues'])} records; fields status, priority, "
                   "assignee, age_days, parent) and users (fields name, team).\n").encode()
        context_hash = digest(context)
        context_path = f"contexts/{context_hash}.txt"
        (output / "public" / context_path).write_bytes(context)
        task_id = f"{SUITE}-{seed}-{row['family']}-{row['instance']}-{row['size']}"
        task = {"task_id": task_id, "question": row["question"], "context_path": context_path, "context_sha256": context_hash,
                "service_fixture_path": fixture_path, "service_fixture_sha256": fixture_hash}
        task["task_sha256"] = digest(encoded(task))
        tasks.append(task)
        answers.append({"task_id": task_id, "family": row["family"], "answer": row["answer"],
                        "initial_state": row["fixture"]["collections"],
                        "expected_state": row["expected_state"], "effects_expected": row["effects_expected"],
                        "optimum_ops": row["optimum_ops"], "answer_type": "exact"})
    write_jsonl(output / "public/tasks.jsonl", tasks)
    write_jsonl(output / "controller/answers.jsonl", answers)
    (output / "controller/answers.jsonl").chmod(0o600)
    scorer_path = Path(__file__)
    manifest = {"schema_version": 1, "suite": SUITE, "dataset": {"generator": "benchmark/service_benchmark.py", "version": VERSION,
                                                                 "seed": seed, "per_family": per_family, "sizes": list(sizes)},
                "scorer": {"path": "benchmark/service_benchmark.py"}, "scorer_sha256": digest(scorer_path.read_bytes()),
                "input_provenance": PROVENANCE, "source_export_sha256": digest(encoded([t["task_id"] for t in tasks])),
                "source_artifacts": [],
                "selection": {"method": VERSION, "families": {f: [t["task_id"] for t in tasks if f"-{f}-" in t["task_id"]] for f in FAMILIES}},
                "task_ids": [t["task_id"] for t in tasks],
                "files": {name: digest((output / name).read_bytes()) for name in ("public/tasks.jsonl", "controller/answers.jsonl")}}
    manifest["suite_sha256"] = digest(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest) + b"\n")
    return manifest


# ---- scoring ----------------------------------------------------------------------------------

def normalize(text):
    text = (text or "").strip()
    if "Answer:" in text:
        text = text.rsplit("Answer:", 1)[1]
    text = text.strip().strip("[]*\"'` ").rstrip(".").strip().lower()
    return re.sub(r"\s+", " ", text)


def score(answer, output_text, state=None):
    """{score, state_ok, unintended_changes, missing_changes}: the answer alone scores the text; the
    state, when given ({collections, calls, log} from service-state.json), scores the effects."""
    result = {"score": 1.0 if normalize(output_text) == normalize(answer["answer"]) else 0.0,
              "parse_confidence": "exact-after-last-answer-marker", "attempted_parse": normalize(output_text)}
    if state is not None:
        expected, actual = answer["expected_state"], state.get("collections", {})
        unintended, missing = [], []
        for name, rows in expected.items():
            for rid, record in rows.items():
                got = actual.get(name, {}).get(rid)
                if got != record:
                    (missing if got == answer_initial(answer, name, rid) else unintended).append(f"{name}/{rid}")
        result.update({"state_ok": not unintended and not missing, "unintended_changes": sorted(unintended),
                       "missing_changes": sorted(missing), "service_calls": state.get("calls")})
    return result


def answer_initial(answer, name, rid):
    return answer.get("initial_state", {}).get(name, {}).get(rid, object())


# ---- report from recorded runs -------------------------------------------------------------------

def _events(path):
    return list(jsonl(path)) if path.is_file() else []


def task_metrics(task_dir, usage_rows, pricing, answer, answer_text, wall_ms):
    from .oolong import account
    events = _events(task_dir / "agent/events.jsonl")
    ops = [e for e in events if e.get("type") == "program-op"]
    programs = [e for e in events if e.get("type") == "program-finished"]
    requests = [e for e in events if e.get("type") == "provider-input"]
    state_path = task_dir / "agent/service-state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else None
    scored = score(answer, answer_text, state)
    decisions = [o["payload"].get("decision") for o in ops]
    statuses = [o["payload"].get("status") for o in ops]
    tokens = {k: sum(int(u.get(k) or 0) for u in usage_rows) for k in ("input_tokens", "output_tokens",
                                                                      "cache_read_input_tokens", "cache_creation_input_tokens")}
    return {**scored, "model_requests": len(requests), "usage_rows": len(usage_rows), **tokens,
            "cost_usd": (account(usage_rows, pricing)["model_cost_usd"] if pricing is not None and usage_rows else None),
            "wall_ms": wall_ms,
            "tool_operations": len(ops), "operations_ok": statuses.count("ok"), "operations_failed": statuses.count("error"),
            "operations_denied": decisions.count("denied"), "operations_deduplicated": decisions.count("deduplicated"),
            "operations_uncertain": decisions.count("uncertain"),
            "effects": sum(1 for o in ops if o["payload"].get("class") == "effect" and o["payload"].get("acted")),
            "programs": len(programs), "programs_failed": sum(1 for p in programs if p["payload"].get("status") != "ok"),
            "direct_operations": sum(1 for o in ops if o["payload"].get("origin") == "direct"),
            "controller_op_ms": sum(float(o["payload"].get("elapsed-ms") or 0) for o in ops),
            "optimum_ops": answer.get("optimum_ops")}


def report(run_dir, suite):
    """Per-task and per-family metrics of one recorded run in the paired layout (results.jsonl rows
    with usage_path, answer_path, wall_time_ms, pricing_usd_per_m). Evidence only; no inference."""
    from .oolong import read_suite
    manifest, tasks, answers = read_suite(suite)
    run_dir = Path(run_dir)
    rows = list(jsonl(run_dir / "results.jsonl"))
    cases = []
    for row in rows:
        if row.get("harness") not in (None, "aljure"):
            continue
        task_dir = run_dir / Path(row["usage_path"]).parent
        usage = list(jsonl(run_dir / row["usage_path"])) if (run_dir / row["usage_path"]).is_file() else []
        text = (run_dir / row["answer_path"]).read_text() if row.get("answer_path") and (run_dir / row["answer_path"]).is_file() else ""
        answer = answers[row["task_id"]]
        cases.append({"task_id": row["task_id"], "family": answer["family"], "status": row["status"],
                      **task_metrics(task_dir, usage, row.get("pricing_usd_per_m"), answer, text, row.get("wall_time_ms"))})
    families = {}
    for family in FAMILIES:
        chosen = [c for c in cases if c["family"] == family]
        if not chosen:
            continue
        def mean(key):
            values = [c[key] for c in chosen if c.get(key) is not None]
            return (sum(values) / len(values)) if values else None
        walls = sorted(c["wall_ms"] for c in chosen if c.get("wall_ms") is not None)
        families[family] = {"tasks": len(chosen), "success": mean("score"),
                            "effects_correct": (sum(1 for c in chosen if c.get("state_ok")) / len(chosen)),
                            "model_requests": mean("model_requests"), "input_tokens": mean("input_tokens"),
                            "output_tokens": mean("output_tokens"), "cost_usd": mean("cost_usd"),
                            "tool_operations": mean("tool_operations"), "operations_failed": mean("operations_failed"),
                            "operations_deduplicated": mean("operations_deduplicated"), "controller_op_ms": mean("controller_op_ms"),
                            "wall_ms_p50": statistics.median(walls) if walls else None,
                            "wall_ms_p95": (walls[min(len(walls) - 1, math.ceil(0.95 * len(walls)) - 1)] if walls else None)}
    return {"suite_sha256": manifest["suite_sha256"], "run": run_dir.name, "tasks": len(cases), "cases": cases, "families": families}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("suite", help="write a seeded suite")
    make.add_argument("--out", required=True)
    make.add_argument("--seed", type=int, required=True)
    make.add_argument("--per-family", type=int, default=2)
    make.add_argument("--sizes", default="120,240")
    rep = sub.add_parser("report", help="metrics of one recorded run")
    rep.add_argument("--run", required=True)
    rep.add_argument("--suite", required=True)
    rep.add_argument("--out")
    args = parser.parse_args(argv)
    if args.command == "suite":
        manifest = write_suite(args.out, seed=args.seed, per_family=args.per_family,
                               sizes=tuple(int(s) for s in args.sizes.split(",")))
        print(json.dumps({"suite_sha256": manifest["suite_sha256"], "tasks": len(manifest["task_ids"])}))
    else:
        value = report(args.run, args.suite)
        text = json.dumps(value, indent=1, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text + "\n")
        print(json.dumps({"tasks": value["tasks"], "families": value["families"]}, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
