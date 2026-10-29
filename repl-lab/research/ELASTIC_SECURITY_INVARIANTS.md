# Elastic execution and controller verification: security invariants

**Status:** the invariants marked **A** are enforced by phase A
(`src/repl_lab/elastic.clj`) and tested in `test/repl_lab/elastic_test.clj`.
That suite ran offline with the real SQLite compare-and-set store and no
Docker: 11 tests, 163 assertions. The other invariants are requirements for
phases B–E and V-A to V-D. Each names its test.

## 1. Invariants

| # | Invariant | Enforced by | Test |
| --- | --- | --- | --- |
| I1 | **Off means absent.** With the switch absent, every elastic operation refuses before writing. There is no denial event and no `:elastic` key. Tool definitions, instructions and broker schemas are byte-identical | A | `off-by-default-writes-nothing-and-changes-no-model-interface` |
| I2 | **Settings are explicit and validated:** known keys only; positive limits; `max-depth ≤ recursion-depth`; `:inherit` always authorized | A | `settings-are-explicit-and-validated` |
| I3 | **No concurrent overspend:** for every resource, `spent + reserved ≤ limit` at every committed state, and children leave the root floor. All admissions are compare-and-set transactions on the run record | A | `concurrent-children-never-overspend-the-shared-budget` (lock on, and compare-and-set alone) |
| I4 | **A quota bounds a subtree:** a child's own and its descendants' `used + held` stay within its quota, and a nested quota is at most the parent's remainder | A | `quotas-bound-subtrees-and-the-root-keeps-its-floor`, `spawn-admission-…` |
| I5 | **Accounting conserves:** the sum of children's `used` equals the elastic share of `:spent`; `held` returns to 0 when no call is in flight | A | the concurrency and executor tests |
| I6 | **Unknown is held, never released and never retried.** Only a receipt for that exact request id settles it. Sibling requests are untouched. Elastic admission halts for the task | A | `an-unknown-outcome-holds-its-reservation-…`, executor failure modes |
| I7 | **Terminal states are monotonic.** Late results are recorded as discarded. A finishing child stops its subtree | A | `deadlines-terminal-monotonicity-…`, executor timeout test |
| I8 | **A call in flight is never interrupted by the controller.** Cancel and expiry wait for it, then charge it | A | `cancellation-cascades-…`, executor cancel test |
| I9 | **Ownership:** only an ancestor may cancel; only the direct parent may collect or read status; children are confined to their task root | A | `cancellation-…`, `deadlines-…-bounded-collection` |
| I10 | **No capability amplification:** a child's context is a subset of its parent's grant, its quota is at most the parent's remainder, its wall time at most the parent's, and its profile is in the plan's authorized set | A | `spawn-admission-refuses-escapes-amplification-and-limits` |
| I11 | **Spec injection is refused:** unknown spec keys (`:shell`, `:env`) are refused; ids are restricted to `[a-z0-9][a-z0-9_-]{0,63}`, so there is no path text; a profile must be a keyword from the authorized set, never a free model string; task and context sizes are bounded | A | `spawn-admission-…` |
| I12 | **Bounded results:** a stored result is at most `result-chars`, with its full length and SHA-256 | A | `deadlines-…-bounded-collection` |
| I13 | **Every worker lease ends closed or flagged:** after `shutdown!`, no child is active and no lease is open. A failed close halts. A restart marks open leases `unconfirmed` | A | executor tests; `restart-recovery-…` |
| I14 | **Recovery is conservative and idempotent,** and runs no retries | A | `restart-recovery-is-conservative-idempotent-and-never-retries` |
| I15 | **SCI isolation is unchanged:** every child worker uses the same image, proof gate (`isolation.clj:46-61`), limits and denied symbols. No elastic or verification code adds a namespace, class, filesystem, process or network capability to SCI | B, C | phase C relay fixture; isolation proof re-run (Docker; after the live chain) |
| I16 | **Bounded context is real:** a child worker binds only its granted context blocks, and the broker refuses `context/query` outside the grant | B | phase B tests with stub workers recording the bindings |
| I17 | **Reviewer blinding:** a reviewer request is exactly the rendered template (instruction hash, question, shuffled sampled records). It never contains the root's answer, labels, var contents, history or worker | V-C | auditor rule and fixture |
| I18 | **The controller never changes an answer.** Verification can only accept, send a bounded notice, or accept with unresolved items recorded | V-B | runtime tests with scripted providers |
| I19 | **Every verification loop is bounded:** at most 1 per task for each of format notice, evidence request, review round and targeted notice | V-B | runtime tests; auditor |
| I20 | **No gold at inference time:** verifiers, the allocator and reviewers never read `controller/answers.jsonl` or labelled columns. Dev gold is read only by offline analysis scripts | V-A | a test that verifier namespaces cannot resolve the answers path; code review |
| I21 | **Credentials never reach generated code or children:** the runner strips `*API_KEY*`, `*TOKEN*` and `REPL_LAB_CLAUDE_*` from the Aljure environment (`benchmark/paired.py:459-460`). Children inherit nothing beyond their worker | existing, C | existing runner tests; phase C fixture |

