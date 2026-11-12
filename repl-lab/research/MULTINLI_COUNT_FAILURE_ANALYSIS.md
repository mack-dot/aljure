# MultiNLI exact count: why Prime got 129 and Aljure got 120

**Task:** `oolong-synth-test-32768-715070023`, dev window `multinli:70016`. Count
the pairs labelled `contradiction` among 438 premise–hypothesis pairs. The gold
answer is 129. The scorer gives 0.75^|error|.

**Status:**
- Diagnostic, from recorded traces and per-pair gold labels. No model calls.
- This document supersedes the conclusions of `PRIME_MULTINLI_TRAJECTORY_ANALYSIS.md`.
  That document said no Prime sub-agent contributed, and that was wrong.

**Sources:**
- Script: `scripts/multinli_count_analysis.py`.
- Evidence: `evidence/multinli-count/`, holding `analysis.json`, `dev-gold-labels.json` and `sonnet-prime-predicted.json`.

**How the gold labels were read:**
- They come from the label-augmented column, for the dev window only.
- Before decoding anything, the script reads metadata columns only and confirms
  that the dev window's row groups (shard 24, groups 4–5) hold no held-out row.
- Shard 24 is not a held-out artifact. No held-out input, label or result was read.

## Result

| Arm | Answer | Error | Score | Calls | Time | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| Opus Prime | 129 | 0 | 1.00 | 26 | 91 s | $0.79 |
| Opus Aljure | 120 | −9 | 0.08 | 8 | 48 s | $0.22 |
| Sonnet Prime | 111 | −18 | 0.01 | 6 | 40 s | $0.14 |
| Sonnet Aljure | 110 | −19 | 0.00 | 5 | 31 s | $0.09 |

Every arm undercounted except Opus Prime.

## Prime Opus: what produced 129

Trace: `30-prime/native/sessions/01a1861e-b9cb-75b5-ad29-dfa6d321a8d0.jsonl`.

1. The root split the pairs into 6 chunks and called `rlm.spawn` 6 times.
   - 2 children failed with "Connection error".
   - 3 children exited without replying, because their Python kernel would not start.
   - `nli2` labelled pairs 146–218, wrote `chunks/l2.txt`, and messaged back "Contradictions: 22".
2. The root read the pairs itself, in four pages. In the call that printed each
   next page, it saved the previous page's count in Python state.
3. It wrote `sum(C)`.

| Segment | Labelled by | Prime said | Gold | Error |
| --- | --- | --- | --- | --- |
| 0–109 | root | 36 | 37 | −1 |
| 110–145 and 219 | root | 11 | 9 | +2 |
| 146–218 | child `nli2` | 22 | 22 | 0 |
| 220–329 | root | 28 | 28 | 0 |
| 330–437 | root | 32 | 33 | −1 |
| **Total** | | **129** | **129** | **0** (4 absolute) |

**The child's own labels** (73 pairs) were 93.2% accurate. Its count was exact
because one false positive cancelled one false negative.

**Which steps contributed:**
- Recording a count per page in program state, then summing it, made the
  aggregation exact.
- Errors that were small and unbiased, in both directions, made the total exact.

**What did not contribute:**
- Verification: the root rechecked nothing. Its only check was that 129 is "about
  a third of 438".
- Delegation, beyond the one child's 73 pairs.

## Aljure Opus: what produced 120

Trace: `31-aljure` (events, plus the raw provider bodies in `gateway/events.jsonl`).

The pages are the `(show a b)` ranges it executed. The stated counts come from its
summarized thinking: page 1 lists its indices, and page 3 states a running total of 72.

| Pages | Aljure said | Gold | Error |
| --- | --- | --- | --- |
| 0–79 | 20 | 23 | −3 |
| 80–164 | 27 | 27 | 0 |
| 165–249 | 25 | 27 | −2 |
| 250–339 | 20 | 23 | −3 |
| 340–437 | 28 | 29 | −1 |
| **Total** | **120** | **129** | **−9** |

**Page 1, item by item:** 19 true positives, 1 false positive (76), and 4 false
negatives (41, 48, 64, 79). Aljure itself called 48 and 64 borderline.

**Items it called uncertain:**
- Aljure named 20 items as uncertain.
- It resolved 11 of them as "not contradiction", or left them out or set them aside.
- **6 of those 11 are contradictions** (48, 64, 134, 298, 334, 354).

