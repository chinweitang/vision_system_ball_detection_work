# `ransac_ms` mis-description — every occurrence, with proposed replacements

Read-only audit. **Nothing was edited.** This report locates the incorrect
description of the `ransac_ms` column, quotes each occurrence with file and line,
and proposes exact replacement text for each. Applying them is a separate act.

Generated 2026-08-24.

---

## 1. What the code actually does (verified, not assumed)

`ransac_ms` is set in `src/pi_benchmarking/prediction_pipeline_sweep_pi.py`:

```
346:    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)
...
379:        t0 = perf_ms()
380:        try:
381:            res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
382:                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
383:                              n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
384:        except RuntimeError as e:
...
388:        ransac_ms = perf_ms() - t0
```

Three facts follow directly:

- **One model, not four.** Line 346 builds the fit/predict pair for `"C"` and
  only `"C"`. No other model letter is constructed anywhere in the timed path.
- **One call inside the timer.** The region between `t0` (line 379) and
  `ransac_ms` (line 388) contains exactly one `ransac_fit(...)` call plus the
  `try`/`except` wrapper. Nothing else.
- **n+1 internal solves of that one model.** `ransac_fit`
  (`src/stereo/trajectory_fit.py`) runs `for _ in range(n_iterations)` with
  `params = fit_fn(...)` at line 203, then one final refit at line 218
  (`final_params = fit_fn(t[best_mask], xyz[best_mask])`). With
  `N_ITERATIONS = 3` (`prediction_pipeline_sweep_pi.py:95`) that is 3 + 1 = **4
  least-squares solves of model C**.

**This is very likely the origin of the error.** There genuinely are four LSQ
solves — but they are four solves of *one* model inside one RANSAC call, not one
solve each of four different models. The count is right; the interpretation is
wrong.

---

## 2. Occurrences of the wrong wording

Seven sites, in two families. Sites 6 and 7 are **generated** from sites 1 and 2;
sites 8 and 9 are generated from site 5. Fixing the four source sites (1–5) and
regenerating fixes all of them.

### Family A — "all four LSQ fits" (names a model count)

#### 1. `src/regen_2class/build_iteration_rows.py:186`

Current:

```
            elsewhere="the production sweep at n_iterations=3 exists only as "
                      "pipeline_sweep_raw.csv's ransac_ms, which is a DIFFERENT "
                      "quantity - it wraps all four LSQ fits, not the Model-C RANSAC "
                      "fit alone, and covers 107 flights rather than stage 1's 8"),
```

Proposed replacement (lines 184–187):

```
            elsewhere="the production sweep at n_iterations=3 exists only as "
                      "pipeline_sweep_raw.csv's ransac_ms, which is a DIFFERENT "
                      "quantity - it times one ransac_fit call over model C at 3 "
                      "iterations (4 LSQ solves of that one model: 3 sampling fits "
                      "plus the final inlier refit), and covers 107 flights rather "
                      "than stage 1's 8"),
```

#### 2. `src/regen_2class/build_iteration_rows.py:394`

Current:

```
        f"`ransac_ms` (median {r2['adj_med']} ms, max {r2['adj_max']} ms over "
        f"n={r2['adj_n']}){s(r2['adj_med'])}, but that wraps ALL four LSQ fits "
        f"over 107 flights, so it is not the same measurement and is not "
        f"presented as the after-value.",
```

Proposed replacement:

```
        f"`ransac_ms` (median {r2['adj_med']} ms, max {r2['adj_max']} ms over "
        f"n={r2['adj_n']}){s(r2['adj_med'])}, but that times one ransac_fit call "
        f"over model C at 3 iterations, over 107 flights, so it is not the same "
        f"measurement and is not presented as the after-value.",
```

#### 6. `results/regenerate_figures/iteration_rows.md:22` — GENERATED from site 2

Current:

> | **Measured effect** | **NOT_FOUND** - no CSV records a RANSAC-wrapped Model-C
> fit timed at 3 iterations. The nearest CSV quantity is the production sweep's
> `ransac_ms` (median 162.6 ms, max 338.2 ms over n=2481)[S4], but that wraps ALL
> four LSQ fits over 107 flights, so it is not the same measurement and is not
> presented as the after-value. |

Do not hand-edit. Regenerate after fixing site 2.

#### 7. `results/regenerate_figures/iteration_rows.md:157` — GENERATED from site 1

Current:

> - Known to exist outside CSV: the production sweep at n_iterations=3 exists
> only as pipeline_sweep_raw.csv's ransac_ms, which is a DIFFERENT quantity - it
> wraps all four LSQ fits, not the Model-C RANSAC fit alone, and covers 107
> flights rather than stage 1's 8

Do not hand-edit. Regenerate after fixing site 1.

### Family B — "ALL the least-squares fitting" (no model count, same error)

These do not say "four", but they assert `ransac_ms` is **broader** than the
RANSAC call. It is not — it is exactly that one call. Same error, different
phrasing, and the user's brief describes this file's docstring and caption, so
they are in scope.

