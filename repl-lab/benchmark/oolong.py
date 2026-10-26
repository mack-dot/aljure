"""Prepare identical inputs and score answers outside either agent implementation."""
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

from .vendor.oolong_synth import synth_process_response

PINS = json.loads(Path(__file__).with_name("upstream.lock.json").read_text())
SCORER = Path(__file__).parent / "vendor" / "oolong_synth.py"
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def jsonl(path):
    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line, parse_constant=invalid_constant)


def write_jsonl(path, rows):
    Path(path).write_bytes(b"".join(encoded(row) + b"\n" for row in rows))


def checked_file(root, relative, expected_hash):
    require(isinstance(relative, str) and bool(relative), "Missing artifact path")
    path = (Path(root) / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(Path(root).resolve()),
            "Artifact path escapes its root")
    data = path.read_bytes()
    require(digest(data) == expected_hash, f"Artifact checksum mismatch: {relative}")
    return path


def prepare(raw, output, *, dataset_revision, subset, context_len, count=10, seed=0, fixture=False):
    """Import a local JSONL export. A claimed HF revision does not authenticate its bytes."""
    require(dataset_revision == PINS["oolong_dataset"]["revision"], "Dataset revision differs from lockfile")
    require(type(count) is int and count > 0 and type(context_len) is int and context_len > 0,
            "Count and context length must be positive integers")
    raw = Path(raw)
    raw_hash = digest(raw.read_bytes())
    selected, seen = [], set()
    for row in jsonl(raw):
        if row.get("dataset") != subset or row.get("context_len") != context_len:
            continue
        require(type(row.get("id")) is int and row["id"] not in seen, "Missing or duplicate dataset ID")
        require(type(row.get("context_window_id")) is int, "Missing context window ID")
        for name in ("context_window_text", "question", "answer", "answer_type"):
            require(isinstance(row.get(name), str) and row[name].strip(), f"Missing {name}")
        seen.add(row["id"])
        selected.append(row)
    require(len(selected) >= count, "Not enough matching rows for the requested pilot")
    # Ranking depends on IDs and seed, not export order or any agent score.
    selected.sort(key=lambda row: (digest(encoded([seed, row["id"]])), row["id"]))
    selected = selected[:count]
    # Fail before creating an output if a gold record cannot be read by the pinned scorer.
    for row in selected:
        synth_process_response(row, "", "blinded")
    require(digest(raw.read_bytes()) == raw_hash, "Input export changed during preparation")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "public" / "contexts").mkdir(parents=True)
    (output / "controller").mkdir(mode=0o700)
    tasks, answers = [], []
    for row in selected:
        context = row["context_window_text"].encode("utf-8")
        context_hash = digest(context)
        context_path = f"contexts/{context_hash}.txt"
        (output / "public" / context_path).write_bytes(context)
        task = {"task_id": f"oolong-synth-test-{row['id']}", "question": row["question"],
                "context_path": context_path, "context_sha256": context_hash}
        task["task_sha256"] = digest(encoded(task))
        tasks.append(task)
        # No answer, answer type, label, or scoring metadata enters the public input.
        answers.append({"task_id": task["task_id"], **{key: row[key] for key in
                        ("id", "context_window_id", "dataset", "answer", "answer_type")}})
    write_jsonl(output / "public/tasks.jsonl", tasks)
    write_jsonl(output / "controller/answers.jsonl", answers)
    (output / "controller/answers.jsonl").chmod(0o600)
    manifest = {"schema_version": 1, "suite": "oolong-synth", "dataset": PINS["oolong_dataset"],
                "scorer": PINS["oolong_scorer"], "scorer_sha256": digest(SCORER.read_bytes()),
                "source_export_sha256": raw_hash,
                "input_provenance": "fixture" if fixture else "unverified-local-export",
                "selection": {"dataset": subset, "context_len": context_len, "count": count, "seed": seed},
                "task_ids": [task["task_id"] for task in tasks],
                "files": {name: digest((output / name).read_bytes()) for name in
                          ("public/tasks.jsonl", "controller/answers.jsonl")}}
    manifest["suite_sha256"] = digest(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest) + b"\n")
    return manifest


