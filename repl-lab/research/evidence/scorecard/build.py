import json, os, statistics, datetime, glob, collections

WORKTREES = ["aljure","aljure-sonnet-pair-v7","aljure-sonnet-pair-v6","aljure-review-v1","aljure-verify-v1","aljure-thesis-v1","aljure-unblock-v1"]
BASE = "/Users/mackianni"
OUT = "/private/tmp/claude-501/-Users-mackianni-aljure/c38a9871-7faa-4e4f-9fa1-5586b6e02c5c/scratchpad/scorecard"

SUITES = {
 "e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded": ("oolong-pairs 8K, 1 task (validation case 1; one context)", "pairs-F1"),
 "90f719a5": ("oolong-pairs 8K, 10 tasks (one context)", "pairs-F1"),
 "e4f4e52a": ("oolong-pairs 32K, 10 tasks (one context)", "pairs-F1"),
 "456f6acf": ("oolong-synth 1-task Opus smoke (negation 415040016)", "synth"),
 "b157ee63": ("oolong-synth 32K dev, 7 independent contexts, 21 tasks", "synth"),
 "dc164044": ("oolong-synth label counts dev, 5 windows, 11 tasks", "synth"),
 "7b23fbbb": ("thesis-pilot trajectory suite, 18 tasks (14 F1 trec_coarse + 4 F2 spam)", "synth"),
 "806c5b2b": ("reuse-pilot (Pilot 1), 27 tasks (21 F1 trec_coarse + 6 F2 spam)", "synth"),
}
def suite_name(s):
    for k,v in SUITES.items():
        if s and s.startswith(k[:8]): return v[0]
    return "UNVERIFIED suite"

