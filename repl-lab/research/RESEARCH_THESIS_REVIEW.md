# Research thesis review: has Aljure drifted from code-as-data?

**Type:** read-only architectural and historical review, 2026-10-29. No code
changed. No inference, Docker or held-out data was used.

**References:**
- `file.clj:N` means `repl-lab/src/repl_lab/file.clj` at `a1c2ce0` (tip of
  `claude/verification-v1`), unless a commit is named.
- `research/*.md` paths are at the same commit.
- Run numbers come from `var/benchmarks/*/report.json` in the dev checkout and
  in the `aljure-sonnet-pair-v7` and `aljure-review-v1` checkouts.
- The per-run table is in `HISTORICAL_PERFORMANCE_AUDIT.md`.

## Verdict

1. **The project drifted, and the drift is measurable.**
   - The last commit that touched any learning or artifact code is `41a1610`
     (10-27 01:25). The touched files are `artifact.clj`, `bundle.clj`,
     `skills.clj`, `live.clj`, `evaluation.clj` and `selector_*.clj`.
   - 89 of the 121 commits on `claude/verification-v1` came after it.
   - All 22 paired benchmark runs (450 arms, about $58.6 API-rate-equivalent)
     gave Aljure a hard-coded empty library (`benchmark/paired.py:579`; the
     value is sha256 of `[]`) and turned learning off
     (`external_task.clj:131`).
   - Live learning used about $2.6, including reserved amounts: one run, on
     10-26.
   - The operator's 10-26 work order put "learning curves and inference cost"
     third and "evolving Aljure versus native Prime" fourth
     (`research/EXPERIMENT_PROTOCOL.md:9-19`). Step 3 never ran. Step 4 ran,
     but with a **non-evolving** Aljure.
2. **This is not abandonment.** The artifact core is intact and tested. The
   learning question stayed explicit in the designs
   (`research/EXECUTABLE_LEARNING_EXPERIMENT.md`). Most benchmark work built
   infrastructure that any learning test needs: accounting, isolation, frozen
   plans and a usable SCI surface.
3. **The thesis is untested, not refuted.**
   - The only live evidence is positive but narrow: one retained scheduling
     policy transferred after a cold restart.
   - Agent-level reuse never occurred.
   - Structural transformation by a model never occurred.
   - Code-as-data has never been tested on any benchmark task.
4. **The current direction leads to a Prime-style harness.** Elastic children,
   compute scaling, review prompts and label audits are harness engineering
   for one benchmark. They do not test whether computation accumulates.

## 1. The original thesis, reconstructed

The root commit `3b905ff` is a squash. The master prompt it implements is not
in the repository (`PROGRESS.md:5` at `3b905ff`). Its sections can be
reconstructed from `ACCEPTANCE.md` §1–§16.

**What was intended:**
- **Purpose:** "A local Clojure experiment for executable skill retention"
  (`README.md:3` at `3b905ff`).
- **Hypotheses:** H1, retained executable skills improve held-out
  performance. H2, the benefit survives fresh processes and conversations with
  only approved executable artifacts. H3, matched Python arms (deferred)
  (`EXPERIMENTS.md:3-5` at `3b905ff`).
- **Learnable components:** "pure policy/analysis functions and declarative
  context/delegation workflows". Artifacts hold source and parsed forms. Only
  the controller approves and activates them (`ARCHITECTURE.md:8-12` at
  `3b905ff`).
- **Requirements:** structural forms, subtree operations and stale-target
  rejection (§6). A validation and promotion lifecycle (§9). An
  executable-only cold-boot export (§11).

**The thesis in one sentence:** a model in a constrained interpreter writes
pure functions and declarative workflows. The controller validates them
against a frozen rule and stores them as immutable, content-addressed program
values. Later tasks, also after a cold restart, run this computation instead
of regenerating it.

**It was never "every answer must be code."** Both arms could answer
directly and write task-local code (`EXPERIMENTS.md:7-10` at `3b905ff`).
`:done` with a text summary existed from the first commit.

**Why Clojure and SCI.** No document states a reason. The design implies four:
- reading is parsing (EDN), so source and forms round-trip with `pr-str`;
- nested lists and maps give stable paths for subtree hashes and patches;
- SCI gives an evaluator with no host eval, filesystem, network or interop;
- the controller runs on the JVM in the same language.

Language was a hypothesis, not an axiom. `213cf96` built a matched Python AST
backend with the same structural operations (`research/LANGUAGE_ARTIFACTS.md`).
That backend shows that structural manipulation does not need
homoiconicity. Homoiconicity makes it cheaper and canonical.

