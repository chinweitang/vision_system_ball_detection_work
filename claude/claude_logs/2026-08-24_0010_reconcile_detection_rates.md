# Work Log: Reconcile detection rates, final production config

**Session:** 2026-08-24_0010
**Start:** 00:10
**Status:** Complete
**Duration:** ~15 min

---

## Original Request

> Read data/detector_tuning/candidate_config_validated_results.csv and
> data/detector_tuning/results_history.csv. Do not modify either. Write
> src/regen_2class/reconcile_detection_rates.py which reports, for the final
> production config only: (a) avg_combined_rate across all 163 flights, (b) labelled
> recall and the point count it is computed over, (c) which flights the recall is
> computed on, (d) the exact config dict the numbers correspond to. Write results to
> data/regenerate_figures/detection_rates_reconciled.txt and log to
> claude/claude_logs/. STOP if the CSV has fewer than 163 unique session-qualified
> flight rows. STOP if the recall point count is not 240. STOP if any value differs
> from 0.9667 combined or 0.9250 recall by more than 0.001; report the discrepancy
> rather than reconciling it silently. Do not compute anything from a sweep-grid CSV.

---

## Path correction

`data/detector_tuning/results_history.csv` does not exist. The file is at
**`data/detector_tuning/history/results_history.csv`**. Used that; flagged rather
than silently substituted.

Sweep-grid CSVs (`sweep_results.csv`, `sweep_results_min_area_circ.csv`) were NOT
read, per the brief. Inputs opened read-only; neither named CSV was modified.

---

## STOP GATES - all three PASS

| gate | result |
|---|---|
| >= 163 unique session-qualified flight rows | **PASS** - 163 rows, 163 unique, 0 duplicates (37 in 2026_07_15_gym, 126 in 2026_07_21_gym) |
| recall point count == 240 | **PASS** - 240, counted from the label CSVs on disk |
| values within +/-0.001 of 0.9667 / 0.9250 | **PASS** - stored 0.9667 and 0.9250 exactly; recomputed mean 0.966747, difference 4.66e-05 |

The CSV has 166 rows: 163 flight rows plus AVERAGE, LABELED_RECALL and CONFIG.

---

## RESULTS

**(a) avg_combined_rate = 0.9667** across 163 flights. Recomputed independently from
the per-flight rows as 0.966747, so the stored figure is the same number rounded to
4 dp. Definition: per-flight co-detected / co-processable frames, then an
**unweighted mean across flights** - each flight counts equally regardless of frame
count, so this is not a pooled frame-level rate.

**(b) labelled recall = 0.9250 over 240 points.** The 240 is not stored in the
validated CSV; it appears only in the history row's free-text
`"flight_01 + flight_22 (240 points)"`. Verified independently by counting rows in
the per-flight `*_labels.csv` files, which total exactly 240. A point counts as a
hit when the kept detection for that (cam, frame) lies within the label's own
tolerance (`diameter_px / 2`, else a 20 px fallback).

**(c) which flights - resolved, and the CSV label is under-specified.**
`10_run_full_dataset.py` matches each entry of `LABELED_FLIGHT_SUBPATHS`
(`"2 ball contacts ground before plane/flight_01"`, `"flight_22"`) against BOTH
sessions. Three directories match:

| directory | points |
|---|--:|
| `2026_07_15_gym/2 ball contacts ground before plane/flight_01` | 54 (cam0 27, cam1 27) |
| `2026_07_15_gym/flight_22` | 186 (cam0 93, cam1 93) |
| `2026_07_21_gym/flight_22` | **0** - matches the pattern, has no label CSVs |

So the recall runs on **two** flights, **both in 2026_07_15_gym**. The CSV row is
labelled `LABELED_RECALL (flight_01 + flight_22)`, which is NOT session-qualified -
and `flight_22` exists under both sessions, so that label alone does not identify
the population. Resolving it required reading the matching rule in the source, not
just the CSV.

**(d) config dict** parsed from the CONFIG cell:

    stride=1  thresh=16  open_k=3  close_k=30
    min_area=30  max_area=50000  min_circ=0.3
    + exclusion_mask_v4 (12 zones total)
    + trajectory_filter (max_speed=80, min_run=2)

History row: 2026-07-25, "candidate + mask v4 (12 zones total) + trajectory filter +
min_area=30/min_circ=0.30 - FULL 163-FLIGHT DATASET (current)".

---

## DISCREPANCY - reported, not reconciled

**A later full-dataset run exists and disagrees.** 2026-08-03, "rect close kernel
validation (MORPH_ELLIPSE -> MORPH_RECT, close_k=30 only, driven by Pi real-time
finding - decision log 63)", same 163 flights, same 240 recall points:

| | avg_combined_rate | labelled recall |
|---|--:|--:|
| 2026-07-25, ELLIPSE close kernel | **0.9667** | **0.9250** |
| 2026-08-03, RECT close kernel | **0.9452** | **0.8875** |

The two configs differ ONLY in the close-kernel shape. `candidate_config.json`
records `close_kernel: 30` but has no shape field, so the two are indistinguishable
from that file alone - the shape lives in code.

**This is not academic.** Every Pi real-time script - `prediction_pipeline_sweep_pi.py`,
`prediction_pipeline_sweep_pi_vaxis.py`, `two_axis_fit_window_sweep_pi.py`,
`parallel_detect_checkpoint_pi.py`, `benchmark_detection_rect_total_pi.py` - defines
and calls a local `compute_mask_rect_close` using `cv2.MORPH_RECT`. Only
`benchmark_pipeline_pi.py` uses the shared `detector_core.compute_mask`, which is
ELLIPSE. So the sweeps that produced every downstream figure ran the RECT variant,
whose validated detection rates are 0.9452 / 0.8875 - not the 0.9667 / 0.9250 being
reported alongside them.

**Which config is "final production" is not resolvable from these files.** The
2026-07-25 ellipse row is annotated "(current)", but the 2026-08-03 rect row is
later and its own notes call it a "REGRESSION, not a free win" (83 of 163 flights
regressed >2pp, 13 improved). Left for a human decision rather than picked silently.

**Second, smaller issue.** `2026_07_21_gym/flight_22` matches the recall subpath but
has no label CSVs, so it contributes 0 points and passes unnoticed. If labels were
ever added there, the recall population would silently change while the CSV's label
text stayed the same.

---

## Outputs

| file | contents |
|---|---|
| `src/regen_2class/reconcile_detection_rates.py` | the script |
| `data/regenerate_figures/detection_rates_reconciled.txt` | the report above, generated |
| this log | |

Neither input CSV was modified. No sweep-grid CSV was read. Nothing was re-run.
