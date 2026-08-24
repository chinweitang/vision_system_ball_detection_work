# Work Log: Plain (non-RANSAC) drag-model sweep

**Session:** 2026-08-24_1700
**Status:** In progress - pilot stage

Re-run of existing Phase 2 analysis with the robustifier disabled. No new data
collection. Related: [2026-08-24_1600_ransac_implementation.md](2026-08-24_1600_ransac_implementation.md),
which established that the existing sweep CSV has no plain variant above each
model's `min_samples` - this fills that gap for Model C.

---

## Original Request

> This is a re-run of existing analysis with the robustifier disabled, not new
> data collection. Read src/stereo/trajectory_model_prediction_sweep_all_flights.py
> and src/stereo/trajectory_fit.py read-only. Write src/regen_2class/plain_drag_sweep.py
> which reproduces the phase 2 sweep for the fixed-gravity-with-drag model ONLY,
> over the same 158 flights and the same window grid, calling the plain fit
> directly instead of ransac_fit. Use the same pooled K, the same held-out target
> and the same frame-exclusion-for-leakage logic as the original; import them
> rather than reimplementing. PILOT on 3 flights first, report per-flight runtime
> and the projected total, and STOP for my approval before running the full
> population. Emit one row per (session, flight, N) with error_mm, and a status
> column distinguishing success from fit failure. STOP if the flight population is
> not 158. STOP if the window grid does not match the RANSAC sweep's grid exactly;
> report the difference rather than aligning them silently. Output to
> results/regenerate_figures/plain_drag_sweep/. Do not modify or overwrite
> prediction_sweep_all_flights.csv. Log incrementally.

---

## [17:00] Step 1 - what can be imported, and the one thing that cannot

"Fixed-gravity-with-drag" is **Model C** (`trajectory_fit.py` lines 18-20:
`dv/dt = g - k*|v|*v`, g fixed, k fixed at the pooled Phase 1 value).

Imported, not reimplemented:

| thing | from |
|---|---|
| `load_pooled_k` | `trajectory_model_prediction_sweep_all_flights` |
| `target_time_sec` (held-out target time) | same |
| `build_model_fit_predict` | `trajectory_fit` |
| `enumerate_eligible_flights`, `load_session_calib`, `g_fixed_for`, `build_corrected_track`, `load_final_point_targets` | `all_flights_common` |
| `triangulate` | `label_vs_detection` |

Importing the sweep module is safe: its `main()` is behind
`if __name__ == "__main__":` (line 378-379), so nothing runs and
`prediction_sweep_all_flights.csv` is never touched on import.

### The exception: leakage exclusion is not importable

The frame-exclusion-for-leakage step is **inline inside
`process_flight_phase2`** (lines 129-136), not a callable:

```
129    # exclude any fit pair that coincides with the target's own frames (avoid leakage)
130    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
131    if len(keep_idx) < 3:
132        return dict(session=session, flight=flight_id, status="skipped",
133                    reason=f"only {len(keep_idx)} fit points after excluding target frame")
134    frames = [frames[i] for i in keep_idx]
135    t = t[np.array(keep_idx)]
136    xyz = xyz[np.array(keep_idx)]
```

Importing `process_flight_phase2` itself is not an option - it runs all three
models through RANSAC, which is the exact thing being disabled here. Factoring
the block out into a shared helper would mean editing
`trajectory_model_prediction_sweep_all_flights.py`, which the brief says to read
**read-only** (and Section 2 requires permission for edits to existing `src/`
files anyway).

So this one block is copied verbatim, and the copy is protected by a
**source-text guard**: at run time the script re-reads lines 129-136 of the
original and STOPs if they no longer match the copy. Same technique as
`ransac_implementation.py`. Flagging it here rather than letting a silent
duplicate drift.

## [17:14] Step 2 - script written, pilot run, STOPPED for approval

`src/regen_2class/plain_drag_sweep.py`. Default invocation runs the pilot and
exits; the full run needs `--full --i-approve-the-projection`.

### Guards that passed before any fitting

