# Official OOLONG inputs and scoring

Status: **IMPLEMENTED / OFFLINE VERIFIED** for public-data import and deterministic
scoring. The unit controls are **FIXTURE**. No agent inference or benchmark performance
result is established by this work.

## Exact primary sources

| Component | Source and revision |
| --- | --- |
| OOLONG synth data | [oolongbench/oolong-synth](https://huggingface.co/datasets/oolongbench/oolong-synth/tree/81d2f8d9349f6ff329d695f9be494051e9f05cb9), `81d2f8d9349f6ff329d695f9be494051e9f05cb9` |
| OOLONG synth scorer | [abertsch72/oolong, eval_helpers.py](https://github.com/abertsch72/oolong/blob/0bb7eabe839218fee7fe8d007f41cfc2fd3ae24c/src/eval/eval_helpers.py), `0bb7eabe839218fee7fe8d007f41cfc2fd3ae24c` |
| OOLONG-Pairs questions and gold | [mit-oasys/oolong-pairs](https://huggingface.co/datasets/mit-oasys/oolong-pairs/tree/d1e1522b86ac0c169bbc890b0471408aaa29e8fa), `d1e1522b86ac0c169bbc890b0471408aaa29e8fa` |
| OOLONG-Pairs task and scorer | [Prime Intellect research-environments, taskset.py](https://github.com/PrimeIntellect-ai/research-environments/blob/ba10ef5a303943a08e1ccf92f9c0d63b1159b369/environments/long_context/oolong_pairs/oolong_pairs/taskset.py), `ba10ef5a303943a08e1ccf92f9c0d63b1159b369` |

The pinned native Prime **agent** revision remains
`c4c238ca025e382d96fb5f37e6328ca77fb82ef3`. The research-environments revision
above pins the independent benchmark task implementation. These are different
repositories and have different roles.

Pairs uses the official `data/oolong-pairs-{context_len}.json` answers, not the
sampled pair summaries. Its context comes from the `trec_coarse` **validation**
rows of OOLONG synth. This is the mapping specified by both primary sources.
The agent receives `context_window_text`. It never receives
`context_window_text_with_labels`. The Pairs source data declares an MIT license.

`benchmark/vendor/oolong_pairs.py` copies the three deterministic scorer function
bodies without changes. The source uses Apache-2.0. The complete source license
is in `benchmark/vendor/LICENSE.oolong-pairs`. The excerpt removes the Verifiers
runtime dependency. An AST comparison against the pinned source found all three
functions identical. Existing synth scoring and its MIT notice remain unchanged.

## Authenticated inputs and selected pilot scope

`benchmark/official.py` downloads only artifact URLs and revisions from
`benchmark/upstream.lock.json`. Every cached or downloaded file must match its
pinned byte count and SHA-256. A corrupted cache causes an error; it is not
silently repaired. Missing files fail when `download=False`. A caller cannot
authenticate an arbitrary JSONL export merely by supplying a revision string.

Supported profiles are deliberately limited:

| Suite | Dataset subset | Context bucket | Pinned files |
| --- | --- | ---: | --- |
| OOLONG synth | negation, test split | 32,768 | test shards 3 and 4 of 41 |
| OOLONG synth | negation, test split | 131,072 | test shard 4 of 41 |
| OOLONG-Pairs | trec_coarse, validation context | 8,192 | validation shard 3 of 9; official 8K Pairs JSON |
| OOLONG-Pairs | trec_coarse, validation context | 32,768 | validation shard 6 of 9; official 32K Pairs JSON |

The 32K Pairs context shard is 379,914,185 bytes. The JSON gold file is
1,564,316 bytes. Both remain in the ignored cache. Full pins and SHA-256 values
are in the lockfile. Row groups are inspected using identifying fields before
context is decoded. The importer does not decode label-augmented context.

Selection is the first one or ten matching rows in the pinned source profile's
row order. Only `seed=0` is supported. This is a fixed prefix, not a random sample.
The one-case task is the first task of the ten-case pilot. Profiles were selected
for bounded public-data import before any model run, not for agent scores.
No answer-conditioned selection is performed.

These pilots cover specific subsets. They cannot reproduce a published overall
OOLONG score or establish broad superiority. Both 32K ten-case pilots contain
**one shared context**, not ten independent contexts. They can find integration
problems. They cannot establish statistical significance or a general advantage.

The public output contains only task ID, question, unlabelled context, and content
hashes. Gold answers and scoring metadata stay in `controller/`, with mode 0700
for the directory and 0600 for the answer file. The paired runner must mount or
copy only `public/` into agent environments. Directory permissions alone do not
isolate untrusted code running as the same host user.

Pairs questions retain the official category instructions and original question.
The answer-format instruction is adapted to the common runner's returned answer
instead of hardcoding the official `/workspace/answer.txt` path. Both harnesses
receive the same adapted text. This prompt change is explicit; the dataset and
scoring rules are unchanged. Full native harness capability parity is a separate
runner requirement.

## Independent scoring

Synth uses the existing official numeric/date/exact-match scorer. Pairs uses the
official order-normalized pair parser, think-tag removal, and set precision,
recall, and F1. F1 is the Pairs score. Duplicate pairs do not add credit. The
official empty-prediction/empty-gold rule is preserved. Runtime failures must
receive zero separately; they must not be presented as successful empty answers.

The scorer receives output and private gold, with no harness identity. The
benchmark controller, not an agent's final claim, decides the score. Successful
data import says nothing about model ability or executable learning.

## Offline validation and reproduction

Tests:

```sh
python3 -m unittest test_python.test_official_benchmarks -v
```

The controls cover exact official scoring behavior, SHA/size validation, corrupt
cache rejection, no partial files on failed downloads, fixed first-N selection,
matching one/ten prefixes, public/private separation, modified provenance rejection,
unsupported-profile errors, and preserving existing output. These are **FIXTURE**
controls, with no model calls. The command passed **13 tests** on 2026-10-26.

The actual pinned upstream bytes were downloaded and verified on 2026-10-26.
All four profiles imported successfully for both one and ten cases, using
`download=False` after cache verification. This is real data validation, not an
agent benchmark result. Artifacts are under:

```text
var/official-cache/
var/official-import-validation/oolong-synth-32768-{1,10}/
var/official-import-validation/oolong-synth-131072-{1,10}/
var/official-import-validation/oolong-pairs-8192-{1,10}/
var/official-import-validation/oolong-pairs-32768-{1,10}/
```

The 32K ten-case suite hashes are:

```text
OOLONG synth: cf8cb56d4bcaa1558f168740ea517d72652395edbd47c67ba44159ceb1256bb1
OOLONG-Pairs: e4f4e52aef20bef1623471b64d90fcf0ba5baf5b0b15324b0c1b3d4bc1d42db1
```

The importer requires `pyarrow==19.0.1`; the existing synth scorer requires
`python-dateutil==2.9.0.post0`. This API downloads only public benchmark data:

```sh
python3 - <<'PY'
from benchmark.official import prepare_official
prepare_official(
    'var/oolong-pairs-first-case-v1',
    suite='oolong-pairs', cache='var/official-cache',
    count=1, context_len=32768, seed=0,
)
PY
```

Use a new output directory and `count=10` for the ten-case pilot. Use
`suite='oolong-synth'` for the pinned negation profile. Set `download=False` to
require a complete local cache and forbid downloads. This command does not run
either agent, contact a model provider, or authorize later inference.