| Essential | Incidental |
| --- | --- |
| Programs as immutable, content-addressed, inspectable values | Clojure syntax as such; EDN command envelopes (replaced by native tools in `a965bd9`) |
| Structural addressing and transformation with stale-target checks | The scheduling simulator as the only domain |
| A constrained interpreter with no host authority | SCI specifically; Docker per session |
| Controller-owned validation, promotion and an executable-only export | SQLite through a Python bridge; the dashboard |
| Paired, budget-matched comparison against a stateless control | Prime parity as the reference point |

**Intended against demonstrated:**

| Claim | Demonstrated? | Evidence |
| --- | --- | --- |
| A model writes executable artifacts | Yes, once: 2 policies and 2 workflows | `research/FIRST_LIVE_RESULTS.md:69` |
| The controller validates them independently | Yes: 1 pair accepted, 1 rejected. The recorded gain (37,630) is inflated by three worker failures | same, `:87-92`; `artifact.clj:116` |
| Retained computation transfers after a cold restart | Yes, by direct controller execution: 8/8 complete, 59.5 against 204.1 ticks, 565 invocations. It only **matched** the fixed estimate baseline | same, `:9-10`, `:134`. Diagnostic replication: 94.2 against 206.5 ticks on 11 pairs (`research/POLICY_RUNTIME_DIAGNOSTIC_V1_RESULTS.md:62`) |
| The agent chooses to reuse | **No.** Zero `artifact/inspect` or `artifact/call` calls; every evolving agent synthesized a temporary policy | `research/SKILL_REUSE_ANALYSIS.md:28` |
| A model transforms a program structurally | **No.** It submitted a complete replacement | `research/FIRST_LIVE_RESULTS.md:83` |
| Workflow or harness improvement | Unproven. The run cost 4.3% less but used slightly more tokens | `research/FIRST_LIVE_RESULTS.md`, "What learned" |
| Clojure is better than Python | Untested live. The Python image is missing | `research/BENCHMARK_VALIDITY_AUDIT.md` §1 |

## 2. Drift timeline

| When (local) | Commit | Change | Class |
| --- | --- | --- | --- |
| 10-26 13:35 | `3b905ff` | Scheduling RLM with artifacts, structural patches, promotion and cold boot | Thesis core |
| 10-26 19:06 | `213cf96` | Python AST backend; Prime adapter; hypotheses renumbered: language H1, **learning H2**, Prime H3 (`research/EXPERIMENT_PROTOCOL.md:9` at `213cf96`) | Useful experiment; first demotion of learning |
| 10-26 19:35 | `bb20bb0` | Operator "restored the original goal". Work order: candidate, reuse and cold boot, learning curves, *evolving* Aljure against Prime, then language. "Do not add benchmark families or general orchestration infrastructure before the first live mechanism test" (`research/EXPERIMENT_PROTOCOL.md:9-19`) | Thesis core |
| 10-26 20:46 | `7126edb` | First and only live learning run | Thesis experiment |
| 10-26 21:47 | `fa55a44` | Postmortem: worker failures; "Do not add Prime benchmarking … while these results remain unresolved" (`research/FIRST_LIVE_POSTMORTEM.md:93`) | Essential diagnosis |
| 10-26 22:44 – 10-27 01:25 | `d347ba4` … `41a1610` | Skill discovery v2–v4 and selector acquisition (fixture only) | Thesis-supporting, never run live |
| 10-26 23:56 | `f9bf1d0` | OOLONG imports and common Messages adapters | Benchmark infrastructure |
| 10-27 00:49 – 10-28 11:15 | `c474438` … `a957de8` | Prime head-to-head V1–V7: receipts, Keychain, transport, Docker, EDN failures | Essential reliability, paid for by Prime runs |
| 10-28 11:37 | `a965bd9` | Native tool calls. The model sees 5 tools and **no artifact tools** (`model_protocol.clj:105-138`) | Essential interface; the artifact surface is lost |
| 10-28 14:16 – 19:57 | `79a3bd9`, `0c4c2d5`, `4cf04c0` | Assisted SCI surface, prewarm, AOT worker, reader syntax | Essential substrate |
| 10-28 15:45 | `00390f6` | Operator brief: **Q-HARNESS (Prime) becomes H1, Q-LEARNING becomes H3** (`research/STATISTICAL_EVALUATION_PROTOCOL.md:16-18`) | Priority inversion |
| 10-29 01:51 – 11:54 | `41b53fa`, `9bb4c95`, `f59c0fb` | Opus gap: truncation retry, terminal text, label and uncertainty prompts, evidence gate | Benchmark-specific; mostly unnecessary |
| 10-29 13:50 – 14:08 | `51f10c4`, `d441ddf` | Asynchronous children (486 lines, off by default), compute scaling, controller verification designs | Orthogonal or premature |

