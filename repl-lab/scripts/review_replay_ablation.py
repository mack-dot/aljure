"""Zero-inference replay ablation of recorded review labels in A1c Aljure arms.

Control replays each arm's recorded commands unchanged in a fresh isolated SCI
worker and must reproduce the recorded answer and official F1. Ablations replay
the same commands with the review output withheld, by exact source edits taken
from the recorded commands. No model is called.

    source var/worker.env && python3 scripts/review_replay_ablation.py RUN_DIR OUT_DIR
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from benchmark.official import score_answer  # noqa: E402


def records(path):
    text, decoder, at, out = Path(path).read_text(), json.JSONDecoder(), 0, []
    while at < len(text):
        while at < len(text) and text[at].isspace():
            at += 1
        if at < len(text):
            value, at = decoder.raw_decode(text, at)
            out.append(value)
    return out


def sources(arm):
    return [e["payload"]["command"].get("source") for e in records(arm / "agent/events.jsonl")
            if e["type"] == "tool-call"]


def form(source, start):
    """The complete form that opens at source[start] ('('), skipping strings and regexes."""
    assert source[start] == "(", (start, source[start:start + 20])
    depth, at, in_string = 0, start, False
    while at < len(source):
        ch = source[at]
        if in_string:
            if ch == "\\":
                at += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[start:at + 1]
        at += 1
    raise ValueError("unbalanced form")


def def_form(source, name):
    head = f"(def {name} "
    assert source.count(head) == 1, (name, source.count(head))
    return form(source, source.index(head))


def literal(source, opener, prefix):
    """A set or vector literal that starts with prefix; it must be unique."""
    assert source.count(prefix) == 1, (prefix, source.count(prefix))
    start, close = source.index(prefix), {"#{": "}", "[": "]"}[opener]
    return source[start:source.index(close, start) + 1]


def ablations(run):
    """Per case: (arm, {step: [[old, new], ...]}, what is withheld). Steps count all recorded calls."""
    out = {}
    s = sources(run / "03-aljure")[5]  # case 2: user-level removals and additions after review
    out["case2-ablation"] = ("03-aljure", {5: [[def_form(s, "no"), "(def no #{})"],
                                               [literal(s, "[", '["14922"'), "[]"]]},
                             "26 removed and 5 added users from review")
    s = sources(run / "08-aljure")[8]  # case 5: entity/numeric item labels from review
    out["case5-ablation"] = ("08-aljure", {8: [[def_form(s, "final"),
                                                "(def final (for [r recs2] (assoc r :f (:l r))))"]]},
                             "review labels; final label = rule label")
    out["case5-withheld-literal"] = ("08-aljure", {8: [[literal(s, "#{", "#{11 21 30"), "#{}"],
                                                       [literal(s, "#{", "#{2 23 101"), "#{}"],
                                                       ["(if (= 470 (:i r)) :other :num)", ":num"]]},
                                     "review sets emptied; computation unchanged")
    s = sources(run / "12-aljure")[5]  # case 7: rules rewritten after reading 228 questions
    out["case7-ablation"] = ("12-aljure", {5: [[def_form(s, name), ""] for name in ("abbr?", "num?", "desc?")]},
                             "rule rewrite after review; step-4 rules kept")
    return out


def main(run, out):
    run, out = Path(run).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    arms = sorted(p.name for p in run.iterdir() if p.name.endswith("-aljure"))
    runs = [{"name": f"control-{a}", "arm": str(run / a), "edits": {}} for a in arms]
    plan = ablations(run)
    runs += [{"name": name, "arm": str(run / arm), "edits": {str(k): v for k, v in edits.items()}}
             for name, (arm, edits, _) in plan.items()]
    spec = out / "spec.json"
    spec.write_text(json.dumps({"out": str(out / "answers"), "runs": runs}, indent=1))
    log = subprocess.run([sys.executable, "scripts/clj.py", "-m", "repl-lab.replay", "--spec", str(spec)],
                         capture_output=True, text=True, timeout=1800)
    (out / "replay.log").write_text(log.stdout + log.stderr)
    status = {}
    for line in log.stdout.splitlines():
        if line.startswith("{"):
            r = json.loads(line)
            status[r["name"]] = r
    gold = {a["task_id"]: a for a in records(run.parent.parent / "official/pairs32-ten/controller/answers.jsonl")}
    rows = []
    for r in runs:
        arm = Path(r["arm"])
        task = json.loads((arm / "trace.json").read_text())["case"]["task_id"]
        recorded = (arm / "answer.txt").read_text()
        path = out / "answers" / f"{r['name']}.txt"
        answer = path.read_text() if path.exists() else None
        row = {"name": r["name"], "arm": arm.name, "case": int(task.rsplit("-", 1)[1]),
               "recorded_f1": score_answer("oolong-pairs", gold[task], recorded)["score"],
               "recorded_sha256": hashlib.sha256(recorded.encode()).hexdigest(),
               "replay_status": {k: status.get(r["name"], {}).get(k) for k in ("evals", "errors", "done", "error")}}
        if answer is not None:
            row["replay_f1"] = score_answer("oolong-pairs", gold[task], answer)["score"]
            row["replay_sha256"] = hashlib.sha256(answer.encode()).hexdigest()
            row["replay_pairs"] = answer.count("\n") + 1 if answer.strip() else 0
        if r["name"] in plan:
            row["withheld"] = plan[r["name"]][2]
        rows.append(row)
    (out / "results.json").write_text(json.dumps(rows, indent=1))
    for row in rows:
        same = row.get("replay_sha256") == row["recorded_sha256"]
        print(f"{row['name']:24} case {row['case']:2} recorded F1 {row['recorded_f1']:.3f} "
              f"replay F1 {row.get('replay_f1', float('nan')):.3f} identical={same} {row['replay_status']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
