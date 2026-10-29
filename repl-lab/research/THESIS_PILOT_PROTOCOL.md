# Thesis pilot protocol (preregistration draft)

**Status:** DRAFT. Not frozen. No plan hash exists yet. Written 2026-10-29 on `claude/thesis-v1`,
before any pilot run. No model call, Docker run or held-out read was made to write it.

**Question** (`RESEARCH_THESIS_REVIEW.md` §5): can an agent that retains and transforms validated
executable knowledge solve related future tasks better or cheaper than one that regenerates the
computation each time?

**This removes the blocker in `THESIS_GO_NO_GO.md`:** a propose step after each task, and a
sequential trajectory mode that passes each committed library pin to the next task.

## 1. What runs, and what is off by default

| Part | Where | Switch (off when absent) |
| --- | --- | --- |
| Proposal turn after the root's recorded answer | `acquisition.clj`, `external_task.clj`, `runtime.clj` (`:after-root-done`) | `aljure_contract.acquisition = {arm: "C" or "E"}`; needs `aljure_contract.artifacts` |
| Validation and promotion (no model call) | `acquisition.clj` (`promote!`, CLI `-m repl-lab.acquisition promote`) | Called only by the trajectory runner |
| Exact-reuse memo (arm C) | `skills.clj` (optional `:memo` pin), `external_task.clj` | Only when a library version names a memo |
| Trajectory plans, runner, rollback, report | `benchmark/paired.py` | Only plans made by `trajectory-plan` |
| Pilot suite and panel importer | `benchmark/official.py`, profile `oolong-synth:thesis-pilot:validation` | Only `thesis-pilot-prepare` |

When the switches are absent, nothing changes. The 98 configs and plans under `config/`,
`research/` and `var/` give the same `capabilities()`, `aljure_contract()` and
`learning_library_sha256` hashes before and after this change. `model_protocol.clj`, the
prompts, the task tools and `executable.clj` are unchanged.

## 2. Partitions

**Suite:** `python3 -m benchmark thesis-pilot-prepare --cache var/official-cache --out var/official/thesis-pilot-validation-v1 --offline`.
- Suite hash (built offline from the pinned cache): `b7518ae3aed979a64667c2ec6f4ab0fbf2f96db554afe9d65a30b68f604312d0`.
- Source shards: `validation-00003-of-00009.parquet`, `validation-00006-of-00009.parquet` (pinned).
- Metadata columns are read first. A row group that holds a held-out row is never read
  further. The sealed held-out suite is test-split; no held-out path is opened.

| Family | Windows `(context_len, window)` | Tasks |
| --- | --- | --- |
| F1 `trec_coarse` (compatible) | (4096,6), (8192,10), (16384,12), (16384,13), (32768,1), (65536,3), (65536,4), (524288,12) | 16 |
| F2 `spam` (incompatible taxonomy, same record format) | (65536,10000), (65536,10001) | 4 |

- **Excluded:** (32768,0) and (8192,9). Earlier suites exposed them. A scan of all prepared
  suites on this machine (held-out paths skipped) finds no other exposed `trec_coarse` or
  `spam` window.
- **Step 0** measured (32768,1), (65536,3) and (65536,4) offline only. No model saw them.
- **Question selection:** per window, one `NUMERIC_ONE_CLASS` counting question when the window
  has one, and one other counting question. Each is a seeded choice by task type and id
  (`random.Random("0:<dataset>:<len>:<window>")`). Answers play no part.
- **Result:** 10 comparison, 9 numeric and 1 label answer types over the 20 tasks. The
  (524288,12) window has no numeric counting question. Task ids are in the manifest
  (`selection.families`).

**Development panel** (`controller/panel.json`, mode 0600, hash in the manifest; never shown to a model):

| Panel window | Records | Scored items | Items whose text also occurs in a task window |
| --- | --- | --- | --- |
| `trec_coarse` (32768,0) | 787 | 787 | 780 |
| `trec_coarse` (8192,9) | 188 | 188 | 187 |
| `spam` (4194304,10019), header + first 1085 records + footer | 69,898 | 1085 | 627 |

- Panel windows are disjoint from every task window and from the held-out suite.
- **Disclosure:** record texts are not disjoint. The windows share an instance pool, and the
  524288-token task window alone holds almost every `trec_coarse` text. An item-disjoint panel
  keeps 8 `trec_coarse` items, so it is not usable. The overlap therefore stays, and it is
  reported: promotion uses gold for records that later tasks also contain. The model never sees
  panel gold. It sees only promotion outcomes, through what is preloaded later.
- The spam panel window is a derived prefix of a 10 MB window; its header still names the full
  record count. This is recorded in the panel file (`derived`).

## 3. Arms (same model, settings, prompts, tools and per-task caps)

