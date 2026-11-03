# Frozen development protocol: when does an executable artifact become useful?

Version: `reuse-causal-development-v1`. No live run is authorized by this file.
Approval must name the exact generated plan hash. The reuse-interface A/B of
commit `82d82e5` (`REUSE_INTERFACE_RESULT.md`) stays NO-GO under its own rules
and is not re-scored here. No held-out inputs are used or opened.

## Question

The interface A/B showed the model reads the library inventory, judges the rules
to match, and still reimplements. This protocol separates three explanations:
interface discovery failure, artifact selection failure, and absence of any
economic reason to reuse. It also asks whether reuse, when it happens, improves
task outcome or total cost against a comparably informed baseline.

## Arms

Two configurations run on two case groups. Configurations differ only in the
`aljure_contract` block: `stateless` has no library (`{}`); `library` adds the
pinned retained library and `skill_interface: "inspect-v1"`. Everything else
(model, transport, thinking, effort, rates, limits, images, task limits) is
identical, and both carry the explicit default execution contract.

- **A**: stateless, full task information. The task text states all rules.
- **B**: library, full task information. The retained artifact, its inventory,
  `artifact_inspect` and `artifact_call` are available. Using them is optional.
- **C**: library, necessity diagnostic. The task text states two of the three
  routing rules and says the third is not restated. The withheld rule is the
  one the asked label needs. It is available only through the approved
  artifact: its model-authored summary in the inventory, its inspected source,
  or its execution. The text names no library, tool or function.
- **C0**: stateless, the same withheld text. This is the guess floor. A correct
  C0 answer means the rule was recoverable without the library and C proves no
  necessity.

C measures reuse under necessity. It supports no claim of improved capability
over a comparably informed baseline; only A against B can address that, and
this sample cannot establish superiority.

## Inputs and schedule

`benchmark/reuse_causal.py` generates ten cases with seed 2026110301. Group ab
(A and B): three Routing v1 counts (retry 40, hold 48, expedite 56 records),
one parity case (20) and one Routing v2 case (48). Group c (C and C0): two
withheld-rule counts (retry 44, hold 52), one sufficient-rule count (expedite
36: decidable from the restated rules, an in-arm control that the withheld text
is otherwise usable), one parity case (24) and one Routing v2 case (40). All
routing feature tuples and record texts are disjoint from every earlier
development record, panel record and reuse-interface record, and from each
other. Parity codes use new ranges. Withheld cases are constructed so that the
answers obtained without the third rule (zero, or the merged retry-plus-hold
count) are wrong. The gold stays on the controller.

The retained applicability predicate matches three literals: `blocked=`, the
quoted label `'hold'`, and `age_minutes>=60 means expedite`. The withheld text
keeps them, so the unchanged predicate admits the artifact on withheld cases.
This is a property of the retained artifact and is recorded as a limitation:
the artifact can never apply to a task whose text omits that fragment.

Twenty attempts, paired on the ten cases: A/B, B/A, A/B, B/A, A/B on group ab,
then C0/C, C/C0, C0/C, C/C0, C0/C on group c. Each attempt starts a new JVM,
conversation and isolated worker. Only the fixed retained library persists. No
retries, replacements, resumption, extra seeds, or edits after outcomes. Every
failed or unattempted case stays in the denominator.

## Attribution levels

Each attempt records, from controller events and executable dependencies:

1. library-present: the pinned library was loaded for the task.
2. exposed: the first provider request carried the approved-functions inventory.
3. admitted: the applicability predicate preloaded an export.
4. inspected: at least one `artifact_inspect` call.
5. attempted: an `artifact_call`, or an evaluation whose source names an export.
6. executed: a counted call of a loaded export (preloaded log or `artifact_call`).
7. useful: an execution returned a non-nil value. The worker log now counts nil
   returns apart; a probe returning nil is executed and never useful.