**Why it happened:**
1. **Reliability.** The first live run lost most episodes to worker startup
   and transport. Fixing that was necessary.
2. **Operator direction.** The 10-28 brief ranked the Prime comparison first
   (`research/BENCHMARK_CAMPAIGN_PROTOCOL.md:3`).
3. **A fast loop.** Each Prime run showed a gap that a fix could close. This
   loop rewards harness engineering.
4. **Domain coupling.** The artifact contracts fit the scheduler: a policy is
   `decide/2` (`skills.clj:58`), and a workflow is
   `{:strategy {:policy :context :delegate}}` (`artifact.clj:39-47`).
   OOLONG tasks had nothing to connect to.

**The project's own evidence about the recent work:**
- **Recursion:** "Neither harness gains from recursion on the measured tasks"
  (`research/ELASTIC_ARCHITECTURE_GAP_ANALYSIS.md:17`).
- **Optional prompt helpers:** 0/11 activation (`research/REVIEW_ABLATION_DECISION.md:13`).
- **F1 truncation retry:** triggered 0 times.
- **F2 terminal-text answer:** lowered completion to 19/21 (`research/CONTRACT_ABLATION_RESULTS.md`).
- **The Opus gap:** 2 of 4 losses were answer delivery
  (`research/SYNTH_INDEPENDENT_32K_OPUS_RESULTS.md`, "Where Aljure lost").
  Count bias correlates with Prime's at r = 0.865
  (`research/CONTROLLER_VERIFICATION_DESIGN.md:27`).

None of this measures accumulated computation.

## 3. Code-as-data capability audit

| Capability | State | Evidence and gap |
| --- | --- | --- |
| Programs as immutable, inspectable data | **Implemented; proven live** | Forms plus source with a hash; `verify` re-derives the forms (`artifact.clj:27-52`); overwrite is refused (`:56-60`); 4 live model artifacts. **Gap:** the hash covers the envelope (author, parent, source text; `:48-49`). The same code gets different hashes, and a cold-boot restore builds new envelopes with new hashes (`bundle.clj:41-43`; `evaluation.clj:9-11`) |
| Structural generation and transformation | **Implemented; not proven** | `subtree`, `replace-subtree` and `patch` with base and target hashes (`artifact.clj:81-101`); runtime ops (`runtime.clj:168-179`); tested offline (`test/repl_lab/runtime_test.clj:99`). No model has used a patch. The ops are absent from the benchmark tools. SCI denies `eval` and `read-string` (`model_protocol.clj:124`) |
| Provenance and exact identity | **Partial** | Parent, author, provenance and dependency closure (`artifact.clj:64`); export manifest hashes (`bundle.clj:44-47`). The live chain `834a4e…` → parent `aa1226…` and workflow `4160eb…` → `834a4e…` is preserved. No forms-only code identity exists |
| Validation before reuse | **Partial; proven once** | Paired development panel and frozen rule (`artifact.clj:103-120`; `live.clj:69`); selector gate v2. **Defects remain:** the sum-of-scores gain counts infrastructure failures; a failed episode is attributed to the retained hash; there is no revalidation or demotion (`research/EXECUTABLE_LEARNING_EXPERIMENT.md` §3). Analysis functions have no validation path |
| Persistence and retrieval across tasks and restarts | **Persistence proven; retrieval not** | Whitelisted bundle, fresh JVM, literal audit (`bundle.clj:31-81`; `test/repl_lab/experiment_test.clj:71`). Cold boot: 8/8 by direct execution. Model retrieval (`skills/list`, `policy/select`; `runtime.clj:159-166`) was never used live |
| Composition of validated functions | **Partial** | Dependency closure; the live workflow depends on the policy; ranker plus packer in fixtures. `artifact/call` runs one export in a **fresh worker** (`executable.clj:23-31`). The model's session code cannot call an approved function |
| Evidence-backed program improvement | **Partial; one instance** | One promoted policy beat a weak serial control and tied a fixed heuristic. No artifact has a validated second version |
| Declining code when a direct answer suffices | **Not tested** | Allowed (`runtime.clj:198`). But 0 of 176 finished paired Aljure arms answered without `repl_eval`, because the context lives outside the window by design (`external_task.clj:124-128`) |

