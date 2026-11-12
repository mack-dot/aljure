# Host execution policy v1 (2026-11-03)

Scope: the host side of one frozen live experiment on this Mac (16 GB RAM, 10 CPUs, Docker Desktop
28.5.1 with an 8 GB Linux VM). It observes and refuses; it never changes a frozen plan, a worker limit,
or the isolation boundary. It lives in `var/` (git-ignored) so the frozen source identity of
Experiment A (`996aa397…`) and the causal plan (`53f2fcb8…`) stay valid; it is archived into
`research/evidence/` with the run.

## Sources of resource pressure found in the Phase 0 audit

1. Host memory is saturated: 15 GB of 16 GB used, 7.2 GB in the compressor, swap 13.1 GB of 14.3 GB,
   0.8 M pageouts. Chrome, Cursor and Claude Code sessions are the consumers; the Docker VM reserves
   8 GB on top. This is the mechanism behind slow `docker info` answers (the supervisor's 5 s readiness
   query timed out twice in ~200 starts on 2026-10-29) and slow worker startup (historical median 6.1 s,
   p90 10.2 s, max 15.8 s against the 30 s limit; today, with a warm engine, 0.5-1.1 s).
2. Another project shares the daemon (61 exited `forge-*` containers, postgres, redis, running jobs
   between 14:51 and 15:32 today). Its jobs can start at any time and cannot be controlled from here.
3. Docker Desktop Resource Saver idles the engine; `docker desktop status` then reports `stopped`
   with a stale session id although `docker ps` answers. The frozen runner refuses a task in that
   state ("Docker Desktop is not running"), so the engine must be awake at launch.
4. An externally killed supervisor leaves an orphan `repl-lab-<hex>` container and no quarantine
   marker (one found: created 15:32:45 EST, lived 1.2 s, removed after its record was saved). The
   frozen runner's per-task Docker check does not look for orphans.
5. Pinned images live only in the daemon and have vanished twice; archives exist (see memory
   `docker-image-identity-hazard`). No OOM kill in 170 recorded worker audits.

## Policy

1. One worker at a time. The frozen runners dispatch tasks sequentially; only the root session opens a
   worker and children never do (`runtime.clj:378`). `run_guarded.py` adds an exclusive host lock, so
   the two frozen experiments cannot run concurrently.
2. Per-worker limits are the frozen supervisor's: 256 MB, 1 CPU, 32 PIDs, 8 MB scratch, 10 s per
   expression, 30 s startup, 64 KB output, 300 s per task (plan `task_seconds`). Nothing here changes them.
3. Startup, execution, cleanup and failure are recorded separately by the supervisor's SessionAudit
   (`container-created`, `worker-ready` with `startup_ms`, `request-written`/`response-read`,
   `supervisor-error` with type and message, `state_before_cleanup` with `OOMKilled` and exit code,
   `cleanup-finished`) under each task's `worker-audit/`. `host_monitor.py` adds, every 5 s, host memory,
   swap, load, Docker Desktop session, container counts by owner, `docker stats` of running containers,
   and every container create/start/die/oom/kill/destroy event from `docker events`.
4. Detection: OOM (`OOMKilled` in the audit, `oom` event in the monitor), worker disappearance
   ("Worker exited during startup", "Worker failed with exit", `die` events without a matching
   `response-read`), readiness timeouts ("Worker startup limit"), daemon stalls (gate/monitor docker
   query timeouts are recorded as such), resource exhaustion (swap, free memory, load samples).
5. Refusal, never weakening: `host_gate.py` refuses to launch when the plan file records authorization
   or calls, the run directory exists, the quarantine is non-empty, an isolation preflight fails, Docker
   Desktop is not `running` or a restart is pending, a pinned image is missing, an orphan worker exists,
   any other project's container is running, host disk is below 10 GB, the OAuth credential expires in
   under the required window (default 1 h; the hard wall cap is 40 × 300 s = 3.3 h), or the positive
   startup probe through the frozen supervisor fails, exceeds 20 s, or leaves a container behind.
   Host swap above 90% (`--max-swap`) is a refusal (owner decision 2026-11-03: launch only after host
   conditions improve). Load above the CPU count and under 512 MB free memory are warnings.
6. Every frozen cap and failure rule stays in force: the gate runs before the runner's own preflight,
   and the runner still performs its per-task Docker state, disk and budget checks.

## Use

```
python3 var/host-policy-20261103/run_guarded.py substrate --approve <plan_sha256>
python3 var/host-policy-20261103/run_guarded.py causal   --approve <plan_sha256>
python3 var/host-policy-20261103/run_guarded.py substrate --approve <plan_sha256> --dry-run 20   # gate + monitor only
```
The launcher sets the pinned image environment from the plan itself and runs exactly
`python3 -m benchmark.<module> run --suite … --plan … --out …/run-1 --authorize-subscription-plan <hash>`.
Records: `gate-<t>.json`, `monitor-<experiment>-<stamp>.jsonl`, `summary-<experiment>-<stamp>.json`.

## Before approving a live run (operator)

Close memory-heavy applications so swap drops; make sure the other project is idle; wake the engine
(`docker ps` or the gate probe); renew the Claude Code OAuth credential if it expires within the run window.
