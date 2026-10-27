"""Independent re-scoring of the shared-controller FIXTURE pilot. No inference."""
import json
from pathlib import Path
import subprocess

from .oolong import PINS, checked_file, digest, encoded, require

ROOT = Path(__file__).resolve().parents[1]


def evaluate_case(family, inputs, output):
    if family == "aggregate":
        ready = [r for r in inputs if r["ready"]]
        return output == {"ids": sorted(r["id"] for r in ready), "total": sum(r["weight"] for r in ready)}
    require(family == "transform", "Unknown language fixture family")
    if not isinstance(output, list) or len(output) > len(inputs):
        return False
    for i, node in enumerate(output):
        if (not isinstance(node, dict) or set(node) != {"op", "value"} or node["op"] not in ("add", "mul")
                or type(node["value"]) is not int):
            return False
        if (node["op"] == "add" and node["value"] == 0) or (node["op"] == "mul" and node["value"] == 1):
            return False
        if i and node["op"] == output[i-1]["op"] == "add":
            return False
    # Independent affine interpretation, not the Clojure evaluator's execution loop.
    def affine(nodes):
        scale, offset = 1, 0
        for n in nodes:
            if n["op"] == "add":
                offset += n["value"]
            else:
                scale *= n["value"]
                offset *= n["value"]
        return scale, offset
    return affine(inputs) == affine(output)


def compare_languages(run):
    root = Path(run).resolve()
    report = json.loads((root / "report.json").read_text())
    require(report.get("evidence") == "FIXTURE" and report.get("action") == "pilot", "Expected the explicit FIXTURE pilot")
    require(report.get("model-calls") == 0 and report.get("learning-claim") is False, "Wrong provenance")
    require(report.get("passed") is True, "Pilot gate failed; retain failure evidence, do not report a passing comparison")
    require(len(report.get("evaluator-controls", [])) == 4, "Missing evaluator controls")
    for control in report["evaluator-controls"]:
        good = control["correct"]
        require(good.get("cases") and not good.get("error") and
                all(evaluate_case(control["family"], r["input"], r.get("output")) and not r.get("error") for r in good["cases"]),
                "Known-correct evaluator control failed")
        wrong = control["incorrect"]
        require(wrong.get("cases") and any(not evaluate_case(control["family"], r["input"], r.get("output")) for r in wrong["cases"]),
                "Known-wrong evaluator control did not establish semantic rejection")
        require(control["malformed"].get("error") and control["malformed"]["score"] == 0, "Malformed-program control failed")
    rows = report.get("rows", [])
    require(rows, "No paired results")
    pairs = {}
    for row in rows:
        language, case = row["language"], row["case-id"]
        require(language in ("clojure", "python") and row["evidence"] == "FIXTURE", "Wrong condition")
        require(row.get("controller-checks") and all(v is True for v in row["controller-checks"].values()), "Controller integration check failed")
        require(language not in pairs.setdefault(case, {}), "Duplicate condition/case")
        checked_file(root, row["source-path"], row["source-sha256"])
        trace = checked_file(root, row["trace-path"], row["trace-sha256"])
        events = [json.loads(s) for s in trace.read_text().splitlines()]
        require(any(e["type"] == "fixture-provider-call" for e in events), "Missing scripted agent trace")
        cases = row.get("cases", [])
        score = int(bool(cases) and not row.get("error") and all(evaluate_case(row["family"], r["input"], r.get("output")) and not r.get("error") for r in cases))
        require(score == row["score"], "Independent scorer disagrees with recorded score")
        pairs[case][language] = {"score": score, "task_sha256": row["task-sha256"], "cases": [r["input"] for r in cases]}
    for pair in pairs.values():
        require(set(pair) == {"clojure", "python"}, "Incomplete paired comparison")
        require(pair["clojure"]["task_sha256"] == pair["python"]["task_sha256"], "Different public task")
        require(pair["clojure"]["cases"] == pair["python"]["cases"], "Different evaluator cases")
    scores = {language: sum(pair[language]["score"] for pair in pairs.values()) / len(pairs) for language in ("clojure", "python")}
    return {"evidence": "FIXTURE", "paired_cases": len(pairs), "verified_success": scores,
            "paired_difference": scores["clojure"] - scores["python"], "model_calls": 0,
            "learning_claim": False, "report_sha256": digest((root / "report.json").read_bytes()),
            "limitations": report["limitations"]}


def prime_doctor():
    checkout = ROOT / "var/upstream/prime-agent"
    expected = PINS["prime"]["commit"]
    if not (checkout / ".git").exists():
        return {"ready": False, "model_calls": 0, "reason": "Pinned Prime checkout is missing", "expected_commit": expected}
    def git(*args):
        return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    actual, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    from .prime.container import doctor as native_doctor
    from .prime.isolation import require_tested
    native = native_doctor()
    try:
        isolation = require_tested()
    except (OSError, ValueError, RuntimeError) as error:
        isolation = {"ready": False, "reason": str(error)}
    fixture = {"ready": False, "evidence": "IMPLEMENTED / UNVERIFIED"}
    try:
        from .prime.fixture import source_snapshot
        receipt = json.loads((ROOT / 'var/prime-adapter-proof.json').read_text())
        valid = (receipt.get('passed') is True and receipt.get('image') == native.get('image')
                 and receipt.get('source_files') == source_snapshot()
                 and digest((Path(receipt['run']) / 'report.json').read_bytes()) == receipt.get('report_sha256'))
        fixture = {"ready": valid, "evidence": "FIXTURE" if valid else "STALE FIXTURE RECEIPT", "run": receipt.get('run')}
    except (OSError, ValueError):
        pass
    return {"ready": False, "model_calls": 0, "source_commit": actual, "source_dirty": dirty,
            "source_pin_verified": actual == expected and not dirty,
            "native_image": native, "native_isolation": isolation,
            "fixture_adapter": fixture,
            "reason": "Use paired-preflight for external one/ten-case adapter and gateway readiness; validated native retention export remains unimplemented",
            "kernel_swap": "Not a language-only swap; see research/PRIME_ARCHITECTURE.md"}
