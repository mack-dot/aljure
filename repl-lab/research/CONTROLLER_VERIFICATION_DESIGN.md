# Controller verification: verification as an executable property of the harness

**Status:** design and a frozen development experiment. Nothing here is built
yet, except the asynchronous-child ledger it reuses (`src/repl_lab/elastic.clj`,
phase A of `ELASTIC_IMPLEMENTATION_PLAN.md`). No model calls were made.

**Scope:** this document is the primary design for verification and
completion. `EVIDENCE_DRIVEN_COMPUTE_SPEC.md` refers to it for the done-time
pipeline and covers only the wider allocation policy.

**Evidence:**
- Script: `scripts/verification_trace_analysis.py`. It reads the execution
  checkout `/Users/mackianni/aljure-review-v1` only and makes no model calls.
- Output: `evidence/controller-verification/l-traces.json`.
- Inputs: 33 Aljure and 32 Prime finished arms of plans L0, L1 and L2 on the
  dev label-count suite (`dc164044…`, 11 tasks). L3 had not started when the
  script ran.
- Dev-suite gold was used for offline error analysis only.

## 1. What the L0–L2 traces show

| # | Finding | Numbers | Consequence for the design |
| --- | --- | --- | --- |
| F1 | **Optional prose capabilities are not used** | L2 (prose + helpers loaded): 0 of 11 arms used `:unknown`, `audit-labels` or `show-items`. Over L0–L2: 4 `show-items` calls in 1 arm, 0 audits, 0 evidence-gate firings | A check must not depend on the model calling it. The L3 gate fires only on an open audit (`runtime.clj:276-295`), so it can never fire when no audit is made |
| F2 | **Format failures are Aljure-specific** | 3 of 33 answered Aljure arms put prose after `Answer: N` ("This is an estimate…"). The official parse takes the text after the last colon (`benchmark/vendor/oolong_synth.py:16`), so `int()` fails and the score is 0 (`:63-71`). Prime: 0 format failures in 31 answers | A deterministic format check at `done` removes the failure class. Here the three counts were far off, so the observed loss was about 0. On an exact task the loss is 1.0, as in F2 task 1 (`CONTRACT_ABLATION_RESULTS.md`) |
| F3 | **Evidence is often already in the worker** | 22 of 33 answered arms kept their per-item decisions in SCI state. In 13, literal id collections sum to the answer or to its complement; 14 define an atom collection. The model's own pattern: an atom holding a set of item indices, updated per page, then counted | The controller can **extract** typed evidence at `done` without asking. It asks once only for the remaining third |
| F4 | **Most count error is shared with Prime** | The per-task mean signed error of Aljure and Prime correlates at r = 0.865. The signs agree on 8 of 8 tasks with a mean of at least 2: app_reviews negative −21 and −20; MultiNLI neutral +13 and +14; formality informal −17 and −18. One error is Aljure's own: formality "formal", +21.7 against +3.7 | A same-model reviewer will probably share most of this bias. Semantic review must be **measured** before it is trusted; its expected benefit on these counts is small |
| F5 | **Noise is large** | Prime's MAE was 6.0, 8.6 and 11.8 over identical L0/L1/L2 runs. One Prime arm moved from −1 to +30 | One run per configuration cannot detect MAE effects below about 5. The experiment repeats tasks and reports per-task paired differences |
| F6 | **The model did delegate** | 2 of 33 arms (MultiNLI) called `agent_call` 4 times each, one child per 110-item chunk, with free-text child summaries | Children are used when chunking is natural. Their results are untyped text |

MAE convention: an unparsed answer counted by its leading number gives the
coordinator's L0 figure, 12.5. Counting parsed answers only gives 9.8. The
document reports both where it matters.

## 2. Principles

1. **Completion is the trigger.** Every root task ends with `done`, so the
   verification pipeline runs on `done` and the model cannot skip it.
2. **Extract, then ask once.** The controller reads evidence that the model
   already built. It asks for typed evidence only when extraction fails, and at
   most once.
3. **The controller never changes the answer.** It decides one of three
   things: accept, send one bounded notice, or accept and report the
   unresolved evidence.
4. **Model confidence is never evidence.** Text in replies is never parsed for
   certainty. Only executed state, tool results and independent judgements count.
5. **Format is checked separately from semantics.**
6. **Every loop is bounded** by fixed per-task counters declared in the plan.
7. **A generic core with pluggable task verifiers.** A verifier is trusted
   controller code, hash-pinned in the plan, and gold-free.
