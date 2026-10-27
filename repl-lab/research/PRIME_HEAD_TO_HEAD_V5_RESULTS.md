# Prime head-to-head V5 results

**NOT RUN / NOT AUTHORIZED.** Plan
`93c6d6f428441ff116a6e733c5dae0795b08e31a2688784d1dde657ade2c0991`
is frozen but blocked. No new provider requests were dispatched.

| Harness | Outcome | Actual F1 | Tokens / inference cost / task time |
| --- | --- | --- | --- |
| Aljure | Not attempted | Not measured | Not measured |
| Native Prime | Not attempted | Not measured | Not measured |

This is not a tie. There is no new policy, harness or competitiveness result.
No V5 inference reservations exist. V2's separate $4.32768 unresolved reservation
remains unchanged.

SCI isolation passed completely after Docker recovery. The native gate then
stopped because the expected Prime image is absent. No replacement image or
stale proof was used, and the revised native/SCI relay did not run. Credential
metadata is configured; that check did not contact the model.

[Protocol and exact pins](PRIME_HEAD_TO_HEAD_V5_PROTOCOL.md),
[failure analysis and preserved diagnostics](SCI_ISOLATION_REPAIR_V1.md),
[final preflight](evidence/prime-head-to-head-v5/preflight.json).

Next required action: restore the pinned native image, then pass native isolation,
the actual relay and final preflight. Request the new inference allocation only
after those checks pass. If a rebuild changes the image, freeze that runtime
revision separately before requesting approval.
