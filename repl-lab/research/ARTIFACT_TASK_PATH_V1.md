# Artifact task path v1: identity, library, applicability, preload

**Type:** implementation note, 2026-10-29. No inference, Docker or held-out data was
used. Companion to `RESEARCH_THESIS_REVIEW.md` §4 and §6 (roadmap items 2 and 3).

## 1. Code identity (always on)

- `artifact/code-hash`: sha256 of the canonical printed forms only, with fixed print
  settings. It does not cover author, parent, provenance, interface or source text.
- `:hash` (the provenance hash) is unchanged. Stored artifacts are not rewritten. The
  code hash is computed when it is needed, so all existing artifacts still verify.
- Identical code has one code hash, also after a cold-boot restore
  (`evaluation/restore-library`). A workflow's code hash still changes after a restore,
  because its forms name a policy by provenance hash.

## 2. Defects fixed (always on)

| Defect | Fix | Test |
| --- | --- | --- |
| The promotion gain summed scores, so failed parent workers inflated it (first live run: 37,630) | `promotion-evidence` takes pairs where either run has `:status :execution-failure` out of the gain and lists them (`:excluded-pairs`, `:healthy-pairs`). A candidate that did not run on a case (`:candidate-execution-failures`), or a panel with no healthy pair, is not approved | `artifact-identity-test/infrastructure-failed-pairs-do-not-inflate-the-promotion-gain` |
| A failed episode recorded the retained hash as its artifact | `records/attribution`: `:artifact` is set only if the policy was called at least once. Otherwise `:artifact nil` and `:assigned-artifact <hash>`. This applies in evaluation, the code panel, the development panel, the acquisition task and the invocation line | `artifact-identity-test/a-failed-episode-names-no-executed-artifact` |

The `:verified-cases` objective is unchanged.

## 3. Library versions (`skills.clj`)

- Root: an existing registry directory (`<root>/artifacts/<hash>.edn`, `artifact/save!`).
- Version: `<root>/libraries/<sha256>.edn`. The sha256 is the hash of the file's bytes.
  A version is immutable. `set-status!`, `add-entry!` and `update-library!` write a new
  version whose `:parent` is the old one.
- Format: `{:schema :aljure-library-v1 :parent <sha|nil> :entries [...]}`.
- Each entry has these fields:
  - `:artifact` and `:code-hash` (the function);
  - `:applicability` and `:applicability-code-hash`, a dependency-free one-argument
    `:analysis` function;
  - `:status`, one of `:approved`, `:quarantined`, `:unknown` or `:rejected`;
  - optional `:summary` (240 characters or fewer) and `:receipt`. The receipt is the
    `promotion-evidence` result. It holds case ids and pass or fail, never gold.
- `load-library` fails closed in these cases:
  - the file is missing or is a symbolic link;
  - the bytes do not match the hash;
  - the schema is wrong;
  - an artifact, predicate or dependency is missing or does not verify;
  - a recorded code hash does not match its artifact.
- `discover` offers only `:approved` entries. The controller discovers entries. The
  model never names or selects them.

## 4. Composition and validation before promotion

- `artifact/compose` builds `(fn [x0 ..] (gN .. (g1 x0 ..)))` as data from verified
  functions. The stages are called by their exported names and pinned by dependency
  hash. The new source is the printed forms. No source text is rewritten.
- `artifact/patch` (unchanged) transforms one subtree and checks the base and target
  hashes.
- `executable/validate!` runs a candidate on development cases in a fresh isolated
  worker. It returns `[{:case :passed}]`. `promotion-evidence` with
  `{:objective :verified-cases}` decides. `skills/add-entry!` records `:approved` or
  `:rejected`. A rejected entry is kept but never offered.

## 5. Switch: `aljure_contract.artifacts` (off by default)

```json
"aljure_contract": {"artifacts": {"library": "var/libraries/pilot", "library_sha256": "<64 hex>"}}
```

- **Absent or null:** off. `aljure_contract()`, `capabilities()`, the request body, the
  prompts, the tools, the task message and the worker are unchanged. All 26 configs and
  plans under `config/`, `research/` and `var/` gave the same `capabilities()` and
  `aljure_contract()` hashes before and after this change.
  `learning_library_sha256` stays sha256 of `[]`.
- **On:**
  - `capabilities()` declares `execution_contract.artifacts` with the pinned hash and
    replaces `aljure.skills`.
  - Preflight requires the version's bytes to match its pin. It also requires
    `var/artifact-path-proof.json`, made with
    `python3 scripts/clj.py -m repl-lab.sci-contract artifacts` (Docker). The proof must
    match the SCI image, the output bound and the current `executable.clj`,
    `external_task.clj`, `skills.clj` and `runtime.clj`.
  - For Aljure rows, `learning_library_sha256` is the pin. Prime rows and the Prime
    arm are unchanged.