```
leakage-block guard PASS: trajectory_model_prediction_sweep_all_flights.py lines 129-136 unchanged
pooled K (same value as the RANSAC sweep): 5.268474e-05 1/mm
163 eligible flights enumerated; RANSAC sweep covers 158 flights / 9923 windows
```

Note the 163 vs 158: `enumerate_eligible_flights()` returns 163, and 5 fall out
on the original's own skip rules (missing final-point label, no corrected track,
target before track start, too few points after leakage exclusion). The 158 is
what remains. The population STOP therefore checks the count **and** that the
surviving set is the identical set of (session, flight) pairs as the RANSAC
sweep - a bare count check would pass even if a different 158 came through.

### Pilot: 3 flights, spread across the ordering

Picked by spreading across the flight ordering rather than taking the first
three, because runtime scales with each flight's window count, and the first
flights are not representative of that.

| flight | windows | runtime | ms/window | fit_failed |
|---|--:|--:|--:|--:|
| 2026_07_21_gym/flight_1 | 84 | 3.8 s | 45 | 0 |
| 2026_07_21_gym/flight_82 | 32 | 0.8 s | 25 | 0 |
| 2026_07_15_gym/flight_60 | 37 | 1.1 s | 30 | 0 |

Mean 2.0 s/flight, 34 ms/window. **Zero fit failures in 153 windows.**

### Projection

| basis | serial total |
|---|--:|
| by flight count (2.0 s x 158) | 320 s (5.3 min) |
| **by window count (34 ms x 9,923)** | **341 s (5.7 min)** |
| parallel, 14 workers | ~24 s (~0.4 min) |

The window-count projection is the one to trust: window counts per flight range
at least 32-84 in the pilot alone, so scaling by flight count assumes an average
flight that may not exist. The 9,923 total comes from the RANSAC CSV's own Model
C row count, so it is the exact number of windows this run will fit, not an
estimate.

For scale: the RANSAC sweep runs 15 nonlinear fits per window plus a final refit
for Model C. Dropping to one fit per window is the expected ~16x saving, which
is consistent with these timings.

**STOPPED for approval before the full run, as instructed.**

## [17:15] Queued follow-up (user, mid-task)

> Join results/regenerate_figures/plain_drag_sweep/ output to the drag-model rows
> of prediction_sweep_all_flights.csv on (session, flight, N), both read-only.
> Write src/regen_2class/ransac_effect_pooled.py producing a single-panel figure
> with two series, "without RANSAC" and "with RANSAC" ... it has dependencies with
> the previous prompt

Depends on the full run existing. Not started; will follow once the full sweep is
approved and complete.

## [17:30] Step 3 - FULL RUN (approved), serial

Three changes made before running, per instruction:

1. **Serial is now the default** for `--full`; the worker pool is opt-in behind
   `--parallel`. Rationale recorded in the module docstring.
2. **`report_fallout()` added**, printing every dropped flight and its rule on
   EVERY run, pass or fail - previously the list only appeared when a gate
   tripped.
3. **Leakage guard moved into the per-flight path** (`sweep_flight`), so it is
   re-asserted 163 times over the run rather than once at startup. One ~13 KB
   file read per flight; negligible against a nonlinear fit per window.

### The 5 flights that fall out of 163

```
FALLOUT: 163 enumerated - 5 dropped = 158 producing rows
    2026_07_15_gym/flight_13  [skipped]  missing final-point label (one or both cams)
    2026_07_21_gym/flight_50  [skipped]  missing final-point label (one or both cams)
    2026_07_21_gym/flight_74  [skipped]  missing final-point label (one or both cams)
    2026_07_21_gym/flight_80  [skipped]  missing final-point label (one or both cams)
    2026_07_21_gym/flight_88  [skipped]  missing final-point label (one or both cams)
```

All five fall to the SAME rule - no final-point label on one or both cameras.
None of the other three skip rules (no corrected track, target frame absent from
timestamps.csv, target before track start, too few points after leakage
exclusion) fired on any flight. So Figure D's 158 and this run's 158 are the same
population for the same reason, which is what the cross-figure consistency check
needed.

