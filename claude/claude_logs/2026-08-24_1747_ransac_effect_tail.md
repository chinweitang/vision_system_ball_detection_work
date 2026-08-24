# Work Log: RANSAC effect - tail statistics

**Session:** 2026-08-24_1747
**Status:** In progress

Related: [2026-08-24_1700_plain_drag_sweep.md](2026-08-24_1700_plain_drag_sweep.md)
(produced both series and the pooled median/IQR figure this one re-cuts).

---

## Original Request

> Read results/regenerate_figures/ransac_effect_pooled/ outputs read-only. Write
> src/regen_2class/ransac_effect_tail.py producing a single-panel figure: x =
> observation window in ms, 100 ms bins as before, two series "without RANSAC"
> and "with RANSAC", y = fraction of paired cells with prediction error above
> 500 mm. Use only the 9,923 matched keys, and exclude the 331 cells where RANSAC
> recorded no value from both series so the pairing stays exact; report how many
> cells that leaves per bin. Emit a companion CSV carrying, per bin and per
> series: n cells, median, p90, p95, max, fraction above 500 mm, and fraction
> above 200 mm. Also report the p95 series so I can see both statistics before
> choosing. STOP if the two series do not share an identical key set after the
> exclusion. STOP if any plotted bin has fewer than 100 cells. Do not smooth, and
> if the tail statistic favours the plain fit at any bin, plot it as measured and
> flag it in the log. Output to results/regenerate_figures/ransac_effect_tail/.
> Log incrementally.

---

## [17:47] Step 1 - read the pooled outputs, check the exclusion is survivable

`results/regenerate_figures/ransac_effect_pooled/ransac_effect_pooled.csv`,
16 bins, read-only.

Per-bin paired counts after removing the 331 RANSAC-missing cells:

| window (ms) | n_cells | n_paired | n_missing |
|---|--:|--:|--:|
| 0-100 | 778 | 778 | 0 |
| 100-200 | 928 | 640 | **288** |
| 200-300 | 932 | 899 | **33** |
| 300-400 | 906 | 898 | **8** |
| 400-500 | 857 | 855 | **2** |
| 500-600 | 808 | 808 | 0 |
| 600-700 | 741 | 741 | 0 |
| 700-800 | 658 | 658 | 0 |
| 800-900 | 625 | 625 | 0 |
| 900-1000 | 598 | 598 | 0 |
| 1000-1100 | 594 | 594 | 0 |
| 1100-1200 | 570 | 570 | 0 |
| 1200-1300 | 482 | 482 | 0 |
| 1300-1400 | 303 | 303 | 0 |
| 1400-1500 | 122 | 122 | 0 |
| 1500-1600 | 21 | 21 | 0 |
| **total** | **9923** | **9592** | **331** |

Two things this settles before any code runs:

1. **The >=100 gate survives the exclusion.** The smallest plotted bin is
   1400-1500 ms at 122 paired cells. 1500-1600 ms (21 cells) stays excluded, as
   in the pooled figure. So the plotted range is unchanged at 0-1500 ms, 15 bins.
2. **All 331 RANSAC failures sit in 100-500 ms** (288+33+8+2 = 331), and 288 of
   them in a single bin. RANSAC's non-convergence is not spread across the sweep;
   it is a short-window phenomenon. Worth carrying into the interpretation - the
   100-200 ms bin loses 31% of its cells to the exclusion, far more than any
   other.

### Note carried forward from the pooled run

The 0-100 ms bin is 778 cells that are all N < 8, where the original never runs
RANSAC and falls back to the plain fit. Both series are numerically identical
there, so every statistic in that bin - tail fraction included - must come out
exactly equal. That is a correctness check on this script, not a finding.

### Binning imported, not re-specified

"100 ms bins as before" is enforced by importing `BIN_MS`, `MIN_CELLS`,
`read_series`, `window_ms_lookup` and the series colours from
`ransac_effect_pooled` rather than restating them, so the two figures cannot
drift onto different grids.

## [17:56] Step 2 - script written and run

`src/regen_2class/ransac_effect_tail.py`.

```
matched keys before exclusion: 9923
excluded 331 cell(s) from BOTH series (331 missing in the RANSAC series, 0 in the plain series)
surviving paired cells: 9592
KEY GATE PASS: both series carry the identical 9592 keys after exclusion
CROSS-CHECK PASS: per-bin surviving counts match the pooled run's n_paired
PLOTTED RANGE: 0-1500 ms (15 bins), all >= 100 cells
  EXCLUDED   1500-1600 ms  n=21 (below 100; reported, not hidden)
```

Added a gate the brief did not ask for: the per-bin surviving counts are checked
against the pooled run's own `n_paired` column. If this script's exclusion ever
produced a different cell set, the two figures would silently be over different
data. It passes on every bin.