## 2. Failure-state transitions

A means "the ledger enforces this now"; B or C means "later phase".

| From | Event | To | Budget effect | Retried? | Fails closed by |
| --- | --- | --- | --- | --- | --- |
| — | spawn admitted | `spawned` | none (quota is a ceiling) | idempotent replay of the same spec | refusal plus `elastic-denied` (A) |
| `spawned` | start | `running` | — | — | refuses unless `spawned` (A) |
| `spawned` | cancel or deadline | `cancelled` / `timed-out` | — | — | A |
| `running` | call admitted | `running` (request `pending`) | `reserved += amount`; chain `held += amount` | — | refusal: `child-quota`, `run-budget`, `child-deadline`, `halted`, `not-running` (A) |
| `running` | receipt ≤ reservation | `running` | reserved → spent; held → used | settle retried on contention only | A |
| `running` | receipt > reservation | `failed` (`budget-overrun`); run `:budget-overrun`; halted | charged | no | the run stops admitting (A; `within-time!`) |
| `running` | not dispatched | `running` | released | no | A |
| `running` or `cancelling` | outcome unknown, or receipt invalid | `unknown`; halted | **held** | **no** | A |
| `unknown` | operator or late receipt for that id | `failed` (`resolved-unknown`) | charged from the receipt; halted stays | no | A |
| `running` | body returns | `completed` (result bounded); subtree stopped | — | no | A |
| `running` | body throws | `failed` / `budget-exhausted` | — | no | A |
| `running` | cancel, no call in flight | `cancelled`; subtree cancelled; worker closed | — | — | A |
| `running` | cancel, call in flight | `cancelling` → `cancelled` when the call ends | the call is charged or held | — | A |
| `running` | deadline (`sweep!`) | `timed-out`, or `cancelling` → `timed-out` | as above | — | A |
| any non-terminal | parent exit (`shutdown!`) | `cancelled`, `unknown` (call in flight) or `orphaned` | held for unknown | no | A |
| any non-terminal | controller crash, then `recover!` | `unknown` (call in flight) or `orphaned`; leases `unconfirmed`; halted | held | no | A |
| lease `open` | close fails | lease `close-failed`; halted | — | no | A; the runner's cleanup stop rule (C) |
| terminal | any later event | unchanged; `late-result-discarded` | — | — | A |
| `budget-exhausted` / `halted` | spawn or call | refused | — | — | A |

**Retried:**
- only idempotent ledger operations: a spawn replay, and a settle under
  compare-and-set contention;
- in later phases, at most one worker open before any model call.

**Never retried:** any provider call after dispatch; any reviewer or child
task; any notice.

**Fails closed:**
- an unknown outcome;
- an invalid receipt;
- a cleanup that is not confirmed;
- an overrun;
- a controller restart.

Each of these halts elastic work, and the benchmark stop rules then stop the
plan.

## 3. Sandbox-escape and abuse cases

| Attempt | Where stopped | Status |
| --- | --- | --- |
| Model asks a child to run shell or set env (`:shell`, `:env` in spec) | spec schema | A, tested |
| Path traversal through a child id (`../etc`) | id pattern | A, tested |
| Picking an unpriced or stronger model by string | profile must be an authorized keyword; the gateway pins settings | A + existing gateway, tested |
| Reading context beyond the grant | spawn refuses; phase B broker refuses | A / B |
| Budget amplification by nesting or by many children | subtree quotas, `max-children`, `max-active`, root floor | A, tested |
| Flooding the parent's history with a child result | `result-chars` bound | A, tested |
| Generated code calling the provider or a child directly | Impossible: SCI has no host, network or process access (`isolation.clj:45`, negative cases). Children are created only by the controller or a broker command | existing |
| Reviewer learning the root's answer through a side channel | the template-equality auditor rule; the reviewer has no worker | V-C |
| Model-authored evidence used as code | evidence is data read by the bounded EDN reader; never evaluated | V-A |
| Model-written text parsed as confidence | never parsed | design rule; auditor |
