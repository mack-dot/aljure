# Prime head-to-head V5: isolation recovery freeze

**FROZEN / BLOCKED / NOT AUTHORIZED / NOT RUN.** SCI now passes. The expected
native Prime image is unavailable locally, so native isolation and the revised
native/SCI relay cannot complete. No inference approval is requested.

| Item | Frozen value |
| --- | --- |
| Plan SHA-256 | `93c6d6f428441ff116a6e733c5dae0795b08e31a2688784d1dde657ade2c0991` |
| Execution commit | `8e6dea8bc6ed42dcbcd7d50ae58cc1b368444a5f` |
| Source SHA-256 | `39be456531494fe588bce6ba324e1afaa13cf1139dd15cd9018b91efba8bb30c` |
| Runtime SHA-256 | `b269ba197229783b53cbc7ea040c33d529df7f407b23a53070cb04f1c51553f9` |
| Configuration SHA-256 | `e0372dadc2c4db90351fcc3c9cb0cdef3de94935da0aa5c8013ac28292998014` |
| Capability SHA-256 | `1c9f81c4da7e964eebc9efb48f464ce9df796c13d8696440fe57f0838f87d95a` |
| Base prompt SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| Response-envelope prompt SHA-256 | `7ee98b9ee1cafa4edff61985d201d031cd3bad4f8a51c1bd92da3a609a3e45db` |
| Official scorer SHA-256 | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Suite SHA-256 | `e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded` |
| Native Prime revision | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` |
| Official case | `oolong-pairs-validation-8192-1` |
| Model / transport | `claude-sonnet-5-5` / Claude subscription OAuth |
| Thinking | Adaptive/summarized, medium effort |
| Order | Aljure first, Prime second |
| Task deadline | 120 seconds per harness |
| Proposed new ceiling | $12 per harness / $24 total API-rate-equivalent |

SCI image remains
`sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
The required native image remains
`sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`;
it is currently missing, not replaced. The clean checkout is
`/Users/mackianni/aljure-sonnet-pair-v5`.

[Plan](evidence/prime-head-to-head-v5/plan.json),
[manifest](evidence/prime-head-to-head-v5/experiment-manifest.json),
[proposal](evidence/prime-head-to-head-v5/proposal.json),
[scope audit](evidence/prime-head-to-head-v5/scope-check.json).

## Changes and unchanged experiment

The sole execution-code delta from V4 is `scripts/isolation.py`: safe query
timings, precise preflight stages, explicit negative-test failure classes, and
stricter fatal OOM evidence. The new proposal records the version; it changes no
scientific setting. [Diagnosis and actual gate evidence](SCI_ISOLATION_REPAIR_V1.md).

V4's strict `single-edn-map-v1` interface and one shared, accounted correction
remain unchanged. Base and appended prompts, scorer, official inputs, model,
provider, thinking, rates, native Prime capabilities, call/token caps and worker
limits all match V4. There are 12 calls and 12M accounted/reserved tokens per arm,
32,768 output tokens per call, no borrowing, and no selective retries.

Unknown provider charges or failed cleanup retain the existing stop rule. Known
command/model failures remain failed arms. In-task formatting correction is not
an arm retry. A missing answer has no measured answer F1. Preserve every attempt,
provider receipt, correction, tool execution, answer and independent score.

The diagnostic reference remains V3 Prime F1 0.967741935483871 and $0.0663848
equivalent cost. These are targets, not new spending caps or evidence of a win.
This reused public case is an engineering recovery test, not a new held-out
observation. No prior answer or transcript enters the fresh conversations.

## Final preflight

- **ACTUAL SCI:** complete strict pass; all nine same-worker negative checks;
  ten confirmed cleanups; unchanged image and limits.
- **OFFLINE / FIXTURE:** 108 Python tests and 96 Clojure tests / 1,804 assertions
  passed. These do not establish new real-provider compatibility.
- **Credential metadata:** configured, unexpired private Claude OAuth;
  no inference, token refresh or API fallback.
- **Native isolation: BLOCKED.** Expected image is absent. Its previous proof
  cannot substitute for a fresh matching execution boundary.
- **Revised native/SCI relay: NOT RUN.** Native prerequisite is unavailable.
- **Combined preflight: NOT READY.** No authorization request and no model calls.

[Preflight](evidence/prime-head-to-head-v5/preflight.json),
[credential status](evidence/prime-head-to-head-v5/credential-status.json),
[SCI proof](evidence/prime-head-to-head-v5/isolation-proof.json),
[native failure](evidence/prime-head-to-head-v5/native-isolation.log).

## Remaining offline commands

After restoring the exact pinned native image, use fresh output directories:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v5/repl-lab
source var/worker.env
source var/prime-worker.env
python3 -m benchmark.prime.isolation
python3 -m benchmark paired-relay-fixture \
  --provider claude-oauth-subscription \
  --config var/sonnet-pair-v5/proposal.json \
  --out var/sonnet-pair-v5/relay-after-image-restoration
python3 -m benchmark paired-preflight \
  --suite var/official/pairs-one --plan var/sonnet-pair-v5/plan.json
```

Require the native gate to pass before the relay, and the relay to pass before
requesting new inference approval. Recheck credential metadata privately. A
replacement image or executable change requires a new freeze. V1/V2/V3 results
and V4's failed readiness evidence remain unchanged. No Opus, selector or ten-case
inference is included. [V5 results](PRIME_HEAD_TO_HEAD_V5_RESULTS.md) remain NOT RUN.
