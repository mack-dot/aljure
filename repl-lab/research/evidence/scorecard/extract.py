import json, os, sys, statistics, datetime, glob

WORKTREES = ["aljure","aljure-sonnet-pair-v7","aljure-sonnet-pair-v6","aljure-review-v1","aljure-verify-v1","aljure-thesis-v1","aljure-unblock-v1"]
BASE = "/Users/mackianni"
OUT = "/private/tmp/claude-501/-Users-mackianni-aljure/c38a9871-7faa-4e4f-9fa1-5586b6e02c5c/scratchpad/scorecard"

rows = []
for wt in WORKTREES:
    var = os.path.join(BASE, wt, "repl-lab", "var")
    for root, dirs, files in os.walk(var):
        dirs[:] = [d for d in dirs if "heldout" not in d.lower()]
        if "heldout" in root.lower():
            continue
        if "report.json" in files and "plan.json" in files and "results.jsonl" in files:
            rp = os.path.join(root, "report.json"); pp = os.path.join(root, "plan.json"); rs = os.path.join(root, "results.jsonl")
            try:
                report = json.load(open(rp)); plan = json.load(open(pp))
            except Exception as e:
                rows.append({"run_dir": root, "error": str(e)}); continue
            results = []
            for line in open(rs):
                line=line.strip()
                if line:
                    try: results.append(json.loads(line))
                    except Exception: pass
            cases = report.get("cases", [])
            harnesses = sorted({c.get("harness") for c in cases})
            per = {}
            for h in harnesses:
                cs = [c for c in cases if c.get("harness")==h]
                rr = [r for r in results if r.get("harness")==h]
                scores = [c.get("score") for c in cs if isinstance(c.get("score"),(int,float))]
                completed = sum(1 for c in cs if c.get("status")=="completed")
                costs = [((c.get("usage") or {}).get("model_cost_usd") or 0.0) for c in cs]
                calls = [((c.get("usage") or {}).get("calls") or 0) for c in cs]
                walls = [r.get("wall_time_ms") for r in rr if isinstance(r.get("wall_time_ms"),(int,float))]
                if not walls:
                    walls = [c.get("wall_time_ms") for c in cs if isinstance(c.get("wall_time_ms"),(int,float))]
                per[h] = {
                    "n_cases": len(cs),
                    "mean_score": (sum(scores)/len(scores)) if scores else None,
                    "report_mean_score": (report.get("mean_score") or {}).get(h),
                    "completed": completed,
                    "completion_rate": completed/len(cs) if cs else None,
                    "statuses": {s: sum(1 for c in cs if c.get("status")==s) for s in sorted({c.get("status") for c in cs})},
                    "total_cost_usd": round(sum(costs),4),
                    "total_calls": sum(calls),
                    "median_wall_s": round(statistics.median(walls)/1000,1) if walls else None,
                    "harness_revision": sorted({r.get("harness_revision") for r in rr if r.get("harness_revision")}),
                }
            mt = os.path.getmtime(rp)
            rows.append({
                "run_name": os.path.basename(root),
                "worktree": wt,
                "run_dir": root,
                "files": {"report": rp, "plan": pp, "results": rs},
                "source_commit": (plan.get("source") or {}).get("commit"),
                "source_dirty": (plan.get("source") or {}).get("dirty"),
                "plan_sha256": plan.get("plan_sha256"),
                "suite_sha256": plan.get("suite_sha256"),
                "report_suite_sha256": report.get("suite_sha256"),
                "model": (plan.get("config") or {}).get("model"),
                "campaign_version": (plan.get("config") or {}).get("campaign_version"),
                "evidence": report.get("evidence"),
                "learning_claim": report.get("learning_claim"),
                "harnesses": harnesses,
                "n_tasks": len({c.get("task_id") for c in cases}),
                "n_cases": len(cases),
                "paired_cases": report.get("paired_cases"),
                "mean_paired_diff_aljure_minus_prime": report.get("mean_paired_difference_aljure_minus_prime"),
                "wins_ties_losses": report.get("wins_ties_losses"),
                "harness_revisions": report.get("harness_revisions"),
                "per_harness": per,
                "report_mtime": datetime.datetime.fromtimestamp(mt).isoformat(timespec="minutes"),
            })

rows.sort(key=lambda r: (r.get("suite_sha256") or "", r.get("worktree",""), r.get("run_name","")))
json.dump(rows, open(os.path.join(OUT, "runs_raw.json"), "w"), indent=1)
for r in rows:
    if "error" in r:
        print("ERR", r); continue
    print(f"{(r['suite_sha256'] or '')[:8]} {r['worktree']:22s} {r['run_name']:40s} plan={ (r['plan_sha256'] or '')[:8]} model={r['model']} commit={(r['source_commit'] or '')[:8]} n_tasks={r['n_tasks']} ev={r['evidence']} mtime={r['report_mtime']}")
    for h,v in r["per_harness"].items():
        print(f"    {h:8s} n={v['n_cases']:3d} mean={v['mean_score']} rep={v['report_mean_score']} comp={v['completed']}/{v['n_cases']} cost=${v['total_cost_usd']} calls={v['total_calls']} medwall={v['median_wall_s']}s rev={[x[:8] for x in v['harness_revision']]} st={v['statuses']}")
