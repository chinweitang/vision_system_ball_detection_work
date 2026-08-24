# Work Log: Per-stage Pi timing breakdown by observation window and class

**Session:** 2026-08-24_0022
**Status:** Complete
**Duration:** ~25 min

---

## Original Request

> Read data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv.
> Do not modify it. Write src/regen_2class/stage_timing_breakdown.py producing, per
> observation window and per class (SHORT/LONG, 45 degree elevation cut, class from
> the full flight record), the median and p95 of last_pair_detect_ms,
> triangulate_ms, ransac_ms, predict_ms, and the fixed 16.667 ms frame lag. Output a
> CSV and a stacked figure to data/regenerate_figures/stage_timing/. Log to
> claude/claude_logs/. STOP if the per-row stage times plus 16.667 do not reconcile
> to latency_ms within 0.5 ms. STOP if the class populations are not SHORT=47 and
> LONG=60. Do not compare ransac_ms here against any ransac_fit_ms from stage 1;
> those used 15 iterations, not the production 3.

---

## STOP GATES - both PASS

**Gate 1, per-row reconciliation.** Checked on all 2481 `status=='ok'` rows
individually, not on an aggregate:

    max residual 0.000333 ms      min residual 0.000333 ms      tolerance 0.5 ms

The residual is identical on every row because it is not noise - it is exactly
`1000/60 - 16.667 = 0.000333`. The harness adds `ONE_FRAME_LAG_MS = CADENCE_MS =
1000/60`; the brief specifies the constant to 3 dp. So the identity
`stage sum + frame lag = latency_ms` holds exactly in the harness, and the whole
discrepancy is the rounding in the stated constant.

**Gate 2, class populations.** SHORT=47, LONG=60. Exact.

Cross-check (advisory, not a gate): the bin-derived class was compared against
`two_class_join.csv` on all 107 flights - **0 class disagreements, 0 flights on the
wrong side of the 45 degree elevation cut**. So the 45-degree framing in the brief
and the FLAT/MID/LOB bins in the raw CSV are the same partition here.

---

## Input shape

| | |
|---|--:|
| rows | 2568 |
| `status=='ok'` | 2481 |
| `status=='fit_failed'` | 87 |
| flights (session-qualified) | 107 |
| observation windows | 24 (150-1250 ms) |

All 87 fit_failed rows carry **blank** `latency_ms` and blank stage columns, so
they are separated out rather than coerced to zero. Every flight's `bin` is
single-valued across all 24 of its window rows, which is what makes "class from the
full flight record" well defined; the script asserts this rather than assuming it.

Keyed on `(session, flight)`, not bare flight id - 32 flight ids exist in both
sessions and a bare-id key silently merges two different flights.

---

## Findings

**ransac_ms dominates, and its name is wrong.** It is **61-83% of median latency**
across every cell. It wraps ALL the least-squares fitting, not just the RANSAC call.
`predict_ms` contains no fitting at all - only `find_own_crossing` + `eval_pos_vel`.
Both names are reproduced verbatim in the CSV so it joins back to the raw sweep, and
the mismatch is called out in the figure caption instead.

**triangulate_ms is negligible** - at worst **0.073%** of median latency (about
0.12-0.21 ms). It is in the stack for completeness but is not visible at this scale;
the caption says so rather than leaving a reader to wonder about the missing band.

**Median composition at the two min-anchored deadlines:**

| | frame lag | detect | triangulate | ransac | predict | latency median | latency p95 |
|---|--:|--:|--:|--:|--:|--:|--:|
| SHORT @ 490 ms | 16.67 | 13.57 | 0.12 | 140.21 | 12.53 | 183.31 | 204.85 |
| LONG @ 1000 ms | 16.67 | 14.16 | 0.18 | 235.60 | 22.35 | 288.82 | 333.41 |

(LONG's deadline is 1040 ms; 1000 is the nearest window on the grid, and the script
labels it as such rather than pretending 1040 was sampled.)

**Detection is nearly flat in the observation window** (~13.5 ms SHORT, ~14.2 ms
LONG) because it times only the newest stereo pair, not the whole track. The growth
in the stack with window length is essentially all `ransac_ms`.

---

## Correction made during the work

The first caption draft asserted that in the MEDIAN panels the stack and the
measured latency line coincide, reasoning from the exact per-row identity. **That
was wrong** - a median is no more additive than a p95. Measured before re-asserting:

- **median**: `|stack - measured|` up to **3.45 ms (1.33%)**, and it takes **both
  signs** - 27 of 48 cells low, 21 high.
- **p95**: stack runs high in **43 of 48** cells by up to **9.54 ms (5.09%)**, but it
  is **not** a strict upper bound either - **5 cells sit below** the measured p95, by
  at most 1.11 ms.

Every number quoted in the caption is now computed by `caption_facts()` and
interpolated, so the caption cannot drift from the data on a re-run. The measured
dashed line is drawn on all four panels and the caption tells the reader to take the
budget from that line, not from the stack top.

---

## Population caveat carried into the output

`n_ok` varies by cell (range **25-60**); **17 of 48 cells rest on a partial
population**, because a short observation window can fail to fit on flights that fit
fine at a long one. LONG @ 150 ms is the thinnest at n=25 of 60. Per-cell `n_ok` and
`n_fit_failed` are columns in the CSV so a thin cell is visible rather than implied
by the panel's n=47/n=60 title.

---

## Explicitly not done

- **No comparison against stage 1's `ransac_fit_ms`.** That benchmark ran 15 RANSAC
  iterations against this sweep's production 3, so they are different quantities. No
  stage-1 file was opened at all.
- Nothing re-run: no detection, no fitting, no Pi job. The input CSV was opened
  read-only; its mtime is still 2026-08-04 19:53.
- No existing figure or CSV overwritten - `stage_timing/` is a new subfolder.

---

## Figure iterations

Three render passes were needed, each fixing a clip found by looking at the PNG:

1. Caption lines overlapped - the line gap (0.0092 fig fraction) was below the line
   height at FS_CAP on a 6.5 in canvas. Gap raised to 0.0142, height to 7.4 in.
2. Over-corrected the line lengths: lines 2, 3, 9 and 11 then ran off the right
   edge. All caption lines capped at ~150 characters.
3. Legend entry `predict_ms (crossing solve, no fitting)` lost its closing bracket
   at the canvas edge. Shortened to `predict_ms (crossing solve)`.

**Palette not machine-validated.** The dataviz bundle's `validate_palette.js` is
absent from this environment (`~/.claude/skills/` does not exist), so the five stage
colours were NOT checked for CVD separation. They are a contiguous run of the
documented categorical order already used elsewhere in this figure set, chosen so
they do not collide with `CLASS_COLOR` or `BAND_COLOR`. Flagged in the script header
too. Re-validate before this goes to print.

Built 1:1 at 6.6 in (0.8 x A4 width), 300 dpi, matching the print convention used by
`step17_print_size_figures.py`, so font points are real page points.

---

## Outputs

| file | contents |
|---|---|
| `src/regen_2class/stage_timing_breakdown.py` | the script |
| `data/regenerate_figures/stage_timing/stage_timing_by_class_window.csv` | 48 rows (2 classes x 24 windows), 20 columns |
| `data/regenerate_figures/stage_timing/figure_stage_timing_breakdown.png` | 2x2 stacked bars: cols SHORT/LONG, rows median/p95 |
| this log | |

CSV columns: `cls2, T_ms, n_ok, n_fit_failed`, then for each of `median` and `p95`:
the five components, `stage_sum`, `latency_ms`, and `sum_minus_latency` (the
non-additivity gap, so it is auditable rather than only asserted in the caption).
