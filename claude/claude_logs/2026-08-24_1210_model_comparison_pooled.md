# Work Log: Pooled trajectory-model comparison figure

**Session:** 2026-08-24_1210
**Status:** Complete

---

## Original Request

> Read results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv
> read-only. Write src/regen_2class/model_comparison_pooled.py producing a
> single-panel figure: x = observation window in ms, y = prediction error at target
> in mm, log scale, three series each with a median line and a shaded IQR band.
> Series labels exactly "free gravity", "fixed gravity", "fixed gravity + drag";
> assert the strings "Model A", "Model B" and "Model C" appear in no user-facing
> string before writing. Pool across all flights. Do NOT split by duration stratum
> and do NOT apply any elevation class. Exclude rows with blank error_mm and report
> how many were excluded per model. Emit a companion CSV of median, IQR and
> contributing n per model per window. STOP if the pooled flight count is not 158 and
> report what it is. STOP if the contributing n at any plotted window falls below 40;
> truncate the x-range instead and say where. Output to
> results/regenerate_figures/model_comparison_pooled/. Log incrementally.

---

## [12:10] Step 1 - the x-axis is not a column, and that needed resolving

The file's columns are `session, flight, N, model, lead_time_ms, error_mm,
rejected_frac`. There is **no observation-window-in-ms column**.

Worse, the generating script
(`src/stereo/trajectory_model_prediction_sweep_all_flights.py`) opens with an
explicit warning against the obvious substitute:

> "aggregated by LEAD TIME (not raw N -- different flights have different frame
> densities/lengths, so **N isn't comparable across flights**)"

So `N` is the sweep variable but the author considered it unsafe to pool on.
`lead_time_ms` is what the file was built around - and it is a DIFFERENT quantity
that runs the opposite way (`lead_time = t_target - t_window_end`, so more
observation means LESS lead time). Plotting lead time against an axis labelled
"observation window" would be simply wrong.

### Checked the warning rather than accepting or ignoring it

Derived each flight's frame period from its own consecutive-`N` lead-time steps:

```
per-flight frame period, n=158 flights
  min 16.6500   median 16.6500   max 16.6500   spread 0.0000
```

**Every one of the 158 flights has an identical 16.65 ms frame period.** The
author's concern was that differing frame densities make `N` incomparable; in this
file there is no such difference, so the concern does not bite. That makes

    observation window (ms) = (N - 1) x 16.65

exact and comparable across all flights, not an approximation.

Two things worth recording about that constant:

- It is **16.65**, not `1000/60 = 16.6667`. Measured from the data rather than
  assumed. The script derives it at runtime and asserts the spread is zero rather
  than hardcoding either value.
- `N-1` intervals, not `N` - the window spans from the first point to the last,
  so 3 points is 2 frame periods (33.3 ms), not 3.

## [12:14] Step 2 - gates

**Flight count: 158.** Matches the required value exactly (`(session, flight)`
pairs; note only 124 distinct bare flight ids, so a bare-id key would have merged
34 flights - keyed on the pair throughout).

**Contributing n >= 40:** satisfied for `N = 3 .. 81`, i.e. windows
**33.3 .. 1332.0 ms**. `N >= 82` falls below 40 on all three series (82 -> 38,
falling to 3 at N=91), so the x-range is truncated at 1332.0 ms rather than
stopping. **No interior violations** - the run from N=3 to N=81 is contiguous, so
truncation is sufficient and nothing thin is hidden mid-plot.

**Blank `error_mm` excluded:** 172 / 228 / 331 rows for the three models
respectively (731 total of 29,769).

### One oddity flagged, not smoothed over

Contributing n is **not monotonic at low N**. Within the kept range the thinnest
windows are:

| window | N | n (free g) | n (fixed g) | n (fixed g + drag) |
|--:|--:|--:|--:|--:|
| 83.2 ms | 6 | 78 | 65 | 158 |
| 116.5 ms | 8 | 135 | 126 | **49** |

All 158 rows are PRESENT at both windows, so these are fit failures, not missing
data. The two free/fixed-gravity series lose points at 83 ms while the drag series
does not; the drag series then loses points at 116 ms while the other two recover.
All stay above the 40 floor so nothing is truncated for it, but a reader comparing
series at those two windows is comparing different subsets of flights. Carried into
the caption and the companion CSV.

---

## [12:22] Step 3 - built and verified

`src/regen_2class/model_comparison_pooled.py`. Three gates, all PASS:

| gate | result |
|---|---|
| pooled flight count == 158 | **PASS** - 158 |
| contributing n >= 40 at every plotted window | **PASS after truncation** at 1332.0 ms |
| forbidden model-code strings absent | **PASS** - 0 of 18 user-facing strings |

The frame period is derived at runtime and the script STOPS if the spread exceeds
0.5 ms, so if this is ever pointed at a file whose flights really do differ in
frame density, it refuses to build the derived axis rather than quietly producing
a wrong one.

### Outputs

| file | |
|---|---|
| `results/regenerate_figures/model_comparison_pooled/model_comparison_pooled.png` | single panel, log y, 6.6 in at 300 dpi |
| `results/regenerate_figures/model_comparison_pooled/model_comparison_pooled.csv` | 237 rows = 3 series x 79 windows |

Source mtime still 2026-07-28 13:10 - not modified.

### One render fix

The caption's source-path line ran to the right edge of the canvas. Split across
two lines rather than left to risk clipping.

### What the figure shows

Median error at four windows (mm):

| window | free gravity | fixed gravity | fixed gravity + drag |
|--:|--:|--:|--:|
| 100 ms | 14,287 | 867 | **613** |
| 300 ms | 2,146 | 653 | **252** |
| 500 ms | 766 | 540 | **177** |
| 1000 ms | 285 | 432 | **118** |

Two things a reader should take from this:

1. **Fixed gravity + drag wins at every window**, by roughly 2-4x on the median.
2. **The other two series CROSS at around 700 ms.** Free gravity is catastrophic
   when short - 268 m median error at 33 ms, i.e. the fit is unconstrained and
   diverging - but overtakes fixed gravity once the window is long enough to pin
   gravity down from the data. Fixing gravity is a strong prior that helps when
   data is scarce and actively hurts once it is not.

The y-axis had to be log for this to be legible at all: the free-gravity series
spans from ~2.7e5 mm down to ~1.8e2 mm, three orders of magnitude, and on a linear
axis the other two series would sit flat against zero.

## Status: COMPLETE
