# Prime head-to-head V7 results

**LIVE MODEL RUN, RUN ONCE (2026-10-28). Native Prime completed with F1 1.0;
Aljure failed before answering.** Plan
`9798e89ed6bceec7c6e741588c82517dbaf50f2923c665116a0b1e620e0b3338`, clean
checkout at `7b0cfa7`, Sonnet 5.5 through the Claude subscription, $12 per
harness / $24 total API-rate-equivalent. Fresh credentials and preflight passed
before the run. The new Docker gate passed for both arms: no pending restart,
both pinned images present, and the same Docker session before and after
each arm.

| Harness | Outcome | Official F1 | Calls / cost / task time |
| --- | --- | --- | --- |
| Aljure | Error: command rejected after its single correction | 0.0 | 4; $0.028404; 32.8 s |
| Native Prime | Completed (official pair parser) | **1.0** | 4; $0.0690464; 38.5 s |

Total $0.0974504 API-rate-equivalent; accounting complete; no unknown or
uncertain requests. Official summary: Prime wins this one case (paired
difference −1.0). One reused public case is diagnostic engineering data, not
a general comparison.

## What the V7 fixes achieved

- Docker: no infrastructure failure. Prime completed, improving on its V3 F1
  of 0.968 on the same case.
- Dead-container handling and the source-block envelope were not exercised:
  no container died, and Aljure never reached a source-block command.

## Aljure failure: native tool-call markup instead of a command

1. Response 1: `<invoke>` / `</invoke>` tags, then a valid map. Rejected
   (`map-envelope`); the single correction was used.
2. Responses 2–3: valid commands (`context/metadata`, `context/query`), executed.
3. Response 4: only two empty `<invoke name="eval">` tag pairs and no command.
   Rejected with no correction left; the session ended.

V3, V6 and V7 all show the model emitting tool-call markup when Aljure asks for
plain-text EDN with no native tools. The string-escaping problem V7 fixed was
real, but secondary. The primary blocker is the text-command interface itself:
the model reaches for native tool calls, which native Prime provides.

## Next experiment (not started; needs a new frozen plan and approval)

Give Aljure's commands to the model as one native provider tool (structured
JSON input mapped to the same EDN command schema and the same broker,
capability and SCI checks), so commands arrive as tool-use blocks instead of
text. Keep strict rejection of everything else. This addresses the failure
seen in every live Aljure arm so far.
