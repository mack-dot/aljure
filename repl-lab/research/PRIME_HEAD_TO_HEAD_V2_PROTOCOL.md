# Prime head-to-head v2: repaired Sonnet protocol

**SEALED / AUTHORIZED / RAN ONCE — INCOMPLETE.** The operator approved this exact
plan and its new $24 ceiling. Preflight passed. Two Aljure responses reconciled;
request 3 became unknown and Prime was not dispatched. See the
[v2 results](PRIME_HEAD_TO_HEAD_V2_RESULTS.md). The frozen plan, execution checkout
and v1 evidence remain unchanged. The preparation text below records the proposal;
it does not authorize a retry.

## Scope and limits

Run one Aljure/Prime pair through the repaired Claude subscription gateway. Use
`claude-sonnet-5-5`, adaptive/summarized thinking and medium effort. Native Prime
keeps its Python tools, skills, children and refinement. Real credentials remain
on the host; no API-credit or model fallback is permitted.

| Item | Frozen value |
| --- | --- |
| Aljure source | `bf9a8fbcb5eb31f7b7ffafe13d58c05dd83b1ca1` |
| Full source SHA-256 | `449d37253cf35ee589ef8e8e7c98137bcf3681e22bfbc0beb56e5e02301de369` |
| Runtime SHA-256 | `d4a2e98d1f74100ecce5a2cc716c2f229bf17aa0bb225239216f7d79b3c58e3d` |
| Prime revision | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` |
| Official case | `oolong-pairs-validation-8192-1` |
| Per arm | 12 calls, 12M accounted/reserved tokens, $12 equivalent, 120 seconds |
| New pair ceiling | **$24 API-rate-equivalent** |
| Output ceiling | 32,768 tokens per request, including thinking |
| Order | Aljure, then Prime |
| Plan SHA-256 | `a5b717479e78fd0e0174ae86a00b7189e82267a618b45622a69da33db10a3b1a` |

The first attempt's reconciled $0.005032 equivalent remains separate. Approving
the new $24 allocation would permit at most $24.005032 equivalent across these
two attempts. This is an accounting ceiling, not an expected subscription bill.
The original unknown reservation remains visible in the sealed ledger; its
separate reconciliation does not rewrite that ledger or grant a successful score.

This reuses the same public case to isolate the transport repair. It is **not a
new held-out observation**. In v1, Aljure saw the question and requested context
metadata. The controller rejected the receipt before executing that command.
Prime never started. V2 begins fresh conversations and processes and loads no v1
transcript or task result. No case was chosen based on a score.

The model-facing instructions, Aljure external-task/runtime code, native relay
bootstrap and official scorer match v1 byte for byte. The relevant changes repair
receipt compatibility and credential-process handling. The new source also
contains independently developed, unused selector and Opus paths; neither is
enabled by this plan. [Scope hashes](evidence/prime-head-to-head-v2/scope-check.json).

## Gates, scoring and failure rules

Both strict isolation proofs and the repaired ten-check native/SCI relay match
this runtime. The private credential check passed without inference. Credentials
must still be valid at dispatch. The existing image limits, official F1 scorer,
capability differences and accounting rules remain unchanged.

All root, descendant, compaction and refinement requests cross the common gateway.
Cumulative streaming counters are merged, and unknown usage retains the full
reservation. Each maximum-output Sonnet request reserves $4.32768. No allowance
is borrowed between arms. Native retries are separate accounted requests; the
runner does not retry a failed arm. An uncertain provider outcome, cleanup failure
or runner exception stops later dispatch. Failed and unattempted slots stay in
the record. Their mechanical zero scores must not be described as measured ties.

Only completed, independently scored answers can support a performance comparison.
Even a valid single pair cannot establish general superiority. Native ancestry
attribution, automatic compaction behavior and unequal whole-system compute limits
remain material limitations from v1. Local compute prices and actual subscription
invoices are unknown.

Evidence: [frozen plan](evidence/prime-head-to-head-v2/plan.json),
[preflight](evidence/prime-head-to-head-v2/preflight.json),
[proposal](evidence/prime-head-to-head-v2/proposal.json), and
[non-secret credential status](evidence/prime-head-to-head-v2/credential-status.json).
The repaired relay is prior offline evidence; it was not repeated for this freeze.

## Execution boundary

This protocol needs explicit approval of its new $24-equivalent allocation.
Earlier approval authorized the sealed v1 attempt. Opus, selector inference and
the ten-case study are excluded.

The execution checkout remains frozen at `/Users/mackianni/aljure-sonnet-pair-v2`.
After approval, select the existing private Keychain source on the trusted host,
then run:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v2/repl-lab
source var/worker.env
source var/prime-worker.env
python3 -m benchmark paired-preflight --suite var/official/pairs-one --plan var/sonnet-pair-v2/plan.json
python3 -m benchmark paired-run --suite var/official/pairs-one --plan var/sonnet-pair-v2/plan.json --out var/benchmarks/sonnet-pair-v2-live --authorize-subscription-plan a5b717479e78fd0e0174ae86a00b7189e82267a618b45622a69da33db10a3b1a
```

No secret belongs in shell arguments, prompts or artifacts. The output directory
must be new. Preserve its complete traces and result even if the attempt fails.