| Arm | State carried between tasks | Proposal turn | Validation |
| --- | --- | --- | --- |
| A | None | Never offered | None |
| C | Exact reuse: memo `sha256(trimmed record text) -> label`, and functions keyed by the exact task question | Offered | None. Promoted as proposed |
| E | Validated record classifiers with applicability predicates; structural patch and composition | Offered | Preregistered panel rule (§4) |

- **Isolation:** each (arm, ordering) trajectory has its own directory, library
  (`<trajectory>/library`), ledger (`trajectory.jsonl`), results and receipts. Nothing is shared.
  Arm A has no library directory.
- **C memo use:** before the first model call, the controller hashes this context's record
  texts (each line, and each ` || ` field without its `Name: ` label, trimmed). Only exact matches
  are defined in the worker as `exact-label`. No match refuses it, with reason `:no-exact-match`.
- **C functions:** the controller writes the predicate `(fn [input] (= (:question input) "<question>"))`.
- **E structural change:** with `replaces`, a proposal whose forms differ from the replaced
  function in one subtree becomes an `artifact/patch` of it (path recorded). Anything else is a
  rewrite with `:parent` set. A function that names approved exports depends on them by exact
  hash (composition). A replaced entry becomes `:superseded`.

## 4. Preregistered promotion rule (arm E)

Stored in `config/thesis-pilot-sonnet.json` (`trajectory.promotion_rule`) and frozen by the plan hash.
Exact integer arithmetic. Promote only if all hold:

1. **Candidate:** over the panel windows its applicability predicate admits, it decides at
   least **1/10** of the records, and at least **19/20** of its decisions are correct. No
   execution error and no non-label result. At least one window is admitted.
2. **No library regression:** the new version's panel precision and coverage are not lower
   than the current version's. A version labels a record with its first approved entry, in
   library order, that is admitted on that window and decides it. Coverage uses all panel
   records. A version that decides nothing has no precision to keep.
3. **Corrected promotion evidence:** `artifact/promotion-evidence` with `:verified-cases` and
   `min-score-improvement 1`. No record that the current version labels correctly is lost, and
   at least one more record is labelled correctly.
4. **Structure:** no reserved or conflicting name; at most 16 preloaded functions.

Otherwise the candidate is kept as rejected (artifacts and receipt, with reasons) and the pin
does not change. A growing library is never assumed better. Validation runs in fresh isolated
SCI workers (one for approved entries, one for the candidate), with no model call. Receipts hold
case ids, pass/fail and counts, never a gold label.

## 5. Proposal turn and the trajectory

**Turn.** After the root's `done` is accepted (the answer-format notice, if on, still acts
first), the controller writes `answer.txt` and `answer-recorded.json`. Then, in C and E only, it
sends one request in session `"proposal"`: the full root history, the `done` result
"Answer recorded … Optional, one turn, no penalty …", the task tools plus `propose_artifact`
and `skip_proposal`, and no cache marker.

- `propose_artifact` (E): `name`, `description` (≤ 240), `function_source` (`(fn [text] ...)` →
  label string or nil), `applicability_source` (`(fn [input] ...)` → boolean over
  `{:question :context}`), optional `replaces`.
- `propose_artifact` (C): `name`, `description`, `memo_source` (evaluated in the session's own SCI
  worker; a map from record text to label), optional `function_source`.
- A decline, a text reply or another tool is recorded as declined. A malformed input is
  recorded as malformed. Nothing in the turn can change the recorded answer. No budget, time
  or call remains → not offered (recorded).

**Trajectory** (`run_trajectory`), per task k:
1. Verify the panel bytes and every committed pin (bytes and parent chain). Fail closed.
2. Run the task on the pin in force. Record its answer, result row and ledger row.
3. Only then (C, E) run `promote` in a fresh JVM. Commit the new pin only for a complete,
   approved receipt whose version verifies against the pin in force.
4. Task k+1 gets exactly the committed pin. A rejection, a decline or a crash keeps the pin.
   A crash leaves no partial version (atomic writes); anything it wrote is listed as an orphan
   and kept.

- **Cold restart:** the runner stops after task 10. The next `trajectory-run` call (new process,
  new JVMs, new conversations) resumes from the trajectory directory alone.
- **Rollback:** `trajectory-rollback --to <pin> --reason ...` puts an earlier committed pin in
  force, recorded in the ledger.
- **Orders:** seeds 101, 202, 303. Each order puts F2 at positions 9, 12, 15 and 18. A, C and E
  share each order.

## 6. Endpoints (`trajectory-report`, from recorded evidence only)

- **Score:** official scorer per task; mean per arm and family.
- **Cost per verified solution** (score 1.0): all task inference plus acquisition, per arm and
  family. Task inference is every root and child call, so the model's handling of records the
  library left unresolved (fallback) is always charged. Acquisition is the proposal call, split
  out by provider id. Validation is reported in local seconds.
