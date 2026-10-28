# Prime head-to-head V6 results

**LIVE MODEL RUN, AUTHORIZED AND RUN ONCE (2026-10-28). Neither arm completed.**
The operator approved plan
`703dbecf7db78d70c2f46be1190606f6021c9bda148c0536f357248c1e0cc31b` ($12 per
harness, $24 total API-rate-equivalent, Claude subscription, Sonnet 5.5). Fresh
checks passed before the run:

- credential metadata: configured, unexpired, no refresh;
- frozen preflight: `ready=true`, no blockers;
- clean checkout at `2184b10`;
- both pinned images present. The native image had disappeared from Docker
  again and was restored from the verified archive (trusted manifest
  `206690a1…5c`) with an exact identity match.

| Harness | Outcome | Official F1 | Real calls / tokens / cost / task time |
| --- | --- | --- | --- |
| Aljure | Error: command rejected after its single correction | 0.0 | 4 calls; 11,882 in / 255 out; $0.026314; 29.6 s |
| Native Prime | Error: infrastructure (Docker VM restarted mid-task) | 0.0 | 4 calls; 10 in / 1,125 out / 43,380 cache read / 18,369 cache write; $0.0615305; 35.3 s |

Total $0.0878445 API-rate-equivalent; accounting complete; no unknown or
uncertain requests; gateway cleanup succeeded; no containers left. The official
summary records a 0–0 tie. **That tie is not a comparison:** both arms failed
before answering.

## Aljure failure (harness)

1. The first model response mixed a stray `<invoke name="x">` tool-call tag with
   the EDN command. It was rejected (`map-envelope`), which used the single
   permitted formatting correction.
2. The fourth response sent Clojure source inside the `:source` string with
   unescaped quotes (regex literals such as `#"User: "`). It was rejected as
   `malformed-edn`. No correction remained, so the session failed with 92 s of
   its deadline unused.

This is the third live failure of the command interface (V3 trailing EDN; V6
envelope and string escaping). Asking the model to embed code inside an EDN
string with escaped quotes is the recurring weak point.

## Prime failure (infrastructure, not Prime)

Prime made four normal model calls and was mid-task when Docker Desktop applied
a pending `RestartVM` setting change (Docker log: "restart needed: true" at
10:24:15 EDT, engine stopping at 10:24:17). The container connection ended with
"error waiting for container: unexpected EOF" (exit 125) at 10:24:20.

A harness bug then masked the cause: `run` computes the status with
`execution.get('completion', {}).get(...)`, but `completion` is present with the
value `None` when a container dies, so the code raised `AttributeError`. The
trace records that exception name instead of an infrastructure failure.

## Rules applied

No retry, borrowing or extra case (frozen rule). V6 is final. Evidence is in the
V6 checkout and copied to `var/benchmarks/sonnet-pair-v6-live/` (git-ignored).

## Next fixes (each requires a new frozen plan and approval)

1. Command interface: stop requiring code inside an escaped string (for example,
   accept the source as an EDN form or a delimited block).
2. Harness: treat a missing completion as an explicit infrastructure failure
   (fix the `None` completion handling).
3. Runtime: check that Docker has no pending restart and the native image is
   present immediately before each arm; keep Docker Desktop from applying
   settings during a run.
