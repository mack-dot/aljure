# SCI isolation repair v1

**ACTUAL ISOLATION PASS. No inference. Native/SCI relay remains blocked.**

The complete strict SCI gate passed on the unchanged worker image after Docker
recovery. All nine negative tests received a successful positive response in the
same worker first. All ten worker lifecycles confirmed cleanup. This is execution
and isolation evidence, not model performance or a security proof for arbitrary
code. [Gate proof](evidence/sci-isolation-repair-v1/isolation-proof.json),
[timing and cleanup summary](evidence/sci-isolation-repair-v1/isolation-summary.json).

## Allocation failure: what the evidence establishes

The earlier V4 allocation worker reached its 10-second operation deadline. It
had no OOM message and was still running with `OOMKilled=false` before cleanup.
That result does **not** establish a memory restriction. It remains a failed test.
The original trace is unchanged at
`evidence/command-envelope-v1/sci-check2-workers/repl-lab-6c38178889564043bb68ec04b39fd285.json`.

A diagnostic image added GC logging to the exact pinned worker filesystem and
JVM flags. It reached a real `java.lang.OutOfMemoryError: Java heap space` and
JVM exit 3. Its GC log shows repeated collection while the initially small heap
grows. This suggests a source of startup overhead; it does not establish why
the historical allocation operation exceeded its deadline.

A proposed `-Xms160m` comparison kept the maximum heap and all container limits
fixed. The first comparison stopped when Docker preflight failed before the
changed worker started. A versioned repeat with query instrumentation stopped
at `docker-info` on its first original-image slot. Both failures are preserved.
**The heap change was not adopted.** No gate used either diagnostic image.

The repaired checker now requires the exact JVM fatal heap-exhaustion line,
the supervisor's report of worker exit 3, and supervisor exit 2. A wall-time
failure, arbitrary nonzero exit, quoted OOM text, or cleanup failure cannot pass.
The existing readiness requirement remains. New result classifications separate
Docker preflight failure, readiness failure, execution deadline, JVM heap
exhaustion, and missing restriction evidence.

## Docker and startup variance

The first five paired Docker metadata probes completed: `info` took 120–629 ms;
image inspection took 38–92 ms. Later, the new instrumentation identified an
`info` timeout at 5,109 ms, before image inspection or worker creation.

Ten diagnostic pairs compared the Docker CLI with a direct local Docker `/info`
request. Both paths timed out in every pair. Direct `/_ping`, `/version`, and
`/containers/json` requests also timed out. Thus the observed outage extended
beyond SCI and the CLI. This does not identify a Docker internal root cause.
The original allocation timeout cannot be attributed conclusively to this later
outage. [CLI/daemon comparison](evidence/sci-isolation-repair-v1/docker-cli-vs-daemon.json),
[endpoint checks](evidence/sci-isolation-repair-v1/daemon-endpoints.json).

The operator separately approved a Docker Desktop restart because it interrupts
SPM PostgreSQL and Redis. The normal restart command timed out. Application quit
stopped the VM but left old backend processes. TERM stopped all but one stale
backend; that remaining backend was killed after the VM had stopped. Docker was
then started successfully. Both SPM services were restored and confirmed running.
No volumes were deleted and no worker resource setting changed. Recovery logs
and all diagnostic attempts are in the [raw archive](evidence/sci-isolation-repair-v1/raw-diagnostics.tar.gz).

The final strict SCI gate ran once after recovery in the frozen V5 checkout:

- Positive control and all nine negative controls: passed.
- Allocation: exact JVM heap OOM and exit 3; 1.769 seconds from observed readiness
  through negative operation and cleanup. This is not a container OOM-kill claim.
- First request to first response: 4.208–7.755 seconds across ten workers.
- End-to-end negative-worker readiness: 5.623–10.208 seconds, including Docker
  preflight/create/inspect. The unchanged 10-second response clock starts at
  transport attach/request, so these are different measurements.
- 24 Docker preflight queries: no failures; maximum 2,277.793 ms.
- Cleanup: 10/10 confirmed; no running benchmark workers or quarantine entries.

Memory remains 256 MiB, JVM maximum heap 160 MiB, CPU one, PIDs 32, scratch 8 MiB,
response deadline 10 seconds, and task/session deadline 120 seconds. Network,
filesystem, credential and evaluator restrictions are unchanged. The image is
`sha256:aa6d6231f2f5552308c657ce05ad9e377832ee0ae83bf0f1044874495a1a33d4`.
Its existing startup profile uses `-XX:TieredStopAtLevel=1`; no new JVM flag was selected.
One passing gate does not prove long-term startup reliability.

## Tests and remaining boundary

Implementation commit: `8e6dea8bc6ed42dcbcd7d50ae58cc1b368444a5f`.
Only `scripts/isolation.py` changes execution behavior relative to V4; the other
runtime delta is the new versioned proposal. No prompt, parser, provider, native
Prime source, worker code, scoring rule, deadline or resource limit changed.

| Command | Evidence | Result |
| --- | --- | --- |
| `python3 -m unittest test_python.test_isolation -v` | Offline pipe fixtures | 14 tests passed |
| `python3 -m unittest discover -s test_python -v` | Offline suite | 108 tests passed |
| `make test` | Offline Clojure suite | 96 tests / 1,804 assertions passed |
| `python3 scripts/isolation.py test` | Actual SCI containers | Complete strict pass |
| `python3 -m benchmark.prime.isolation` | Actual prerequisite check | Failed: pinned native image absent |
| Revised actual native/SCI relay | NOT RUN | Native prerequisite unavailable |

After recovery, native image
`sha256:26cf6378c68b94e8edfe12f9c79976c26d35d774ac3ef6223e49baf39cf314ff`
could not be inspected. Docker lists no native Prime image and no build cache.
No exact image archive was found in the checked local experiment locations.
The inspected Docker logs do not establish when or why the image disappeared.
Do not infer that restarting Docker normally deletes images.
[Exact blocker](evidence/sci-isolation-repair-v1/native-image-blocker.json).

No replacement was selected. Restoring the exact image is required to finish
this frozen execution boundary. If restoration requires a rebuild with a new
image identity, record that runtime change in a new freeze before authorization.
This SCI-only repair did not change Prime or rebuild its environment.

V1's 23 files, V2's 21 files, V3's 52 files, and 128 published historical files
match their prior hashes. V4 remains blocked and untouched.
[Integrity check](evidence/sci-isolation-repair-v1/historical-integrity.json).

## Reproduction and next gate

The final gate command used the dedicated clean checkout:

```sh
cd /Users/mackianni/aljure-sonnet-pair-v5/repl-lab
source var/worker.env
REPL_LAB_WORKER_AUDIT_DIR="$PWD/var/sonnet-pair-v5/isolation-workers" \
  python3 scripts/isolation.py test
```

Use a fresh audit directory for any new diagnostic; do not overwrite this one.
After the exact native image is restored, run its strict gate, then the existing
`paired-relay-fixture`, then combined preflight. Require all checks before asking
for inference approval. [V5 frozen protocol](PRIME_HEAD_TO_HEAD_V5_PROTOCOL.md).
