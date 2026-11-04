"""Exploratory benchmarks for pilot 2: OBLIQ-Bench (Math Meta-Program subset) and LongBench Pro (English, 8k-32k,
T4 excluded). Pinned public inputs through the lockfile, seeded dev/held-out splits fixed before any run, gold kept
controller-side, independent scorers (benchmark/vendor/obliq_math.py, benchmark/vendor/longbench_pro.py).

These suites are kept apart from the sealed OOLONG Phase B inputs: different lockfile profiles, suite names and
plans. Nothing here is a claim about either harness until a frozen plan runs.

    python3 -m benchmark prepare-official --suite obliq-math --role dev --cache var/official-cache --out var/official/obliq-math-dev --offline
    python3 -m benchmark prepare-official --suite longbench-pro --role dev --cache var/official-cache --out var/official/longbench-pro-dev --offline
"""
import hashlib
import json
import random
from pathlib import Path

from .oolong import PINS, digest, encoded, require, write_jsonl

EXPLORATORY = "exploratory-split-v1"
OBLIQ = "obliq-math"
LONGBENCH = "longbench-pro"
OBLIQ_QUESTION = (
    "The context lists {n} mathematics problems, one per line, each as 'ID: <id> || <problem text>'. "
    "Find the problems that are analogues of the following problem: they can be solved by the same meta-program "
    "(the same method, structure or key idea), even when their surface topic differs.\n\n{query}\n\n"
    "Return the IDs of the 10 most relevant problems, most relevant first, exactly one ID per line copied verbatim "
    "from the context, and nothing else.")


