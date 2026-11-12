# Prime head-to-head V7: source blocks and a Docker gate

**FROZEN / READY / NOT RUN.** All offline gates pass. No V7 model request has
been dispatched. Running it requires explicit approval of the exact plan below.

## What V7 changes, and why (from V6)

| V6 cause | V7 fix | Evidence |
| --- | --- | --- |
| Aljure: valid code with quotes could not survive EDN string escaping after the single correction was spent | Envelope `edn-map-source-block-v1`: the same strict map, optionally followed by one verbatim `<<<SOURCE … SOURCE>>>` block; nothing extracted or repaired; v1 unchanged | 3 new Clojure tests (verbatim code, 14 malformed-block cases, v1 unchanged); two injected rule bugs caught; relay `source_block` check |
| Contract text wrongly allowed regex literals | Contract now states the SCI worker's EDN-reader rule and the substitutes (`re-pattern`, `fn`, `quote`, `deref`) | Relay run showed `No dispatch macro for: "` before the fix |
| Prime: Docker Desktop restarted its VM mid-task; `paired.py` raised `AttributeError` | `arm_status` records `NativeCompletionMissing`; a gate refuses each arm before any model call unless Docker Desktop is running, no restart is pending and both pinned images are present; a session change during an arm stops the pilot | 6 new Python tests, including the exact V6 dead-container case |
| Pinned images "vanished" three times | Root cause: Docker Desktop switched from the containerd to the classic image store; the same image has different IDs in each | Archive index digest `0dac4e17…` loads as config digest `f3e30aaa…` |

## Exact freeze

| Item | Value |
| --- | --- |
| Plan SHA-256 for authorization | `9798e89ed6bceec7c6e741588c82517dbaf50f2923c665116a0b1e620e0b3338` |
| Execution commit (clean) | `7b0cfa7` (branch `claude/sonnet-pair-v7`) |
| Clean execution checkout | `/Users/mackianni/aljure-sonnet-pair-v7` |
| Proposal | `config/external-subscription-proposal-v7.json` |
| Native Prime image | `sha256:f3e30aaa1ce3de92d381f05f597e84f9d1738a15c4a6453fdbd13bd4739446ad` (classic-store ID of the trusted V6 archive; tag `repl-lab-prime:v7-pinned`) |
| SCI worker image | `sha256:4e65f5bbe491c8c7c6ea94ead75c1f7cbb30b45ee2f73856ced7cea6d8377dc3` (rebuilt from the pinned recipe; tag `repl-lab-worker:v7-pinned`; archive SHA-256 `6b4bd97e…`) |
| Official case | `oolong-pairs-validation-8192-1` (unchanged) |
| Model / transport / caps | `claude-sonnet-5-5`, Claude subscription OAuth, $12 per harness / $24 total API-rate-equivalent, 120 s per harness, Aljure first |

## Validation (all in the clean checkout unless noted)

| Gate | Result |
| --- | --- |
| Python regression suite (development tree) | 119 tests pass |
| Clojure regression suite (development tree) | 99 tests / 1,828 assertions pass |
| SCI isolation | Positive control plus 9 of 9 negative controls |
| Native Prime isolation | 10 of 10 controls |
| Subscription relay (scripted responses through actual containers) | 13 of 13 checks, including the new block-form eval; 0 model calls |
| Preflight | `ready=true`, no blockers |
| Credential metadata | Configured, unexpired, no refresh, 0 model calls |
| Docker gate | No blockers |

## Run rules

Same as V6: one pair, no retries, borrowing, model substitution or extra cases;
failed and unattempted arms remain so. Evidence goes to
`var/benchmarks/sonnet-pair-v7-live` in the clean checkout.

```sh
cd /Users/mackianni/aljure-sonnet-pair-v7/repl-lab
source var/worker.env && source var/prime-worker.env
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
python3 -m benchmark paired-run --suite var/official/pairs-one \
  --plan var/sonnet-pair-v7/plan.json --out var/benchmarks/sonnet-pair-v7-live \
  --authorize-subscription-plan 9798e89ed6bceec7c6e741588c82517dbaf50f2923c665116a0b1e620e0b3338
```