**Cross-cutting finding.** Two independent experiments show that models do
not use optional computation:
- 0 retrievals of a retained skill (`research/SKILL_REUSE_ANALYSIS.md:28`);
- 0/11 activations of developer-supplied audit helpers (`research/REVIEW_ABLATION_DECISION.md:13`).

So a reuse test with model-optional retrieval mostly measures prompt
salience. Retrieval must be done by the controller, or it must be the
measured variable.

**Evidence of regenerated computation.**
- In A1c, ten arms wrote ten independent regex rule sets for the same context
  window. Pooled across 8 arms, items where two rule sets disagreed were wrong
  36% of the time, against 9% elsewhere.
- The analysis notes that a single task lacks a second rule set "unless the
  agent builds one or reuses a retained one" (`research/RESIDUAL_REASONING_ANALYSIS.md:34`, `:64`).
- 22 of 33 L0–L2 arms rebuilt the same per-item ledger pattern in SCI
  (`research/CONTROLLER_VERIFICATION_DESIGN.md:26`).

This is the waste the thesis targets, measured in the project's own traces.

## 4. Minimal architecture

1. **Model loop:** unchanged. Natural-language reasoning, the REPL, optional
   children and `done`. Code is optional. Text answers stay valid.
2. **SCI substrate:** a constrained interpreter. Before the first turn, the
   controller loads every *applicable* approved artifact into the session
   namespace as ordinary functions. It announces their names, interfaces and
   validation summaries in the task message, not in system-prompt prose.
   - Seam 1: `:initialize-worker` (`external_task.clj:134`).
   - Seam 2: `executable/load!` (`executable.clj:6-14`).
3. **Artifact store:** program values with these fields:
   - forms;
   - a **code hash** over canonical forms only;
   - an envelope with provenance;
   - an interface;
   - an **executable applicability predicate** over public task metadata;
   - validation receipts.
4. **Controller:** owns execution, budgets, permissions and the artifact
   lifecycle: propose, validate, promote, apply, revalidate, demote. It also
   owns deterministic `done`-time checks. Validation runs in SCI against
   development data with controller-only gold. It needs no inference. The
   controller does not supervise each reasoning step.
5. **Model-facing additions:** at most two tools, `artifact_propose` and
   `artifact_patch` (subtree-addressed). Applicability, loading, invocation
   records and scoring stay with the controller.
6. **No general multi-agent framework.** Keep synchronous `agent_call`.
   Leave `elastic.clj` off (`elastic.clj:43`) until a task shows that
   concurrency limits accuracy or cost.

## 5. The decisive experiment

**Question:** can an agent that retains and transforms validated executable
knowledge solve related future tasks more accurately, reliably or cheaply
than one that regenerates computation each time?

**Task family:** OOLONG questions over the `trec_coarse` taxonomy (Pairs and
synth counts or comparisons). Official data and the pinned scorers are used.
- **Compatible tasks (F1):** unseen windows of the same taxonomy.
- **Incompatible tasks (F2):** another taxonomy with the same record format.
  The parser transfers. The classifier must be refused.
- **Selection:** freeze a manifest of windows that are not exposed and not
  held out. Measure item-text overlap with earlier windows, because windows
  share an instance pool.
- **Sealed held-out:** unchanged and unused.

**Arms:** same model and limits. No Prime arm, because Prime costs about
twice Aljure per arm and answers a different question.

| Arm | State carried between tasks |
| --- | --- |
| A, stateless | None (current L0 or F1 Aljure) |
| B, developer-supplied | Hand-written parser, ledger and tally, preloaded by the controller |
| C, exact cache | Content-addressed memo: item-text hash → earlier label, and functions keyed by exact task signature. No validation, no generalization |
| D, model-generated validated artifacts | Parser and rule set (label or `:unknown`) proposed after tasks. Promoted on inference-free checks (properties, rule precision on controller-only gold). Applied by the predicate |
| E, D plus structural improvement | After each task, the agent may patch a retained artifact (for example, edit one `cond` clause). Promote only on no regression on the frozen development panel |

**Protocol:**
- Prequential order: 20 tasks per trajectory, 16 F1 and 4 F2, with F2 tasks
  interleaved at positions 9, 12, 15 and 18.
- A cold restart after task 10: new JVM, new conversation, bundle-only state.
- Each task is scored once. Scores never return to the learner.
- Three independent trajectories per arm, each with a seeded order.

**Accounting:**
- Report acquisition, proposal, validation (local SCI seconds) and task
  inference separately. Report the break-even task count.
- Activation is a primary endpoint: the share of tasks where retained code
  ran **and** its output entered the answer, from invocation events.
