# Deterministic verification primitives for SCI

**Purpose:** let the model check, cheaply and without a model call, whether its
own computation is complete and consistent. Then extra model judgement goes only
to the items that are still open.

**Status:**
- Implemented in the dev repo, behind a plan switch that is off by default.
- Proven in the real isolated worker.
- Not run live.

## The three properties, kept apart

| Property | Meaning | Checkable deterministically? | Interface |
| --- | --- | --- | --- |
| **Structural completeness** | Every expected item was processed and shown whole; none missing, extra or duplicated | **Yes** | `audit-labels`: missing, unexpected, repeated. `show-items`: whole items, and `:never-shown-count` |
| **Computational consistency** | The counts and aggregates follow from the recorded per-item labels; conflicts and unknowns are visible | **Yes** | `audit-labels`: counts derived from labels, conflicts, unknowns, and the `:count-range` each count can still take |
| **Semantic correctness** | Each label is right | **No** | none. Needs model judgement or independent evidence |

**Rule:**
- No output of these helpers says a label is right.
- `audit-labels` carries its scope in its own report: `:checks "coverage,
  duplicates, conflicts and arithmetic only; not whether a label is right"`.
- `:complete true` means only that every expected id has exactly one known label.

## Interface (`resources/sci-verify.edn`)

**`(show-items xs start)`, `(show-items xs start budget)`**
- Returns whole numbered items of `xs` from `start`: as many as fit in `budget`
  characters (default 24,000), and always at least one.
- Ends with `[items a-b of n shown whole; next start k]`.
- Records the shown indices, so a later audit can report items never shown.
- It replaces ad hoc paging that cuts items. Sonnet Aljure cut 134 of 438
  MultiNLI pairs that way (`MULTINLI_COUNT_FAILURE_ANALYSIS.md`).

**`(audit-labels ids labels)`**
- `labels` is a map of id to label, or `[id label]` pairs from several passes or
  rules. `nil`, `:unknown` and `"unknown"` mark an undecided item.
- Returns:
  - `:expected` and `:labelled`;
  - `:missing`, `:unexpected` and `:repeated-count`;
  - `:conflicts`: ids with two or more distinct known labels;
  - `:unresolved`: ids with only unknown labels;
  - `:counts` for each known label;
  - `:count-range` for each label: `[resolved, resolved + every open item that could take it]`;
  - `:open` and `:complete`;
  - `:never-shown-count`, if `show-items` was used.
- Samples list at most 25 ids.
- The last report is kept in the worker, in `aljure-audit`.

**Not provided, on purpose:**
- **Answer-schema checks:** the requested form lives in task text, and parsing
  it would be benchmark-specific.
- **Provenance of every intermediate value:** SCI definitions already persist,
  and the ledger plus the audit carry the provenance that matters, which is item
  labels to counts.
- **Gold-dependent checks of any kind.**

## Switches (`aljure_contract`, all default `false`, nested)

*Renamed 2026-10-29 for the four-configuration review evaluation
(`REVIEW_ABLATION_PROTOCOL.md`).*

| Switch | Effect | Requires |
| --- | --- | --- |
| `structured_labels` | Loads `sci-verify.edn` into each root and child worker. Appends `resources/structured-labels.txt` (58 words): record one label per item and compute the answer from them; `show-items` pages whole items | — |
| `uncertainty_audit` | Appends `resources/uncertainty-audit.txt` (64 words): label unsure items `:unknown`; `audit-labels` reports coverage, conflicts, unknowns and count ranges | `structured_labels` |
| `targeted_review` | Appends `resources/targeted-review.txt` (13 words): reread and decide open items before `done`. Enables the evidence gate: at most once, a root `done` whose last audit left items open is answered with that audit, and the next `done` is accepted | `uncertainty_audit` |

**With every switch off:**
- the worker gets no new definitions: `audit-labels` is unresolvable (proof probe `verification-absent`);
- the system text is byte-identical (`prompt-text-appears-only-with-its-switch`);
- the declared capabilities are identical (`test_verification_switches_are_declared_only_when_on`).

## Isolation and contract

- The helpers are SCI functions evaluated inside the existing isolated worker:
  - no new namespaces, classes or host access;
  - the same denied-symbol list;
  - the same output bound.
- They use only `atom`, `swap!`, `reset!` and `deref`, all already available to
  model code.
- **SCI contract proof** (`var/sci-contract-proof.json`, copied to
  `evidence/verification/`):
  - status TESTED on the pinned image `sha256:58550c92…`, 76 results, all passed;
  - this includes 7 new verification probes: helpers absent when off, whole-item
    paging, coverage, conflicts, unknowns, count ranges, and the stored audit;
  - the proof now also hashes `sci-verify.edn`, and preflight refuses a stale proof.
- **A bug the proof found:**
  - The controller sends raw code to the worker, which reads it as EDN. EDN has
    no `@` reader macro, so the helper file and the gate's query must use `(deref …)`.
  - Without the proof, the gate would have silently never fired.
- **Evidence gate:**
  - The controller evaluates one read-only expression in the session's existing
    worker, the same way it initializes context. No model text is executed.
  - It is recorded as an `evidence-gate` event, with `executed: false`.
  - The contract auditor checks it: switch on, root `done` only, at most once,
    and only on an open audit.

## What the checks would have shown on recorded failures

| Recorded failure | Structural check | Consistency check | Semantic error left |
| --- | --- | --- | --- |
| Sonnet Aljure MultiNLI (110; 134 pairs cut) | **detects:** 134 items never shown whole | the answer was an estimate, with no per-item labels to count | yes |
| Opus Aljure MultiNLI (120) | passes: all 438 shown whole | **detects, if uncertain items are recorded as `:unknown`:** 11 open items, contradiction range [120, 131], gold 129 | partly. The review must decide the 11 items |
| Opus Prime MultiNLI (129) | passes | passes | none, net (±2 per page, cancelling) |
| Sonnet Prime MultiNLI (111) | **detects:** 57 pairs cut | passes over its recorded labels: 111 known, 0 open | 22 false negatives |

The rows above come from `evidence/multinli-count/analysis.json`. The Opus Aljure
row is constructed from its summarized thinking. That is what the audit would
report had it recorded what it said, not a replay of a live run.
Rows for the other weak tasks are in `ADAPTIVE_COMPUTE_POLICY.md`.

## Tests

- **Clojure** `test/repl_lab/verification_test.clj` (4 tests, 33 assertions):
  - the gate answers one `done` with the open audit, and the next `done` is accepted;
  - the gate costs nothing when off, when the audit is complete, when nothing was
    audited, or when no worker exists;
  - the prompt text appears only with its switch;
  - finalization provenance.
- **Python** `test_aljure_sci.py`: switch validation, the dependency rule, and capabilities declared only when on.
- **Python** `test_contract_audit.py`: the evidence gate is conformant only when on, root only, and once.
- **SCI proof:** 7 verification probes in the real worker.
