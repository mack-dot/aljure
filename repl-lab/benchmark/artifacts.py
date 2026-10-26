"""Independent checks of developer-written artifact fixtures. Never a learning score."""
import json
import re
from pathlib import Path

from .oolong import checked_file, digest, require


def verify_rows(rows, inputs):
    require([row["input"] for row in rows] == inputs, "Missing, reordered or substituted fixture cases")
    outcomes = []
    for row in rows:
        # Independent arithmetic oracle; do not trust the stored expected answer.
        value = row["input"]
        expected = value + value + 1
        passed = type(row.get("output")) is int and row["output"] == expected
        require(row.get("expected") == expected and row.get("passed") is passed, "Fixture scoring disagreement")
        outcomes.append(passed)
    return outcomes


def compare_artifacts(run):
    root = Path(run).resolve()
    path = root / "report.json"
    report = json.loads(path.read_text())
    require(report.get("evidence") == "FIXTURE" and report.get("passed") is True, "Expected a passing artifact FIXTURE")
    require(report.get("model-calls") == 0 and report.get("model-created-skill") is False
            and report.get("learning-claim") is False, "Wrong provenance")
    require(len(report["acquisition"]) == len(report["cold"]) == 2, "Missing language arm")
    acquisition = {r["language"]: r for r in report["acquisition"]}
    cold = {r["language"]: r for r in report["cold"]}
    require(set(acquisition) == set(cold) == {"clojure", "python"}, "Incomplete paired fixture")
    checks = {"unapproved-call-denied", "stale-patch-denied", "promoted", "approved-invocation",
              "frozen-task-local-code", "frozen-retention-denied"}
    scores = {}
    for language, arm in acquisition.items():
        require(set(arm["checks"]) == checks and all(v is True for v in arm["checks"].values()), "Artifact gate failed")
        development = arm["development"]
        before = verify_rows(development["old"], [-3, 0, 4])
        after = verify_rows(development["new"], [-3, 0, 4])
        require(development["rule"] == {"objective": "verified-cases", "min-score-improvement": 1}, "Fixture rule changed")
        require(development["approved"] is True and sum(after) - sum(before) >= 1
                and all(not a or b for a, b in zip(before, after)), "Independent development acceptance failed")
        export = arm["export"]
        directory = root / language / "export"
        require({p.name for p in directory.iterdir()} == set(export["files"]) | {"manifest.edn"}, "Export whitelist mismatch")
        for filename, info in export["files"].items():
            require(re.fullmatch(r"[a-f0-9]{64}\.edn", filename), "Invalid exported path")
            artifact = checked_file(root, f"{language}/export/{filename}", info["sha256"])
            require(artifact.stat().st_size == info["bytes"], "Export size mismatch")
        fresh = cold[language]
        retained = verify_rows(fresh["learned"], [-11, -1, 2, 19])
        ablated = verify_rows(fresh["ablation"], [-11, -1, 2, 19])
        require(fresh["passed"] is True and all(retained) and not any(ablated), "Cold fixture failed")
        events = [json.loads(line) for line in (root / language / "cold/events.jsonl").read_text().splitlines()]
        require(any(event["type"] == "artifact-invoked" and event["payload"]["hash"] == fresh["restored-hash"]
                    and event["payload"]["arguments"] == [19] and event["payload"]["value"] == 39 for event in events),
                "Missing actual approved export invocation")
        require(any(event["type"] == "fixture-provider-call" for event in events), "Missing fresh scripted conversation")
        scores[language] = {"retained_correct": sum(retained), "fallback_correct": sum(ablated), "cases": len(retained)}
    return {"evidence": "FIXTURE", "passed": True, "model_calls": 0, "learning_claim": False,
            "cold_boot": scores, "report_sha256": digest(path.read_bytes()), "limitations": report["limitations"]}