- Patches and full rewrites are counted separately.
- Development tasks may be used for iteration. Each trajectory's transfer
  tasks are used once.

**Step 0 (zero inference, run first).**
- Replay the recorded A1c rule functions and parsers in SCI on other
  development windows of `trec_coarse`, against item gold. Use the
  `scripts/residual_reasoning_analysis.py` path.
- Measure coverage and precision on items never seen before, alone and as a
  union or vote.
- If retained rules cannot decide a useful share of unseen items at high
  precision, the accuracy route is already falsified for this family. The
  cost route (parser and ledger) remains.

**Smallest live falsification test (MF):** arms A, C and E only. E contains D.
C separates caching from generalization. That is 3 arms × 20 tasks × 3
trajectories = 180 task runs, on Sonnet.

The thesis is **falsified at this scale** if any of these holds:
1. E fails to reach at least one of these on F1, with activation of at least
   80%:
   - cost per verified solution at most 0.8 × A's, including all acquisition
     cost, with mean score at least A − 0.03;
   - mean score at least A + 0.05 at no more than A's cost.
2. E's advantage over A disappears on items not seen in earlier windows (so
   the effect is caching, E ≈ C).
3. E scores below A − 0.05 on F2 and the controller did not refuse.
4. Break-even needs more than 16 related tasks.

If activation stays below 80%, or no artifact is promoted, the result is
**uninformative**, not negative. Report it, then run B to separate the value
of reuse from the model's ability to acquire.

**Cost** (measured Aljure cost per arm):
- Sonnet: $0.039 (synth 32K) to $0.083 (Pairs 32K A1c).
- Opus: $0.074–0.086 (synth) to $0.225–0.252 (label counts).
- Operator ranges: Opus $0.08–0.40, Sonnet about half.

| Run | Task runs | Sonnet | Opus |
| --- | --- | --- | --- |
| Step 0 | 0 | $0 | $0 |
| MF (A, C, E) | 180, plus about +25% proposal turns on 60 E runs | **$10–15 likely**; cap $40 | $20–45 likely; cap $80 |
| Full (A–E), only if MF is positive | 300, plus D and E proposal turns | $15–25 likely; cap $65 | $40–75 likely; cap $130 |

## 6. Roadmap

**Fundamental (do now, in this order):**
1. **Freeze Prime-gap optimization.** Keep the paired runner, gateway,
   isolation proofs and accounting as regression infrastructure. Run Prime
   once per milestone, not once per change.
2. **Put artifacts into the task path.**
   - Preload applicable approved bundles into the session worker
     (`external_task.clj:134`, `executable.clj:6-14`).
   - Record each call with an invocation wrapper.
   - Make learning a plan switch instead of `:allow-learning false` and the
     empty library (`paired.py:579`).
3. **Make analysis artifacts first-class.**
   - Add a forms-only code hash.
   - Add an executable applicability predicate.
   - Add property and gold-oracle validation, with no inference.
   - Fix the sum-of-scores gain and the failed-episode attribution defects.
   - Add revalidation and demotion.
4. **Run Step 0**, then **MF** on Sonnet.

**Supports the thesis (after a positive MF):**
- The full A–E experiment, then an Opus replication.
- An `artifact_patch` native tool.
- Q-SUBSTRATE as a code-as-data test: patch rate, validation rate and
  artifact size for Clojure forms against the Python AST, not benchmark score.

**Benchmark infrastructure (keep; do not grow):**
- OOLONG importers, the subscription gateway, relay fixtures and latency work.
- The deterministic `done`-time answer-format validator. It is generic, costs
  about $0, and the controller owns it.

**Optional (off by default):**
- `elastic.clj`.
- F1 truncation retry (keep; 0 triggers so far).
- `sci-verify.edn` helpers.

**Postpone or remove from the default path:**
- The L1–L3 label, audit and review prompts (`resources/structured-labels.txt`,
  `resources/uncertainty-audit.txt`, `resources/targeted-review.txt`).
- The F2 terminal-text path.
- Elastic phases B–E and model-facing spawn.
- The compute-scaling plan.
- The six-condition selector campaign; a controller applicability guard
  replaces it.
- The held-out Q-HARNESS campaign, until a Q-LEARNING result exists.

**North star check.** Today Aljure differs from Prime mainly by having better
accounting and a smaller prompt. The differences that matter for the thesis
are retained, inspectable and transformable computation, but the benchmark
path does not use them. The next step is not to close the Prime gap. The next
step is to measure, with Step 0 at no cost and with MF for about $10–15,
whether computation accumulates.