def first_time(run_dir):
    # earliest time_unix_ms in any arm's gateway/transport.jsonl
    ts=[]
    for f in sorted(glob.glob(os.path.join(run_dir,"*","gateway","transport.jsonl")))[:3]:
        try:
            for line in open(f):
                d=json.loads(line)
                if "time_unix_ms" in d:
                    ts.append(d["time_unix_ms"]); break
        except Exception: pass
    if ts:
        return datetime.datetime.fromtimestamp(min(ts)/1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%MZ"), "gateway/transport.jsonl time_unix_ms"
    return None, None

rows = []
for wt in WORKTREES:
    var = os.path.join(BASE, wt, "repl-lab", "var")
    for root, dirs, files in os.walk(var):
        dirs[:] = [d for d in dirs if "heldout" not in d.lower() and d not in ("relay-fixture","gateway")]
        if "heldout" in root.lower() or "relay-fixture" in root or "fixture" in os.path.basename(root):
            continue
        if not ("report.json" in files and "plan.json" in files and "results.jsonl" in files):
            continue
        rp = os.path.join(root, "report.json"); pp = os.path.join(root, "plan.json"); rs = os.path.join(root, "results.jsonl")
        report = json.load(open(rp)); plan = json.load(open(pp))
        if report.get("evidence") != "LIVE MODEL RUN":
            continue
        results = [json.loads(l) for l in open(rs) if l.strip()]
        cases = report.get("cases", [])
        harnesses = sorted({c.get("harness") for c in cases})
        per = {}
        for h in harnesses:
            cs = [c for c in cases if c.get("harness")==h]
            rr = [r for r in results if r.get("harness")==h]
            scores = [c.get("score") for c in cs if isinstance(c.get("score"),(int,float))]
            completed = sum(1 for c in cs if c.get("status")=="completed")
            u = [c.get("usage") or {} for c in cs]
            walls = [r.get("wall_time_ms") for r in rr if isinstance(r.get("wall_time_ms"),(int,float))]
            walls_completed = [r.get("wall_time_ms") for r in rr if isinstance(r.get("wall_time_ms"),(int,float)) and r.get("status")=="completed"]
            per[h] = {
                "n_cases": len(cs),
                "mean_score": round(sum(scores)/len(scores),4) if scores else None,
                "report_mean_score": (report.get("mean_score") or {}).get(h),
                "completed": completed,
                "completion_rate": round(completed/len(cs),3) if cs else None,
                "statuses": {s: sum(1 for c in cs if c.get("status")==s) for s in sorted({str(c.get("status")) for c in cs})},
                "total_model_cost_usd": round(sum((x.get("model_cost_usd") or 0.0) for x in u),4),
                "total_known_model_cost_usd": round(sum((x.get("known_model_cost_usd") or 0.0) for x in u),4),
                "total_reserved_unknown_usd": round(sum((x.get("reserved_unknown_usd") or 0.0) for x in u),4),
                "unknown_calls": sum((x.get("unknown_calls") or 0) for x in u),
                "total_calls": sum((x.get("calls") or 0) for x in u),
                "median_wall_s_all_cases": round(statistics.median(walls)/1000,1) if walls else None,
                "median_wall_s_completed": round(statistics.median(walls_completed)/1000,1) if walls_completed else None,
                "total_wall_s": round(sum(walls)/1000) if walls else None,
                "harness_revision": sorted({r.get("harness_revision") for r in rr if r.get("harness_revision")}),
            }
        date, date_src = first_time(root)
        rows.append({
            "run_name": os.path.basename(root),
            "worktree": wt,
            "run_dir": root,
            "source_files": {"report": rp, "plan": pp, "results": rs, "date": (os.path.join(root,"<arm>",date_src) if date_src else "report.json mtime")},
            "source_commit": (plan.get("source") or {}).get("commit"),
            "source_dirty": (plan.get("source") or {}).get("dirty"),
            "plan_sha256": plan.get("plan_sha256"),
            "suite_sha256": plan.get("suite_sha256"),
            "suite": suite_name(plan.get("suite_sha256")),
            "report_suite_matches_plan": report.get("suite_sha256")==plan.get("suite_sha256"),
            "model": (plan.get("config") or {}).get("model"),
            "campaign_version": (plan.get("config") or {}).get("campaign_version"),
            "evidence": report.get("evidence"),
            "accounting_complete": report.get("accounting_complete"),
            "learning_claim": report.get("learning_claim"),
            "harnesses": harnesses,
            "n_tasks": len({c.get("task_id") for c in cases}),
            "n_cases": len(cases),
            "paired_cases": report.get("paired_cases"),
            "mean_paired_diff_aljure_minus_prime": report.get("mean_paired_difference_aljure_minus_prime"),
            "wins_ties_losses": report.get("wins_ties_losses"),
            "harness_revisions": report.get("harness_revisions"),
            "per_harness": per,
            "date_utc": date or datetime.datetime.fromtimestamp(os.path.getmtime(rp)).strftime("%Y-%m-%d %H:%M local(mtime)"),
        })

# dedupe: identical (plan, run_name) in several worktrees -> keep the non-"aljure" copy, note duplicates
groups = collections.defaultdict(list)
for r in rows: groups[(r["plan_sha256"], r["run_name"])].append(r)
final = []
for k, v in groups.items():
    v.sort(key=lambda r: (r["worktree"]=="aljure", r["worktree"]))
    keep = v[0]
    keep["duplicate_copies"] = [x["run_dir"] for x in v[1:]]
    keep["duplicates_identical"] = len({json.dumps(x["per_harness"], sort_keys=True) for x in v})==1
    final.append(keep)
final.sort(key=lambda r: (r["suite_sha256"], r["date_utc"]))
json.dump(final, open(os.path.join(OUT,"scorecard.json"),"w"), indent=1)

# markdown tables per suite
def f(x, nd=3):
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x,float) else str(x))
md = []
by_suite = collections.OrderedDict()
for r in final: by_suite.setdefault(r["suite_sha256"], []).append(r)
for s, rs in by_suite.items():
    md.append(f"\n### Suite `{s[:8]}` — {suite_name(s)}\n")
    md.append("| Run | Worktree | Commit | Plan | Model | Arm | n | Mean score | Completed | Cost $ (model) | Reserved/unknown $ | Calls | Median wall s (all / completed) | Date (UTC) |")
    md.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rs:
        for h, p in r["per_harness"].items():
            md.append(f"| {r['run_name']} | {r['worktree']} | `{(r['source_commit'] or '')[:8]}` | `{(r['plan_sha256'] or '')[:8]}` | {r['model']} | {h} | {p['n_cases']} | {f(p['mean_score'])} | {p['completed']}/{p['n_cases']} | {f(p['total_model_cost_usd'],4)} | {f(p['total_reserved_unknown_usd'],2)} ({p['unknown_calls']} unk) | {p['total_calls']} | {f(p['median_wall_s_all_cases'],1)} / {f(p['median_wall_s_completed'],1)} | {r['date_utc']} |")
    # repeated plans
    plans = collections.defaultdict(list)
    for r in rs: plans[r["plan_sha256"]].append(r)
    for ph, prs in plans.items():
        if len(prs) > 1:
            md.append(f"\nPlan `{ph[:8]}` ran {len(prs)} times ({', '.join(x['run_name'] for x in prs)}):")
            for h in prs[0]["per_harness"]:
                ms = [x["per_harness"][h]["mean_score"] for x in prs]
                cs = [x["per_harness"][h]["total_model_cost_usd"] for x in prs]
                md.append(f"- {h}: mean score per run {', '.join(f(m) for m in ms)}; min–max {f(min(ms))}–{f(max(ms))}, range {f(max(ms)-min(ms))}, SD {f(statistics.stdev(ms)) if len(ms)>1 else '—'}; cost per run {', '.join(f(c,3) for c in cs)}")
open(os.path.join(OUT,"tables.md"),"w").write("\n".join(md))
print("\n".join(md))
print("\nrows:", len(final))
