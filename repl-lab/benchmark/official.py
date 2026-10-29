"""Authenticated imports from pinned official OOLONG sources; no inference.

Only the small, reviewed profiles in upstream.lock.json are enabled. The importer
selects the first N matching upstream rows, or a seeded sample from each pinned
context window, before any agent run or score exists.
"""
import hashlib
import json
import os
import random
import re
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
FIRST_N = "first-n-in-pinned-upstream-order"
PER_WINDOW = "seeded-sample-per-window"
LABEL_COUNT = "whole-window-label-count"
LABEL_COUNT_QUESTION = re.compile(r"^In the above data, how many data points should be classified as label '[^']+'\?")


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


def _window_rows(paths, dataset, window, context_len):
    """Every pinned row of one context window, in upstream order. Like _parquet_rows,
    it never decodes the label-augmented column."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ValueError("Official imports require pyarrow==19.0.1; install benchmark/requirements-official.txt") from exc
    columns = ["id", "dataset", "context_len", "context_window_id", "context_window_text", "question", "answer",
               "answer_type"]
    rows, seen = [], set()
    for path in paths:
        parquet = pq.ParquetFile(path)
        for group in range(parquet.num_row_groups):
            metadata = parquet.read_row_group(group, columns=["id", "dataset", "context_len",
                                                              "context_window_id"]).to_pylist()
            indices = [i for i, row in enumerate(metadata)
                       if row["dataset"] == dataset and row["context_len"] == context_len
                       and row["context_window_id"] == window and row["id"] not in seen]
            if indices:
                for row in parquet.read_row_group(group, columns=columns).take(indices).to_pylist():
                    seen.add(row["id"])
                    rows.append(row)
    return rows


def _clean_window_rows(paths, dataset, window, context_len, heldout):
    """Like _window_rows, but a row group that also holds a row of a held-out window is
    never read past its metadata columns, so no held-out question or answer is decoded."""
    import pyarrow.parquet as pq
    columns = ["id", "dataset", "context_len", "context_window_id", "context_window_text", "question", "answer",
               "answer_type"]
    rows, seen = [], set()
    for path in paths:
        parquet = pq.ParquetFile(path)
        for group in range(parquet.num_row_groups):
            metadata = parquet.read_row_group(group, columns=["id", "dataset", "context_len",
                                                              "context_window_id"]).to_pylist()
            if any((row["dataset"], row["context_window_id"]) in heldout for row in metadata):
                continue
            indices = [i for i, row in enumerate(metadata)
                       if row["dataset"] == dataset and row["context_len"] == context_len
                       and row["context_window_id"] == window and row["id"] not in seen]
            if indices:
                for row in parquet.read_row_group(group, columns=columns).take(indices).to_pylist():
                    seen.add(row["id"])
                    rows.append(row)
    return rows


def prepare_label_counts(output, *, cache, context_len=32768, download=True):
    """Every whole-window label-count question of the pinned dev windows, for count-accuracy
    development. Held-out windows are excluded and their row groups are never decoded."""
    suite = "oolong-synth"
    profile = PINS["official_profiles"].get(f"{suite}:dev-label-counts:{context_len}")
    require(profile is not None and profile.get("selection") == LABEL_COUNT, "Label-count profile not pinned")
    heldout = {tuple(w) for w in PINS["official_profiles"][f"{suite}:independent-heldout:{context_len}"]["windows"]}
    require(not {tuple(w) for w in profile["windows"]} & heldout, "A label-count window is a held-out window")
    require(not Path(output).exists(), "Output exists; preserve previous evidence and use a new directory")
    sources = {name: fetch_artifact(name, cache, download=download) for name in profile["artifacts"]}
    rows = []
    for dataset, window in profile["windows"]:
        found = _clean_window_rows(list(sources.values()), dataset, window, context_len, heldout)
        require(len({row["context_window_text"] for row in found}) == 1, f"Window {dataset}:{window} has two contexts")
        # Selected by question text alone, in upstream order; answers play no part.
        rows.extend(row for row in found if LABEL_COUNT_QUESTION.match(row["question"]))
    require(len(rows) == profile["count"] and len({row["id"] for row in rows}) == len(rows),
            "Label-count selection differs from the pinned count")
    for row in rows:
        score_answer(suite, row, "")
    for name, path in sources.items():
        require(file_digest(path) == PINS["official_artifacts"][name]["sha256"], "Upstream cache changed during preparation")
    return _write_suite(output, suite, profile, sources, rows,
                        {"dataset": "dev-label-counts", "context_len": context_len, "count": len(rows), "seed": 0,
                         "split": profile["split"], "method": LABEL_COUNT, "windows": profile["windows"]})


def sample_window(rows, dataset, window, count, seed):
    """A fixed-seed sample of one window's questions, kept in upstream order."""
    require(len(rows) >= count, f"Window {dataset}:{window} has fewer than {count} pinned questions")
    require(len({row["context_window_text"] for row in rows}) == 1, f"Window {dataset}:{window} has two contexts")
    chosen = set(random.Random(f"{seed}:{dataset}:{window}").sample(sorted(row["id"] for row in rows), count))
    return [row for row in rows if row["id"] in chosen]