Correctness check that had to hold: the 0-100 ms bin is 778 cells all at N < 8,
where the original falls back to the plain fit. Every statistic there comes out
byte-identical between the series - median 977.6, p90 3740.4, p95 5295.8, max
13615.8, tail fraction 0.7301 on both sides. It does.

### PLOTTED STATISTIC - fraction of cells with error > 500 mm

| window (ms) | without | with | diff | n |
|---|--:|--:|--:|--:|
| 0-100 | 0.7301 | 0.7301 | +0.0000 | 778 |
| 100-200 | 0.3125 | 0.3328 | **+0.0203** | 640 |
| 200-300 | 0.1379 | 0.2069 | **+0.0690** | 899 |
| 300-400 | 0.0267 | 0.0947 | **+0.0679** | 898 |
| 400-500 | 0.0152 | 0.0515 | **+0.0363** | 855 |
| 500-600 | 0.0359 | 0.0136 | -0.0223 | 808 |
| 600-700 | 0.0418 | 0.0000 | -0.0418 | 741 |
| 700-800 | 0.0502 | 0.0000 | -0.0502 | 658 |
| 800-900 | 0.0640 | 0.0000 | -0.0640 | 625 |
| 900-1000 | 0.0635 | 0.0000 | -0.0635 | 598 |
| 1000-1100 | 0.0842 | 0.0000 | -0.0842 | 594 |
| 1100-1200 | 0.0702 | 0.0000 | -0.0702 | 570 |
| 1200-1300 | 0.0851 | 0.0000 | -0.0851 | 482 |
| 1300-1400 | 0.1221 | 0.0000 | -0.1221 | 303 |
| 1400-1500 | 0.1148 | 0.0000 | -0.1148 | 122 |

### FLAGGED - the plain fit wins at 4 of 15 windows

**100-200, 200-300, 300-400 and 400-500 ms**: the plain fit has the SMALLER tail
fraction, by up to 6.9 percentage points (300-400 ms: 2.67% vs 9.47%). Plotted as
measured, not smoothed, not dropped. p95 agrees - the plain fit is lower at
exactly the same four windows (300-400 ms: 447 mm vs 627 mm).

The two statistics therefore do NOT disagree about where the crossover is. Both
put it at **500-600 ms**.

### The exact zeros are real - verified against max, not assumed

"with RANSAC" reads exactly 0.0000 at every bin from 600 ms up. That is a
suspicious number over 4,693 cells, so it was checked against the per-bin
maximum rather than taken at face value:

| window (ms) | max without | max with |
|---|--:|--:|
| 600-700 | 5027.3 | **496.3** |
| 700-800 | 4057.6 | **487.9** |
| 800-900 | 2954.5 | **429.8** |
| 900-1000 | 3823.6 | **420.6** |
| 1000-1100 | 3691.7 | **367.0** |
| 1100-1200 | 2642.2 | **352.6** |
| 1200-1300 | 2634.9 | **346.6** |
| 1300-1400 | 2046.5 | **336.2** |
| 1400-1500 | 1540.6 | **327.1** |

The zeros are genuine: RANSAC's WORST single prediction at any window >= 600 ms
is 496 mm, under the threshold, while the plain fit produces individual
predictions up to 5.7 m off in the same bins. Not a clipping artefact.

### Subtlety worth carrying into the report

At **400-500 ms** the two tail measures point opposite ways: the plain fit has
the smaller >500 mm fraction (0.0152 vs 0.0515) but a far worse maximum
(4905.7 mm vs 973.8 mm). Fewer moderate overruns, one catastrophic one. That is
the whole trade in miniature - RANSAC accepts more mid-sized misses in exchange
for removing the catastrophic ones. A report quoting only the >500 mm fraction at
that window would read as a loss for RANSAC while its worst case is 5x better.

### Second figure (extra, ignorable)

The brief asked to SEE p95 alongside the tail rate before choosing. p95 is in the
companion CSV, but the two statistics do not share a y unit, so it also got its
own PNG (`ransac_effect_p95.png`). Not a replacement for the requested
single-panel tail figure, which is unchanged.

### Sources untouched

`prediction_sweep_all_flights.csv` 2026-07-28 13:10, `plain_drag_sweep.csv` and
`ransac_effect_pooled.csv` unchanged.

## Deliverables

- `results/regenerate_figures/ransac_effect_tail/ransac_effect_tail.png`
- `results/regenerate_figures/ransac_effect_tail/ransac_effect_p95.png`
- `results/regenerate_figures/ransac_effect_tail/ransac_effect_tail.csv`
- `results/regenerate_figures/ransac_effect_tail/ransac_effect_tail_summary.txt`

**Status: Complete.**
