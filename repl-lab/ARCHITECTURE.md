# REPL Lab

The controller is trusted Clojure on the JVM. The scheduling simulator uses
immutable values and integer virtual time. Policies see a projection of state.
They cannot call the simulator transition functions. Controller records live in
SQLite. JSONL exports and content-addressed EDN artifacts support replay.

Fixed components: simulator, checker, scoring, split definitions, capability
broker, budget accounting, isolation runner, and promotion rules. Changing one
creates a new experiment version. Learnable components: pure policy/analysis
functions and declarative context/delegation workflows. Artifacts contain source
and parsed forms. The controller alone can approve and activate artifacts.

Simulator workers execute jobs. Agent sessions investigate and propose changes.
These are separate identities. Each session pins an artifact hash. Child model
calls share the root budget. The inner scheduling loop uses deterministic code.
The provider stays outside the code worker. No evaluator or provider objects enter
SCI. A narrow, serializable request protocol connects the two.

SQLite is accessed through a small Python standard-library bridge. Clojure owns
the controller logic; the bridge only performs bounded storage transactions.
This avoids an unavailable native JDBC dependency in the offline environment.

The local fixture path runs reviewed developer fixtures, never arbitrary source.
Generated code requires a separately isolated SCI worker. Failing isolation
preflight disables that path. Fixture replay cannot establish learning.
