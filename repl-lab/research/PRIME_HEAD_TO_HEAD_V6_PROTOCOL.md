# Prime head-to-head V6: verified native-image recovery

**READY FOR APPROVAL / NOT AUTHORIZED / NOT RUN.** All required offline gates
pass. No V6 model request has been dispatched. The new $24-equivalent allocation
requires separate approval of the exact plan below.

## Exact freeze

| Item | Frozen value |
| --- | --- |
| Plan SHA-256 for authorization | `703dbecf7db78d70c2f46be1190606f6021c9bda148c0536f357248c1e0cc31b` |
| Execution commit | `2184b10299d36ec08cc18b888a56b879108ee8ad` |
| Source SHA-256 | `0b9a2d22e670deb018e09652521cec235f3148ad8f83f8bf03fa29140f815a45` |
| Runtime SHA-256 | `586d91292f914332f265f1d28dce73267dfdb8337c7572393e1dd2c6986fe2fb` |
| Configuration SHA-256 | `8c8ee2bf00e5dd7ba82b60d99645e42d4ead5b983e5a6129ba918a5256246fa9` |
| Capability SHA-256 | `1c9f81c4da7e964eebc9efb48f464ce9df796c13d8696440fe57f0838f87d95a` |
| Base prompt SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| Command-envelope prompt SHA-256 | `7ee98b9ee1cafa4edff61985d201d031cd3bad4f8a51c1bd92da3a609a3e45db` |
| Official scorer SHA-256 | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Official suite SHA-256 | `e1491d5e13dcbc2a25fbc9f059f230bb0b985a106cd16bc513719508c66bbded` |
| Native Prime revision | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3` |
| Official case | `oolong-pairs-validation-8192-1` |
| Model / transport | `claude-sonnet-5-5` / Claude subscription OAuth |
| Thinking | Adaptive/summarized, medium effort |
| Order | Aljure first, native Prime second |
| Deadline | 120 seconds per harness |
| New proposed allocation | $12 per harness / $24 total API-rate-equivalent |

The clean execution checkout is `/Users/mackianni/aljure-sonnet-pair-v6`.
Use the authorization hash above, not the separate byte hash of the JSON file.
[Plan](evidence/prime-head-to-head-v6/plan.json),
[manifest](evidence/prime-head-to-head-v6/experiment-manifest.json),
[configuration](evidence/prime-head-to-head-v6/proposal.json),
[scope audit](evidence/prime-head-to-head-v6/scope-check.json).

## Explicit runtime change

The missing original image `sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`
was **not recovered**. The unchanged pinned recipe, source revision, base images
and dependency locks produced a new independently validated image:

`sha256:0dac4e174087d8d05f002917291f56fc85ad5a4b3ec4a32a9399bb73fe1ad640`.

All 1,618 historical source files match. The new native binary reports 0.10.1;
the image contains 61 Python distributions and nine packaged native skills.
No Prime source, algorithm, prompt, tool or skill implementation was edited.
No claim of binary equivalence with the lost image is made.

SCI remains `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Both image IDs are now part of the plan configuration and enforced by preflight.
A different image fails even if it has new passing proofs.

| Recovery artifact | SHA-256 |
| --- | --- |
| Trusted recovery manifest | `206690a182edfcf9f3500d4cf027d3621ebcdd3127bd7bce9b607a557405685c` |
| Exact image archive | `f6c7ce1e80aa0871b2c7296b3b9311c43ab2a8bd1580b79316bbc24482f2dc78` |
| Build-input archive | `5d131d51998d6d1e68b847c369917aa85ab7a2cda63d57f35f2a3ae8e0598575` |
| Native binary | `d8d8a4341c5fc10cf0d25c39d41455f990e8fcb47ff2f176453df649ed02a876` |
| Installed-package inventory | `f8bd5a3a8f9d0d76dbec33a9a047238632dcb4703995af4123da8ad9ab6778b9` |

The image was exported, independently hash-checked, removed, confirmed absent,
and restored. Image ID, configuration, architecture and filesystem identity
matched exactly after import. The image and source bundles are outside Docker at
`/Users/mackianni/aljure/repl-lab/var/prime-image-recovery/rebuilt-20261027-v1`.
They are not credentials or old agent state. The large archives stay outside Git;
their trusted manifest, source/dependency hashes and procedure are committed.
[Recovery procedure](PRIME_IMAGE_RECOVERY.md),
[manifest](evidence/prime-image-recovery-v1/recovery-manifest.json),
[actual restoration](evidence/prime-image-recovery-v1/roundtrip.json),
[binary/package inventory](evidence/prime-image-recovery-v1/artifact-inventory.json).

The only runtime-source changes from V5 are image-pin checks in
`benchmark/paired.py`, the archive recovery helper, and V6 configuration metadata.
Benchmark inputs, official F1 scoring, model, prompts, reasoning settings, rates,
tool capabilities, budgets and deadlines are unchanged. The recovery helper is
not exposed to agents. The rebuilt native image is the sole declared runtime-image
change. No worker resource limit or execution deadline changed.

