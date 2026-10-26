# Decisions

- 2026-10-26: The workspace was empty and was not a Git repository. Create
  `repl-lab/`; do not touch production apps, infrastructure, or global settings.
- Pin Clojure 1.11.3 and data.json 2.5.0, which are cached locally. Use Java 21.
  The offline launcher reads these exact jars and never downloads dependencies.
  Standard `deps.edn` remains the connected-machine setup path.
- Pin SCI 0.10.49 for the isolated worker. Its API was checked against the tagged
  official README/API. It is absent from this machine's Maven cache.
- Use Python's SQLite bridge for durability because sqlite-jdbc is not cached.
  Record the actual Python and SQLite runtime versions in manifests.
- Docker access is denied in this sandbox. Maven DNS resolution also fails.
  Generated-code execution must fail closed. Continue trusted fixture tests.
- Order simultaneous events by failure, recovery, then completion, then stable
  event sequence. Dispatch happens only after pending events at the current time.
- Use keyed SHA-256 workload values. Policies cannot alter the random stream.
- Keep baselines outside the initial learner library. Use fixtures only to test
  evolution plumbing. Do not attribute their authorship to an experimental model.

Official references checked on 2026-10-26:

- https://clojure.org/reference/deps_edn — pinned dependency coordinates.
- https://clojure.github.io/data.json/ — `read-str` and `write-str`.
- https://github.com/babashka/sci/blob/v0.10.49/API.md — `init`, `eval-string*`.
- https://github.com/babashka/sci/blob/v0.10.49/README.md — classes and permissions.
- https://docs.docker.com/engine/containers/resource_constraints/ — resource flags.
- https://docs.python.org/3/library/sqlite3.html — transactions and parameterized SQL.
- https://platform.claude.com/docs/en/api/messages/create — provider request/usage shape.
- https://platform.claude.com/docs/en/api/messages/count_tokens — pre-inference token count.
- https://react.dev/reference/react-dom/client/createRoot — React root API.
- https://esbuild.github.io/api/ — static dashboard bundling.
- https://www.typescriptlang.org/tsconfig/ — TypeScript compiler options.

- The Sites skill's local-only workflow applies to the dashboard. No Site was
  registered or published. React packages were available in the npm content cache;
  a checked extraction path was used after offline metadata resolution failed.
- Native dashboard package integrity values are stored in both the npm lock and
  the offline manifest. The cached native esbuild package is Darwin/ARM64; other
  platforms need their matching pinned esbuild binary during setup.
- A bundle omits old author/session IDs but keeps artifact origin. Restoring a
  library produces fresh content hashes and consistently remaps dependency/workflow
  references. The evaluator records the original-to-fresh mapping.

- Experiment version 2 gives frozen and evolving acquisition arms identical task
  runners and fresh stores. Both can stage, test, and use code within a task. Only
  approved evolving artifacts cross task boundaries. Narratives do not cross in
  either arm. Arm order alternates. The operator cap is split equally across all
  arm/task pairs; unused allowances do not move between tasks.
- Resume uses durable task checkpoints. An interrupted task becomes a recorded
  failure unless its episode was already saved. Pending provider outcomes retain
  their full reservations. Resume never repeats those calls or resets allowances.
  A process lock prevents concurrent acquisition. Final seals prohibit resume.
- Full development worlds and replay hashes stay in controller-only files. The
  learner receives bounded observation/action traces. Failed execution has an
  explicit replay transition and remains in scoring.
- Direct skill-removal panels compare retained code and the compatible initial
  policy with no model replacement or inference. These panels isolate code effect;
  frozen/evolving RLM panels separately measure agent behavior with equal tools.
- Provider input hashes and responses support strict recorded-response playback.
  Playback records zero new token charges and preserves original usage separately.
  It refuses divergent inputs and unknown outcomes. It is not a fresh model rerun.
- Child SCI workers persist across child-session resume until the root task ends,
  subject to the same worker lifetime limits. Cancellation/failure closes workers.
  The lifecycle is mock-tested; actual SCI persistence remains an isolation gate.
- Git is now present at the workspace parent. New manifests record HEAD and dirty
  status in addition to the exact source hashes. Earlier no-Git manifests remain
  unchanged historical records.

- Continued audit: worker cleanup must be confirmed. Failed removal or timeout
  quarantines generated-code execution until recorded container cleanup succeeds.
  A successful empty daemon listing can establish that a failed create left no
  container. An unavailable daemon cannot establish absence.
- Worker transport drains final output after process exit and rejects non-EDN
  results. Definition examples end in nil. The positive isolation control now
  sets a binding and reads it in a later request; it has not run on actual SCI here.
- Docker limits remain fixed in the trusted supervisor. The Clojure preflight
  rejects a config that advertises different limits. Changing enforcement requires
  a new frozen source snapshot and new isolation tests.
- Subagent model calls currently run synchronously, including nested delegation.
  Nested subagents can message each other through the controller without root
  forwarding. A scripted integration test exercises depth two and direct acked
  messages. This does not claim autonomous decomposition or real model recursion.

- Final evaluation normalizes the initial control library through the same fresh
  artifact-envelope path as the retained export. When no skill changed, metadata,
  model inputs, and deterministic outcomes must match across arms. Final evaluation
  also verifies the frozen source before/after each model episode and before report
  publication, so source changes invalidate the evaluation instead of being hidden
  in a later manifest.

- Experiment version 3 propagates the configured event limit and one absolute
  task deadline into development, final, and learning policy execution. Count-token
  and inference HTTP phases share that deadline. Workers convert the remaining
  task time to a monotonic deadline; requests cannot extend it. Cleanup and durable
  recording can continue after useful execution stops, within their own bounded
  transport timeouts. Recorded wall-budget outcomes remain scored and replayable.
- Idle SCI workers retain bindings while a parent waits for the model. The
  per-expression wall limit applies during execution; the task/session deadline
  bounds idle lifetime as well. No generated code ran in the host pipe tests.
## Sonnet 5.5 live-run preparation — 2026-10-26

- The user selected `claude-sonnet-5-5` at $2/million input and $10/million
  output tokens. Anthropic's model page confirms that API ID and standard rates:
  https://platform.claude.com/docs/en/models/sonnet-5-5/overview.
- The proposed caps are $15 acquisition, $10 held-out, and $10 cold boot. The
  user explicitly withheld spending approval until a later confirmation and
  private credential setup. `config/live-proposal.edn` is inert proposal data.
- Reserve a proposed $1 smoke allowance within acquisition, leaving $14 for
  matched frozen/evolving acquisition. This allocation is also unapproved.
  Do not silently add smoke spending above the $35 total or retry a paid attempt.
- All live entry points now require the same worker-image proof with all nine
  negative-test results true. Docker readiness alone does not satisfy this gate.
- The smoke verifier requires ordered external-query, root SCI, selected-context
  child call, child SCI, consumed child result, and final-answer evidence. It
  checks real-provider receipts for both sessions. Smoke establishes capability,
  not learned skill retention or performance improvement.
- Broker results and errors now reference their call sequence in durable traces.
  This changes the fixed runtime and advances the experiment version to 4.
- No paid request, container build, or actual SCI test has run during this
  preparation. Docker access is denied. Credentials and a worker image are absent.
