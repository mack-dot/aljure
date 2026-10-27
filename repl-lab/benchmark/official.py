"""Authenticated imports from pinned official OOLONG sources; no inference.

Only the small, reviewed profiles in upstream.lock.json are enabled. The importer
selects the first N matching upstream rows, before any agent run or score exists.
"""
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from .oolong import PINS, digest, encoded, require, write_jsonl
from .vendor.oolong_pairs import PROMPT_PREFIX, _pair_metrics, _parse_pairs, _strip_think_tags
from .vendor.oolong_synth import synth_process_response

SCORERS = {
    "oolong-synth": Path(__file__).parent / "vendor/oolong_synth.py",
    "oolong-pairs": Path(__file__).parent / "vendor/oolong_pairs.py",
}
PROVENANCE = "verified-pinned-upstream"


def suite_pins(suite):
    """Return the exact dataset and scorer records expected for a suite."""
    require(suite in SCORERS, "Unsupported official suite")
    prefix = "oolong" if suite == "oolong-synth" else "oolong_pairs"
    return PINS[prefix + "_dataset"], PINS[prefix + "_scorer"], SCORERS[suite]


def score_answer(suite, answer, output):
    """Score without agent identity, using the pinned official implementation."""
    if suite == "oolong-synth":
        return synth_process_response(answer, output, "blinded")
    require(suite == "oolong-pairs", "Unsupported official suite")
    metrics = _pair_metrics(output, _parse_pairs(answer["answer"]))
    return {"score": metrics["f1"], "parse_confidence": "official-pair-parser",
            "attempted_parse": sorted(_parse_pairs(_strip_think_tags(output or ""))), **metrics}


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fetch_artifact(name, cache, *, download=True):
    """Use only lockfile URLs/hashes. Reject, rather than repair, corrupt caches."""
    require(name in PINS["official_artifacts"], "Unknown pinned upstream artifact")
    pin = PINS["official_artifacts"][name]
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (pin["sha256"] + "-" + Path(pin["path"]).name)
    if not path.exists():
        require(download, f"Missing verified cache file: {path}; enable public-data download")
        url = f"{pin['repository']}/resolve/{pin['revision']}/{pin['path']}"
        fd, temporary = tempfile.mkstemp(prefix=".download-", dir=cache)
        try:
            size = 0
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=90) as response:
                while block := response.read(1024 * 1024):
                    size += len(block)
                    require(size <= pin["size"], "Upstream download exceeds pinned size")
                    out.write(block)
            require(size == pin["size"] and file_digest(temporary) == pin["sha256"],
                    "Downloaded upstream artifact does not match lockfile")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    require(path.is_file() and path.stat().st_size == pin["size"] and
            file_digest(path) == pin["sha256"], f"Corrupt pinned upstream cache: {name}")
    return path


def _parquet_rows(path, subset, context_len, count, *, context_only=False):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ValueError("Official imports require pyarrow==19.0.1; install benchmark/requirements-official.txt") from exc
    parquet = pq.ParquetFile(path)
    # Read only identifying fields first. Never decode the label-augmented column.
    columns = ["id", "dataset", "context_len", "context_window_id", "context_window_text"]
    if not context_only:
        columns += ["question", "answer", "answer_type"]
    selected = []
    for group in range(parquet.num_row_groups):
        metadata = parquet.read_row_group(group, columns=["dataset", "context_len"]).to_pylist()
        indices = [i for i, row in enumerate(metadata)
                   if row["dataset"] == subset and row["context_len"] == context_len]
        indices = indices[:count - len(selected)]
        if indices:
            table = parquet.read_row_group(group, columns=columns)
            selected.extend(table.take(indices).to_pylist())
        if len(selected) == count:
            break
    return selected


def validate_provenance(manifest):
    """Reject unpinned profile, artifact, prompt, or selection metadata."""
    require(manifest.get("input_provenance") == PROVENANCE, "Input is not a verified upstream import")
    selection = manifest["selection"]
    key = f"{manifest['suite']}:{selection['dataset']}:{selection['context_len']}"
    profile = PINS["official_profiles"].get(key)
    require(profile is not None, "Unknown pinned import profile")
    require(selection.get("method") == "first-n-in-pinned-upstream-order" and selection.get("seed") == 0,
            "Official pilot selection must use the pinned first-N protocol")
    require(selection.get("split") == profile["split"], "Official split mismatch")
    require(type(selection.get("count")) is int and selection["count"] in (1, 10) and
            len(manifest["task_ids"]) == selection["count"],
            "Official pilot must contain exactly one or ten cases")
    expected = [{"name": name, **PINS["official_artifacts"][name]} for name in profile["artifacts"]]
    require(manifest.get("source_artifacts") == expected, "Official source artifact pins differ")


