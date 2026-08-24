# Answers: RANSAC iteration-count provenance (Q1–Q3)

Companion to `audit_ransac_iterations.md`. Read-only; every claim below is
traced to a file and line.

> **Path note.** The repo moved derived outputs from `data/` to `results/` on
> 2026-08-24. All paths are post-migration.

> **Filename note.** This report is deliberately NOT called
> `audit_threading_provenance.md`. A concurrent session rewrote
> `src/regen_2class/audit_threading_provenance.py` at 20:42 with a different
> scope (serial/threaded/multiprocess timings and morphology kernel shapes) and
> wrote its own reports into this directory. Nothing of theirs has been
> overwritten. See the collision notice at the end.

---

## Q1. Which machine produced 1162.7 and 295.5, and which n each belongs to

**Machine: the laptop, not the Pi.** Established from the producing script's own
docstring, `src/stereo/ransac_iterations_sweep.py`:

> "Runs on the LAPTOP, not the Pi -- these are relative-shape/tradeoff numbers
> (time vs n_iterations, error vs n_iterations), not the Pi's absolute timing
> (already measured separately, Pi benchmark Stage 1)."

Corroborated by `claude/decision_log.md:1077`, which writes "**laptop timing**"
inline next to these two figures.

| number | n_iterations | source CSV | row | column | stored |
|--:|--:|---|--:|---|--:|
| **1162.7 ms** | **15** | `results/trajectory_fit_comparison/ransac_iterations_sweep/table1_wallclock_by_niterations.csv` | 6 | `median_wall_ms` | 1162.68 |
| **295.5 ms** | **3** | same file | 2 | `median_wall_ms` | 295.46 |

Both recomputed independently from `ransac_sweep_raw.csv` and matched to 0.01 ms.

### While tracing these, a related pair needs correcting

The brief pairs "193.6 mm and 189.8 mm". They are **not** the endpoints people
usually assume:

| number | n_iterations | note |
|--:|--:|---|
| 193.6 mm | **3** | `median_error_mm` = 193.55, row 2 |
| 189.8 mm | **25** | `median_error_mm` = 189.79, row 7 |

189.8 is the **n=25** value, not n=15. The n=15 median is **189.55**. So the
"<4 mm spread" quoted in decision log 70 spans n=3 to n=**25**, i.e. the full
grid, not n=3 to the old production setting of 15. Against n=15 specifically the
spread is 4.00 mm (193.55 → 189.55).

---

## Q2. Reconciling 295.5 ms against the Pi sweep's ransac_ms

Both quoted Pi medians reproduce exactly from
`results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv`:

| class | window | quoted | recomputed | n |
|---|--:|--:|--:|--:|
| SHORT | 490 ms | 140.21 | 140.21 | 47 |
| LONG | 1000 ms | 235.60 | 235.60 | 60 |

### Same quantity? YES

This corrects an earlier claim of mine in this project. `ransac_ms` is set by
`src/pi_benchmarking/prediction_pipeline_sweep_pi.py` lines **378–388**, and that
region contains exactly one call:

```python
t0 = perf_ms()
try:
    res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
                      inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                      n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
except RuntimeError as e:
    ...
ransac_ms = perf_ms() - t0
```

`fit_fn, predict_fn` come from `build_model_fit_predict("C", ...)` at line 346 —
**model C only**. `ransac_fit` (trajectory_fit.py) takes a single `fit_fn` and
runs `n_iterations` sample-fit-score rounds plus "one final `fit_fn` call on that
winning set".

So at n=3 the timer covers **4 least-squares solves of the same model**, which is
exactly what the laptop's `wall_ms` covers — its timed region is a single
`ransac_fit` call, also model C, also n_iterations from the same grid.

**Correction:** I previously described `ransac_ms` as wrapping "all four LSQ
fits", meaning four *different models*. That is wrong. It is one RANSAC call over
one model, internally doing n+1 fits of that model. The wrong wording is baked
into `src/regen_2class/stage_timing_breakdown.py` (docstring and figure caption)
and `results/regenerate_figures/iteration_rows.md` row 2. Flagged here rather
than silently edited, because fixing them regenerates a figure and a report.

### Same window? NO

| | Pi | laptop |
|---|---|---|
| observation window | **swept**, 24 values 150–1250 ms; the quoted figures read at 490 and 1000 | **fixed 430 ms** (`FIT_WINDOW_S = 0.430`, points taken by `searchsorted`) |

