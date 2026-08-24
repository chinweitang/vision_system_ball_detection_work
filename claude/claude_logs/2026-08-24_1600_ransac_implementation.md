# Work Log: RANSAC implementation readout

**Session:** 2026-08-24_1600
**Status:** In progress

Both inputs opened read-only. Nothing re-run.

---

## Original Request

> Read src/stereo/trajectory_fit.py read-only. Report, quoting the relevant
> lines: (a) whether ransac_fit performs a final refit on the full inlier set
> after selecting the consensus set, or returns a model fitted on the minimal
> subsample; (b) the point set over which any returned residual is computed,
> inliers only or all points; (c) the minimum inlier count and the inlier
> distance threshold, with the line each is defined on. Then read
> results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv
> read-only and report whether it contains a plain, non-RANSAC variant for any
> model across the full population, naming the column that distinguishes them if
> so. Also report the fraction of flights with rejected_frac > 0 at a
> representative window. STOP and say so if the plain variant exists only for a
> subset of flights, naming the subset. Write to
> results/regenerate_figures/ransac_implementation.txt. Log incrementally.

---

## [16:00] Step 1 - trajectory_fit.py, 309 lines

### (a) Final refit: YES, on the full winning inlier set

`ransac_fit` line 218 refits over `best_mask`, not the minimal draw:

```
218    final_params = fit_fn(t[best_mask], xyz[best_mask])
```

The sampling loop (200-212) only ever records the mask, never the params - the
subsample fit at line 203 is discarded each iteration:

```
203            params = fit_fn(t[idx], xyz[idx])
204            pred_all = predict_fn(params, t)
...
210        if count > best_count:
211            best_count = count
212            best_mask = mask
```

Docstring lines 189-190 state the same: "keeps the largest inlier set seen, then
does one final fit_fn call on that winning set".

### (b) Residual: INLIERS ONLY

Lines 219-221 slice both the prediction and the data by `best_mask`:

```
219    pred_final = predict_fn(final_params, t[best_mask])
220    resid_final = np.linalg.norm(pred_final - xyz[best_mask], axis=1)
221    rms = float(np.sqrt(np.mean(resid_final ** 2)))
```

So the returned `residual_rms_mm` (line 232) is computed over the accepted set
and **excludes every rejected point**. Consequence worth stating in the report:
this RMS is not comparable like-for-like with a plain least-squares RMS over all
points - the rejected points are exactly the large-residual ones, so the RANSAC
figure is biased low by construction. It measures fit quality on the consensus
set, not on the flight.

### (c) Minimum inlier count and inlier threshold

**Minimum inlier count** - there is no separate parameter; the acceptance gate
reuses `min_samples`, line 214:

```
214    if best_mask is None or best_count < min_samples:
```

`min_samples` is supplied per model from line 245:

```
245 RANSAC_MIN_SAMPLES = {"A": 6, "B": 6, "C": 8}
```

A second, earlier use of the same constant guards the input size at line 195:

```
195    if n < min_samples:
196        raise RuntimeError(f"ransac_fit: only {n} points, need >= min_samples={min_samples}")
```

**Inlier distance threshold** - line 241:

```
241 RANSAC_INLIER_THRESHOLD_MM = 75.0
```

applied as a Euclidean 3-D distance at lines 207-208:

```
207        resid = np.linalg.norm(pred_all - xyz, axis=1)
208        mask = resid <= inlier_threshold_mm
```

One value for all three models and both phases (the comment at 241-244 records
that a per-phase alternative was investigated and rejected).

## [16:12] Step 2 - the sweep CSV: no plain/RANSAC variant column

`results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv`,
29,769 data rows, 158 flights across both sessions. Header:

```
session,flight,N,model,lead_time_ms,error_mm,rejected_frac
```

**There is no column distinguishing a plain fit from a RANSAC fit.** `model`
takes exactly three values - A (9,923), B (9,923), C (9,923) - with no `_plain`
/ `_ransac` suffix and no separate variant/method field. There is one row per
(session, flight, N, model), so no plain and RANSAC row ever coexist at the same
window for the same model.

### Blank rejected_frac splits into TWO different things - checked, not assumed

2,469 rows have a blank `rejected_frac`. They are not one category:

