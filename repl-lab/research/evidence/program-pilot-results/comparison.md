| Metric (pooled, 2 runs) | A direct tools | A per run | B program_run | B per run |
| --- | --- | --- | --- | --- |
| Success | 0.81 | 0.78 / 0.83 | 0.92 | 0.94 / 0.89 |
| Effects correct | 0.94 | 0.94 / 0.94 | 1.00 | 1.00 / 1.00 |
| Failures (tasks) | 2 | 1 / 1 | 0 | 0 / 0 |
| Unintended changes | 0 | 0 / 0 | 0 | 0 / 0 |
| Model requests / task | 11.11 | 11.11 / 11.11 | 2.69 | 2.56 / 2.83 |
| Input tokens / task | 24.22 | 24.22 / 24.22 | 7.39 | 7.11 / 7.67 |
| Cache-read tokens / task | 67840.97 | 67866.22 / 67815.72 | 6838.75 | 6365.67 / 7311.83 |
| Output tokens / task | 1295.89 | 1299.50 / 1292.28 | 310.33 | 297.44 / 323.22 |
| Cost USD / task | 0.03 | 0.03 / 0.03 | 0.01 | 0.01 / 0.01 |
| Cost USD total | 1.02 | 0.51 / 0.51 | 0.27 | 0.13 / 0.14 |
| Latency p50 ms | 38318.40 | 45602.17 / 24189.71 | 24952.61 | 37329.91 / 19271.89 |
| Latency p95 ms | 146956.73 | 171071.70 / 113205.85 | 70013.46 | 74850.56 / 26862.58 |
| Tool operations / task | 10.06 | 10.06 / 10.06 | 12.67 | 12.33 / 13.00 |
| Failed operations / task | 0.22 | 0.22 / 0.22 | 0.31 | 0.28 / 0.33 |
| Deduplicated operations / task | 0.00 | 0.00 / 0.00 | 0.00 | 0.00 / 0.00 |
| Programs / task | 0.00 | 0.00 / 0.00 | 1.42 | 1.33 / 1.50 |
| Programs failed | 0 | 0 / 0 | 4 | 1 / 3 |
| Controller op ms / task | 74.59 | 109.44 / 39.75 | 82.69 | 132.39 / 33.00 |

| Family | A success | B success | A effects | B effects | A requests | B requests | A cost | B cost | B−A success (min..max) | B−A requests (min..max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| read | 1.00 | 1.00 | 1.00 | 1.00 | 2.0 | 2.0 | 0.0069 | 0.0069 | 0.00 (0.00..0.00) | 0.0 (0..0) |
| seq | 1.00 | 1.00 | 1.00 | 1.00 | 7.0 | 2.0 | 0.0108 | 0.0053 | 0.00 (0.00..0.00) | -5.0 (-5..-5) |
| cond | 0.75 | 1.00 | 1.00 | 1.00 | 22.5 | 6.2 | 0.0519 | 0.0146 | 0.25 (0.00..1.00) | -16.2 (-25..-8) |
| bulk | 0.00 | 0.50 | 1.00 | 1.00 | 15.0 | 3.0 | 0.0370 | 0.0082 | 0.50 (0.00..1.00) | -12.0 (-18..-6) |
| verify | 0.50 | 1.00 | 0.50 | 1.00 | 35.0 | 3.8 | 0.1030 | 0.0109 | 0.50 (0.00..1.00) | -31.2 (-37..-27) |
| fault | 1.00 | 0.75 | 1.00 | 1.00 | 14.5 | 3.2 | 0.0345 | 0.0096 | -0.25 (-1.00..0.00) | -11.2 (-17..-6) |
| rate | 1.00 | 1.00 | 1.00 | 1.00 | 2.0 | 2.0 | 0.0048 | 0.0053 | 0.00 (0.00..0.00) | 0.0 (0..0) |
| auth | 1.00 | 1.00 | 1.00 | 1.00 | 1.0 | 1.0 | 0.0034 | 0.0035 | 0.00 (0.00..0.00) | 0.0 (0..0) |
| direct | 1.00 | 1.00 | 1.00 | 1.00 | 1.0 | 1.0 | 0.0032 | 0.0031 | 0.00 (0.00..0.00) | 0.0 (0..0) |

**Verdict: NO-GO**
- success_within_tolerance: pass
- effects_within_tolerance: pass
- requests_halved_on_op_heavy: pass
- cost_per_task_ratio_ok: pass
- no_family_loses_more_than_tolerance: FAIL
- no_more_unintended_changes: pass
- reduction_not_only_direct_auth: pass
- requests on op-heavy families, B/A: 0.22; cost per task, B/A: 0.26
- non-completed tasks: A program-A-r1 service-sim-1-verify-1-240 (error); A program-A-r2 service-sim-1-verify-1-240 (error)
