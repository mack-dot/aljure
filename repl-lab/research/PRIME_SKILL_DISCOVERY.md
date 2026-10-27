# Prime skill discovery audit

Read-only source audit of Prime `c4c238ca025e382d96fb5f37e6328ca77fb82ef3`.
The checkout is `var/upstream/prime-agent`. No Prime source was changed or copied.
This is an architectural assessment, not a comparison result.

## What this version implements

- **Discovery:** `crates/pa-core/src/skills/discovery.rs:66` parses frontmatter,
  validates name/description, and excludes empty descriptions. Python detection
  at line 36 checks `pyproject.toml`, a valid normalized import, and
  `src/<import>/__init__.py`. Discovery does not establish behavioral correctness.
  `skills/loader.rs:82` resolves configured locations and reports collisions.
- **Progressive disclosure:** `skills/mod.rs:209` emits a compact inventory with
  name, type, Python import, description, and file location. It tells the model to
  inspect the file when relevant. Hidden/model-disabled entries are filtered.
  `skills/skill-creator/SKILL.md:62` explains routing descriptions and small skill
  bodies with references loaded on demand. This is a useful contrast with
  Aljure's former unexplained hashes.
- **Executable skills:** `skills/skill-creator/references/python-skills.md`
  documents editable kernel packages, direct callable imports, `run()` signatures,
  docstrings, and dependency handling. `kernel/bootstrap/venv/skills.rs:110`
  records package metadata hashes and resolves sibling dependencies.
  `kernel/bootstrap/runtime_code.rs:122` creates callable modules and copies
  `run()` signatures/docstrings; it exposes import failures as explicit errors.
  `prime-agent-runtime/src/rlm/skill.py:13` handles sync/async CLI calls.
  Package/source availability and callability are distinct from learning.
- **Refinement:** `skills/refine/SKILL.md` and its Python wrapper schedule host
  refinement after the turn. `refinement/planner.rs:10` asks a model for focused
  create/update/delete edits to prompt notes, memories, skills, subagents and
  factory workflows. The base prompt is immutable. Local/global scopes differ.
  Skill edits require arguments and a Python reference (`planner.rs:224`).
  `executor.rs:187` plans before mutation; `session_engine/refine.rs:247` rereads
  the store, applies, persists, and audits the result. Before/after snapshots
  support rollback (`refinement/mod.rs:350`). These checks do not independently
  demonstrate a held-out performance gain. Refinement is not a substitute for
  executable package review or testing.

## Narrow application to Aljure

Keep immutable artifacts, the broker, SCI isolation, the existing simulator,
independent acceptance, and shared budgets. Add controller-owned descriptions,
version-pinned interfaces, on-demand source inspection, and explicit hash selection.
Do not add Prime's package installer, memory store, prompt-rewrite loop, or a new
agent controller. Prime's host-permission execution is not Aljure's isolation model.

`skills.clj` derives interface and provenance from verified artifact envelopes.
It derives validation counts from hash-pinned controller evidence. Behavioral
descriptions are a **developer source review** in `config/skill-descriptions-v1.edn`,
bound to exact artifact hashes. They are not model claims or formal proofs.
Source inspection found that the retained policy checks CPU and memory only.
Its metadata states this limitation. Unknown hashes receive no behavioral claim.
Models cannot register or approve their own metadata. Staged artifacts do not
become selectable merely because they exist in the artifact directory.

`skills/list` exposes compact entries. `skills/describe` adds provenance.
`artifact/inspect` retains full code/forms on demand. `policy/select` installs
an approved policy for the current task, while `artifact/call` invokes it once.
Selection does not change promotion rules. Existing experiment prompts are
unchanged; only the versioned discovery study adds the new interface documentation.

Better descriptions are interface engineering. Deterministic reuse is a control.
A learned selector still needs independent development acceptance and unseen
comparison against both simpler alternatives. None of these edits proves learning.
