# Acceptance audit

This file preserves the full requested scope. A fixture does not satisfy a live
learning requirement. `PROGRESS.md` contains exact command results.

| Gate | Current evidence | Status |
|---|---|---|
| M0 repository inspection, architecture, threat model, protocol, runnable skeleton | Empty workspace inspection; named documents; `make doctor` | Tested offline |
| M1 deterministic simulator, baselines, observation whitelist, invariants, stale attempts, replay | 30 seeded worlds × 2 policies; direct fault/tie/invalid-action tests; 48 recorded episode replays | Tested within these bounds |
| M2 SCI isolation and negative execution tests | Worker, image recipe, verified container settings, host runner checks; negative suite reports UNVERIFIED | External isolation gate remains |
| M2 context/code selection, structural forms, broker, provider/mock, recursion | Runtime tests; exact fixture recursive transport; SCI-backed API implemented | Mock path tested; real child model call unverified |
| M2 persistent communicating subagents and budgets | SQLite CAS records, transactional effects, duplicate/recipient/failure/cancel/depth tests, in-flight accounting | Tested offline; provider crash windows require live fault testing |
| M3 candidate evaluation, promotion, recovery, immutable activation | Measured development fixture comparison, no-change rejection, parent CAS and safe boundary checks, corruption tests | Fixture path tested |
| M3 model-authored retained skill and changed harness | Live synthesis/broker path exists; fixture policy and structural workflow invoked | No real model result |
| M4 frozen/evolving model parity and sealed final evaluation | Equal per-case caps, fresh stores, temporary policy capability in both arms, split hash and atomic use seals | Implemented; mock parity tests and live verification required |
| M4 export/cold boot/compatible ablation | Whitelist checks, literal audit, fresh JVM fixture evaluation and serial fallback | Fixture checks passed; real-model H2 untested |
| M4 costs, raw cases, uncertainty, reproducible artifacts | Fixture reports, per-case records, budget ledger, action replay | Fixture path tested; real cost aggregation still requires audit |
| M5 dashboard and presentation path | React/TS build, typecheck, server render, recorded data packaging, six-minute script | Local artifact works; browser interaction QA blocked |
| M6 text-only memory, matched Python, formal model | Explicitly deferred until MVP evidence | Deferred as requested |

Remaining work includes independent review of the unexecuted SCI/live paths,
actual isolated worker tests, exact process-crash recovery injection, a real
recursive model call, and a capped learning/evaluation/cold-boot run when authorized.
No completion claim is made for the full learning demonstration.