def prepare_official(output, *, suite="oolong-synth", cache, count=1,
                     context_len=32768, subset=None, seed=0, download=True):
    """Create public tasks and controller-only gold from authenticated bytes.

    Enabled synth profiles use negation (32K or 128K). Pairs uses trec_coarse
    (8K or 32K). This is a selected pilot, not an aggregate benchmark score.
    ``download=False`` permits an entirely offline replay from a verified cache.
    """
    dataset, scorer, scorer_path = suite_pins(suite)
    require(type(count) is int and count in (1, 10), "Official pilots require one or ten cases")
    require(type(seed) is int and seed == 0, "Official first-N pilot requires seed=0")
    subset = subset or ("negation" if suite == "oolong-synth" else "trec_coarse")
    profile = PINS["official_profiles"].get(f"{suite}:{subset}:{context_len}")
    require(profile is not None, "Profile not pinned; available: " + ", ".join(PINS["official_profiles"]))
    require(not Path(output).exists(), "Output exists; preserve previous evidence and use a new directory")
    sources = {name: fetch_artifact(name, cache, download=download) for name in profile["artifacts"]}
    rows = []
    if suite == "oolong-synth":
        for name, path in sources.items():
            rows.extend(_parquet_rows(path, subset, context_len, count - len(rows)))
            if len(rows) == count:
                break
    else:
        context_path = next(path for name, path in sources.items() if name.endswith(".parquet"))
        contexts = _parquet_rows(context_path, subset, context_len, 1, context_only=True)
        require(len(contexts) == 1, "Official Pairs context is unavailable at the pinned revision")
        questions = json.loads(next(path for name, path in sources.items() if name.endswith(".json")).read_text())
        for question in questions[:count]:
            gold = question["answer"]
            require(isinstance(gold, (list, str)), "Invalid official Pairs answer type")
            rows.append({**contexts[0], "id": question["id"], "question": PROMPT_PREFIX + question["question"] +
                         "\n\nReturn every matching pair as (user_id_1, user_id_2), one per line, sorted by "
                         "the first user ID. If there are no matching pairs, return exactly [].",
                         "answer": "\n".join(gold) if isinstance(gold, list) else gold, "answer_type": "pairs"})
    require(len(rows) == count, "Not enough cases in the pinned source profile")
    require(len({row["id"] for row in rows}) == count, "Duplicate official task ID")
    for row in rows:
        require(isinstance(row["context_window_text"], str) and row["context_window_text"], "Missing context")
        score_answer(suite, row, "")
    for name, path in sources.items():
        require(file_digest(path) == PINS["official_artifacts"][name]["sha256"],
                "Upstream cache changed during preparation")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "public/contexts").mkdir(parents=True)
    (output / "controller").mkdir(mode=0o700)
    tasks, answers = [], []
    for row in rows:
        context = row["context_window_text"].encode("utf-8")
        context_hash = digest(context)
        context_path = f"contexts/{context_hash}.txt"
        (output / "public" / context_path).write_bytes(context)
        task_id = f"{suite}-{profile['split']}-{context_len}-{row['id']}"
        task = {"task_id": task_id, "question": row["question"], "context_path": context_path,
                "context_sha256": context_hash}
        task["task_sha256"] = digest(encoded(task))
        tasks.append(task)
        answers.append({"task_id": task_id, **{key: row[key] for key in
                        ("id", "context_window_id", "dataset", "answer", "answer_type")}})
    write_jsonl(output / "public/tasks.jsonl", tasks)
    write_jsonl(output / "controller/answers.jsonl", answers)
    (output / "controller/answers.jsonl").chmod(0o600)
    manifest = {"schema_version": 1, "suite": suite, "dataset": dataset, "scorer": scorer,
                "scorer_sha256": digest(scorer_path.read_bytes()), "input_provenance": PROVENANCE,
                "source_export_sha256": digest(encoded(rows)),
                "source_artifacts": [{"name": name, **PINS["official_artifacts"][name]} for name in sources],
                "selection": {"dataset": subset, "context_len": context_len, "count": count,
                              "seed": seed, "split": profile["split"], "method": "first-n-in-pinned-upstream-order"},
                "task_ids": [task["task_id"] for task in tasks],
                "files": {name: digest((output / name).read_bytes()) for name in
                          ("public/tasks.jsonl", "controller/answers.jsonl")}}
    validate_provenance(manifest)
    manifest["suite_sha256"] = digest(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest) + b"\n")
    return manifest
