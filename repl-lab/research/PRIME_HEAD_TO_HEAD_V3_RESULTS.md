# Prime head-to-head v3 results

**LIVE MODEL RUN — Prime completed; Aljure failed before code execution.**
The authorized pair ran once on 2026-10-27, from 14:35:28 to 14:36:43 UTC.
Prime's official F1 is **0.967741935483871**. Aljure returned no answer because
its third model response violated the EDN command contract. All seven requests
have complete provider receipts. Total usage is **$0.0855548 API-rate-equivalent**,
with **$0 unresolved** for V3. This used the Claude subscription, not API credits.

There was no selective retry, model change, source change, scorer change or
deadline extension. The first two-answer scored comparison is still incomplete.
Prime succeeded on this attempt; Aljure did not. No language-superiority or
harness-learning conclusion follows from this result.

## Frozen experiment and authorization

The [protocol](PRIME_HEAD_TO_HEAD_V3_PROTOCOL.md) remains the original freeze
record. Its earlier NOT RUN status describes the state before this execution.
The operator separately approved the exact plan and new allocation.
[Authorization](evidence/prime-head-to-head-v3-live-attempt1/authorization.json),
[final preflight](evidence/prime-head-to-head-v3-live-attempt1/authorized-final-preflight.json),
[credential metadata](evidence/prime-head-to-head-v3-live-attempt1/authorized-credential-status.json),
and [launcher status](evidence/prime-head-to-head-v3-live-attempt1/launcher-status.json)
are preserved.

| Pin | Value |
| --- | --- |
| Plan SHA-256 | `b81b71d58858258c2d7869b20ad8fbef30bd62596e4001b5d6a816921bcb40c8` |
| Aljure source commit | `7c06c68d0aa400ea4fe1ed364cccf80585af9281` |
| Full source SHA-256 | `ce1aec169cd491abda4dd16bf94d8cfadd68afdeee5764b0de84f0a4b37acb25` |
| Runtime SHA-256 | `c930cf81a0ebe519d475634602e5a342f47381d5ba211d1c7edde0c9b0b40d4f` |
| Native Prime revision | `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`, unmodified |
| Official case | `oolong-pairs-validation-8192-1` |
| Scorer SHA-256 | `1f9960867e367fb45d392e816333e3764928d4b79f43ca1a471763034154c2ce` |
| Base prompt SHA-256 | `8c86337af0528283f1359fa83f6248bec3594736ed91e0a45901adf68b993005` |
| Requested and returned model | `claude-sonnet-5-5`, all seven receipts |
| Provider | Claude subscription OAuth, `native-claude-oauth-v1`, Anthropic messages endpoint |
| Settings | Adaptive/summarized thinking, medium effort, 32,768 maximum output tokens |
| Order and limits | Aljure then Prime; 120 seconds, 12 calls and $12 equivalent per arm; $24 new total |

