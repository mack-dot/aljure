# Recursive compaction ablation

Controlled comparison of answer and intermediate-value transport. Analysis
rules are in `STATISTICAL_EVALUATION_PROTOCOL.md`. Everything below is
development evidence. A held-out claim needs a separate frozen evaluation.

## Strategies

| ID | Strategy | Status |
| --- | --- | --- |
| A | Raw output: the value is returned in one worker reply (≤ 64 KiB) | historical control (A1, `d5038fe2…`) |
| B | Deterministic paging: evaluate once, `[length hash]`, pages of at most bound/8, host assembly and check | implemented on this branch; offline tests pending |
| C | Immutable host-side result handles (`ARTIFACT_PROTOCOL_DESIGN.md`) | design only |
| D | Parent and child exchanging artifact references | deferred; no observed use of children |

## Separating delivery effects from reasoning effects

Stratify every analysis by **answer size**:
- Delivery-bound tasks: gold answers over 64 KiB, which are 6 of 10 in the 32K
  Pairs development suite (cases 1–3 and 6–8).
- Delivery-free tasks: answers under 64 KiB (cases 4, 5, 9 and 10).

A strategy that changes only delivery-bound scores is a **transport
correction**. A change on delivery-free tasks is a reasoning or tooling
effect. Report the two strata separately and never pool them into one
"improvement".

## Experiments

### Offline (deterministic; no model)

| ID | Design | Measures |
| --- | --- | --- |
| O1 | Real SCI worker; answers of 10K, 60K, 100K, 500K, 2M and 8M characters (ASCII and multi-byte); A against B | delivered or failed; exact match (SHA-256); pages; delivery ms; worker heap; restarts |
| O2 | Fault injection for B: a worker killed mid-page, a corrupted page, a length mismatch, a value over the cap | failure is explicit; no answer written; worker retired |
| O3 | Scripted relay fixture with one large-answer `done source` (zero model calls) | end-to-end through the real gateway and containers |

**Results.**
- **O1:** paged delivery (B) was exact at every size, 10K to 8M characters,
  with a 4-byte emoji at 100K and 500K. Every case used one worker and no
  restart. A single reply (A) failed above the 64 KiB bound. Each measurement,
  cold start included, took 1.5–2.9 s up to 2M characters and 5.2 s at 8M on
  image `58550c92…` (`HARNESS_LATENCY.md`).
- **Replay of A1:** the counterfactual replay shows the delivery effect
  without a model call (`SCI_EXECUTION_CONTRACT.md` §7). The delivery-bound
  cases score 0.65–0.88 instead of 0, while Prime stays ahead on each.
- O2 and O3 are not run.

### Live (each needs a frozen plan and approval)

| ID | Design | Purpose |
| --- | --- | --- |
| L1 (A1b) | Same as A1 with B delivery; 32K Pairs development suite | Delivery-bound cases should now deliver; delivery-free scores should stay within run-to-run variance of A1 |
| L2 | B against C on the same suite | Only if C is built: durability or sharing benefit over paging |
| L3 | Single agent with handles against parent and child with text against parent and child with references, on a **decomposable** task family where children are used (for example, multi-document aggregation) | HC3; only after L1, and only with such a family |
| L4 | Verified reusable programs (Q-LEARNING arms A–D) | semantic compaction; `EXECUTABLE_LEARNING_EXPERIMENT.md` |

## Measures (all strategies)

- Accuracy and completion, stratified by answer size.
- Model calls and tokens.
- Cost.
- Latency and critical-path depth.
- Bytes crossing the model boundary.
- Worker starts, stops and their time.
- Delivery failures.
- Artifact integrity (hash checks).
- Reuse rate and negative transfer (L4 only).

Report every measure as a function of context size, answer size, recursion
depth (L3) and the number of intermediate artifacts.

## Expected outcome (stated in advance)

- B removes A1's delivery failures and the restarts they caused. Each failed
  Aljure arm spent 32.6–40.7 s on 4–5 cold starts.
- C should add nothing on these tasks, unless worker loss remains common after
  B.
- D is not expected to help on OOLONG, where neither harness used children.

If these predictions hold, the conclusion is: **paging solves the observed
problem, and handles and recursion are not yet justified.**