8. **The prompt stays minimal.** No system-prompt text is added. Model-visible
   text appears only in a notice that actually fires.
9. **Activation is an endpoint.** Every stage records whether it was
   eligible, whether it fired and what it changed.

## 3. The done-time pipeline

Switch: `aljure_contract.controller_verification`, a map, off by default. It
is declared in capabilities only when on, like the existing switches
(`benchmark/paired.py:80-104`). The pipeline runs on a root `done` or
`done/eval`, at the point where the evidence gate runs now
(`runtime.clj:315`), and before `finish-session!`.

```
root done ──► V0 format ──► V1 extract evidence ──► V2 invariants ──► V3 review decision ──► V4 stop rule
                 │                │                       │                  │ (blind reviewer child)
                 └── notice? ─────┴────── notice? ────────┴──── notice? ─────┘
```

### V0 Format (answer contract)

- The task verifier supplies an **answer contract**: a pattern and a maximum
  length, taken from the task family's public answer form. Example for OOLONG
  label counts: `^Answer: (0|[1-9][0-9]*)$`, at most 64 characters.
- The summary is checked verbatim. Nothing is extracted or repaired.
- On a failure, while the format counter is 0: send the format notice and do
  not accept the answer. The format counter is separate from the existing
  command-correction counter (`runtime.clj:256-268`).
- The notice (fixed template, about 40 words): "Not submitted: the answer must
  match the required form exactly, as one line with nothing else, for example
  `Answer: 12`. Your summary has N lines. Call done again with only the
  answer."
- A second failure is accepted as is and recorded as `format: failed`. The
  controller never trims the text, because trimming would be guessing.

### V1 Evidence extraction

- One fixed, read-only SCI expression is evaluated in the root's existing
  worker. This is how the evidence gate already queries `aljure-audit`
  (`runtime.clj:286-288`).
- Candidate vars come from the `def` names in the recorded `repl_eval` sources.
  The controller already holds those sources in the ledger. No reflection
  over namespaces is needed.
- For each candidate the probe returns a bounded summary: kind (set, map,
  vector or atom of these), count, whether all elements are integer ids in
  `[0, n)`, and for a map, a label histogram with at most 16 labels.
- Output is bounded to 16 KB.
- The probe source is hashed. It must pass an SCI contract probe before any
  plan may use it (phase V-A).

**Typed evidence (canonical EDN).** This is the one interface. The model may
also bind it itself to `aljure-evidence`, but it is never told to.

```clojure
{:evidence/version 1
 :scope    {:kind :records :count 602}          ; from the task verifier, never from the model
 :items    {17 :formal 18 :informal}            ; id -> label, or
 :selected #{17 42}                             ; the ids counted by the answer
 :unsure   #{}                                  ; ids the model left undecided (optional)
 :answer   {:value 285 :link [:selected :count]}; how the answer follows; nil when unlinked
 :provenance {:var "formal-ids" :kind :atom-set :source :worker-state :call-sequence 41}}
```

**Linking rule (deterministic).** The controller reads an integer answer from
the summary through the verifier's contract.
- It prefers an id→label map whose histogram contains the answer.
- Otherwise it takes an id set whose count equals the answer (`[:selected :count]`)
  or `n` minus the answer (`[:selected :complement]`).
- On a tie, the var defined last wins.
- With no match, the status is `:unlinked`. SCI computation is never
  restricted: the controller only reads what exists.

### V2 Invariants

| Invariant | Generic or verifier | Check | Action on failure |
| --- | --- | --- | --- |
| ids in scope | generic | every evidence id is in `[0, n)` | targeted notice listing at most 10 bad ids |
| no duplicates | generic | vector evidence has unique ids | targeted notice |
| answer linked | generic | V1 status `:linked` | **evidence request**, once |
| map coverage | generic, map evidence only | every id in scope has a label or is in `:unsure` | targeted notice: count and up to 25 missing ids |
| shown coverage | generic, report only | share of scope records whose whole text appeared in a model-visible tool result (exact line match over recorded results) | none; recorded. `ADAPTIVE_COMPUTE_POLICY.md` showed partial coverage alone is a poor trigger |
| answer range | verifier | e.g. `0 ≤ answer ≤ n` | targeted notice |

**Evidence request** (fixed template, about 60 words, at most once): "Not
submitted: your answer is not linked to recorded per-item results. Keep one
decision per record in SCI, either as a set of the counted record ids or as a
map from id to label, compute the answer from it, then call done. If you
cannot, call done again to submit as is."

