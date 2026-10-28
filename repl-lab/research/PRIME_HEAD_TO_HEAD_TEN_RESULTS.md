# Prime head-to-head, ten cases: results

**LIVE MODEL RUN, RUN ONCE (2026-10-28). Prime ahead: Aljure 2 wins, 3 ties,
5 losses; mean F1 0.847 against 0.965.** Plan
`357787994ee4f1fd640f6f3236f90339723aae6cfc5add569ed6da2aaae1672b`, clean
checkout at `9cc0812`, Sonnet 5.5 through the Claude subscription. The suite is
the first ten OOLONG-Pairs 8K validation tasks, built offline from pinned
upstream data. They share one context, so they are not ten independent samples.
Task 1 is the case used in all earlier runs. The arm order alternated by case.

| Case | Aljure F1 | Prime F1 | Aljure $ / s | Prime $ / s |
| --- | --- | --- | --- | --- |
| 1 | 1.000 | 1.000 | 0.0517 / 61 | 0.0701 / 42 |
| 2 | 0.930 | 0.930 | 0.0519 / 56 | 0.0671 / 35 |
| 3 | 0.859 | 0.966 | 0.0532 / 69 | 0.0651 / 43 |
| 4 | 1.000 | 0.950 | 0.0596 / 84 | 0.0743 / 47 |
| 5 | 0 (timeout) | 0.929 | 0.0995 / 123 | 0.0844 / 67 |
| 6 | 0.934 | 1.000 | 0.0652 / 103 | 0.0643 / 42 |
| 7 | 0.957 | 0.957 | 0.0677 / 70 | 0.0822 / 52 |
| 8 | 1.000 | 0.960 | 0.0642 / 92 | 0.0676 / 45 |
| 9 | 0.895 | 0.963 | 0.0760 / 77 | 0.0775 / 40 |
| 10 | 0.900 | 1.000 | 0.0560 / 67 | 0.0646 / 38 |

Totals: Aljure $0.6449 and 800 s; Prime $0.7173 and 452 s. Accounting is
complete, with no unknown requests. On the nine cases Aljure completed, the mean
F1 is 0.942 for Aljure and 0.969 for Prime.

## Diagnosis

1. **Controller overhead, not SCI, made Aljure slow.** Per arm, worker startup
   was 5–7 s and all evaluation took under 0.5 s. The time between model calls
   was 18–48 s for Aljure and 7–9 s for Prime. Every ledger read parsed the
   whole run record with a reflective per-character scan:
   `bounded-reader-input!` lacked a `String` type hint. A 284 KB ledger took
   514 ms to parse, and each step reads it several times. With the hint, a read
   takes 53 ms instead of 560 ms, and a write 95 ms instead of 608 ms. The case-5
   timeout and the near-timeouts (103 s, 92 s) follow from this.
2. **The two harnesses displayed tool output differently.** Prime's tool
   returns printed output as lines. Aljure returned a string value as escaped
   EDN, which puts the whole result on one line with `\n` sequences. In case 3,
   a 56-line question list reached the model as one line. String values are now
   plain text in tool mode. Its effect on accuracy is untested.

Both fixes are generic, not case-specific. Rerunning these same ten cases
measures the fixes, but the cases are no longer independent of the development
that used them.