SCI image: `sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Native image: `sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`.
Provider/configuration hashes and the complete source-file map are in the
[frozen manifest](evidence/prime-head-to-head-v3/experiment-manifest.json).
The execution checkout remained clean after the run. Prompts, official input,
scorer, native capabilities, timeouts and ceilings remained as frozen.

Strict SCI/native isolation, the repaired ten-check relay, credential metadata,
and source/accounting preflight passed before dispatch. The recorded 34 Python
tests and 18 Clojure tests / 156 assertions remain **OFFLINE / FIXTURE** evidence.
The 61-second transport regression uses a virtual clock. None of V3's provider
requests lasted over 45 seconds, so V3 adds no live long-response observation.

## Actual outcomes

| Measure | Aljure | Native Prime |
| --- | --- | --- |
| Terminal status | Failed: `Trailing EDN` | Completed |
| Official answer F1 | Not measured: no answer | **0.967741935483871** |
| Runner failure-denominator score | 0 | 0.967741935483871 |
| Correct / predicted / gold pairs | No answer | 465 / 465 / 496 |
| Precision / recall | Not measured | 1.0 / 0.9375 |
| Model calls | 3 | 4 |
| Uncached input tokens | 7,600 | 10 |
| Cache creation input tokens (5 minutes) | 0 | 18,747 |
| Cache read input tokens | 0 | 43,373 |
| Total input, including cache | 7,600 | 62,130 |
| Output tokens, including thinking | 397 | 1,516 |
| Known API-rate-equivalent usage | $0.0191700 | $0.0663848 |
| Unresolved calls / reserved amount | 0 / $0 | 0 / $0 |
| Full arm wall time | 31.788650 s | 40.465693 s |
| Agent supervision span | 30.115386 s | 37.165017 s |
| Summed host provider-transport duration | 19.795030 s | 15.248968 s |
| Executed tools | 2 context operations | 3 Python REPL operations |
| Recorded tool duration | 810.573 ms, broker elapsed | 25 ms, native kernel-reported total |
| Actual SCI evaluations | 0 | Not applicable |
| Observed child / refinement / compaction calls | 0 / 0 / 0 | 0 / 0 / 0 |
| Retained skill invocation / learned artifact | None | None observed |

The [independent audit](evidence/prime-head-to-head-v3-live-attempt1/independent-audit.json)
recomputed official F1, checked every receipt against saved JSON/SSE responses,
and reconciled exact decimal rates against both ledgers. It verified all seven
request settings, all 46 trace artifact hashes and three SQLite stores.
The [original report](evidence/prime-head-to-head-v3-live-attempt1/report.json)
is unchanged. Its zero for Aljure keeps the failed slot in the denominator; the
answer scorer was not run on a nonexistent answer. Its loss count is not a
comparison of two valid answers.

Prime missed 31 gold pairs and added none. They correspond to omitting one of
32 eligible users. No answer repair or additional evaluation case was run.
Aljure's lower spend and shorter duration reflect early failure, not demonstrated
inference efficiency. Prime's native cache behavior also differs from Aljure's
uncached requests. Rates per million are input $2, output $10, 5-minute cache
creation $2.50, cache reads $0.10; no 1-hour cache creation occurred. Actual
subscription invoices and local compute cost remain unknown.

Provider-transport duration includes trusted helper, credential, network and
response-read overhead. It is not server-only generation time. Whole-arm wall
time also includes startup, forwarding, persistence, collection and cleanup.
Native tool start/end observations total 24.532 ms; the kernel reports rounded
durations of 4, 8 and 13 ms. Broker and kernel timing instruments differ. Neither
arm exhausted its 120-second execution limit.

## Exact failure and execution paths

Aljure's first two responses were valid commands. It queried metadata (195
context records), then the first five lines, including one actual question.
Both operations completed. The third response arrived intact with HTTP 200 and
valid usage. Its text mixed XML-like invocation fragments and Markdown with an
EDN map. It violated the explicit one-map/no-Markdown contract.

The frozen `util/read-edn` rejected trailing forms. `runtime/run-session!` parses
the command before its recoverable broker-error block. The parse error reached
the outer session failure handler. The proposed SCI operation never ran. This
was a **model-command/interface failure**, not a transport timeout, unknown charge,
worker startup failure or demonstrated Clojure computation failure.
The [read-only parser reproduction](evidence/prime-head-to-head-v3-live-attempt1/parser-reproduction.json)
reproduces `Trailing EDN` from the original response without executing generated
code. It does not establish why the model produced malformed output.

Exact boundary, relative to the archived `sonnet-pair-v3-live/` root:

- Gateway request: `abe7ea37-2854-4a7e-a0e9-12f4cd3d1109`.
- HTTP request: `req_011CgSuhR7SqYzhNFJPbZgdp`.
- Provider message: `msg_011CgSuhRPJxkwrNFa96RhsQ`.
- Raw body: `00-aljure/gateway/transport-bodies/af83ce73-0550-44f3-9604-7a5cff363461.body`.
- Body SHA-256: `94ceaf057076832a0a16d61ff34813bf5fa859c64ff74bc84a1dce32a3aac557`.
- Accounting/transport: `00-aljure/gateway/usage.jsonl` and `transport.jsonl`.
- Agent trace: `00-aljure/agent/events.jsonl`, sequences 12–14: third input,
  reconciled result, then failed root. Successful tools are sequences 4–5 and 9–10.
- Terminal result: `00-aljure/agent/result.json`.

Prime read the context file and previewed it, parsed all 188 question rows, then
selected row indices and used Python combinations to write its answer. All three
`python_repl` calls completed without kernel restart. This is context processing
and model-directed classification, not learned-skill use. Its trace contains one
session, four turns and no subagent spawn, refinement or compaction. Aggregate
accounting covers all gateway requests. General native per-agent ancestry remains
unverified and was not exercised by this one-session run.

Prime evidence:

- `01-prime/native/native.jsonl`: exact generated code, tool results and lifecycle.
- `01-prime/event-timing.jsonl`: tool starts/ends at sequences 21–22, 61–62 and
  136–137; complete agent timing is preserved.
- `01-prime/answer.txt`: scored answer, SHA-256
  `b368de951e7d6b122cd481cc4929a110ccd280e19e6fca0bb2126ff9f943e460`.
- `01-prime/gateway/events.jsonl`: all exact request bodies and receipts.
- `01-prime/gateway/transport-bodies/`: four original SSE responses. Terminal
  usage counters were merged as cumulative values, not added repeatedly.

Both `execution.json` files contain attach-client exit `-9`. The frozen
supervisor explicitly kills its attached process after receiving completion.
Native completion codes are Aljure 2 and Prime 0; supervisor failure fields are
null. This `-9` is not evidence of OOM or timeout. Both gateway cleanup reports pass.

## Preservation and cleanup

[Raw archive](evidence/prime-head-to-head-v3-live-attempt1/raw-run.tar.gz):
**52 original files**, byte-preserved. SHA-256:
`c9862436dd5073e69fb759004af44a9ed3c32cfc6f3d1d4d97ff6c94d70e375b`.
The [manifest](evidence/prime-head-to-head-v3-live-attempt1/manifest.json) lists every
file hash. No native pickle was deserialized. The secret-shape scan found only
the exact pinned, noncredential loopback sentinel in native configuration;
`auth.json` is empty. Private provider credentials remained on the trusted host.
[Credential scan](evidence/prime-head-to-head-v3-live-attempt1/credential-scan.json).

[Post-run inspection](evidence/prime-head-to-head-v3-live-attempt1/post-run-cleanup.json)
found no running benchmark process or container and no new container residue.
The broader `docker ps -a` check found one never-started SCI container created at
03:59 UTC, before this 14:35 attempt. Its PID is 0 and start timestamp is unset.
It is preserved separately; the pre-run `docker ps` check listed running
containers only. This is not attributed to V3 startup or cleanup.

V1's 23 original files, V2's 21 original files and both archives still match their
previous hashes. Their reports and ledgers were not modified.
[Integrity checks](evidence/prime-head-to-head-v3-live-attempt1/previous-attempt-integrity.json).
V2's **$4.32768 unresolved reservation remains unresolved**. V3's zero unknown
balance does not settle that previous request.

## Reproduction and next step

The exact authorized command ran once from the frozen checkout:

```sh
python3 -m benchmark paired-run \
  --suite var/official/pairs-one \
  --plan var/sonnet-pair-v3/plan.json \
  --out var/benchmarks/sonnet-pair-v3-live \
  --authorize-subscription-plan b81b71d58858258c2d7869b20ad8fbef30bd62596e4001b5d6a816921bcb40c8