### V3 Review decision and the blinded review protocol

**When.** Review needs all of these:
- the verifier marks the task aggregate;
- the evidence is linked;
- the allocator authorizes it (section 4).

A random audit can also select a task that the allocator skipped.

**Sample.**
- Seed: `sha256(run-id, task-id, "review-v1")`. It is reproducible from the ledger.
- Strata:
  - `k_sel` ids from the selected (or labelled-positive) set;
  - `k_rest` ids from the complement;
  - every `:unsure` id, at most 8.
- The first two strata are **confident decisions**: the model did not mark
  them unsure. So the random audit of confident judgements is built in.
- Default `k = 24`, with 12 per stratum.

**Reviewer.**
- One controller-dispatched elastic child per task (`elastic/spawn!` with the
  controller as caller, phase V-C). Same model, `:inherit` profile.
- Its own quota: 2 calls and the `:review-usd` cap. It has no SCI worker; the
  records are inline.

**Blinding.** The reviewer request contains only:
1. a fixed reviewer instruction (versioned, hashed in the plan);
2. the task question, verbatim;
3. the sampled records' text, shuffled with the seed and renamed `r1…rk`.

It never contains the root's answer, labels, var contents, history or worker.
The contract auditor checks this deterministically: the reviewer's request body
must equal the template rendered from (instruction hash, question, sampled
records), and nothing else.