| category | rows | `error_mm` | meaning |
|---|--:|---|---|
| N < model's min_samples | 1,738 | **populated** | plain fit, RANSAC skipped |
| N >= min_samples | 731 | **blank** | RANSAC raised, nothing recorded |

Verified against the generating script
`src/stereo/trajectory_model_prediction_sweep_all_flights.py` rather than
inferred from the data alone. Its `fit_and_predict_ransac` docstring says it
"falls back to the plain fit when the window is smaller than RANSAC's
min_samples", and the code returns `None` for the rejected list on that path:

```
    if len(t_win) < min_samples:
        if model == "A":
            p0, v0, a = fit_constant_accel(t_win, xyz_win)
            return predict_at(p0, v0, a, t_target), None
        params = fit_fn(t_win, xyz_win)
        return predict_fn(params, np.array([t_target]))[0], None
```

while the caller turns a `RuntimeError` into a NaN error AND a `None` fraction,
which is why the second category has both fields blank:

```
            except RuntimeError as e:
                err = np.nan
                rejected_frac = None
```

`rejected_frac = (len(rejected) / N) if rejected is not None else None`, so a
blank fraction with a populated error is the plain-fit signature.

### The STOP condition, evaluated literally

The plain fits appear for **all 158 of 158 flights** (and for all three models
individually) - so the plain variant is NOT restricted to a subset of flights,
and the STOP as worded does not fire.

**But the restriction is real and needs stating**: the plain variant exists only
at windows below the model's `min_samples` - N < 6 for A and B, N < 8 for C.
Above that, every fit in this file is a RANSAC fit. So the file supports no
plain-vs-RANSAC comparison at matched N for any model, at any window a report
would actually quote. Reporting that prominently rather than answering a bare
"no".

## [16:20] Step 3 - rejected_frac > 0 at a representative window

Representative window taken as **N = 30**, the window this project already uses
as its representative elsewhere (`src/regen_2class/step14_flight_binning_n30_replot.py`,
the N30 distribution figures). Denominator caveat: 146 of the 158 flights have a
row at N=30 at all - the other 12 are shorter than 30 points.

| model | flights with a RANSAC row at N=30 | of those, rejected_frac > 0 | share |
|---|--:|--:|--:|
| A | 146 | 146 | **100.0%** |
| B | 146 | 146 | **100.0%** |
| C | 146 | 145 | **99.3%** |

Checked adjacent windows so N=30 is not a cherry-pick:

| N | A | B | C | flights with a row |
|--:|--:|--:|--:|--:|
| 10 | 71.4% | 70.1% | 60.2% | 154 / 147 / 108 |
| 20 | 91.0% | 94.2% | 93.5% | 155 / 155 / 154 |
| 30 | 100.0% | 100.0% | 99.3% | 146 |
| 40 | 100.0% | 100.0% | 100.0% | 127 |
| 50 | 100.0% | 100.0% | 100.0% | 108 |

The share rises monotonically with window size and saturates at 100% by N=40:
at any window a report would quote, essentially every flight has at least one
point rejected. Combined with finding (b), that matters - the reported residual
excludes those points on effectively every flight, not on a rare subset.

## [16:34] Step 4 - report written

`src/regen_2class/ransac_implementation.py` ->
`results/regenerate_figures/ransac_implementation.txt` (new file, nothing
overwritten).

Design point: the quoted source lines are **re-read from trajectory_fit.py at run
time** and each checked against an expected fragment, rather than transcribed
into string literals. If that file is edited so a quoted line number no longer
carries the code described, the script STOPs instead of printing a stale quote.
11 lines guarded; all pass.

Second guard: the script asserts that every "blank rejected_frac + populated
error_mm" row really does sit below its model's `min_samples`. If any such row
appeared at a larger N, the plain-fallback explanation would not account for it
and the script STOPs rather than mislabelling it. None found.

### Sources untouched

Confirmed by mtime after the run:
- `src/stereo/trajectory_fit.py` - 2026-07-27 (unchanged)
- `prediction_sweep_all_flights.csv` - 2026-07-28 13:10 (unchanged)

## Deliverable

`results/regenerate_figures/ransac_implementation.txt`

**Status: Complete.**