def _load_obliq(sources):
    corpus = [json.loads(line) for line in Path(sources["obliq-math-corpus.jsonl"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    queries = [json.loads(line) for line in Path(sources["obliq-math-queries.jsonl"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    def qrels(name):
        table = {}
        for i, line in enumerate(Path(sources[name]).read_text(encoding="utf-8").splitlines()):
            if i == 0 or not line.strip():
                continue
            query, doc, grade = line.rstrip("\n").split("\t")
            table.setdefault(query, {})[doc] = int(grade)
        return table
    excluded = json.loads(Path(sources["obliq-math-per_query_excluded_ids.json"]).read_text(encoding="utf-8"))
    ids = [d["_id"] for d in corpus]
    require(len(ids) == len(set(ids)) and all(set(q) <= set(ids) for q in qrels("obliq-math-qrels.tsv").values()),
            "OBLIQ corpus ids are not unique or qrels name unknown documents")
    return corpus, queries, qrels("obliq-math-qrels.tsv"), qrels("obliq-math-qrels_pool.tsv"), excluded


def obliq_context(corpus):
    return "\n".join(f"ID: {d['_id']} || {' '.join(str(d['text']).split())}" for d in corpus)


def split_obliq(query_ids, profile):
    rng = random.Random(f"{profile['seed']}:{OBLIQ}")
    order = sorted(query_ids)
    rng.shuffle(order)
    dev = order[:10]
    return dev if profile["role"] == "dev" else order[10:]


def prepare_obliq(output, *, role, cache, download=True):
    from .official import fetch_artifact, file_digest
    profile = PINS["official_profiles"][f"{OBLIQ}:{role}:corpus"]
    require(not Path(output).exists(), "Output exists; preserve previous evidence and use a new directory")
    sources = {name: fetch_artifact(name, cache, download=download) for name in profile["artifacts"]}
    corpus, queries, gold, pooled, excluded = _load_obliq(sources)
    chosen = split_obliq([q["_id"] for q in queries], profile)
    require(len(chosen) == profile["count"], "OBLIQ split size differs from the pinned profile")
    context = obliq_context(corpus)
    by_id = {q["_id"]: q for q in queries}
    rows = []
    for qid in chosen:
        rows.append({"id": qid, "context_window_id": "obliq-math-corpus", "dataset": OBLIQ,
                     "question": OBLIQ_QUESTION.format(n=len(corpus), query=" ".join(str(by_id[qid]["text"]).split())),
                     "answer": gold[qid], "pooled": pooled.get(qid, {}), "excluded": excluded.get(qid, []), "answer_type": "ranked-ids"})
    for name, path in sources.items():
        require(file_digest(path) == PINS["official_artifacts"][name]["sha256"], "Upstream cache changed during preparation")
    return write_suite(output, OBLIQ, profile, sources, rows, context_by_row=lambda r: context,
                       selection={"dataset": role, "context_len": "corpus", "method": EXPLORATORY, "seed": profile["seed"],
                                  "role": role, "count": len(rows), "corpus_documents": len(corpus), "context_chars": len(context)})


def _load_longbench(sources):
    data = json.loads(Path(sources["longbench_pro.json"]).read_text(encoding="utf-8"))
    rows = [r for r in data if r["language"] == "English" and not r["primary_task"].startswith("T4")
            and r["token_length"] in ("8k", "16k", "32k")]
    for r in rows:
        r["_context_hash"] = hashlib.sha256(r["context"].encode("utf-8")).hexdigest()
    return rows


def split_longbench(rows, profile):
    """Seeded shuffle of the context hashes within each length; dev takes the first per_length['dev'] contexts,
    held-out the next per_length['heldout'] contexts, so the two never overlap. One question per context,
    chosen by the same seed from the context's rows (sorted by id)."""
    dev_profile = PINS["official_profiles"][f"{LONGBENCH}:dev:mixed"]
    held_profile = PINS["official_profiles"][f"{LONGBENCH}:heldout:mixed"]
    chosen = []
    for length in ("8k", "16k", "32k"):
        hashes = sorted({r["_context_hash"] for r in rows if r["token_length"] == length})
        rng = random.Random(f"{profile['seed']}:{LONGBENCH}:{length}")
        rng.shuffle(hashes)
        n_dev, n_held = dev_profile["per_length"][length], held_profile["per_length"][length]
        take = hashes[:n_dev] if profile["role"] == "dev" else hashes[n_dev:n_dev + n_held]
        require(len(take) == (n_dev if profile["role"] == "dev" else n_held), f"Too few {length} contexts")
        for h in take:
            mine = sorted((r for r in rows if r["_context_hash"] == h), key=lambda r: r["id"])
            chosen.append(random.Random(f"{profile['seed']}:{h}").choice(mine))
    return chosen


def prepare_longbench(output, *, role, cache, download=True):
    from .official import fetch_artifact, file_digest
    profile = PINS["official_profiles"][f"{LONGBENCH}:{role}:mixed"]
    require(not Path(output).exists(), "Output exists; preserve previous evidence and use a new directory")
    sources = {name: fetch_artifact(name, cache, download=download) for name in profile["artifacts"]}
    rows = _load_longbench(sources)
    chosen = split_longbench(rows, profile)
    out = []
    for r in chosen:
        out.append({"id": r["id"], "context_window_id": r["_context_hash"][:16], "dataset": LONGBENCH,
                    "question": r[profile["question"]], "answer": r["answer"], "answer_type": "list",
                    "secondary_task": r["secondary_task"], "primary_task": r["primary_task"], "token_length": r["token_length"],
                    "difficulty": r["difficulty"], "contextual_requirement": r["contextual_requirement"], "_context": r["context"]})
    for name, path in sources.items():
        require(file_digest(path) == PINS["official_artifacts"][name]["sha256"], "Upstream cache changed during preparation")
    return write_suite(output, LONGBENCH, profile, sources, out, context_by_row=lambda r: r["_context"],
                       selection={"dataset": role, "context_len": "mixed", "method": EXPLORATORY, "seed": profile["seed"], "role": role,
                                  "count": len(out), "per_length": profile["per_length"], "question": profile["question"],
                                  "filter": "English; primary task not T4; token_length in 8k/16k/32k"})


def write_suite(output, suite, profile, sources, rows, *, context_by_row, selection):
    from .official import suite_pins, validate_provenance
    dataset, scorer, scorer_path = suite_pins(suite)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "public/contexts").mkdir(parents=True)
    (output / "controller").mkdir(mode=0o700)
    tasks, answers = [], []
    for row in rows:
        context = context_by_row(row).encode("utf-8")
        context_hash = digest(context)
        context_path = f"contexts/{context_hash}.txt"
        if not (output / "public" / context_path).exists():
            (output / "public" / context_path).write_bytes(context)
        task_id = f"{suite}-{selection['role']}-{row['id']}"
        task = {"task_id": task_id, "question": row["question"], "context_path": context_path, "context_sha256": context_hash}
        task["task_sha256"] = digest(encoded(task))
        tasks.append(task)
        answers.append({"task_id": task_id, **{k: v for k, v in row.items() if k not in ("question", "_context")}})
    write_jsonl(output / "public/tasks.jsonl", tasks)
    write_jsonl(output / "controller/answers.jsonl", answers)
    (output / "controller/answers.jsonl").chmod(0o600)
    manifest = {"schema_version": 1, "suite": suite, "dataset": dataset, "scorer": scorer,
                "scorer_sha256": digest(scorer_path.read_bytes()), "input_provenance": "verified-pinned-upstream",
                "source_export_sha256": digest(encoded([{k: v for k, v in r.items() if k != "_context"} for r in rows])),
                "source_artifacts": [{"name": name, **PINS["official_artifacts"][name]} for name in sources],
                "selection": selection, "task_ids": [t["task_id"] for t in tasks],
                "files": {name: digest((output / name).read_bytes()) for name in ("public/tasks.jsonl", "controller/answers.jsonl")}}
    validate_provenance(manifest)
    manifest["suite_sha256"] = digest(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest) + b"\n")
    return manifest


def validate_selection(manifest, profile):
    selection = manifest["selection"]
    require(selection.get("method") == EXPLORATORY and selection.get("seed") == profile["seed"] and selection.get("role") == profile["role"],
            "Exploratory selection differs from the pinned profile")
    if manifest["suite"] == OBLIQ:
        require(selection.get("count") == profile["count"] == len(manifest["task_ids"]), "OBLIQ suite size differs from the pinned profile")
    else:
        require(selection.get("per_length") == profile["per_length"] and selection.get("question") == profile["question"] and
                selection.get("count") == sum(profile["per_length"].values()) == len(manifest["task_ids"]),
                "LongBench Pro selection differs from the pinned profile")


def score_answer(suite, answer, output):
    if suite == OBLIQ:
        from .vendor.obliq_math import score
        return score(answer["answer"], answer.get("pooled") or {}, answer.get("excluded") or [], output)
    require(suite == LONGBENCH, "Unsupported exploratory suite")
    from .vendor.longbench_pro import normalize_prediction, score
    value = score(answer["secondary_task"], answer["answer"], output or "")
    return {"score": value, "parse_confidence": "longbench-pro-official-normalization",
            "attempted_parse": " | ".join(normalize_prediction(output or "")[:12]), "metric": answer["secondary_task"]}