- **Activation split:** eligible reuse, correct refusal (an F2 task refused only functions F1
  tasks proposed, or the memo for lack of an exact match), direct answer, and the rest.
- **Library quality per version:** panel precision and coverage of each committed E version
  (receipts).
- **Break-even position:** the first task after which cumulative cost stays at or below arm A's
  on the same order.
- **Seen-record share:** per task, the share of its records that earlier windows of the same
  trajectory held (for endpoint 2 below).

## 7. Falsification (`RESEARCH_THESIS_REVIEW.md` §5, with the operator's notes)

The thesis is **falsified at this scale** if any of these holds:
1. E fails both, on F1, with activation of at least 80%:
   - cost per verified solution ≤ 0.8 × A's, all acquisition and fallback included, with mean
     score ≥ A − 0.03;
   - mean score ≥ A + 0.05 at no more than A's cost.
2. E's advantage over A disappears on tasks whose records were not seen in earlier windows
   (E ≈ C: caching, not generalization).
3. E scores below A − 0.05 on F2 and the controller did not refuse.
4. Break-even needs more than 16 related tasks.

If activation stays below 80%, or no artifact is promoted, the result is **uninformative**, not
negative. Report it, then run arm B.

## 8. Budget

- **Per task** (all arms): 12 calls including the proposal turn, 300 s, `usd_per_arm` 5. The
  gateway reserves a whole-context worst case per call (about $4.33), so a task can start a
  call only while its recorded spend is at most about $0.67. Worst case per task: $5.
- **Pilot cap:** $40 API-rate-equivalent. A task starts only if the recorded spend plus unknown
  reservations of all nine trajectories, plus a $1 margin, is within $40.
- **Estimate:** 180 task runs at $0.04–0.08 → $7–15. 120 proposal turns (C, E) re-read the
  conversation without cache: about $0.03–0.09 each → $4–11. Likely $11–26 in total. Validation
  costs only local SCI seconds.

## 9. Event schema additions (task ledger, `events.jsonl`, `result.json`)

| Event | Payload |
| --- | --- |
| `:artifact-memo-loaded` | `:memo-sha256`, `:hits` |
| `:artifact-applicability` | as before; new reasons `:exact-match`, `:no-exact-match` (name `exact-label`) |
| `:artifact-proposal` | `:decision` (`:proposed`, `:declined`, `:malformed`, `:not-offered`), `:reason`, `:request-id`, `:provider-id`, `:name`, `:replaces`, `:memo-counts`, `:proposal-sha256` |
| `result.json :acquisition` | the proposal summary and `:spend {:session "proposal" :calls :usd :provider-ids :unknown}` |

## 10. Evidence status and what remains

- **Offline (done):** `acquisition_test.clj` (12 tests) and `test_thesis_trajectory.py` (14 tests)
  use scripted fixtures only. They are labelled FIXTURE: they prove the plumbing, not that a
  model proposes useful code.
- **UNVERIFIED in the real worker** until the operator runs, in `repl-lab`:
  1. `python3 scripts/clj.py -m repl-lab.sci-contract artifacts` → `var/artifact-path-proof.json`
     (stale: `external_task.clj`, `skills.clj` and `runtime.clj` changed).
  2. `python3 scripts/clj.py -m repl-lab.sci-contract acquisition` → `var/acquisition-proof.json` (new).
  3. `python3 -m benchmark trajectory-acquisition-fixture --config config/thesis-pilot-sonnet.json --out var/benchmarks/thesis-acquisition-fixture`
     → `var/acquisition-relay-proof.json` (scripted responses through the real gateway, SCI worker
     and promotion JVM; run after the final commit).
  4. The subscription relay proof for this config (`paired-relay-fixture --provider claude-oauth-subscription --config config/thesis-pilot-sonnet.json`), if its transport contract differs.
- **Freeze:** prepare the suite, then `trajectory-plan`, `trajectory-preflight` (must be ready),
  operator approval of the exact plan hash, then `trajectory-run --trajectory <id>` twice per
  trajectory (before and after the cold restart).

## 11. Known limitations

- E promotes record classifiers only (`(fn [text] label-or-nil)`), because the rule measures
  record precision. Parsers and tallies are not promoted; the parser cost route is not tested.
- The proposal turn changes the tool list, so the provider cache cannot be used for it. This
  is charged as acquisition and it raises E's and C's cost. A cheaper turn is future work.
- `trajectory-report` reads only recorded files. Scores need a complete trajectory.
- The panel overlap in §2 can make E's panel precision optimistic for records that recur in
  later tasks. Endpoint 2 and the seen-record share are the check.
