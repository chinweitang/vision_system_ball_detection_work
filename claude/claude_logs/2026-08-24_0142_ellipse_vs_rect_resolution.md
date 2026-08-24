# Work Log: Ellipse vs rect close kernel - per-flight resolution

**Session:** 2026-08-24_0142
**Status:** Complete

Related: [2026-08-24_0010_reconcile_detection_rates.md](2026-08-24_0010_reconcile_detection_rates.md)
first surfaced this conflict; [2026-08-24_0037_iteration_rows.md](2026-08-24_0037_iteration_rows.md)
carried it as row 1. This task resolves it per-flight and confirms the deployed path.

---

## Original Request

> Read data/detector_tuning/candidate_config_validated_results.csv and
> candidate_config_rect_close_results.csv. Do not modify either. For each of the 163
> session-qualified flights, report the per-flight combined-rate delta rect minus
> ellipse. Output the distribution, the count regressing by more than 2 pp, the count
> improving, and the identity of the boundary flights at exactly +/-2.00 pp. Then
> confirm, by reading the Pi scripts under src/pi_benchmarking/, which mask function
> each calls, and list any script using the shared ellipse detector_core.compute_mask.
> Write to data/regenerate_figures/ellipse_vs_rect_resolution.txt. Log to
> claude/claude_logs/. STOP if the two CSVs do not cover the same 163 flights.

---

## [01:42] Step 1 - starting

Deltas will be computed from the two source CSVs directly, NOT read from the
existing `rect_vs_ellipse_comparison.csv`. That file is used only as a cross-check
at the end - if my independently computed deltas disagree with it, that is worth
knowing rather than hiding.

---

## [01:48] Step 2 - STOP gate PASS

Both CSVs are 167 lines: 1 header + 163 session-qualified flight rows + AVERAGE,
LABELED_RECALL, CONFIG. Flight sets are **identical** - symmetric difference 0, no
duplicates in either. Gate passes.

Stored summaries: ellipse 0.9667 / 0.9250, rect 0.9452 / 0.8875.

---

## [01:52] Step 3 - per-flight deltas

Computed from the two source CSVs directly. `combined_rate` is stored to 4 dp, so
`delta_pp` lands on exact hundredths - the `round(..., 2)` in the script removes
float representation noise only, it is not a tolerance fudge.

### Distribution (rect minus ellipse, percentage points)

| stat | value |
|---|--:|
| n | 163 |
| mean | -2.151 |
| min | -10.23 |
| P5 | -8.32 |
| Q1 | -3.98 |
| median | -2.08 |
| Q3 | +0.00 |
| P95 | +2.41 |
| max | +4.88 |

The shape matters more than the mean: **the distribution is broadly shifted, not
long-tailed.** Q3 is exactly 0.00, so three quarters of all flights are at best
unchanged. 44 flights sit in the [-4, -2) bucket alone - this is a systematic
degradation across the population, not a handful of bad flights dragging a mean.

### Counts

| | |
|---|--:|
| regressing > 2 pp | **83** (50.9%) |
| improving > 2 pp | **12** (7.4%) |
| improving at all | 25 |
| unchanged | 35 |
| worse at all | **103** |

### Boundary flights at exactly +/-2.00 pp

- exactly -2.00 pp: **none**
- exactly +2.00 pp: **1** - `2026_07_21_gym/flight_69`, 0.9600 -> 0.9800

That single flight is the whole discrepancy between "12 improved" (strict >) and
the history row's "13 improved" (>=). Confirmed here from the source CSVs, not
inferred from the derived comparison file.

---

## [01:55] Step 4 - which mask each Pi script calls

Read from source. `detector_core.compute_mask` uses **MORPH_ELLIPSE for both** the
open and close kernels.

| script | calls |
|---|---|
| benchmark_detection_rect_total_pi.py | local rect |
| benchmark_mask_breakdown_pi.py | neither (timing-only mirror, builds both kernels inline) |
| **benchmark_pipeline_pi.py** | **shared `detector_core.compute_mask` (ELLIPSE)** |
| compare_pi_vs_laptop_output.py | neither (diffs saved outputs) |
| parallel_detect_checkpoint_pi.py | local rect |
| prediction_pipeline_sweep_pi.py | local rect |
| prediction_pipeline_sweep_pi_vaxis.py | local rect |
| two_axis_fit_window_sweep_pi.py | local rect |

**Exactly one script uses the shared ellipse detector: `benchmark_pipeline_pi.py`.**
Five call the local rect variant. Definition and call site were checked separately,
and module docstrings were stripped before scanning so prose mentioning
`compute_mask` could not register as a call.

Each local `compute_mask_rect_close` keeps the OPEN kernel as MORPH_ELLIPSE and
changes only the CLOSE kernel - matching the rect CSV's CONFIG cell, which records
`open_k=3(ELLIPSE) close_k=30(RECT, changed from ELLIPSE)`.

### This also explains an earlier confound

`benchmark_pipeline_pi.py` is the Stage 1 script, and it is the ELLIPSE one. That
is why the serial detection figure in `timing_history.csv` (88.66-89.80 ms/frame/cam)
cannot be differenced against the threaded sweep figure to isolate threading - the
two numbers come from scripts running different kernels. Flagged as NOT_FOUND in
`iteration_rows.md` row 3; now confirmed as a genuine confound rather than a gap.

---

## [01:57] Step 5 - cross-check and completion

The independently computed deltas were checked against the pre-existing
`rect_vs_ellipse_comparison.csv`, which was NOT used as an input:

- 163 rows, 0 flights missing
- **0 delta disagreements** above 0.005 pp
- `flagged_regression == YES` count 83, matching the 83 computed as regressing >2 pp

Two independent derivations agree exactly, so both are trustworthy.

### Outputs

| file | |
|---|---|
| `src/regen_2class/ellipse_vs_rect_resolution.py` | the analysis |
| `data/regenerate_figures/ellipse_vs_rect_resolution.txt` | the report |
| this log | |

Input mtimes unchanged: validated 2026-07-24 11:23, rect 2026-08-03 15:44. Neither
modified. Nothing re-run.

### The resolution

The conflict first raised on 2026-08-24_0010 now has an answer on the evidence:

- RECT is **systematically worse**, not situationally worse. 103 of 163 flights
  degrade, Q3 is 0.00, and the regression is spread across the population.
- The **deployed** Pi path is RECT in 5 of 8 scripts, including every sweep that
  produced downstream figures.
- Therefore the detection rates that belong alongside the Pi results are
  **0.9452 / 0.8875**, not the 0.9667 / 0.9250 usually quoted.

What is NOT resolved, and remains a human decision: whether to keep RECT (and quote
the lower rates) or revisit it, given that the 17.6x mask speedup is what brought
detection inside the 16.667 ms cadence in the first place. The speed was not
optional; the accuracy cost is real. That trade-off is the open question.