### Same population? NO

| | Pi | laptop |
|---|---|---|
| flights | **107** crossing flights (SHORT 47, LONG 60) | **150** flights, filtered only on duration ≥ 430 ms |
| runs behind the median | 47 and 60 | 3,723 (150 flights × 25 seeds, minus failures) |
| seeds | 1 (`random_seed=42`, fixed) | 25 per flight |

### Same machine? NO

Raspberry Pi versus laptop.

### What each actually measures

- **Pi `ransac_ms` at SHORT/490 = 140.21 ms** — median, across 47 crossing
  flights, of one model-C RANSAC fit at n=3, seed 42, on the points falling in
  the first 490 ms, executed on the Pi.
- **Pi `ransac_ms` at LONG/1000 = 235.60 ms** — same, 60 flights, 1000 ms window.
- **Laptop `wall_ms` at n=3 = 295.46 ms** — median across 3,723 runs (150 flights
  × 25 seeds) of one model-C RANSAC fit at n=3 on a fixed 430 ms window, on the
  laptop.

**Verdict: the same quantity, measured on different hardware over different
windows and different flight populations.** The comparison is legitimate only for
the *shape* of cost against iteration count, which is precisely the use the
laptop script's docstring claims for itself. Quoting 295.5 ms as a Pi cost is not
supported — and note the direction is counter-intuitive: the Pi number at a
*longer* window (490 ms) is *lower* (140.21) than the laptop's at 430 ms
(295.46), so a naive read would wrongly suggest the Pi is twice as fast as the
laptop. Population and point-count differences, not hardware, dominate that gap.

---

## Q3. Does decision log 70's after-value appear in a CSV?

**Yes.**

- Decision log entry: `claude/decision_log.md:1060` (entry begins), value on the
  line reading `N=3 -> 295.5ms vs N=15 -> 1162.7ms median`.
- Parsed after-value: **295.5 ms**
- Found at: `results/trajectory_fit_comparison/ransac_iterations_sweep/table1_wallclock_by_niterations.csv`,
  **row 2** (first data row), column `median_wall_ms`, stored value **295.46**,
  `n_iterations = 3`, `n_runs = 3723`.

The log rounds 295.46 to 295.5. The same value recomputes from the raw grid to
0.01 ms.

---

## Provenance summary for all six numbers

| number | source CSV | producing script | machine | window | population | wall-clock units |
|---|---|---|---|---|---|---|
| 193.6 mm (n=3) | `table2_error_by_niterations.csv` | `src/stereo/ransac_iterations_sweep.py` | laptop | fixed 430 ms | 150 flights, dur ≥ 430 ms | n/a (mm) |
| 189.8 mm (n=25) | same | same | laptop | fixed 430 ms | same | n/a (mm) |
| 1162.7 ms (n=15) | `table1_wallclock_by_niterations.csv` | same | laptop | fixed 430 ms | same | **ms** |
| 295.5 ms (n=3) | same | same | laptop | fixed 430 ms | same | **ms** |
| 22,367 runs | `ransac_sweep_raw.csv` | same | laptop | fixed 430 ms | same | n/a |
| 150 × 6 × 25 | `ransac_sweep_raw.csv` | same | laptop | fixed 430 ms | same | n/a |

**Units of the wall-clock column:** milliseconds, from
`wall_ms = (time.perf_counter() - t0) * 1000.0` — `perf_counter` returns seconds,
scaled by 1000.

**22,367** = rows with `status == 'ok'` in `ransac_sweep_raw.csv`, out of 22,500
total (150 × 6 × 25). The 133 shortfall is failed fits. It equals the sum of
`n_runs` across `table1`. Eight flights were excluded before the grid ran, listed
in `excluded_flights.csv`, all for `duration < 430ms`.

---

## Collision notice

While this audit was running, a **concurrent session** rewrote
`src/regen_2class/audit_threading_provenance.py` (20:42) to a different scope and
wrote `answers_1_to_5.md`, `provenance_threading_morphology.md` and
`audit_threading_provenance_02.log`.

- My attempted edit to that script **failed rather than overwriting it** — the
  correct outcome.
- `audit_threading_provenance.md` in this directory was produced by my earlier
  version of that script, which no longer exists on disk. Its Pi-side content is
  superseded by Q2 above, which corrects the `ransac_ms` reading.
- Nothing belonging to the other session has been modified or deleted.
