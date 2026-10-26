# External benchmark preparation and scoring

This package prepares matched OOLONG inputs and scores normalized results outside
the agents. Offline language and native Prime adapters also run scripted integration
tasks. The OOLONG path does not yet launch either harness. These commands make
**zero model calls**. No real head-to-head result exists.

`upstream.lock.json` pins the OOLONG scorer, dataset revision, and Prime source.
The two synthetic-task scoring functions in `vendor/oolong_synth.py` retain their
upstream bodies. The official numeric rule gives `0.75 ** abs(error)` credit.
The upstream license is included. Install `benchmark/requirements.txt` if
`python-dateutil` is unavailable.

## Prepare inputs

From `repl-lab`, use a JSONL export of the locked Hugging Face dataset's `test`
split. Select the exact `dataset` and `context_len` values in that export:

```sh
python3 -m benchmark prepare --raw-jsonl /path/to/oolong-test.jsonl \
  --subset SUBSET_VALUE --context-len CONTEXT_LEN_VALUE \
  --count 10 --seed 0 --out var/benchmarks/pilot-inputs
```

Selection is deterministic and independent of export order. The suite records the
export hash, selected IDs, context hashes, scorer hash, and dataset revision.
The importer cannot authenticate a local file's origin. It labels the source
`unverified-local-export`; a pinned downloader and source verification remain
required before a live benchmark claim. Use `--fixture` for synthetic test data.

Only `public/` may enter either agent's environment. `controller/` contains gold
answers and stays outside both environments. Directory separation is not an OS
isolation boundary. Live adapters must enforce that boundary. Do not give an
agent access to this repository or the whole suite directory.

## Compare saved results

```sh
python3 -m benchmark compare --suite var/benchmarks/pilot-inputs \
  --results /path/to/results.jsonl --out var/benchmarks/comparison.json
```

Each result must identify the task and suite hashes, `harness` (`aljure` or
`prime`), a stable `harness_revision`, `provenance` (`fixture` or
`recorded-model-run`), and `fresh_session: true`. `model_config` must contain
`provider`, `model`, `thinking`, `temperature`, and `max_output_tokens`.
Both harnesses use the same settings, `budget_usd`, and `pricing_usd_per_m`.
Use explicit `provider-default` values for settings left to the provider.

Every record also carries `status`, `wall_time_ms`, and relative artifact paths
with SHA-256 hashes: `trace_path`/`trace_sha256`, `usage_path`/`usage_sha256`, and,
for completed tasks, `answer_path`/`answer_sha256`. Artifacts stay below the result
file's directory. The answer file is UTF-8 text. Supported statuses are
`completed`, `error`, `budget_exhausted`, and `timeout`. Failed tasks receive zero
and remain in the denominator. Missing outcomes or duplicate task/harness records
stop report generation. Agent-supplied scores are ignored.

Usage JSONL contains one `kind: provider-call` row per invocation, including every
child. Each row needs `call_id`, `session_id`, `model`, and `status`.
Completed calls need a unique `provider_request_id` and integer counts for
`input_tokens`, `output_tokens`, `cache_read_input_tokens`, and
`cache_creation_input_tokens`. Unknown calls retain a positive `reserved_usd`.
Pricing uses those same four token field names with USD-per-million values.
For the approved model, ordinary input/output rates are 2 and 10. Nonzero cache
usage without an explicit cache rate makes total cost unknown. Unknown cost is
`null`, never zero. Counts called `known_tokens` exclude unresolved calls.

When receipts include `cache_creation` duration counts, configure separate
`cache_creation_5m_input_tokens` and `cache_creation_1h_input_tokens` rates. The
scorer checks their sum against the aggregate count and does not substitute a
generic cache rate for missing duration prices.

Prime's pinned implementation folds child usage into some parent usage rows.
Do not sum parent aggregates and child receipts together. This reader rejects
aggregate rows and duplicate provider receipts. A native Prime JSONL stream is
not yet a normalized usage file; its adapter must extract actual provider calls.

Reports are descriptive paired pilots. They include individual outcomes, mean
scores, paired differences, and the number of distinct context windows. Questions
can share context; ten questions need not be ten independent observations.
Fixture provenance stays explicit. The report makes no learning or language
superiority claim. Its `paid_execution_ready` remains false: scoring alone cannot
verify worker isolation, provider routing, or hard spending enforcement.

## Remaining live integration

1. The authorized subscription/SCI capability smoke passed. Validate the matched
   direct-provider path for both languages before a new live pair.
2. Verify a pinned dataset download and package the selected public inputs.
3. Add an Aljure OOLONG task adapter and the pinned Prime CLI adapter. Preserve
   Prime's Python REPL, native skills, subagents, messaging, and refinement.
4. Enforce one shared provider cap across every root and child request. Prime's
   goal token budget is not sufficient evidence of a hard dollar cap.
5. Verify fresh agent environments, hidden scorer data, full native traces,
   normalized receipts, and matching model settings with one paired live case.
6. Expand to ten only after that case passes and further spending is authorized.

The original frozen/evolving learning and cold-boot experiments remain separate.
Neither these unit tests nor a successful capability smoke demonstrates learning.

Sources: [OOLONG scorer](https://github.com/abertsch72/oolong/blob/0bb7eabe839218fee7fe8d007f41cfc2fd3ae24c/src/eval/eval_helpers.py),
[dataset](https://huggingface.co/datasets/oolongbench/oolong-synth/tree/81d2f8d9349f6ff329d695f9be494051e9f05cb9),
[Prime print runtime](https://github.com/PrimeIntellect-ai/prime-agent/blob/c4c238ca025e382d96fb5f37e6328ca77fb82ef3/crates/pa-cli/README.md),
[Prime child usage](https://github.com/PrimeIntellect-ai/prime-agent/blob/c4c238ca025e382d96fb5f37e6328ca77fb82ef3/crates/pa-core/src/session_engine/rlm_usage.rs).