def read_suite(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    body = {key: value for key, value in manifest.items() if key != "suite_sha256"}
    require(digest(encoded(body)) == manifest["suite_sha256"], "Suite manifest checksum mismatch")
    require(manifest["scorer_sha256"] == digest(SCORER.read_bytes()) and manifest["scorer"] == PINS["oolong_scorer"],
            "Scorer differs from the prepared suite")
    require(manifest["dataset"] == PINS["oolong_dataset"], "Dataset differs from the lockfile")
    for name in ("public/tasks.jsonl", "controller/answers.jsonl"):
        checked_file(root, name, manifest["files"][name])
    tasks = list(jsonl(root / "public/tasks.jsonl"))
    answers = list(jsonl(root / "controller/answers.jsonl"))
    require([row["task_id"] for row in tasks] == manifest["task_ids"] == [row["task_id"] for row in answers],
            "Task lists differ")
    require(len(set(manifest["task_ids"])) == len(tasks) > 0, "Empty or duplicate task list")
    for task in tasks:
        checked_file(root / "public", task["context_path"], task["context_sha256"])
        require(digest(encoded({k: v for k, v in task.items() if k != "task_sha256"})) == task["task_sha256"],
                "Task checksum mismatch")
    return manifest, {t["task_id"]: t for t in tasks}, {a["task_id"]: a for a in answers}


def money(value):
    require(not isinstance(value, bool), "Invalid dollar amount")
    value = Decimal(str(value))
    require(value.is_finite() and value >= 0, "Invalid dollar amount")
    return value


def account(receipts, pricing):
    """Sum unique provider calls. Never accept Prime's parent/child aggregate rows."""
    calls, provider_ids = set(), set()
    known_tokens = dict.fromkeys(TOKEN_FIELDS, 0)
    known_cost, reserved = Decimal(0), Decimal(0)
    unresolved, unpriced = 0, 0
    for receipt in receipts:
        require(receipt.get("kind") == "provider-call", "Usage must contain individual provider calls")
        call_id = receipt.get("call_id")
        require(isinstance(call_id, str) and call_id and call_id not in calls, "Missing or duplicate call ID")
        require(isinstance(receipt.get("session_id"), str) and receipt["session_id"], "Missing session ID")
        calls.add(call_id)
        status = receipt.get("status")
        require(status in ("complete", "unknown"), "Unsupported receipt status")
        if status == "unknown":
            unresolved += 1
            reservation = money(receipt["reserved_usd"])
            require(reservation > 0, "Unknown calls must retain their reservation")
            reserved += reservation
            continue
        provider_id = receipt.get("provider_request_id")
        require(isinstance(provider_id, str) and provider_id and provider_id not in provider_ids,
                "Missing or duplicate provider receipt")
        provider_ids.add(provider_id)
        for field in TOKEN_FIELDS:
            count = receipt.get(field)
            require(type(count) is int and count >= 0, f"Invalid {field}")
            known_tokens[field] += count
        cost, priced = Decimal(0), True
        for field in TOKEN_FIELDS:
            if receipt[field]:
                if field == 'cache_creation_input_tokens' and receipt.get('cache_creation') is not None:
                    creation = receipt['cache_creation']
                    parts = {'ephemeral_5m_input_tokens': 'cache_creation_5m_input_tokens',
                             'ephemeral_1h_input_tokens': 'cache_creation_1h_input_tokens'}
                    require(isinstance(creation, dict) and not set(creation) - set(parts), 'Invalid cache duration fields')
                    require(all(type(creation.get(key, 0)) is int and creation.get(key, 0) >= 0 for key in parts),
                            'Invalid cache duration counts')
                    require(sum(creation.values()) == receipt[field], 'Cache duration counts do not match total')
                    for key, rate_key in parts.items():
                        count = creation.get(key, 0)
                        if count:
                            rate = pricing.get(rate_key)
                            if rate is None:
                                priced = False
                            else:
                                cost += Decimal(count) * money(rate) / Decimal(1000000)
                    continue
                rate = pricing.get(field)
                if rate is None:
                    priced = False
                else:
                    cost += Decimal(receipt[field]) * money(rate) / Decimal(1000000)
        if priced:
            known_cost += cost
        else:
            unpriced += 1
    complete = unresolved == unpriced == 0
    return {"calls": len(calls), "known_tokens": known_tokens, "unknown_calls": unresolved,
            "unpriced_calls": unpriced, "known_model_cost_usd": float(known_cost),
            "reserved_unknown_usd": float(reserved), "accounting_complete": complete,
            "model_cost_usd": float(known_cost) if complete else None}


def compare(suite, results_path):
    manifest, tasks, answers = read_suite(suite)
    results_path = Path(results_path)
    results_hash = digest(results_path.read_bytes())
    results = list(jsonl(results_path))
    indexed, rows, common, fixture = {}, [], None, manifest["input_provenance"] == "fixture"
    harness_revisions, provider_ids = {}, set()
    for result in results:
        key = result["task_id"], result["harness"]
        require(key[0] in tasks and key[1] in ("aljure", "prime") and key not in indexed,
                "Unknown or duplicate task/harness result")
        require(result["suite_sha256"] == manifest["suite_sha256"] and
                result["task_sha256"] == tasks[key[0]]["task_sha256"], "Result used different task inputs")
        require(result.get("provenance") in ("fixture", "recorded-model-run"), "Missing result provenance")
        fixture |= result["provenance"] == "fixture"
        require(result.get("fresh_session") is True, "Pilot requires a fresh session for each task")
        model = result["model_config"]
        require(set(model) == {"provider", "model", "thinking", "temperature", "max_output_tokens"},
                "Explicit, matching model settings are required")
        require(isinstance(model["model"], str) and model["model"], "Missing model")
        require(type(model["max_output_tokens"]) is int and model["max_output_tokens"] > 0,
                "Missing output token limit")
        budget = money(result["budget_usd"])
        require(budget > 0, "Missing positive per-task budget")
        contract = {"model": model, "budget_usd": str(budget.normalize()), "pricing": result["pricing_usd_per_m"]}
        if common is None:
            common = contract
        require(contract == common, "Model settings, pricing, or budgets differ")
        require(isinstance(result.get("harness_revision"), str) and result["harness_revision"], "Missing harness revision")
        previous_revision = harness_revisions.setdefault(key[1], result["harness_revision"])
        require(previous_revision == result["harness_revision"], "Frozen harness changed between pilot tasks")
        status = result["status"]
        require(status in ("completed", "error", "budget_exhausted", "timeout"), "Unsupported result status")
        require(type(result.get("wall_time_ms")) in (int, float) and math.isfinite(result["wall_time_ms"])
                and result["wall_time_ms"] >= 0, "Invalid wall time")
        checked_file(results_path.parent, result["trace_path"], result["trace_sha256"])
        usage_path = checked_file(results_path.parent, result["usage_path"], result["usage_sha256"])
        receipts = list(jsonl(usage_path))
        for receipt in receipts:
            require(receipt.get("model") == model["model"], "Root or child used a different model")
            if receipt.get("status") == "complete":
                provider_id = receipt.get("provider_request_id")
                require(provider_id not in provider_ids, "Provider receipt reused across results")
                provider_ids.add(provider_id)
        usage = account(receipts, result["pricing_usd_per_m"])
        require(status != "completed" or usage["calls"] > 0, "Completed run has no model receipt")
        require(money(usage["known_model_cost_usd"]) + money(usage["reserved_unknown_usd"]) <= budget,
                "Recorded spend and retained reservations exceeded the task budget")
        output = ""
        if status == "completed":
            output = checked_file(results_path.parent, result["answer_path"], result["answer_sha256"]).read_text(encoding="utf-8")
        # The scorer sees no harness name, provider identity, or agent-supplied score.
        scored = synth_process_response(answers[key[0]], output, "blinded") if status == "completed" else {
            "score": 0, "parse_confidence": "not-completed", "attempted_parse": ""}
        row = {"task_id": key[0], "harness": key[1], "status": status, "score": float(scored["score"]),
               "parse_confidence": scored["parse_confidence"], "attempted_parse": scored["attempted_parse"],
               "wall_time_ms": result["wall_time_ms"], "usage": usage}
        indexed[key] = row
        rows.append(row)
    expected = {(task, harness) for task in tasks for harness in ("aljure", "prime")}
    require(set(indexed) == expected, "Every selected task needs both harness outcomes, including failures")
    require(digest(results_path.read_bytes()) == results_hash, "Results changed during scoring")
    rows.sort(key=lambda row: (row["task_id"], row["harness"]))
    deltas = [indexed[task, "aljure"]["score"] - indexed[task, "prime"]["score"] for task in sorted(tasks)]
    return {"schema_version": 1, "suite_sha256": manifest["suite_sha256"], "results_sha256": results_hash,
            "scorer_sha256": manifest["scorer_sha256"], "harness_revisions": harness_revisions, "contract": common,
            "evidence": "offline-fixture" if fixture else "recorded-results-with-unverified-input-export",
            "paid_execution_ready": False, "learning_claim": False,
            "scope": "Descriptive paired pilot; no language superiority or statistical significance claim.",
            "paired_cases": len(tasks), "independent_contexts": len({a["context_window_id"] for a in answers.values()}),
            "mean_score": {h: sum(indexed[t, h]["score"] for t in tasks) / len(tasks) for h in ("aljure", "prime")},
            "mean_paired_difference_aljure_minus_prime": sum(deltas) / len(deltas),
            "wins_ties_losses": [sum(x > 0 for x in deltas), sum(x == 0 for x in deltas), sum(x < 0 for x in deltas)],
            "accounting_complete": all(row["usage"]["accounting_complete"] for row in rows), "cases": rows}