**Reviewer output.**
- A `done` summary holding one EDN map `{"r1" "yes" …}`, with values in
  `yes | no | unsure` ("does this record count toward the answer of the
  question?").
- The controller validates it with the bounded EDN reader: every `r` id exactly
  once. One malformed reply is refused, and the review is then recorded as
  `failed`. A failed review never blocks acceptance.

**Comparison.** `D` is the set of ids where the reviewer's yes/no differs from
membership in the selected set. A reviewer `unsure` is reported, not counted.

**Outcome.**
- `D` empty: accept.
- `D` not empty and the review counter is 0: one **targeted-review notice**
  (about 45 words): "Not submitted: an independent check of 24 sampled
  records disagreed with your decisions on records [ids]. Reread these records,
  decide each, update your result if needed, then call done." The notice does
  not say the reviewer is right.
- The next `done` runs V0–V2 again with no second review, and is accepted.
  `D` and its resolution are recorded.

**Estimate, report only.** From the two strata the controller computes a
stratified estimate of the root's error in each direction. That gives a
corrected count with a 90% interval. It goes into the verification record, as
a measured endpoint, and **never** replaces the answer.

### V4 Stop rule (deterministic, bounded)

Per task, each counter allows at most 1: format notice, evidence request,
review round, targeted notice. So at most 3 extra root turns and at most 2
reviewer calls. On each root `done`:

```
run V0..V2 (and V3 at most once)
if a check fails and its counter is 0      -> send that notice, counter := 1, do not accept
elif budget or wall left < the plan floor  -> accept; record "verification skipped: budget"
else                                       -> accept; record every unresolved item
```

- Notices go in a fixed priority order: format, then evidence request, then
  invariants, then review.
- No path issues a second notice of the same kind, so the pipeline cannot loop.
- The plan's normal call, token, cost and time caps still apply.

### Accounting, events and reproducibility

**Events:**
- `verification-check` {stage, eligible, result};
- `evidence-extracted` {var, kind, count, link};
- `verification-notice` {kind, executed false};
- `review-dispatched` {seed, sample-sha256, k, child};
- `review-result` {agree, disagree, unsure, estimate};
- `verification-accepted` {unresolved, skipped}.

**Accounting:**
- Reviewer calls use the elastic reservation path: a shared run budget, a
  root floor and a per-child quota.
- A reviewer call whose outcome is unknown halts further review for the task.
  The run itself goes on, and the unknown outcome is still reported.

**Contract auditor** (`scripts/contract_audit.py`): the switch is on; each
notice kind appears at most once and only after a root `done`; the
reviewer-blinding check passes; no notice follows an accepted answer.

**Reproducibility:** seed, template hashes, verifier hash and probe hash are
all in the plan or the ledger. Given the recorded reviewer replies, a replay
reproduces every decision.

## 4. Adaptive allocation (summary; policy detail in `EVIDENCE_DRIVEN_COMPUTE_SPEC.md`)

The allocator uses observable inputs only:
- answer type from the verifier;
- scope size `n`;
- V1 link status;
- remaining calls, cost and wall time;
- the plan's p95 call latency.

| Situation | Action | Extra calls | Expected benefit (dev evidence) |
| --- | --- | --- | --- |
| Format fails | format notice | 1 root turn when triggered | removes a failure seen in about 10% of Aljure arms (F2) |
| Aggregate, unlinked | evidence request | 1 root turn | enables V2/V3 on the remaining third of tasks (F3) |
| Aggregate, linked, `n ≥ 50`, budget for review + 1 turn + floor, wall ≥ 2 × p95 | review, `k = 24` | 1–2 reviewer calls (about $0.03–0.06), plus 1 root turn if `D` is not empty (about $0.02–0.04); +10–25 s | **unknown; probably small on these counts (F4)**. The experiment measures it |
| Non-aggregate answer (label, comparison, date) | format only | 0 | — |
| Random audit (probability 0.2, seeded, at most 3 per run) on a task the allocator skipped | review, **measurement only**: no notice is sent, so the audited trajectory stays unchanged | reviewer calls only | estimates how often the skip rule passes a confidently wrong answer |

## 5. Pluggable task verifiers

A verifier is a trusted map of pure functions in `src/repl_lab/verifiers/`:
- reviewed;
- hash-pinned in the plan;
- declared in capabilities.

It never reads gold, never calls a model and never runs model-authored code.

```clojure
{:id "oolong-label-count-v1"
 :answer-contract {:pattern "^Answer: (0|[1-9][0-9]*)$" :max-chars 64}
 :aggregate? true                                     ; the answer is a count over records
 :scope (fn [public-context] {:kind :records :count n :records [...]}) ; item lines after the header
 :invariants (fn [evidence answer scope] [])          ; extra checks; [] = none
 :review {:question :verbatim :decision ["yes" "no" "unsure"]}}
```

- **`generic-v1`** is the default. It has no contract, `:aggregate? false`, and
  no review. With it, only typed evidence the model binds itself is checked.
- **Coding tasks:** a verifier runs the task's declared tests or contracts in
  the isolated worker. Completion means the tests pass; it is reported, not
  forced. Review there means a reviewer child reading the diff, which is not
  in this experiment. No single completion gate covers all task types.
- **Fairness:** a verifier is an Aljure harness capability. It is disclosed in
  capabilities like `sci-verify` is. Prime is unchanged.

## 6. Isolation and the minimal prompt

- The extraction probe is read-only SCI in the same worker. It adds no
  namespaces, classes, host access or output bound. Its hash is pinned by the
  SCI contract proof.
- The reviewer has no worker. Its records come from the immutable context
  block on the controller side (`controller.clj:164-187`).
- Model-supplied evidence is data, read only through the bounded EDN reader
  (`util.clj:21-44`).
- With the switch off:
  - tool definitions and system text are byte-identical;
  - no probe runs and no event is written.

  This is tested in the same way as `verification_test.clj` and
  `elastic_test.clj`.
- With the switch on, system text is still unchanged. Only a notice that
  fires is visible to the model.

## 7. Frozen development experiment: optional audits against controller-triggered verification

**Question.** Does verification that runs on `done` remove delivery failures
and reduce count error more than optional audits, at the same inference cost?
Separately, does blind semantic review add anything beyond one more turn?

**Suite:**
- Primary: the dev label-count suite `dc164044…` (11 tasks, 5 window
  clusters), 3 repeats.
- Side effects: the 21-task dev suite `b157ee63…`, 1 repeat, for
  non-aggregate tasks and adaptivity.
- The sealed held-out suite `c74547bd…` is not touched.

**Aljure arms** (Opus 5.5; base contract F1; identical except for the switch):

| Arm | Contract | What fires |
| --- | --- | --- |
| **V1 optional audits** | the L2 configuration (`structured_labels`, `uncertainty_audit`) | nothing unless the model audits (F1 predicts nothing) |
| **V2 done-triggered verification** | `controller_verification {review: off}` | V0 format, V1 extraction, V2 invariants, evidence request |
| **V3 adaptive review** | `controller_verification {review: adaptive}` | V2, plus blind review and the targeted notice |
| **V3s matched self-check** | `controller_verification {review: self}` | V2, plus one **unblinded** "recheck these records" notice on the same sampled ids, with no reviewer. It uses the same root-turn budget as V3, and the money V3 spends on the reviewer is left unspent and reported |

**Matched budgets.**
- V3 and V3s have the same extra root turns by construction. V3 adds 1–2
  reviewer calls.
- All arms are compared on an accuracy–cost plot. V3 must beat V3s at no more
  than V3's realized cost.

**Prime reference.** No Prime re-runs. The reference is the pinned Prime arms
already recorded on these suites:
- L0–L2 on `dc164044…`: 32 arms finished when this was written, plus L3
  when it finishes;
- control, F1 and F2 on `b157ee63…`.

They are cited by plan hash. This needs the Aljure-only plan support in
`COMPUTE_SCALING_EXPERIMENT_PLAN.md`, section 5. If that support is not
approved, add one Prime block once, for about +$17.

**Endpoints.**

*Activation (first-class), per arm:*
- eligible tasks;
- for each stage: fired, and acted (the answer or evidence changed);
- extraction success rate;
- reviewer validity rate;
- review disagreement rate;
- share of disagreements the root changed.

*Delivery:*
- official parse-failure rate;
- completion.

*Accuracy:*
- count MAE, by both conventions;
- signed error;
- per-task paired difference against V1, with a 95% cluster bootstrap over windows;
- official score.

*Review validity (offline only):*
- MultiNLI has per-item gold (`evidence/multinli-count/dev-gold-labels.json`).
- Measure the reviewer's accuracy on sampled items, and the precision of `D`:
  the share of disagreements in which the reviewer matches gold.
- Measure the error of the reported estimate.

*Cost and latency:*
- cost, calls, input and output tokens;
- p50 and p95 latency;
- extra turns;
- reviewer cost;
- Aljure/Prime cost ratio against the reference.

*Integrity:*
- auditor violations (target 0);
- blinding-check failures (target 0);
- unknown outcomes.

**Decision rules (fixed before any run):**

1. **V2 is adopted** only if all four hold:
   - the official parse-failure rate is 0 over all V2 arms;
   - evidence is linked (extracted or after the request) on ≥ 90% of aggregate tasks;
   - V2's MAE is no worse than V1's by more than 2.0 (pooled over repeats);
   - the Aljure/Prime cost ratio stays ≤ 0.6.
2. **V3 is adopted over V2** only if all of these hold:
   - review fires on ≥ 90% of eligible tasks;
   - mean per-task absolute error is lower than V2's on ≥ 7 of 11 tasks;
   - pooled MAE is lower than both V2's and V3s's;
   - the cost ratio stays ≤ 0.6;
   - offline `D` precision ≥ 0.5 on MultiNLI.

   Otherwise: "no benefit from blind same-model review shown". F4 predicts
   this outcome. The finding then points to calibration or a different
   reviewer profile, not to more review calls.
3. **A mechanism with activation below 50%** of its eligible tasks is reported
   as "not activated", never as "no effect".
4. **Development evidence only.** A passing configuration goes next to a new
   dev dataset and then, with separate approval, to the sealed held-out suite
   once.

**Projected cost** (API-rate equivalent; Opus per-arm costs measured in L0/L1:
Aljure $0.22–0.24, Prime $0.53):

| Block | Arms | $/arm | Total |
| --- | --- | --- | --- |
| Count suite: V1, V2, V3, V3s × 11 tasks × 3 repeats | 132 | 0.23–0.32 | $30–42 |
| 21-task suite: V2, V3 × 21 | 42 | 0.08–0.10 | $3–4 |
| Prime | 0 (reference reused) | — | $0 (or +$17) |
| **Total** | 174 | | **about $35–46; hard cap $70** |

Wall time is about 3 hours sequential: about 65 s per count arm and 30 s per
21-task arm.

**Stop rules:** as in `REVIEW_ABLATION_PROTOCOL.md`. Any isolation refusal,
unknown provider outcome, Docker restart or unconfirmed cleanup stops the plan.

## 8. Build order (phases V-A to V-D; file-level detail in `ELASTIC_IMPLEMENTATION_PLAN.md`)

**V-A, offline:**
- the answer-contract checker and the stop-rule counters, as pure functions;
- the extraction probe source;
- the linking rule;
- the typed-evidence validator;
- the `oolong-label-count-v1` and `generic-v1` verifiers;
- tests over the recorded L0–L2 sources as fixtures.

**V-B, offline:**
- runtime wiring at `done`, behind the switch, with scripted providers and
  stub workers, in the style of `verification_test.clj`;
- byte-identity tests;
- auditor rules.

**V-C:**
- the reviewer dispatched as an elastic child, with blinding;
- a blinding auditor test;
- the relay fixture.

  This needs Docker, so it runs after the live chain ends.

**V-D:**
- the SCI contract probe for the extractor;
- the review fixture through the real gateway;
- freezing the four plans.

Then the operator approves the run.