8. used: the evaluation that executed the export returned the delivered number;
   the answer was computed in a done source that executed it; or the
   `artifact_call` values equal to the asked label count to the delivered number.

Textual similarity never establishes a level above 5. Copying inspected source
into fresh code is at most level 4. Controller applicability checks and fixture
calls never count. The automatic report is provisional until the trace review
confirms task-data use and the absence of counter manipulation.

## Endpoints

Primary: number of the three B eligible tasks with level 8 and a correct answer.
Necessity: C withheld correct count against C0 withheld correct count, with the
C levels reached. Parity of information: A against B correctness, requests,
cost, latency and first-request prompt tokens; tool-schema bytes per arm.
Negative transfer: parity must refuse execution and stay correct; Routing v2
must stay correct with no execution of the old classifier. Costs include every
request, inspection, error and cache charge; unknown reservations are kept.

Frozen outcome mapping, computed by `summarize`:

- `voluntary-useful-reuse`: any B eligible task reaches level 8 and is correct.
  The interface is usable and chosen when the task restates the rule.
- `reuse-only-when-necessary`: no B reuse, but a C withheld task reaches level 8
  and is correct. Discovery works; selection is governed by need, so the
  interface A/B measured absence of incentive, not inability.
- `knowledge-reuse-without-execution`: no execution anywhere, but C beats C0 on
  withheld cases with correct answers. The model takes rules from the inventory
  or inspection and reimplements. Executable reuse is not what the model wants
  from the library; descriptions are.
- `rule-recoverable-without-library`: C0 answers withheld cases as well as C.
  The necessity manipulation failed; nothing about selection is learned.
- `no-reuse-even-when-necessary`: withheld cases are wrong in C and C0 and no C
  task executes the artifact. Discovery or selection fails even with need.
- `NEGATIVE-CONTROL-FAILURE`: any negative control executes the classifier or
  is wrong in a library arm. No pattern is assigned.
- `INCOMPLETE`: fewer than twenty complete, safe, fully accounted attempts.

None of these is a GO. The gate is `COMPLETE-PENDING-ATTRIBUTION-REVIEW` or a
failure; the pattern is a diagnosis to be confirmed by trace review. With one
trial per cell nothing here is a statistical claim; three favorable discordant
pairs give two-sided exact McNemar p=0.25.

## Cost and safety

Same pinned Sonnet 5.5 subscription transport, adaptive thinking, medium
effort, rates, images and task limits as the interface A/B. No API fallback. At
most 12 requests per task, 240 across twenty tasks, 32768 output tokens per
request, 300 seconds per task, $5 per-task API-rate-equivalent ceiling, and a
**$6 hard aggregate equivalent ceiling**. Before each task, known cost plus
unknown reservations must leave the full $5 task allowance, so the run stops
before a new task once prior cost exceeds $1. The interface A/B cost $0.099 for
ten attempts; the expected total here is about $0.25. Report new expenditure
once; the $0.025166 historical acquisition overhead is shown separately.

Before live execution: verify frozen source and protocol hashes, suite and
library bytes, both configuration files, the exact SCI image, current sandbox
and artifact-path proofs, acquisition regression proof, subscription relay
proof, and the causal fixture proof. Require 6 GiB free disk before each task.
Refuse a pending Docker restart. Stop on infrastructure, cleanup, accounting or
source-integrity failures. Do not repeat a paid attempt after a runner crash.
No reward, instruction to prefer reuse, automatic application, benchmark-specific
instruction, or privileged shortcut to the answer is added in any arm. The only
general runtime changes since `82d82e5` are the nil-return count in the
invocation log and a range-error hint that names the documented `page` helper.

Commands are `python3 -m benchmark.reuse_causal prepare|plan|preflight|run` and
`python3 -m benchmark.reuse_causal_fixture --suite ... --out ...`. The run
command requires `--authorize-subscription-plan <exact-new-plan-hash>` after
explicit approval. Freeze from a clean committed checkout; archive results in a
separate later commit.
