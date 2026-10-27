# V3 live evidence

Evidence category: **LIVE MODEL RUN**. One authorized pair; no selective retries.
Prime completed. Aljure failed command parsing. The full interpretation is in
[the results report](../../PRIME_HEAD_TO_HEAD_V3_RESULTS.md).

- `manifest.json` lists all 52 original files and the raw archive hash.
- `raw-run.tar.gz` contains `sonnet-pair-v3-live/`, including request bodies,
  JSON/SSE responses, traces, answer, SQLite stores and native state snapshots.
- `authorization.json` records exact-plan approval. `authorized-final-preflight.json`
  and `authorized-credential-status.json` record the checks before execution.
- `results.jsonl`, `report.json` and `preflight.json` are unchanged copies from
  the original run. Aljure's report zero is a failure penalty, not answer F1.
- `verify.py` reads the frozen official scorer and independently checks scores,
  receipts, decimal costs, request settings, trace hashes and SQLite integrity.
  `independent-audit.json` is its output. It makes no model calls.
- `parser-reproduction.json` contains the exact data-only replay command and
  `Trailing EDN` result. It does not evaluate generated source.
- `post-run-cleanup.json` distinguishes current-run cleanup from a never-started
  container created before V3. Its inspection is preserved separately.
- `previous-attempt-integrity.json` verifies V1/V2 unchanged.
- `credential-scan.json` identifies only the pinned noncredential loopback
  sentinel. `audit-preparation-note.json` records analysis-script corrections.

Do not deserialize the archived native pickle in a host process. The audit reads
only its bytes for hashing. No provider credentials are required to rescore.
The frozen protocol and offline validation remain in `../prime-head-to-head-v3/`.
The execution command in the results report is historical, not permission to rerun.