## Complete validation

| Boundary | Evidence | Result |
| --- | --- | --- |
| Python regression suite | OFFLINE / FIXTURE | 113 tests passed |
| Clojure regression suite | OFFLINE / FIXTURE | 96 tests / 1,804 assertions; no failures/errors |
| SCI isolation | ACTUAL prior V5 gate, unchanged image/supervisor; current preflight verified | 9/9 negative controls, 10/10 cleanups; fresh SCI execution also passed in relay |
| Restored native Prime isolation | ACTUAL fresh containers | All ten controls passed, including OOM, PID limit, reset and unrelated-kill rejection |
| Common relay | FIXTURE responses through ACTUAL native/SCI containers | All 12 checks passed |
| Accounting reconciliation | FIXTURE | Six complete unique receipts per arm; no unknown receipts; all three SQLite stores pass integrity checks |
| Credential metadata | Read-only private OAuth check | Configured/unexpired; no refresh, inference or API fallback |
| Combined preflight | Read-only verification | `ready=true`, no blockers |
| Cleanup | Actual Docker query | No running benchmark containers or quarantine entries |

The relay exercised Aljure's strict envelope, rejected fragment nonexecution,
one accounted correction, context retrieval, SCI execution and recursive child
sessions. Native Prime exercised Python tools, root/child sessions, signed
thinking round trips, manual compaction and manual refinement. The twelve
receipts are scripted responses, **not twelve real model calls**. This does not
establish automatic compaction behavior, real-provider compatibility of this
new image, learning or benchmark accuracy.

The initial full Python run had one error: a transport fixture with a 0.8-second
test deadline did not produce its expected partial-response file while the Rust
build was running. The failure is retained. The full suite passed after the build
without changing test/transport code or deadlines. Scheduling interference is plausible, not
proven. No failed live run or official case was retried.

[Native proof](evidence/prime-head-to-head-v6/prime-isolation-proof.json),
[relay proof](evidence/prime-head-to-head-v6/subscription-relay-proof.json),
[raw relay archive](evidence/prime-head-to-head-v6/relay-raw.tar.gz),
[reconciliation](evidence/prime-head-to-head-v6/relay-reconciliation.json),
[regressions](evidence/prime-image-recovery-v1/regression-results.json),
[final preflight](evidence/prime-head-to-head-v6/preflight.json),
[credential status](evidence/prime-head-to-head-v6/credential-status.json).

## Run rules and authorization

Run one paired case only after new approval. Caps remain 12 calls and 12M
accounted/reserved tokens per arm, 32,768 maximum output tokens per request, and
the stated $12/$24 ceiling. All root, descendant, refinement, compaction and
allowed correction requests share the accounted gateway. No borrowing, selective
retries, model substitutions or additional cases. Unknown charges and cleanup
failure retain the existing stop rule. Failed and unattempted arms remain so.

Aljure retains `single-edn-map-v1` and one shared, accounted in-task formatting
correction. That allowance does not permit an arm rerun or execution of a rejected
fragment. Prime keeps its native architecture and legitimate capabilities.

V1/V2/V3 results and V4/V5 blocked plans are unchanged. V2's $4.32768 unresolved
reservation remains separate. An earlier unapproved V6 prevalidation candidate
was preserved before the final configuration added recovery-evidence hashes;
it dispatched no requests and is not the plan offered for approval.

This is a reused public engineering-recovery case, not a new held-out observation.
V3 Prime's exact F1 0.967741935483871 and cost $0.0663848 remain diagnostic
references. One successful pair cannot establish general superiority, a Clojure
language effect, or learned harness improvement. No old transcript or answer is
loaded into the new sessions.

**Approval request:** authorize plan
`703dbecf7db78d70c2f46be1190606f6021c9bda148c0536f357248c1e0cc31b`
for one Sonnet 5.5 pair through the Claude subscription, with a new maximum of
$12 per harness and $24 total API-rate-equivalent. This does not authorize Opus,
selector learning or the ten-case campaign. These are equivalents, not subscription
invoice amounts. Earlier approvals do not apply to this new plan.

After approval, recheck current credentials and preflight, then execute exactly:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v6/repl-lab
source var/worker.env
source var/prime-worker.env
export REPL_LAB_CLAUDE_KEYCHAIN_SERVICE='Claude Code-credentials'
export REPL_LAB_CLAUDE_KEYCHAIN_ACCOUNT="$(id -un)"
python3 -m benchmark paired-preflight \
  --suite var/official/pairs-one --plan var/sonnet-pair-v6/plan.json
python3 -m benchmark paired-run \
  --suite var/official/pairs-one --plan var/sonnet-pair-v6/plan.json \
  --out var/benchmarks/sonnet-pair-v6-live \
  --authorize-subscription-plan 703dbecf7db78d70c2f46be1190606f6021c9bda148c0536f357248c1e0cc31b
```

The environment variables identify the private Keychain entry; they contain no
token. Do not execute `paired-run` before approval. [Results](PRIME_HEAD_TO_HEAD_V6_RESULTS.md)
remain **NOT RUN**.