### Gates

```
POPULATION PASS: 158 flights, identical set to the RANSAC sweep
GRID PASS: per-flight window grid matches on all 158 flights
```

Population gate checks set identity, not just the count. Grid gate compares
per-flight N sets: 9,923 rows, exactly matching the RANSAC sweep's Model C row
count.

### Result

158 flights, **9,923 rows, 9,923 ok, 0 fit_failed**. Runtime **478 s (8.0 min)**
serial - the pilot projected 341 s, so the projection was ~40% optimistic (the
3-flight pilot happened to draw flights cheaper per window than the population
average). Not a problem at this scale, but the projection method is worth
distrusting by ~1.5x next time.

### Defect found and fixed

The summary's timing line hardcoded the word "parallel". It ran serial, so the
emitted file said something false about how it was produced. Fixed the f-string
to interpolate the actual mode, and corrected the one word in the already-written
summary file. No numbers were affected.

## [17:41] Step 4 - join and pooled figure

`src/regen_2class/ransac_effect_pooled.py`.

### Key-set gate

```
KEY GATE PASS: both series carry the identical 9923 (session, flight, N) keys
```

### x axis: recomputed, not approximated

Neither CSV carries an observation window in ms - they carry N and
`lead_time_ms` (lead time TO the target, a different quantity). Rather than
approximating from a nominal frame rate, the window duration is recomputed
exactly as `(t[N-1] - t[0]) * 1000` from each flight's own corrected track via
`prepare_flight`. That call does calibration + track building only, no fitting -
about 1 s for all 158 flights, so exactness costs nothing here.

### RANSAC has 331 windows with no value; the plain fit has 0

The plain fit converged on every one of 9,923 windows. RANSAC failed to record an
error on 331. Those keys exist (so the key gate passes) but cannot enter a paired
comparison; excluded from paired stats only, counted per bin as
`n_ransac_missing`.

### Correction caught before reporting: ties are not losses

First run reported `frac_ransac_better = 0.000` at 0-100 ms, which reads as
RANSAC losing every cell. Checked the actual values rather than reporting it:
**all 778 of those cells are numerically IDENTICAL**, and all 778 have N < 8 -
below Model C's `min_samples`, where the original never runs RANSAC at all and
falls back to the plain fit. Identical by construction, not a loss.

A second, distinct tie mechanism appears at larger windows: at 100-200 ms, 253 of
640 cells are identical but only 11 have N < 8. The other 242 ran RANSAC, it
rejected nothing, and its refit on the full set therefore IS the plain fit.

Added `frac_cells_ransac_worse`, `frac_cells_identical`, `n_cells_identical` and
`n_cells_below_min_samples` to the companion CSV, and changed the "worse" test to
compare wins against LOSSES rather than against not-wins.

| window | better | worse | tied | identical (of which N<8) |
|---|--:|--:|--:|---|
| 0-100 | 0.000 | 0.000 | 1.000 | 778/778 (778) |
| 100-200 | 0.245 | 0.359 | 0.395 | 253/640 (11) |
| 200-300 | 0.379 | 0.474 | 0.147 | 132/899 (1) |
| 300-400 | 0.434 | 0.518 | 0.048 | 43/898 (0) |
| 400-500 | 0.468 | 0.516 | 0.016 | 14/855 (0) |

### RANSAC is WORSE at two windows - reported, not smoothed

```
200-300 ms  without=268.6 mm  with=269.1 mm  (+0.4 mm)
300-400 ms  without=209.5 mm  with=211.2 mm  (+1.7 mm)
```

Both plotted as-is. By paired cell count RANSAC also loses more cells than it
wins at four windows (100-500 ms). Flagged to the user.

### Plotted range

0-1500 ms, 15 bins of 100 ms, every bin >= 100 cells in both series. One bin
excluded: 1500-1600 ms at 21 cells. Reported in the summary and on stdout, not
silently trimmed. The passing bins are contiguous, so no gap-spanning line.

### Sources untouched

`prediction_sweep_all_flights.csv` mtime still 2026-07-28 13:10.

**Status: Complete.**
