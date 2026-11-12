# Reuse economics result: reimplementation-regardless-of-length

Run 1 of the frozen plan `ffbbb00f45e7baf4bf49251ce896210304a04c7a086c74f82d03d5c8dbae08cf`
(protocol `REUSE_ECONOMICS_PROTOCOL.md`, version `reuse-economics-development-v1`,
suite `8f7f4510…`, retained library `f273cf89…`) executed live on 2026-11-04 from
12:21:41 to 12:27:09 local time against source commit `2873a49`. The owner approved
the exact plan hash and asked for it to be launched through the host launcher
(`run_guarded.py economics --approve <hash>`). The owner's own earlier invocation at
11:56 was refused by the host gate (OAuth credential under one hour) and dispatched no
inference; the credential was renewed and the 12:21 gate admitted the run. The frozen
criteria, scorer, gold and library are unchanged. The automatic development gate
reports **COMPLETE-PENDING-ATTRIBUTION-REVIEW** with outcome pattern
**`reimplementation-regardless-of-length`** and summary effect **`none`**. The trace
review in section 3 confirms both. Raw traces remain in
`var/reuse-economics-20261104/run-1`; the committed copy is
`evidence/reuse-economics-20261104/` (it omits raw transport bodies and sqlite stores).
Every number below is a live model result unless marked otherwise.

## 1. Official gate

All twenty-four attempts completed with exact accounting, cleanup evidence and no
failure. All twenty-four answers were correct, including the eight negative controls.
No attempt in any arm inspected or called the retained classifier. No negative control
executed it, and none was wrong in a library arm.

| Endpoint | Value |
| --- | --- |
| B eligible tasks at level 8 (used) and correct | 0 of 6 |
| BN eligible tasks at level 8 (used) and correct | 0 of 6 |
| B / BN eligible tasks that inspected the artifact | 0 of 6 / 0 of 6 |
| A / B / BN eligible correct | 6 of 6 / 6 of 6 / 6 of 6 |
| A / B / BN eligible evaluations | 12 / 11 / 10 |
| A / B / BN eligible requests | 18 / 19 / 25 |
| A / B / BN eligible known cost $ | 0.0645 / 0.0767 / 0.1076 |
| A / B / BN eligible wall s | 62.6 / 75.9 / 108.8 |
| Negative-control executions, all arms | 0 |
| Negative-control failures, library arms | 0 |

Frozen mapping: B reached level 8 on 0 eligible tasks, so the pattern is
`reimplementation-regardless-of-length`. B and BN both reached level 8 on 0 tasks, so
the summary effect is `none`. With one trial per cell this is a diagnosis, not a
statistical claim.

## 2. Arms

| Arm | Configuration | Tasks | Correct | Known cost $ | Requests | Wall s | First-request tokens, mean | Tool schema bytes | Levels |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | stateless, long rule | 8 | 8 | 0.0835 | 24 | 82.8 | 2738 | 3090 | no-library 8 |
| B | library, long rule | 8 | 8 | 0.0966 | 25 | 101.4 | 3757 | 4576 | admitted 7, exposed 1 |
| BN | library with summaries withheld, long rule | 8 | 8 | 0.1330 | 32 | 141.2 | 4157 | 4576 | admitted 7, exposed 1 |

Total: $0.3131 known model cost, $0 unknown reservations, 81 of 288 allowed requests,
329 s wall, all under the $6 ceiling. Every task took 3 to 6 requests. Costs include
every request and cache charge.

Parity of information (A against B): same correctness, B cost 19% more on the eligible
cases, one more request, 13 s more total wall time and about 1,000 more first-request
tokens. The library again adds prompt and tool-schema bytes and, when the task text
states the rule, buys nothing. BN cost more than B (eligible $0.1076 against $0.0767,
25 against 19 requests, 109 s against 76 s). Section 3 traces that difference to how the
model answered, not to any use of the artifact.

## 3. Trace review

Every tool call of all twenty-four tasks is listed in
`evidence/reuse-economics-20261104/run-1/trace-review.json`, produced by
`host-policy/review_economics.py`. Checks made on the raw traces:

