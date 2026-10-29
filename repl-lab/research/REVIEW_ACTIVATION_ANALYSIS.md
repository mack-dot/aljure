# Review ablation: did each mechanism actually run?

**Rule (preregistered):** a change on a task is credited to a level only if that
level's mechanism ran on that task. A level used on fewer than 6 of 11 tasks is
"not used by the model".

**Activation counts** come from executed SCI code and results
(`scripts/review_levels_compare.py`, `RULES`). A separate trace analysis by the
design agent (`evidence/controller-verification/l-traces.json`) agrees.

| Signal | L0 | L1 | L2 | L3 (1 arm) |
| --- | --- | --- | --- | --- |
| Per-item state kept in SCI (id sets, maps, atoms) | 4/11 | 6/11 | 5/11 | 0/1 |
| `show-items` calls | — | 0/11 | 0/11 | 0/1 |
| `:unknown` labels in executed code | — | — | **0/11** | 0/1 |
| `audit-labels` calls | — | — | **0/11** | 0/1 |
| Evidence gate fired | — | — | — | 0/1 |
| Answer computed in SCI (number appears in a tool result) | 11/11 | 10/11 | 11/11 | — |

## What the model did instead

- **Opus already uses its own structured pattern:**
  - read items in pages;
  - keep the indices of one label in an atom or set (`(def inf (atom #{…}))`, then `swap! … into` per page);
  - count at the end.
- It does this in the baseline (4/11) and kept doing it under L1 and L2, which
  described a different interface.
- The prose interface (58 + 64 + 13 words at the end of the system prompt) did
  not displace it. The model judged its own method adequate.
- **The single L3 arm** used no audit. It made 19 model calls with only 3 root
  `repl_eval` calls and started 6 workers. That fits delegation to child
  sessions; the child events were not checked.

## Consequences

1. **L1 was used** (6/11), but no more often than the baseline's own pattern
   would explain. Its effect cannot be separated from noise.
2. **L2 was not used by the model.** Its error change cannot be credited to the audit.
3. **L3 is structurally inert in this form.**
   - The gate fires only when the model's own last audit left items open.
   - The review sentence asks the model to reread `:unknown` items.
   - Neither can happen if the model never audits and never marks unknowns.
4. **Design lesson:** a verification mechanism that depends on the model
   volunteering the signal will not run. It has to be triggered by the
   controller, at `done`, from evidence the controller can read
   (`CONTROLLER_VERIFICATION_DESIGN.md`, on the design branch).