#### 3. `src/regen_2class/stage_timing_breakdown.py:18` (module docstring)

Current:

```
NAMING, because two of these columns do not mean what they say:
  - ransac_ms wraps ALL the least-squares fitting, not just the RANSAC call.
  - predict_ms contains NO fitting - only find_own_crossing + eval_pos_vel.
```

Proposed replacement for line 18:

```
  - ransac_ms times one ransac_fit call over model C - internally 3 sampling
    fits plus the final inlier refit, i.e. 4 LSQ solves of that ONE model, not
    one solve each of several models.
```

Note line 17 says "two of these columns do not mean what they say". After the
fix that remains true for `ransac_ms` (the name still implies the RANSAC search
alone rather than search + final refit) and for `predict_ms`, so the count of
two stands.

#### 4. `src/regen_2class/stage_timing_breakdown.py:76` (figure legend label)

Current:

```
    "ransac_ms": "ransac_ms  (all LSQ fitting)",
```

Proposed replacement:

```
    "ransac_ms": "ransac_ms  (model-C fit, 3 iters + refit)",
```

Shorter alternative if the legend is width-constrained:

```
    "ransac_ms": "ransac_ms  (model-C RANSAC fit)",
```

#### 5. `src/regen_2class/stage_timing_breakdown.py:340` (figure caption)

Current:

```
        f"Two column names from the raw CSV mislead: ransac_ms wraps ALL the least-squares fitting, not just the RANSAC call, and is {rs_lo:.0f}-{rs_hi:.0f}% of median latency.",
```

Proposed replacement:

```
        f"Two column names from the raw CSV mislead: ransac_ms times one ransac_fit call over model C (3 sampling fits plus the final inlier refit), and is {rs_lo:.0f}-{rs_hi:.0f}% of median latency.",
```

#### 8. `results/regenerate_figures/stage_timing/figure_stage_timing_breakdown.caption.txt:2` — GENERATED from site 5

Current:

> Two column names from the raw CSV mislead: ransac_ms wraps ALL the
> least-squares fitting, not just the RANSAC call, and is 61-83% of median
> latency.

Do not hand-edit. Regenerate after fixing site 5.

#### 9. `results/regenerate_figures/CAPTIONS.md:364` — GENERATED from site 5

Same sentence as site 8, quoted into the captions index. Regenerate after fixing
site 5.

### Also baked into pixels

`results/regenerate_figures/stage_timing/figure_stage_timing_breakdown.png`
carries the site-5 caption drawn on the canvas, and both that PNG and
`figure_stage_timing_breakdown_clean.png` carry the site-4 legend label. Neither
can be corrected without re-rendering.

---

## 3. A related but DIFFERENT error, in this same directory

`results/regenerate_figures/03_realtime/audits/audit_threading_provenance.md`
(written by a concurrent run, not by this audit) states:

> That region contains **2 fitting calls**, covering model letters **C**.

> `ransac_ms` does not time a single RANSAC call - it brackets the whole fitting
> block for every model the sweep fits.

Both sentences are wrong, in the same direction but with a different count: the
timed region contains **one** `ransac_fit` call, and the sweep fits exactly one
model. Flagged because that file sits alongside this one and a reader could
reasonably take it as the corrected version. It is not.

---

## 4. Do NOT "fix" this one

`results/regenerate_figures/03_realtime/audits/audit_ransac_answers_q1_q3.md:90-91`
already carries the correction:

> **Correction:** I previously described `ransac_ms` as wrapping "all four LSQ
> fits", meaning four *different models*. That is wrong. It is one RANSAC call over
> ...

This is a record of the error being corrected, not an instance of it. It should
stay as written.

---

## 5. Summary

| # | file | line | family | generated from |
|---|---|--:|---|---|
| 1 | `src/regen_2class/build_iteration_rows.py` | 186 | A | — (source) |
| 2 | `src/regen_2class/build_iteration_rows.py` | 394 | A | — (source) |
| 3 | `src/regen_2class/stage_timing_breakdown.py` | 18 | B | — (source) |
| 4 | `src/regen_2class/stage_timing_breakdown.py` | 76 | B | — (source) |
| 5 | `src/regen_2class/stage_timing_breakdown.py` | 340 | B | — (source) |
| 6 | `results/regenerate_figures/iteration_rows.md` | 22 | A | site 2 |
| 7 | `results/regenerate_figures/iteration_rows.md` | 157 | A | site 1 |
| 8 | `.../stage_timing/figure_stage_timing_breakdown.caption.txt` | 2 | B | site 5 |
| 9 | `results/regenerate_figures/CAPTIONS.md` | 364 | B | site 5 |

**5 source edits** (sites 1–5) in 2 files, then regenerate to clear sites 6–9 and
re-render the two stage-timing PNGs.

Separately: `audit_threading_provenance.md` carries a different wrong count (2
calls) and would need its own correction.