- **Manipulation delivered.** All six B eligible first requests carried the inventory
  with the model-authored summary ("blocked=yes→hold; age_minutes>=60→expedite;
  attempts>=3→retry; else hold"). All six BN eligible first requests carried the
  inventory with the summary absent and the limits text "Summaries are withheld on
  this task." Both arms listed `route-hold-rules` by name, hash and call syntax. A
  carried no inventory.
- **Applicability.** The predicate preloaded the artifact on all 12 eligible and both
  Routing v2 texts and refused it on both parity texts, as in the causal study.
- **Zero artifact use.** Across 24 attempts: 0 `artifact_inspect`, 0 `artifact_call`,
  0 evaluations naming `route-hold-rules`. The worker invocation logs record no call
  of the retained code hash. No model text mentions the artifact, the inventory or the
  approved-functions block.

**How the model answered instead.** The six-clause statement was read in full in every
attempt (one `repl_eval` or context read returned the rule text and the records). Then:

| Arm | Fresh one-expression classifier | Read the records and counted without code |
| --- | --- | --- |
| A eligible | 6 of 6 | 0 of 6 |
| B eligible | 5 of 6 (attempts 02, 04, 11, 13, 18) | 1 of 6 (attempt 09) |
| BN eligible | 3 of 6 (attempts 03, 05, 07) | 3 of 6 (attempts 12, 14, 16) |

Every fresh classifier was a single regex-and-count expression. The model collapsed the
six ordered clauses to their logical content (for example, attempt 02-B:
`blocked=no, age_minutes<60, attempts>=3` for retry; attempt 05-BN: `blocked=yes or
(age_minutes<60 and attempts<3)` for hold) and never wrote a six-branch expression. In
the read-and-count attempts the model printed all records and tallied them in its own
reasoning; all four such answers were correct, but they were the slowest and most
expensive attempts of the run (12-BN: 27.2 s, $0.0193; 14-BN and 16-BN: $0.0192 each),
which is the whole of BN's extra cost. BN attempts also opened with a
`context/metadata` call that B and A rarely made.

**Negative controls.** Parity (19-A, 20-B, 21-BN): artifact refused, fresh code, all
correct. Routing v2 (22-B, 23-BN, 24-A): artifact preloaded on the changed rules; the
model wrote the new rule in fresh code without executing the old one; all correct
against the v2 gold, which differs from the old classifier's output.

Attribution review verdict: the automatic levels are accurate. No execution needs
review for copying or counter manipulation because none occurred.

## 4. Answer to the protocol's question

The protocol asked whether the model switches to the retained skill when
reimplementation is expensive but possible, and whether the model-authored summary is
what it uses when it does.

1. **Longer rule text did not move selection toward the skill.** 0 of 12 library-arm
   eligible attempts inspected or executed it. Across the three studies the model has
   now chosen the retained artifact in 0 of 18 eligible tasks whose text states the rule
   (interface A/B 3, causal 3, economics 12).
2. **The summary is not what holds reimplementation in place.** Withholding it changed
   nothing about artifact use (0 of 6 either way). It did change how the model computed:
   half of the BN attempts counted by hand instead of writing code, at higher cost. One
   reading is that the names-only inventory and its "summaries are withheld" notice made
   the model less inclined to write code at all; with six trials this is a hypothesis,
   not a finding.
3. **The manipulation did not make reimplementation expensive.** The six-clause
   statement is logically equal to the three-rule v1 (by design, so the retained skill
   stays correct), and the model compressed it to one expression in every coding
   attempt. The fresh implementation stayed one request and one short expression. The
   protocol stated that the manipulation was clause count and precedence, not evaluation
   count; the run shows that clause count alone does not raise the model's cost of
   reimplementation. A rule that is long and incompressible would be needed to test the
   economics claim properly, and such a rule is close to a necessity case: either the
   text carries all of it, and the model will type it, or the text omits part of it, and
   that is the withheld condition already measured.

Engineering implication, following the owner's rule from the causal study: the
retained-skill mechanism should be judged on necessity cases alone. When the harness
restates a rule the library already encodes, the model reimplements it, and no
inventory wording tested so far changes that. The harness levers that remain are to
stop restating what the library encodes (make the skill the only route) and to make
the skill the cheaper route when the fresh path is genuinely long, which this design
could not produce.

## 5. Host and isolation record

Launched through host policy v1 (`evidence/reuse-economics-20261104/host-policy/`).
Gate record `gate-1793812895.json`: admitted with two warnings (under 512 MB free host
memory; one-minute load above the CPU count), credential 7.6 h from expiry. The refused
attempt (`gate-1793811409.json`, 11:56) measured the credential at 0.09 h. Docker
Desktop restarted between the two gates (session id changed); the admitting gate
verified both pinned images present and the SCI probe answered in 3.8 s with cleanup
confirmed. During the run (54 samples at 5 s): swap 74.8% to 77.6% of a 5 GB swap file,
free host memory 73 MB to 731 MB, one-minute load 9.3 to 19.3, Docker Desktop session
unchanged, no other project's container at any sample. Docker events: 24 worker
containers, each create, start, die with exit 0, destroy; no OOM kill. Worker audits: 24
containers, startup 708 / 901 / 1107 ms (min / median / max), no supervisor error, 24
cleanups confirmed; gateway cleanup `ok` on all 24 tasks; no orphan after the run.

## 6. Limitations

- One trial per cell. Nothing here is a rate.
- The long rule is compressible, so the cost of reimplementation was not raised. See
  section 4, point 3.
- BN's extra cost is confounded: the names-only inventory changed the model's method
  (hand counting) in three of six attempts, and that, not the artifact, drove cost and
  wall time. Six trials cannot separate a real method effect from noise.
- The applicability predicate matches text literals, so it admitted the artifact on the
  Routing v2 text. No wrong answer followed.
- Single model (pinned Sonnet 5.5 subscription transport), development cases only, no
  held-out inputs. Supports no claim of capability over a comparably informed baseline,
  as the protocol states.
- The host ran at 75% to 78% swap with free memory as low as 73 MB. No worker or Docker
  failure occurred, but the latency figures were measured on a saturated host.

## 7. Recommendation (not frozen)

Stop testing preference for reuse with the rule in the text; three studies and 18
eligible tasks agree. Judge the retained-skill mechanism on necessity cases. The
smallest useful next study is a necessity study with more than one trial per cell:
withheld-rule tasks only, library against stateless, five or more cases, two trials
each, with the summary-withheld interface as a third arm so that execution reuse and
description reuse (both seen once in the causal study) each get a rate. About $0.40.
Freeze and approve separately.

## 8. Files

- `var/reuse-economics-20261104/run-1/results.json` sha256 `c4794ef0…`; `report.json` `7ccde3ec…`; `authorization.json` `0b079ebb…`; `plan.json` `19f67280…`.
- `evidence/reuse-economics-20261104/MANIFEST.json` lists every archived file with its hash.
- Host policy files as archived: `host_gate.py` `29841b6a…`, `run_guarded.py`, `host_monitor.py`, `review_economics.py`.
