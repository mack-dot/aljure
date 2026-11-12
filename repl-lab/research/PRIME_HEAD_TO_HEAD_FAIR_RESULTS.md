# Prime head-to-head after the fairness fixes: results

**LIVE MODEL RUN, RUN ONCE (2026-10-28). Tie: both arms F1 0.968 with identical
answers. Aljure cost 21% less and took 35% longer.** Plan
`6462f7806fcf89cab32b827e477bca740f2838a0411bfc693d262a7b1f1d9a7e`, clean
checkout at `1a570af`, Sonnet 5.5 through the Claude subscription, $12 per
harness / $24 total API-rate-equivalent. Both isolation proofs were regenerated
for the changed supervisor (SCI 9/9, native 10/10). The relay passed 15/15, and
preflight, credentials and the Docker gate passed.

| Harness | Outcome | Official F1 | Calls / cost / task time |
| --- | --- | --- | --- |
| Aljure | Completed, 465 pairs | 0.968 | 6; $0.0510413; 43.2 s |
| Native Prime | Completed, 465 pairs | 0.968 | 4; $0.0645428; 32.0 s |

Total $0.1155841 API-rate-equivalent; accounting complete; no unknown requests.
The two pair sets are identical: both arms selected the same 31 users and both
missed user 58392. Aljure found all 32 users in the previous run, so this miss
is run-to-run model variance, not a harness property.

## Effect of the three fixes (`1a570af`)

| Fix | Previous run | This run |
| --- | --- | --- |
| Worker startup outside the expression limit | First expression killed at 10.1 s | Worker ready in 5.1 s; no startup error |
| Prompt caching, as Prime | 0 cache reads; $0.172 | Cache reads on 5 of 6 calls; $0.051 |
| Answer from code (`done` with `source`) | 4,506 output tokens to type 496 pairs | Answer built in SCI; 1,549 output tokens in total |

## How Aljure worked

`context_metadata`, one 12-record `context_query`, then `repl_eval` to parse all
records in SCI (one recoverable error: the model called an undefined function).
The model then chose the matching users from the parsed list, and `done` with
`source` built the pair list in SCI. There were no command rejections.

## Limits

One reused public case with identical answers cannot separate the two harnesses
on accuracy. The cost and time differences are from one run each.
