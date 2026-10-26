#!/usr/bin/env python3
"""Package recorded controller data. Never infer measurements from UI state."""
import json
from pathlib import Path
import subprocess
import sys


def load_dashboard(run):
    run = Path(run).resolve()
    report = json.loads((run / "report.json").read_text())
    provenance = report["provenance"]
    labels = {"synthetic-fixture": "SYNTHETIC FIXTURE", "recorded-model-run": "RECORDED MODEL RUN"}
    if provenance not in labels:
        raise ValueError("Unsupported recorded provenance")
    report["label"] = labels[provenance]
    report.setdefault("run-id", run.name)
    event_file = run / "events.jsonl"
    events = [json.loads(line) for line in event_file.read_text().splitlines() if line] if event_file.exists() else []
    cases = report.get("raw-cases", report.get("raw-frozen", []) + report.get("raw-evolving", []))
    cases = cases + report.get("raw-ablation", [])
    # Preserve all measured failed cases. No synthesized episodes or scores.
    report["raw-cases"] = cases
    if "conditions" not in report:
        report["conditions"] = {key: report[source] for key, source in
                                 [("retained", "summary"), ("fallback", "ablation")] if source in report}
    decisions = [e["payload"] for e in events if e["type"] == "candidate-decision"]
    for key, status in [("promotion", "approved"), ("rejection", "rejected")]:
        decision = next((d for d in reversed(decisions) if d["status"] == status), None)
        if decision:
            report[key] = decision["evidence"]
    forms = {"before": "Not recorded", "after": "Not recorded"}
    decision = decisions[-1] if decisions else None
    hashes = {"before": decision.get("parent"), "after": decision.get("artifact")} if decision else {}
    if not hashes:
        event = next((e for e in reversed(events) if e["type"] == "workflow-invoked"), None)
        hashes = {"after": event["payload"]["artifact"]} if event else {}
    for key, digest in hashes.items():
        if digest and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            paths = sorted(run.glob("**/artifacts/" + digest + ".edn"))
            if paths:
                forms[key] = paths[0].read_text()
    costs = report.get("costs", {})
    def usage(name):
        item = costs.get(name, {})
        spent = item.get("spent", item)
        reserved = item.get("reserved-unknown", item.get("reserved", {}))
        snapshot = report.get("acquisition-manifest", report.get("manifest", {})) if name == "acquisition" else report.get("manifest", {})
        limits = snapshot.get("config", report.get("config", {})).get("limits", {})
        task_count = (len(report.get("tasks", [])) or snapshot.get("acquisition-design", {}).get("tasks-per-arm", 0) * 2) if name == "acquisition" else len(report.get("raw-frozen", [])) + len(report.get("raw-evolving", []))
        caps = {key: limits[key] * task_count for key in ("calls", "tokens", "usd") if key in limits and task_count}
        return {"calls": spent.get("llm-calls", spent.get("calls")), "tokens": spent.get("tokens"),
                "usd": spent.get("usd"), "reserved": reserved, "caps": caps}
    report["cost-view"] = {"acquisition": usage("acquisition"), "evaluation": usage("evaluation")}
    return {"report": report, "events": events, "forms": forms}


def main():
    payload = load_dashboard(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "--json":
        print(json.dumps(payload))
        return
    dashboard = Path(__file__).resolve().parents[1] / "dashboard"
    if not (dashboard / "node_modules/esbuild").exists():
        sys.exit("Dashboard dependencies missing. Run: cd dashboard && npm ci --ignore-scripts")
    subprocess.run(["npm", "run", "build"], cwd=dashboard, check=True)
    (dashboard / "dist/data.js").write_text("window.REPL_LAB=" + json.dumps(payload).replace("<", "\\u003c") + ";\n")
    print("Open " + str(dashboard / "dist/index.html"))


if __name__ == "__main__":
    main()