def validate_provenance(manifest):
    """Reject unpinned profile, artifact, prompt, or selection metadata."""
    require(manifest.get("input_provenance") == PROVENANCE, "Input is not a verified upstream import")
    selection = manifest["selection"]
    key = f"{manifest['suite']}:{selection['dataset']}:{selection['context_len']}"
    profile = PINS["official_profiles"].get(key)
    require(profile is not None, "Unknown pinned import profile")
    require(selection.get("split") == profile["split"], "Official split mismatch")
    if profile.get("selection") == LABEL_COUNT:
        # Every whole-window label-count question of the pinned dev windows; the count is pinned.
        require(selection.get("method") == LABEL_COUNT and selection.get("windows") == profile["windows"],
                "Label-count selection differs from the pinned profile")
        require(selection.get("count") == profile["count"] == len(manifest["task_ids"]),
                "Label-count suite must contain every pinned question")
    elif "windows" in profile:
        # Independent contexts: the profile fixes the windows and the sample size.
        require(selection.get("method") == PER_WINDOW and selection.get("seed") == 0,
                "Window profiles must use the pinned seeded per-window sample")
        require(selection.get("windows") == profile["windows"] and selection.get("per_window") == profile["per_window"],
                "Window selection differs from the pinned profile")
        require(selection.get("count") == len(profile["windows"]) * profile["per_window"] == len(manifest["task_ids"]),
                "Window suite must contain every pinned window's sample")
    else:
        require(selection.get("method") == FIRST_N and selection.get("seed") == 0,
                "Official pilot selection must use the pinned first-N protocol")
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
    return _write_suite(output, suite, profile, sources, rows,
                        {"dataset": subset, "context_len": context_len, "count": count,
                         "seed": seed, "split": profile["split"], "method": FIRST_N})


def prepare_independent(output, *, role, cache, context_len=32768, seed=0, download=True):
    """One pinned OOLONG-synth suite over independent context windows: a fixed-seed
    sample of each window's questions. The dev and held-out roles use disjoint windows."""
    suite = "oolong-synth"
    require(role in ("dev", "heldout"), "Independent suites are dev or heldout")
    require(type(seed) is int and seed == 0, "The per-window sample is pinned to seed 0")
    profile = PINS["official_profiles"].get(f"{suite}:independent-{role}:{context_len}")
    require(profile is not None and "windows" in profile, "Independent profile not pinned")
    require(not Path(output).exists(), "Output exists; preserve previous evidence and use a new directory")
    sources = {name: fetch_artifact(name, cache, download=download) for name in profile["artifacts"]}
    rows = []
    for dataset, window in profile["windows"]:
        found = _window_rows(list(sources.values()), dataset, window, context_len)
        rows.extend(sample_window(found, dataset, window, profile["per_window"], seed))
    require(len({row["id"] for row in rows}) == len(rows), "Duplicate official task ID")
    for row in rows:
        score_answer(suite, row, "")
    for name, path in sources.items():
        require(file_digest(path) == PINS["official_artifacts"][name]["sha256"],
                "Upstream cache changed during preparation")
    return _write_suite(output, suite, profile, sources, rows,
                        {"dataset": f"independent-{role}", "context_len": context_len, "count": len(rows),
                         "seed": seed, "split": profile["split"], "method": PER_WINDOW,
                         "windows": profile["windows"], "per_window": profile["per_window"]})


def _write_suite(output, suite, profile, sources, rows, selection):
    dataset, scorer, scorer_path = suite_pins(suite)
    context_len = selection["context_len"]
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
                "selection": selection,
                "task_ids": [task["task_id"] for task in tasks],
                "files": {name: digest((output / name).read_bytes()) for name in
                          ("public/tasks.jsonl", "controller/answers.jsonl")}}
    validate_provenance(manifest)
    manifest["suite_sha256"] = digest(encoded(manifest))
    (output / "manifest.json").write_bytes(encoded(manifest) + b"\n")
    return manifest
