# Prime head-to-head with native tool calls: results

**LIVE MODEL RUN, RUN ONCE (2026-10-28). Both arms completed. Aljure F1 1.0,
native Prime F1 0.968.** Plan
`78d14e14734d5c6624dac1fe693cbc6d98271bb2788faaf41baaee1ff231ba37`, clean
checkout at `a965bd9`, Sonnet 5.5 through the Claude subscription, $12 per
harness / $24 total API-rate-equivalent. Preflight, credentials and the Docker
gate passed. The Docker session was stable through both arms.

| Harness | Outcome | Official F1 | Calls / cost / task time |
| --- | --- | --- | --- |
| Aljure | Completed (official pair parser), 496 pairs | **1.0** | 7; $0.1722; 102.7 s of 120 s |
| Native Prime | Completed (official pair parser), 465 pairs | 0.968 | 4; $0.0668908; 41.2 s |

Total $0.2390908 API-rate-equivalent; accounting complete; no unknown requests.
Prime's 465 pairs are a subset of Aljure's 496: Prime missed user 58392
(31 users against 32).

## What changed from V7

Each Aljure command is now a provider-native tool call (`a965bd9`). There were
no command rejections: all 7 responses were valid tool calls. The markup
failure seen in V3, V6 and V7 did not recur.

## How Aljure got the answer

1. `repl_eval` failed: the first SCI worker took longer than the 10 s
   per-expression wall-time limit on its first request (see below).
2. Three `context_query` pages (64 lines each) read the 188 records into the
   model window.
3. `repl_eval` generated all pairs from the 32 user IDs the model had selected
   by reading.
4. `done` with the pair list.

So this run did not compute over the context in SCI, which is Aljure's intended
method. It worked because this context is small (19,142 characters).

## Limits of this result

- One reused public case. Prime's score on this same case varies by run: 0.968
  in V3, 1.0 in V7, 0.968 here. A 0.032 difference on one case is within that
  range, and is not evidence that Aljure is better.
- Aljure cost 2.6 times as much and used 103 s of its 120 s deadline.

## Defect found: worker cold start counts against the expression limit

A worker's first request includes container and SCI startup. The second worker's
first request took 5.9 s; its later requests took 3–66 ms. The first worker took
more than 10.1 s and was terminated, so the model's first expression failed
before it ran. Startup needs its own bound, or the worker must be warm before
the expression clock starts.