```

This records execution; it does not authorize another run. Reproduce only the
score and accounting audit, with no inference or generated-code execution:

```sh
cd /Users/mackianni/aljure/repl-lab
PYTHONPATH=/Users/mackianni/aljure-sonnet-pair-v3/repl-lab \
  python3 research/evidence/prime-head-to-head-v3-live-attempt1/verify.py \
  /Users/mackianni/aljure-sonnet-pair-v3/repl-lab/var/benchmarks/sonnet-pair-v3-live \
  /Users/mackianni/aljure-sonnet-pair-v3/repl-lab/var/official/pairs-one
```

The run directory can also be restored from the archive. Use frozen source and
the verified official suite. Do not restore native pickle state into a host
interpreter. Official import and environment commands remain in the protocol.

**One recommended next step:** conduct a versioned, offline command-boundary
repair using the saved malformed response. Verify bounded error feedback while
keeping malformed commands non-executable and subsequent requests subject to the
same caps. Preserve V3. Any new live pair needs a new protocol and approval.
A multi-case study should follow a completed two-answer pair; it needs independent
context variation and its own budget.

This is the same public recovery case used in V1/V2, not a new held-out observation.
Native Python, prompt, filesystem, cache and process differences remain as
preregistered. SCI was not exercised here. Language effects, autonomous reuse and
harness-level learning remain unproven. No Opus, selector or ten-case inference
was run or authorized here.