- **Task behaviour when on** (`external-task/prepare-artifacts!`, before the first
  model call):
  1. The controller loads and verifies the pinned version, then discovers the
     approved entries.
  2. It opens the root's first worker with the normal context initialization.
  3. Each predicate runs in that worker on `{:question <task question> :context
     external-context}`. Only `true` admits an entry.
  4. These entries are refused, and each refusal is recorded:
     - inapplicable;
     - predicate error;
     - non-boolean result;
     - unsupported language;
     - reserved name (clojure.core, prelude and verification names, `aljure-*`);
     - name conflict;
     - more than 16 functions;
     - a definition larger than the worker's request bound.
  5. Admitted functions and their dependencies are defined under their exported
     names. Each one is wrapped to count calls by code hash.
  6. The worker goes to the root session as its prewarmed worker. Replacement and
     child workers get the same functions without a second check.
  7. If at least one function is preloaded, the task message gets
     `:approved-functions {:note .. :functions [{:name :arity :summary}]}`. The system
     prompt and the tools do not change.
  8. After each model `repl_eval` or `done` source that ran in the current worker, the
     controller reads and clears the worker's call log.
- **What does not change:** code is never forced. A `done` summary and the
  answer-format notice work as before. Generated code runs only in the isolated SCI
  worker. The model gets no artifact tools. Discovery, predicates and preload make no
  model call and change no budget. Their time counts against the task's wall clock and
  is recorded as `:elapsed-ms`.

## 6. Event schema (task ledger, exported to `events.jsonl`)

| Event | When | Payload |
| --- | --- | --- |
| `:artifact-library-loaded` | once, before the first model call | `:library-sha256`, `:statuses` (count per status), `:approved` (count) |
| `:artifact-applicability` | once per approved entry, in library order | `:artifact`, `:code-hash`, `:applicability-code-hash`, `:name`, `:decision` (`:preload` or `:refuse`), `:reason` (`:applicable`, `:inapplicable`, `:predicate-error`, `:not-boolean`, `:unsupported-language`, `:reserved-name`, `:name-conflict`, `:limit`, `:too-large`), `:elapsed-ms`, `:error` (predicate errors only) |
| `:artifact-preloaded` | each worker that receives the functions (`:worker` 0 is the root's first) | `:worker`, `:elapsed-ms`, `:functions [{:name :arity :hash :code-hash :role}]`, where `:role` is `:export` or `:dependency` |
| `:artifact-invocations` | after a model evaluation that called a preloaded function, or whose log could not be read | `:session`, `:op` (`:repl/eval` or `:done/eval`), `:call-sequence` (the matching `:tool-call` sequence), `:invocations [{:code-hash :artifact :name :calls :returns :values}]` or `:error`. `:values` holds up to 8 distinct short scalar results |
| `:artifact-reuse-summary` | once, after the root finishes; also copied to `result.json` as `:artifact-reuse` | see below |

`:artifact-reuse-summary` (`skills/reuse-summary`, a pure function of the events and
the result):

- `:exports`: code hashes admitted as entries. `:available`: all preloaded functions,
  dependencies included.
- `:refused`: `[{:artifact :code-hash :reason}]`.
- `:invoked`: `{code-hash calls}` over all sessions.
- `:in-answer`: `{code-hash :computed-in-answer | :value-equals-answer}`.
  `:computed-in-answer` means the function returned inside the root's delivered `done`
  source evaluation. `:value-equals-answer` means one of its recorded scalar results
  equals the trimmed answer.
- `:answer-mode`: `:done-summary`, `:done-eval`, `:terminal-text` or `:none`.
  `:model-evaluations` counts the model's `repl_eval` and `done` source calls in all
  sessions.
- `:classification`, the first match in this order:
  1. `:no-answer`.
  2. `:direct-answer` (c): no model evaluation.
  3. `:no-applicable-artifact`.
  4. `:eligible-reuse` (a): an admitted function ran and its output entered the answer.
  5. `:invoked-not-in-answer`.
  6. `:available-not-invoked`.
- **Correct refusals (b):** join `:refused` (or the `:artifact-applicability` events)
  with the task family. A refusal is correct when the artifact does not apply to that
  family (for example, F2 in `RESEARCH_THESIS_REVIEW.md` §5).

**Known undercount:**
- `:in-answer` misses an output that the model copies by hand when that output is not
  a scalar equal to the answer.
- A worker that stops during an expression loses that expression's counts.
- The model can redefine a name or clear `aljure-invocations`. This loses records, but
  it cannot add a call that did not happen.

## 7. Evidence status

- Offline tests (`artifact_identity_test.clj`, `artifact_library_test.clj`,
  `test_python/test_aljure_sci.py`) use a backend that runs only compiled developer
  fixtures. The backend finds each fixture by code hash and never evaluates source
  text on the host.
- The SCI templates (predicate call, wrappers, drain) are checked offline only for
  readability by the worker's EDN reader and against the worker's denied symbols.
- Their behaviour in the real worker is **UNVERIFIED** until the operator runs
  `python3 scripts/clj.py -m repl-lab.sci-contract artifacts`. Preflight refuses an
  `artifacts` plan until that proof exists.