### The eight questions

1. **Did it classify all records?** Yes. All 438 pairs were shown whole, in 5 pages.
2. **Did it skip records?** No.
3. **Were its labels semantically wrong?** Yes. Four of its five pages are
   undercounts. The errors run one way, so this is a bias, not noise.
4. **Was its aggregation wrong?** No. Its page tallies, 20 + 27 + 25 + 20 + 28,
   sum to its answer. It kept them in thinking, not in SCI.
5. **Did it detect unresolved classifications?** Yes: about 20 items, by name.
   It then resolved the uncertain ones by leaving them out. That default produced
   most of the undercount.
6. **Did it have time and budget?** Yes. It used 8 of 1,000 calls and 48 of 900 s.
7. **Why did it submit 120?** It judged the task done. Its final note reads: "a
   few borderline pairs could shift that count slightly."
   - Nothing recorded which items were open.
   - Nothing asked it to resolve them.
   - The harness accepts any `done`.
8. **Which of Prime's steps contributed?** See above: per-page state, plus small
   unbiased errors. Prime's root also named some of the same items as hard: 334 and 354.

## Sonnet: the same bias, plus a structural gap

**Sonnet Prime** saved its contradiction indices in Python state, so its labels
can be checked item by item:
- 107 true positives, 4 false positives, 22 false negatives;
- precision 0.96, recall 0.83.

**Both Sonnet arms cut each item's text** before reading it:

| Arm | Cut each pair at | Pairs shown cut | Of which contradictions |
| --- | --- | --- | --- |
| Sonnet Aljure | 230, 200, 190 characters | 134 | 44 |
| Sonnet Prime | 300, 260, 260 characters | 57 | 19 |

- 8 of Sonnet Prime's 22 misses were pairs whose text it saw cut.
- Sonnet Aljure called its own counts estimates: "rough estimate of around 115",
  "working toward a total near 110".
- The Opus arms of both harnesses printed every pair whole.

## How much of the result is chance

Suppose each item's errors are independent, at the rates measured above:

| Error model | Mean error | SD | P(exact) | Expected score |
| --- | --- | --- | --- | --- |
| Unbiased, Opus child rates (FN 1/22, FP 1/51) | +0.2 | 3.4 | 0.12 | **0.54** |
| Biased, Aljure Opus page 1 (FN 4/23, FP 1/57) | −17 | 4.9 | 0.00 | 0.02 |
| Biased, Sonnet Prime (FN 22/129, FP 4/309) | −18 | 4.7 | 0.00 | 0.01 |

**What follows:**
- An unbiased labeller with Opus's accuracy is expected to score about 0.54 here,
  and is exact only about 12% of the time.
- Prime's 1.0 is therefore partly a favourable draw.
- Aljure's 0.08 comes mainly from bias. The rates are estimated from 73 and 80
  pairs, so they are rough.

**Consequence for the gap:**
- One run attributes −0.044 of the Opus gap to this task (`SONNET_OPUS_PAIRED_DECOMPOSITION.md`).
- Removing Aljure's bias would raise its expected score on this task from about
  0.02–0.08 to about 0.5. That is about **+0.02** on the 21-task mean, not +0.044.
- More paging or more calls would not have helped. Aljure already read
  everything, and its arithmetic was right.

## Mechanisms separated

| Layer | Opus Aljure | Opus Prime | Deterministic check that would see it |
| --- | --- | --- | --- |
| Record coverage | complete, whole | complete, whole | coverage of ids (`audit-labels`); "shown whole" (`show-items`) |
| Shown text | whole | whole | detects Sonnet's cut items |
| Semantic labels | biased low (−9) | unbiased, ±2 per page | **none**; needs judgement |
| Unresolved items | about 20 named; 11 dropped as not C | some named | an `:unknown` label makes them countable: the count range becomes [120, 131] |
| Aggregation | correct (in thinking) | correct (in state) | arithmetic over recorded labels |
| Finalization | `done`, no check | answer file, no check | an evidence gate on open items |

The one check that would have changed Aljure's answer is not a structural one.
It needs the item-level uncertainty Aljure already noticed to be recorded where a
check can count it, so that the open items are reviewed instead of dropped.
`DETERMINISTIC_VERIFICATION_DESIGN.md` and `ADAPTIVE_COMPUTE_POLICY.md` build on this.
