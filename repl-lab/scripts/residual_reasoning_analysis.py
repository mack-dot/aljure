"""Offline coverage, correctness and residual-review analysis of A1c Aljure rules.

Item-level gold comes from the pinned source column context_window_text_with_labels.
It is used here for offline measurement only, never for a live decision. Each arm's
own rules are replayed in isolated SCI (no model calls); only the final done
expression is replaced so that the arm returns one label per question.

    source var/worker.env && python3 scripts/residual_reasoning_analysis.py RUN_DIR PARQUET OUT_DIR
"""
import datetime
import itertools
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark.official import score_answer  # noqa: E402
from review_replay_ablation import ablations, records, sources  # noqa: E402

NAMES = {"abbreviation": "abb", "description and abstract concept": "desc", "entity": "ent",
         "human being": "hum", "location": "loc", "numeric value": "num"}
LINE = re.compile(r"Date: (\w+ \d+, \d{4}) \|\| User: (\d+) \|\| Instance: (.*?)(?: \|\| Label: (.*))?$")

# Per arm: (done step, expression returning one label per question in context order).
# A label is a gold class name, or "unk" when the arm's rules decide nothing.
DIAGNOSTICS = {
    "00-aljure": (3, '(clojure.string/join "\\n" (map (fn [[u q]] (cond (re-find num-re q) "num" (re-find loc-re q) "loc" :else "unk")) rows))'),
    "03-aljure": (6, '(clojure.string/join "\\n" (map (fn [[u q]] (let [l (lab q)] (if (= :ent l) "ent*" ({:abb "abb" :hum "hum" :num "num" :loc "loc" :desc "desc"} l)))) rows))'),
    "04-aljure": (3, '(clojure.string/join "\\n" (map (fn [[u q]] ({:a "abb" :d "desc" :o "unk"} (lab q))) rows))'),
    "08-aljure": (9, '(clojure.string/join "\\n" (map (fn [r] (str (if (= :ent (:l r)) "ent*" ({:abb "abb" :hum "hum" :num "num" :loc "loc" :desc "desc"} (:l r))) "," (name (:f r)))) final))'),
    "11-aljure": (3, '(clojure.string/join "\\n" (map (fn [[u q]] ({:abb "abb" :loc "loc" :other "unk"} (lab q))) recs))'),
    "12-aljure": (6, '(clojure.string/join "\\n" (map (fn [r] (let [q (:q r)] (cond (num? q) "num" (desc? q) "desc" :else "unk"))) recs))'),
    "15-aljure": (4, '(clojure.string/join "\\n" (map (fn [[u q]] ({:h "hum" :d "desc" :o "unk"} (lab q))) rows))'),
    "19-aljure": (3, '(clojure.string/join "\\n" (map (fn [r] (let [q (:q r)] (cond (ab2? q) "abb" (num? q) "num" :else "unk"))) recs))'),
}
# Arms 03 and 08 put every unmatched question into :else :ent. That default is marked "ent*":
# the arm used it as entity, but it is the absence of a decision, so coverage counts it as unknown.


def gold_lines(parquet, public_context):
    import pyarrow.parquet as pq
    rows = pq.read_table(parquet, columns=["dataset", "context_len", "context_window_text",
                                           "context_window_text_with_labels"],
                         filters=[("dataset", "=", "trec_coarse"), ("context_len", "=", 32768)]).to_pylist()
    match = {r["context_window_text_with_labels"] for r in rows
             if r["context_window_text"].strip() == public_context.strip()}
    assert len(match) == 1, "public context must match exactly one labeled window"
    out = []
    for line in match.pop().split("\n"):
        m = LINE.match(line)
        if m:
            out.append({"date": datetime.datetime.strptime(m[1], "%b %d, %Y").date(), "user": m[2],
                        "q": m[3], "gold": NAMES[m[4]]})
    return out


def task_rule(question):
    m = re.search(r"at least one instance with an? (.+?) or (.+?)(?:\.|, and all instances that are an? (.+?) "
                  r"for both users must be (after|before) (\w+ \d+, \d{4}))", question)
    when = None
    if m[3]:
        when = (NAMES[m[3]], m[4], datetime.datetime.strptime(m[5], "%B %d, %Y").date())
    return {NAMES[m[1]], NAMES[m[2]]}, when


def answer(items, labels, rule):
    """The official pair semantics, computed from one label per item."""
    targets, when = rule
    users = defaultdict(list)
    for item, label in zip(items, labels):
        users[item["user"]].append((item["date"], label))
    ok = []
    for user, rows in users.items():
        if not any(label in targets for _, label in rows):
            continue
        if when:
            cls, side, day = when
            if not all((d > day) if side == "after" else (d < day) for d, label in rows if label == cls):
                continue
        ok.append(int(user))
    ok.sort()
    return "\n".join(f"({a}, {b})" for a, b in itertools.combinations(ok, 2))


