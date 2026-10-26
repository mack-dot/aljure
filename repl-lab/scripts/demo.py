#!/usr/bin/env python3
"""Package existing trace data for a local, offline React dashboard."""
import json
from pathlib import Path
import subprocess
import sys

run = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[1]
report = json.loads((run / "report.json").read_text())
events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines() if line]
workflow_event = next((e for e in events if e["type"] == "workflow-invoked"), None)
forms = {"before": "", "after": ""}
# Form text comes from the recorded artifact files, not a UI simulation.
if workflow_event:
    active = workflow_event["payload"]["artifact"]
    forms["after"] = (run / "artifacts" / (active + ".edn")).read_text()
    decision = next((e for e in events if e["type"] == "candidate-decision" and e["payload"]["status"] == "approved"), None)
    if decision:
        forms["before"] = (run / "artifacts" / (decision["payload"]["parent"] + ".edn")).read_text()
dashboard = root / "dashboard"
if not (dashboard / "node_modules/esbuild").exists():
    sys.exit("Dashboard dependencies missing. Run: cd dashboard && npm ci --ignore-scripts")
subprocess.run(["npm", "run", "build"], cwd=dashboard, check=True)
payload = {"report": report, "events": events, "forms": forms}
(dashboard / "dist/data.js").write_text("window.REPL_LAB=" + json.dumps(payload).replace("<", "\\u003c") + ";\n")
print("Open " + str(dashboard / "dist/index.html"))