def replay_labels(run, out):
    plan = ablations(run)
    runs = []
    for arm, (step, expr) in DIAGNOSTICS.items():
        done = sources(run / arm)[step]
        runs.append({"name": f"diag-{arm}", "arm": str(run / arm), "edits": {str(step): [[done, expr]]}})
    arm, edits, _ = plan["case7-ablation"]  # case 7's rules before the post-review rewrite
    step, expr = DIAGNOSTICS[arm]
    runs.append({"name": f"diag-{arm}-before-review", "arm": str(run / arm),
                 "edits": {**{str(k): v for k, v in edits.items()}, str(step): [[sources(run / arm)[step], expr]]}})
    spec = out / "diag-spec.json"
    spec.write_text(json.dumps({"out": str(out / "labels"), "runs": runs}, indent=1))
    log = subprocess.run([sys.executable, "scripts/clj.py", "-m", "repl-lab.replay", "--spec", str(spec)],
                         capture_output=True, text=True, timeout=1800)
    (out / "diag-replay.log").write_text(log.stdout + log.stderr)
    return {r["name"]: (out / "labels" / f"{r['name']}.txt").read_text().split("\n") for r in runs}


def prf(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return p, r


def main(run, parquet, out):
    run, out = Path(run).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    arms = sorted(p.name for p in run.iterdir() if p.name.endswith("-aljure"))
    public = json.loads((run / arms[0] / "public-input.json").read_text())["context"]
    items = gold_lines(parquet, public)
    golds = [i["gold"] for i in items]
    answers = {a["task_id"]: a for a in records(run.parent.parent / "official/pairs32-ten/controller/answers.jsonl")}
    case = {}
    for arm in arms:
        pi = json.loads((run / arm / "public-input.json").read_text())
        assert pi["context"] == public, "all A1c cases must share one context"
        task = json.loads((run / arm / "trace.json").read_text())["case"]["task_id"]
        rule = task_rule(pi["task"]["question"])
        f1 = score_answer("oolong-pairs", answers[task], answer(items, golds, rule))["score"]
        case[arm] = {"case": int(task.rsplit("-", 1)[1]), "task": task, "rule": rule, "gold_semantics_f1": f1}
    labels = replay_labels(run, out)
    report = {"items": len(items), "distinct_questions": len({i["q"] for i in items}),
              "gold_class_counts": Counter(golds), "cases": [], "review_accuracy": {}}

    def score(arm, labs):
        return score_answer("oolong-pairs", answers[case[arm]["task"]], answer(items, labs, case[arm]["rule"]))["score"]

    # Independent rule sets: each other arm's explicit decisions for one class.
    # Each arm's rules before any review: case 7's rules before its rewrite, case 5's before its labels.
    actual = {arm: labels[f"diag-{arm}"] for arm in DIAGNOSTICS}
    actual["08-aljure"] = [x.split(",")[0] for x in labels["diag-08-aljure"]]
    actual["12-aljure"] = labels["diag-12-aljure-before-review"]
    explicit = {arm: ["unk" if l.endswith("*") else l for l in labs] for arm, labs in actual.items()}
    for arm, (step, _) in DIAGNOSTICS.items():
        own = explicit[arm]
        assert len(own) == len(items), (arm, len(own))
        targets, when = case[arm]["rule"]
        relevant = targets | ({when[0]} if when else set())
        # The labels the arm computed with, defaults included.
        rules_only = [l.rstrip("*") for l in actual[arm]]
        unknown = [i for i, l in enumerate(own) if l == "unk"]
        # Conflict: another arm's rules explicitly decide this item differently on a relevant class.
        conflict = [i for i, l in enumerate(own) if l != "unk" and any(
            o != "unk" and o != l and (o in relevant or l in relevant)
            for other, labs in explicit.items() if other != arm for o in [labs[i]])]

        def reviewed(idx):
            s = set(idx)
            return [golds[i] if i in s else rules_only[i] for i in range(len(items))]

        pred = {i for i, l in enumerate(rules_only) if l in targets}
        recorded = score_answer("oolong-pairs", answers[case[arm]["task"]], (run / arm / "answer.txt").read_text())["score"]
        gold_t = {i for i, g in enumerate(golds) if g in targets}
        labeled = [i for i, l in enumerate(own) if l != "unk"]
        # A rule error that matters to this task: the rule or the gold class is one the task depends on.
        wrong = lambda i: own[i] != golds[i] and (own[i] in relevant or golds[i] in relevant)  # noqa: E731
        calm = [i for i in labeled if i not in set(conflict)]
        p, r = prf(pred, gold_t)
        row = {"arm": arm, "case": case[arm]["case"], "targets": sorted(targets), "date_class": when and when[0],
               "gold_semantics_f1": case[arm]["gold_semantics_f1"], "recorded_f1": recorded,
               "coverage": len(labeled) / len(items), "unknown": len(unknown),
               "target_precision": p, "target_recall": r,
               "labeled": len(labeled), "rule_labeled_relevant_errors": sum(map(wrong, labeled)),
               "relevant_gold_in_unknown": sum(golds[i] in relevant for i in unknown),
               "conflicting": len(conflict),
               "conflicting_wrong": sum(map(wrong, conflict)),
               "labeled_not_conflicting": len(calm), "labeled_not_conflicting_wrong": sum(map(wrong, calm)),
               "f1": {"A_rules_only": score(arm, rules_only),
                      "C_review_unknown_oracle": score(arm, reviewed(unknown)),
                      "D_review_unknown_and_conflict_oracle": score(arm, reviewed(unknown + conflict)),
                      "B_review_all_oracle": score(arm, golds)},
               "reviewed_items": {"A_rules_only": 0, "C_review_unknown_oracle": len(unknown),
                                  "D_review_unknown_and_conflict_oracle": len(set(unknown + conflict)),
                                  "B_review_all_oracle": len(items)}}
        report["cases"].append(row)
    # Model review accuracy where the model wrote item-level labels.
    s4 = sources(run / "07-aljure")[5]
    hum = {int(x) for x in re.search(r"H #\{([^}]*)\}", s4)[1].split()}
    loc = {int(x) for x in re.search(r"Lc #\{([^}]*)\}", s4)[1].split()}
    for name, mine in (("case4_model_human", hum), ("case4_model_location", loc)):
        cls = "hum" if "human" in name else "loc"
        p, r = prf(mine, {i for i, g in enumerate(golds) if g == cls})
        report["review_accuracy"][name] = {"labeled": len(mine), "precision": p, "recall": r}
    # Case 5: the model saw every default-entity, numeric and description item (steps 6-7) and decided
    # entity / numeric / other for each. Compare its decision and the rule's on those items.
    final5 = [x.split(",")[1] for x in labels["diag-08-aljure"]]
    rule5 = [x.split(",")[0] for x in labels["diag-08-aljure"]]
    shown = [i for i in range(len(items)) if rule5[i] in ("ent*", "num", "desc")]
    three = lambda g: g if g in ("ent", "num") else "other"  # noqa: E731
    rule3 = {"ent*": "ent", "num": "num"}
    report["review_accuracy"]["case5_entity_numeric_other"] = {
        "shown": len(shown),
        "model_correct": sum(final5[i] == three(golds[i]) for i in shown) / len(shown),
        "rule_correct": sum(rule3.get(rule5[i], "other") == three(golds[i]) for i in shown) / len(shown)}
    before, after = labels["diag-12-aljure-before-review"], labels["diag-12-aljure"]
    changed = [i for i in range(len(items)) if before[i] != after[i]]
    report["review_accuracy"]["case7_rule_rewrite"] = {
        "items_changed": len(changed),
        "changed_to_correct_on_num_desc": sum((after[i] == golds[i]) or (after[i] == "unk" and golds[i] not in ("num", "desc"))
                                              for i in changed),
        "changed_from_correct": sum((before[i] == golds[i]) or (before[i] == "unk" and golds[i] not in ("num", "desc"))
                                    for i in changed)}
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=1, default=str))
    for c in sorted(report["cases"], key=lambda c: c["case"]):
        print(f"case {c['case']:2} {c['arm']} gold-sem {c['gold_semantics_f1']:.3f} rec {c['recorded_f1']:.3f} cov {c['coverage']:.2f} "
              f"unk {c['unknown']:3} rule-errors {c['rule_labeled_relevant_errors']:3}/{c['labeled']:3} "
              f"conflict wrong {c['conflicting_wrong']:3}/{c['conflicting']:3} "
              f"calm wrong {c['labeled_not_conflicting_wrong']:3}/{c['labeled_not_conflicting']:3} | P {c['target_precision']:.2f} "
              f"R {c['target_recall']:.2f} | " + " ".join(f"{k.split('_')[0]} {v:.3f}/{c['reviewed_items'][k]}"
                                                            for k, v in c["f1"].items()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
