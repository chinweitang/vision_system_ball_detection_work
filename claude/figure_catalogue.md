# Figure catalogue - all plot figures under `data/`

Read-only audit. Nothing under `data/` or `calibration_outputs/` was created, modified, moved or deleted.

**Scope**: plot/chart figures only. Raw imagery (flight frames, checkerboard captures, ball crops, contact sheets, inspection crops) is excluded by request - see [§9](#9-image-sets-excluded-counts-only) for a one-line count of each so nothing is silently dropped.

**Totals**: `data/` holds 103,303 PNG files / ~78 GB. Of those, **113 are plot figures**; the remaining ~103,190 are raw or rendered imagery.

**Inspection status**: every figure marked ✅ below was opened and read visually (axes, units, series, N read off the render itself). Figures marked ⚪ were not opened individually - they are same-script siblings of an inspected figure (same generator, different input file), and their description is inferred from the inspected sibling plus the worklog. Treat ⚪ axis details as high-confidence but not eyeballed.

**Verdict key**
- **report-ready** - usable in the thesis as-is
- **needs redraw** - the result is sound but the render has a defect (clipping, tick collision, default styling) that must be fixed before it goes in the report
- **diagnostic-only** - a working/QA artefact; superseded, pilot-scale, or per-flight. Not report material

---

## Report-ready shortlist

If you only pull a handful into the thesis, these are the ones that carry the headline results:

| Figure | Carries |
|---|---|
| `figures2/figure1_margin.png` | Real-time feasibility: max-usable cutoff per regime (FLAT 300 / MID 450 / LOB 800 ms) |
| `figures2/figure2_feasibility_panels.png` | Observation + compute vs each regime's own deadline |
| `figures2/figure3_position_error_at_operating_point.png` | Crossing-point error at the *feasible* operating point (all three regimes < 100 mm) |
| `figures2/figure4_velocity_error_by_axis.png` | Per-axis velocity bias vs scatter, with the Y-width floor flagged unresolved |
| `05_budget_by_elevation_bin/budget_by_bin_histogram.png` | FLAT P5 = 502 ms is the design budget; pooled P5 was inflated by throw mix |
| `ransac_iterations_sweep/figure1` + `figure2` | RANSAC cost is linear (71.4 ms/iter); n_iterations=3 costs nothing in accuracy |
| `01_crossing_plane_setup/crossing_scatter_pooled.png` | HIT/MISS classification over the rebounder aperture, 107 crossers |
| `all_flights/axis_decomposition/axis_error_long.png` | Model C's width-axis error crossing the ±100 mm spec line |
| `board_frame/quiver_img_0036_*.png` | Triangulation precision at 5 m: ~1-2 mm/axis scatter, ~2 mm warp |

Two headline figures need a redraw first: `all_flights/phase2/prediction_error_vs_leadtime.png` (title clipped) and `two_axis_sweep/figure1` (y-label clipped). Both are detailed below.

---

## 1. `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures/`

Source: `src/stereo/pipeline_sweep_figures.py`, from the 107-crosser × 24-cutoff Pi sweep (2,568 rows; 2,481 "ok", 87 RANSAC fit-failures concentrated at small t). Worklog: `2026-08-04_1906_pi_prediction_pipeline_sweep_worklog.md`.

**Population for all three: n = 107 crossers** (FLAT 35 / MID 12 / LOB 60).

### `figure1_accuracy_vs_t.png` ✅
- 222 KB · 2026-08-04 19:55
- **x**: prediction cutoff time t (ms), 150-1250. **y**: HIT/MISS accuracy vs full-arc reference (%), 0-100.
- **Series**: 3 lines - FLAT (blue, n=35/35 @490 ms), MID (amber, n=12/12), LOB (red, n=59/60). Dotted vertical at t=490 ms (v1 deadline).
- **Takeaway**: LOB is the hard regime - 60% accuracy at t=150 ms, only reaching ~95% by 450 ms; FLAT and MID are at or near 100% almost throughout.
- **Verdict**: **report-ready**. Title carries the "CONVERGENCE, NOT ground truth" caveat, and n counts are folded into the legend labels.

### `figure2_position_error_vs_t.png` ✅
- 239 KB · 2026-08-04 19:55
- **x**: prediction cutoff time t (ms), 150-1250. **y**: crossing-point position error, median (mm), 0-~550.
- **Series**: FLAT / MID / LOB median lines. Dotted horizontal at 100 mm (provisional threshold), dotted vertical at t=490 ms.
- **Takeaway**: all three converge monotonically-ish; LOB needs ~700 ms to reach 100 mm where FLAT gets there by ~250 ms. MID is visibly noisy (n=12).
- **Verdict**: **report-ready**, but largely superseded by `figures2/figure3`, which adds the IQR band and marks the actually-feasible cutoff.

### `figure3_latency_vs_t.png` ✅
- 290 KB · 2026-08-04 19:55
- **x**: cutoff t (ms). **y**: pipeline latency, median (ms) - composed of last-pair detect + triangulate + RANSAC + predict + 1-frame lag. Range ~100-320.
- **Series**: FLAT / MID / LOB. Dashed horizontal at the 490 ms deadline. Inset box: threaded detect median 13.7 ms vs 60 fps cadence 16.7 ms.
- **Takeaway**: latency alone never approaches 490 ms - but this is the **misleading** framing.
- **Verdict**: **diagnostic-only, do not use in the report**. The worklog itself flags this (2026-08-05 12:35 section): plotting `latency(t)` alone drops the observation term `t`, so it answers "does compute fit in 490 ms?" rather than "does observation + compute fit before the ball crosses?". `figures2/figure1_margin.png` supersedes it and reaches a materially tighter conclusion. If both appear in the thesis without reconciliation, they read as contradictory.

---

## 2. `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures2/`

The corrected feasibility set. Source: same sweep, re-aggregated into `margin_analysis.csv` (72 rows) plus a per-axis re-run (`pipeline_sweep_full_vaxis_20260805.json`, regression-checked against the original at 0 mismatches across all 2,481 rows).

Deadlines used throughout: FLAT 490 ms (population min, chosen over P5=502 ms because n=35 is thin), MID 710 ms (P5), LOB 1080 ms (P5).

### `figure1_margin.png` ✅
- 422 KB · 2026-08-05 12:37
- **x**: cutoff t (ms), 150-1250. **y**: `margin_p95(t) = deadline − t − latency_p95(t)` (ms), ~+780 to −1000.
- **Series**: 3 solid lines (p95, the actual guarantee) + 3 lighter dashed companions (median, reference only). Dotted `margin = 0` boundary, pink shading below it (infeasible), 3 coloured verticals at each regime's max-usable-t.
- **N**: FLAT 35, MID 12, LOB 59-60 per t.
- **Takeaway**: max-usable-t is **FLAT 300 ms, MID 450 ms, LOB 800 ms** - far earlier than the nominal deadlines. LOB's margin at 800 ms is 1.2 ms, i.e. right on the boundary; the next step (850 ms) is already at −58 ms.
- **Verdict**: **report-ready**. This is THE feasibility figure. Using p95 not median as the boundary is the right call and is stated in the subtitle.

### `figure2_feasibility_panels.png` ✅
- 401 KB · 2026-08-05 12:37
- Three panels, one per regime. **x**: cutoff t (ms). **y**: `T_ready(t) = t + latency(t)` (ms), ~280-1600.
- **Series per panel**: T_ready p95 (solid, coloured) + T_ready median (dashed, lighter). Dotted horizontal at that regime's deadline, pink shading above it, dotted vertical at max-usable-t.
- **Takeaway**: the same result as figure1 in "when is the answer actually available" form - the rising curve crosses each regime's own deadline at 300 / 450 / 800 ms.
- **Verdict**: **report-ready**. Note each panel has its own y-scale, so panels are not directly comparable by eye - fine given each has its own deadline line, but worth a caption sentence.

### `figure3_position_error_at_operating_point.png` ✅
- 374 KB · 2026-08-05 12:37
- **x**: cutoff t (ms) - x-label states the verticals are each regime's max-usable-t. **y**: crossing-point position error, median (mm), 0-800, shaded band = IQR.
- **Series**: FLAT / MID / LOB median + IQR ribbon. Dotted horizontal at 100 mm, 3 coloured verticals at 300 / 450 / 800 ms.
- **Takeaway**: at each regime's *feasible* cutoff, median error is 80.5 / 77.8 / 76.7 mm - all under 100 mm. Accuracy is not the limiter; time budget is.
- **Verdict**: **report-ready**. Title cites both the convergence caveat and the ~106 mm label-vs-fit reference floor, which is the honest framing.

### `figure4_velocity_error_by_axis.png` ✅
- 735 KB · 2026-08-05 13:15
- Three panels: X_world (depth), Y_world (width), Z_world (up). **x**: cutoff t (ms). **y**: velocity error - line = signed bias, band = ±scatter RMS (mm/s). Grey band = that axis's label-precision floor (155 / 282 / 135 mm/s). Dotted verticals at max-usable-t.
- **Series**: FLAT / MID / LOB per panel.
- **Takeaway**: bias sign is structurally consistent - X and Z negative, Y positive - across all three regimes, and shrinks toward zero as t grows. Scatter sits at or below each axis's floor at every operating point.
- **Verdict**: **report-ready**, and it is the only figure in the set that visually distinguishes the *validated* X/Z floors from the *unresolved* Y-width floor (panel title says so explicitly). Keep that annotation if you re-render. Minor: each panel has an independent y-scale (X ±500, Y ±600, Z −800/+200), which understates how much larger the Y-width errors are - worth a caption note.

---

## 3. `data/pi_benchmarking/two_axis_sweep/figures/`

Earlier Pi sweep, **serial** (not threaded) detection, batched-detection assumption. **n = 150 flights** (duration ≥ 430 ms), RANSAC n_iterations=3, rect kernel. 2026-08-03 21:35, ~175-216 KB each.

This whole set was **superseded the following evening** by the concurrent-with-capture model in §1-2, which reversed its conclusion. Under the batched assumption no fit window under 430 ms cleared the budget even at the median; under the corrected model, latency never binds and the constraint is the observation term instead.

### `figure1_W_vs_time_consumed.png` ✅
- **x**: fit window duration W (ms), discrete 150/200/250/300/350/400/430. **y**: total elapsed time = W + detection + triangulation + RANSAC (ms), ~150-1080.
- **Series**: W alone (grey dashed, observation only), W + compute median (blue), W + compute p95 (red). Dotted horizontal at the 430 ms actuation budget.
- **Takeaway**: under serial batched detection every W lands above the 430 ms line - the pessimistic result that the parallel-detection work later corrected.
- **Verdict**: **needs redraw** if used at all - the y-axis label is **clipped at the top of the canvas** ("...(ms," is cut off mid-word). But given it is superseded, **diagnostic-only** is the right call; use it only if you want to show the correction narrative, and redraw it if so.

### `figure2_W_vs_position_error.png` ✅
- **x**: fit window W (ms). **y**: final-point position error (mm), 100-600, shaded = IQR.
- **Series**: single median line, n=150 flights (stated in the title).
- **Takeaway**: error falls 409 mm → 192 mm as W goes 150 → 430 ms; diminishing returns past ~250 ms.
- **Verdict**: **diagnostic-only** (superseded by the crossing-plane error figures, which measure the operationally relevant quantity rather than final-point).

### `figure3_W_vs_velocity_error.png` ✅
- **x**: fit window W (ms). **y**: velocity prediction error, median (mm/s), **log scale**.
- **Series**: (a) full-trajectory self-consistency (blue, solid) and (b) independent finite-difference (red, dashed). Title states (a) is a self-consistency check, not ground truth.
- **Takeaway**: the two methods differ by roughly an order of magnitude and (b) is flat vs W - the independent estimate carries much more noise.
- **Verdict**: **needs redraw**. The log y-axis has exactly one labelled tick (10³), so no value can be read off the chart at all. Honest framing in the title, unreadable quantitatively.

---

## 4. `data/prediction/`

### 4.1 `01_crossing_plane_setup/` - 2026-08-04 13:58

All four share axes: **x** = Y (mm, along the tape from P_far), **y** = Z (mm, up from P_far). Grey rectangle = the 2 m × 2 m rebounder aperture. Green circles = HIT, amber triangles = MISS_HIGH_WIDE. MISS_SHORT flights (56) are correctly not plotted - they never reach the plane.

Classification totals across 163 eligible flights: HIT 87, MISS_HIGH_WIDE 20, MISS_SHORT 56, 0 skipped.

| File | Size | N | Inspected |
|---|---|---|---|
| `crossing_scatter_pooled.png` | 65 KB | HIT 87 + MISS_HIGH_WIDE 20 = 107 | ✅ |
| `crossing_scatter_REG_15.png` | 51 KB | HIT 13 + MISS 9 | ✅ |
| `crossing_scatter_REG_21_1.png` | 53 KB | (per-registration split of the pooled 107) | ⚪ |
| `crossing_scatter_REG_21_2.png` | 54 KB | (per-registration split of the pooled 107) | ⚪ |

- **Takeaway (pooled)**: HITs fill the aperture box fairly evenly; MISS_HIGH_WIDE cluster above and to the left of it, i.e. mostly too high rather than too wide. Visual confirmation the classifier is doing what it claims.
- **Verdict**: pooled is **report-ready** (clean, well-labelled, counts in the legend). The three per-registration versions are **diagnostic-only** - they are the same story at n=13-22 and only exist to confirm no registration is an outlier.

### 4.2 `02_candidate_reselection/candidates_scatter.png` ✅
- 61 KB · 2026-08-04 16:52
- Same Y/Z aperture axes. **Series**: 20 selected candidate flights, colour = elevation stratum (FLAT blue / MID orange / LOB green), marker shape = HIT circle / MISS_HIGH_WIDE triangle. Four reserved probes labelled inline (flight_109, 87, 13, 75).
- **N**: 20 candidates drawn from 107 crossers (FLAT 7 / MID 7 / LOB 6).
- **Takeaway**: the v2 selection spreads across the aperture within each stratum, fixing v1's failure mode (edge-distance ranking filled the list with near-edge lobs and excluded flat drives entirely).
- **Verdict**: **diagnostic-only** - it documents a sampling decision, not a result. If you do use it, the legend block sits on the aperture box's top-left corner and should be moved.

### 4.3 `04_launch_to_crossing_budget/launch_to_crossing_histogram.png` ✅
- 106 KB · 2026-08-04 17:44
- **x**: launch-to-crossing-plane duration (ms), ~470-1570. **y**: flight count, 0-13.
- **Series**: single histogram (~25 bins), **n = 107 crossers**. Three red vertical lines at P5 = 536, P10 = 561, P15 = 582 ms; values in a corner text box.
- **Takeaway**: strongly **bimodal** - a flat-drive cluster around 500-700 ms and a lob cluster around 1050-1500 ms, with a near-empty gap between. Pooling them into a single P5 is exactly what §4.4 corrects.
- **Verdict**: **report-ready** as the setup for the per-bin figure, and the bimodality is itself the argument for binning. One fix: the three red lines are distinguished only by dash pattern and are not individually keyed - the text box gives values but not which line is which.

### 4.4 `05_budget_by_elevation_bin/budget_by_bin_histogram.png` ✅
- 147 KB · 2026-08-04 17:57
- **x**: launch-to-crossing-plane duration (ms), ~470-1570. **y**: flight count, 0-10.
- **Series**: 3 overlaid semi-transparent histograms - FLAT (blue, n=35), MID (amber, n=12), LOB (red, n=60) - plus a dashed vertical at each bin's own P5. Corner box: FLAT P5 = 502, MID P5 = 710, LOB P5 = 1080 ms.
- **Takeaway**: **FLAT P5 = 502 ms is the design budget.** The pooled P5 of 536 ms was inflated by throw mix (60 of 107 crossers are lobs); the throw-mix-independent worst case is lower. This is the number the whole feasibility analysis is anchored to.
- **Verdict**: **report-ready**. One of the most load-bearing figures in the project.

### 4.5 `06_label_vs_fit/` - 2026-08-04 19:36

**N = 20 manually-bracket-labelled flights**, compared against the Model-C full-arc fit.

#### `position_scatter.png` ✅
- 83 KB
- Same Y/Z aperture axes. **Series**: filled marker = Model-C predicted crossing position, open marker of the same colour = label-derived fit, joined by a thin line so the disagreement is a visible segment. Colour = elevation stratum; `×` marks asymmetric/flagged flights.
- **Takeaway**: most pairs sit within a couple of hundred mm; disagreements are systematically down-and-right (label lower/further along the tape than Model C), and the largest gaps are on the flagged flights.
- **Verdict**: **report-ready**. This is the closest thing to a ground-truth check on the crossing prediction and the source of the ~106 mm reference floor cited elsewhere.

#### `velocity_comparison.png` ✅
- 118 KB
- Three panels: X_world (depth), Y_world (width), Z_world (up). **x**: flight ID (20 categorical ticks: 109, 87, 13, 75, 88, 6, 53, 69, 11, 33, 19, 73, 119, 15, 118, 22, 14, 56, 12, 107). **y**: velocity component (mm/s) - X ~2000-8000, Y ~−2500 to +500, Z ~−7000 to −3800.
- **Series**: open circle = label, filled square = Model-C, error bars = label-fit SD. Colour = elevation stratum.
- **Takeaway**: X and Z agree closely (markers often overlap within the error bar). **Y_world (width) is where they diverge**, frequently by more than the error bar - consistent with Y being the weak/unvalidated axis throughout the project.
- **Verdict**: **report-ready** with a caveat - the legend appears only in the first panel, and the per-panel y-scales differ by ~3×, so the Y-panel disagreement looks smaller than it is relative to X. Worth a caption sentence.

---

## 5. `data/trajectory_fit_comparison/`

### 5.1 `all_flights/phase2/prediction_error_vs_leadtime.png` ✅ - THE Model A/B/C figure
- 671 KB · 2026-07-28 13:10
- **x**: lead time (ms), 0-1600. **y**: prediction error at target (mm), **log scale**, ~4 to 3×10⁶.
- **Series**: 9 - for each of A (blue) / B (orange) / C (green): faint scatter of all points, `×` markers for RANSAC-health-flagged points, and a bold median trend line with an IQR ribbon.
- **N**: **158 flights** (stated in the title). Note: `context.md` describes this analysis as "163 flights" - 163 is the eligible population, 158 is the number that produced valid rows here. Worth reconciling before the number goes in the thesis.
- **Takeaway**: Model C is lowest at every lead time and the gap widens with lead time. Model A diverges catastrophically past ~600-700 ms (median exceeding 10⁵ mm); Model B never blows up but never wins.
- **Verdict**: **needs redraw**. Two defects:
  1. **The title is clipped at the right edge** - it ends mid-word ("...see pilot out"), so the caveat it was written to carry is cut off.
  2. It is rendered in **default matplotlib styling** (default palette, boxed legend, grey gridlines), unlike the dataviz-styled Pi and RANSAC figures. In a thesis it will visibly not match them.
  The underlying result is the decisive one in the project - it is worth the redraw.

### 5.2 `all_flights/phase1/` - drag coefficient K discovery, 2026-07-28 12:42-12:46

| File | Size | Axes | N | Insp. |
|---|---|---|---|---|
| `residual_vs_K_pooled.png` | 87 KB | x: K (1/mm, log) · y: pooled residual RMS (mm, count-weighted), 20-160 | 163 flights | ✅ |
| `per_flight_k_distribution.png` | 37 KB | x: per-flight refined K (1/mm), 1.5-7.2e-5 · y: count, 0-26 | 159 flights | ✅ |
| `k_vs_velocity.png` | 62 KB | x: fitted \|v0\| (mm/s), 6000-10500 · y: per-flight K (1/mm) | 159 flights | ✅ |
| `models_full_arc_residual_distribution.png` | 46 KB | x: model A/B/C (categorical) · y: full-arc RANSAC residual RMS (mm, log), 30-55 | 163 flights | ✅ |

- **`residual_vs_K_pooled`**: clean single-minimum bowl. Red dashed at the refined pooled K = 5.268e-5, green dotted at the 2-flight pilot K = 6.054e-5 - the two sit close together on a flat-bottomed curve, which is the evidence that the pilot value was not badly wrong. **Report-ready**; this is the figure that justifies the pooled-K method.
- **`per_flight_k_distribution`**: unimodal, slightly left-skewed, centred ~5.2e-5, pilot value marked at the right shoulder. **Report-ready** - it shows real per-flight K spread rather than a fitting artefact.
- **`k_vs_velocity`**: scatter, Pearson r = −0.374 in the title. **Diagnostic-only** - the correlation is weak and the worklog is careful not to assert the Reynolds-number explanation. Do not put a trendline story on this.
- **`models_full_arc_residual_distribution`**: box plot, log y. Counter-intuitive but important - on **full-arc residual** A has the lowest median (~40 mm) and C is slightly higher (~41 mm), with B worst (~46 mm). **Report-ready if paired with §5.1**, because the point is precisely that full-arc fit quality does not predict extrapolation quality: A fits the observed arc well and then diverges. On its own it is misleading.

### 5.3 `all_flights/duration_distribution/flight_duration_histogram.png` ✅
- 49 KB · 2026-07-28 16:14
- **x**: total observable duration, first usable fit frame → held-out target (ms), 200-1600. **y**: count (flights), 0-25. **n = 158**.
- **Series**: single histogram + 3 red dashed verticals labelled p25 / median / p75 (~720 / ~1300 / ~1420 ms).
- **Takeaway**: bimodal again (short ~400-800 ms, long ~1200-1500 ms), which is exactly why the duration-stratified reanalysis was needed - a pooled comparison would mix two populations.
- **Verdict**: **report-ready** as the justification for stratifying.

### 5.4 `all_flights/stratified_by_duration/` - 2026-07-28 16:23

Four figures, two axes × two strata. **short stratum n = 55, long stratum n = 103** (55 + 103 = 158, consistent).

| File | Size | x-axis | Insp. |
|---|---|---|---|
| `prediction_error_vs_obsduration_short.png` | 375 KB | fit window duration (ms), 0-1000 | ⚪ |
| `prediction_error_vs_obsduration_long.png` | 627 KB | fit window duration (ms), 0-1600 | ✅ |
| `prediction_error_vs_leadtime_short.png` | 351 KB | lead time (ms), 0-950 | ✅ |
| `prediction_error_vs_leadtime_long.png` | 611 KB | lead time (ms) | ⚪ |

- **y (all four)**: prediction error at target (mm, log scale). **Series**: A/B/C scatter + RANSAC-flagged `×` + median trend + IQR ribbon, same 9-series structure as §5.1.
- **Takeaway**: the C < B < A ranking in the degraded regime holds **independently in both strata**, so it is not an artefact of pooling short and long flights. On the observation-duration axis, error falls with more data; on the lead-time axis it rises with extrapolation distance - two views of the same trade.
- **Verdict**: **report-ready as a robustness appendix**, not headline. Same default-matplotlib styling issue as §5.1. Pick one axis (observation-duration is the more decision-relevant one) rather than printing all four.

### 5.5 `all_flights/axis_decomposition/` - 2026-07-28 17:31

| File | Size | N | Insp. |
|---|---|---|---|
| `axis_error_short.png` | 638 KB | 55 flights | ✅ |
| `axis_error_long.png` | 1.02 MB | 103 flights | ✅ |

- Three panels each: X (person→rebounder, STRONG), Y (width, WEAK - ±100 mm spec), Z (up, STRONG). **x**: fit window duration (ms). **y**: \|axis error\| (mm, log scale). **Series**: A/B/C scatter + median trend; **red dashed ±100 mm spec line in the Y panel only**.
- **Takeaway**: this is where the width-axis spec question is answered visually. In the long stratum, C's Y-median drops below the 100 mm line around ~500-600 ms of observation and stays there. In the short stratum C tracks the line closely from ~200 ms but with a much wider point cloud above it.
- **Verdict**: **report-ready** - `axis_error_long.png` in particular. The spec line drawn only on the axis the spec applies to is the right choice. Same default styling caveat.

### 5.6 `phase1/` and `phase2/` - 2-flight pilot, 2026-07-28 11:35-11:43

| File | Size | Content | Insp. |
|---|---|---|---|
| `phase1/residual_vs_K.png` | 113 KB | residual-vs-K bowls, plain fit | ⚪ |
| `phase1/residual_vs_K_ransac.png` | 138 KB | 3 panels (flight_01 / flight_22 / pooled), x: K (1/mm) · y: full-arc residual RMS (mm); plain vs RANSAC | ✅ |
| `phase1/models_full_arc_residual.png` | 47 KB | A/B/C residual bars, plain | ⚪ |
| `phase1/models_full_arc_residual_ransac.png` | 58 KB | paired bars, x: flight_01 / flight_22 · y: residual RMS (mm), 6 series (A/B/C × plain/RANSAC) | ✅ |
| `phase2/prediction_sweep_flight_01.png` | 163 KB | per-model error vs N | ⚪ |
| `phase2/prediction_sweep_flight_22.png` | 176 KB | per-model error vs N | ⚪ |
| `phase2/prediction_sweep_ransac_flight_01.png` | 190 KB | as below, flight_01 | ⚪ |
| `phase2/prediction_sweep_ransac_flight_22.png` | 223 KB | 3 panels (A/B/C), x: N frames in fit window 3-90 · y: error at target (mm, log); 4 series: plain/RANSAC × label/det | ✅ |
| `phase2/prediction_sweep_ransac_zoom_flight_22.png` | 166 KB | 2 panels (label pts / det pts), x: N 35-55 · y: error (mm, log); 6 series; pink band = known hand-pickup frames 44-47 | ✅ |

- **Takeaway (`models_full_arc_residual_ransac`)**: RANSAC's benefit is not uniform - on flight_22 it cuts model B's residual from ~110 mm to ~46 mm, while on flight_01 it changes almost nothing. RANSAC earns its place on contaminated flights specifically.
- **Takeaway (`prediction_sweep_ransac_zoom_flight_22`)**: the cleanest single demonstration of RANSAC working. On detected points the plain fits (dashed) spike by an order of magnitude exactly across the shaded hand-pickup window, while the RANSAC fits (solid) stay flat through it. On labelled points there is no spike, confirming the contamination is a detector artefact and not real ball motion.
- **Verdict**: all **diagnostic-only** (n=2, superseded by the 158-flight run) **except `prediction_sweep_ransac_zoom_flight_22.png`**, which is genuinely **report-ready** as the visual justification for RANSAC - a population-scale figure cannot show a single confirmed contamination event this clearly.
- One defect: `phase1/residual_vs_K_ransac.png` x-tick labels **overlap into an unreadable run** ("0.000000.000020.00004..."). Needs scientific notation or fewer ticks if used.

### 5.7 `ransac_iterations_sweep/figures/` - the two thesis figures

Source `src/stereo/ransac_sweep_figures.py`, dataviz palette (blue #2a78d6 / red #e34948, CVD-validated). **n = 150 flights, 25 seeds**, fit window 430 ms.

#### `figure1_ransac_wallclock_vs_niterations.png` ✅ - 265 KB · 2026-08-03 19:20
- **x**: n_iterations (categorical: 3, 5, 7, 10, 15, 25). **y**: wall-clock time (ms), 250-2250. Title states **laptop timing**, not Pi.
- **Series**: median (solid, filled) + p95 (dashed, open). Dotted horizontal at 480 ms labelled "hits-regime ceiling*", with a footnote below the axes spelling out that it is an **upper bound, not the true RANSAC allowance** (observation window, triangulation, non-RANSAC fit overhead, comms and unmeasured actuation latency all still need subtracting).
- **Takeaway**: cost is linear at **71.4 ms/iteration**, confirming the theoretical model empirically. Only n_iterations = 3 sits below the 480 ms upper bound at median.
- **Verdict**: **report-ready**. The footnote is the reason - it refuses to overclaim a budget number that has not been derived. Keep it if you re-render.

#### `figure2_ransac_error_vs_niterations.png` ✅ - 156 KB · 2026-08-03 19:20
- **x**: n_iterations (3-25). **y**: final-point prediction error (mm), 125-305.
- **Series**: full population (blue, n=150, median + IQR ribbon) and structurally-unstable subset (red dashed, n=7, median). Legend placed below the axes to avoid the red line.
- **Takeaway**: population median is **flat at ~190 mm across all iteration counts** - buying more iterations buys no accuracy. The 7-flight unstable subset sits at 260-301 mm and stays elevated even at n=25, i.e. it is a separate population, not the tail of the same one.
- **Verdict**: **report-ready**. Together with figure1 this is the complete justification for n_iterations = 3.

#### `figure3_unstable_subset_error_vs_niterations.png` ✅ - 120 KB · 2026-08-03 19:36
- **x**: n_iterations. **y**: final-point prediction error (mm), 150-465. **Series**: the n=7 subset alone, median + IQR.
- **Takeaway**: the IQR band is enormous (~160-460 mm) and essentially constant - these flights are not stabilised by any iteration count.
- **Verdict**: **diagnostic-only** - figure2 already carries this and shows the population contrast that makes it meaningful.

### 5.8 `ransac_distance_threshold_sweep/figures/` - 2026-08-03 19:55

**n = 150 flights × 5 thresholds × 25 seeds** = 18,750 rows attempted, 18,533 succeeded (217 fit-failures concentrated at threshold = 50 mm). n_iterations fixed at 3.

| File | Size | Axes | Insp. |
|---|---|---|---|
| `figure1_threshold_error_population_vs_subset.png` | 183 KB | x: inlier distance threshold (mm) 50-150 · y: final-point error (mm) 185-330 | ✅ |
| `figure2_threshold_jaccard_unstable_subset.png` | 242 KB | x: threshold (mm) · y: mean pairwise Jaccard overlap of accepted-inlier sets across 25 seeds, 0-1 | ✅ |
| `figure3_threshold_inlier_count.png` | 163 KB | x: threshold (mm) · y: mean accepted inlier count, 9.5-24 | ✅ |

- **figure1 takeaway**: population median is flat (~188-197 mm) across the whole 50-150 mm range - threshold barely matters at population level. The n=7 unstable subset shows a shallow minimum right at the production value of 75 mm (260 mm) and degrades either side. Dotted vertical marks production 75 mm.
- **figure2 takeaway**: Jaccard overlap **rises steadily** 0.57 → 0.88 with threshold, with 7 grey per-flight lines behind the red mean. The subtitle states the interpretation rule up front ("rising = threshold was the bottleneck; flat = candidate-pool mechanism") - and it rises, so a looser threshold does stabilise *which points get accepted* even though it does not improve accuracy.
- **figure3 takeaway**: inlier count rises with threshold for both groups, with the unstable subset consistently ~5 points below the population - the mechanistic evidence for the candidate-pool diagnosis.
- **Verdict**: **figure1 report-ready** (it justifies keeping 75 mm). **figure2 and figure3 diagnostic-only** - they support the internal decision-66 argument about *why* the subset is unstable, which is finer detail than an 8,000-word thesis will carry.

---

## 6. `data/flight_binning/` - 2026-07-25 20:41-20:42

Speed/elevation distribution across both gym sessions using the tuned detector. **All five use default matplotlib styling.**

| File | Size | Axes | N | Insp. |
|---|---|---|---|---|
| `distribution_N20.png` | 86 KB | joint scatter + marginal histograms; x: elevation angle (deg, world frame) −30 to +68 · y: speed (m/s) 5.8-11 | 162 flights (121 flagged) | ✅ |
| `distribution_N30.png` | 88 KB | as above, N=30 fit window | 162 flights | ⚪ |
| `distribution_overlay_histograms.png` | 55 KB | 2 panels; x: speed (m/s) 6-11 / elevation (deg) −30 to +68 · y: count | 162 each | ✅ |
| `distribution_N_sensitivity.png` | 108 KB | x: elevation (deg) · y: speed (m/s); each flight a line from its N=20 to its N=30 point | 161 flights with both | ✅ |
| `distribution_by_session.png` | 85 KB | x: elevation (deg) · y: speed (m/s), coloured by session | 126 (07_21) + 36 (07_15) = 162 | ✅ |

- **Series detail (`distribution_N20`)**: blue circles = "ok", red triangles = "flagged (gravity crosscheck / accel)". Marginal histograms on top and right.
- **Takeaway**: the throw population is **strongly bimodal in elevation** - a flat/drive cluster around −15° to +20° and a lob cluster around +40° to +65°, with a near-empty gap at 25-38°. Speed is unimodal ~7-8 m/s and mildly anti-correlated with elevation. This bimodality is the same structure that appears in the launch-to-crossing budget (§4.3-4.4) and is the physical reason the FLAT/MID/LOB stratification exists.
- **`distribution_N_sensitivity`**: most flights move only slightly between N=20 and N=30; a handful move a long way. Supports N=20 being adequate.
- **`distribution_by_session`**: the two sessions overlap thoroughly - no session effect. Useful negative result.
- **Verdict**: all five are **needs redraw** for report use. The content is sound and `distribution_N20` / `distribution_by_session` are the two worth carrying, but they are default-matplotlib and will clash badly with the dataviz-styled Pi/RANSAC figures. Note the flagged fraction is high (121 of 162) - if `distribution_N20` goes in the thesis, the caption must explain what "flagged" means or a reader will read it as 75% bad data.

---

## 7. Calibration / triangulation validation

### 7.1 `data/2026_07_12_session/validation/results/board_frame/` - 2026-07-14 12:15

10 files. Four boards (img_0006, 0026, 0035, 0036) × two extrinsic solutions (2026_07_11_session, 2026_07_12_session).

**`quiver_img_*.png`** (8 files, ~144-150 KB each) ✅ (img_0036/07_11 inspected; other 7 ⚪)
- Two panels. Left: in-plane residual (dx,dy) after similarity fit as a quiver field; **x** = board X (mm along columns) 0-420, **y** = board Y (mm along rows) 0-700; arrows exaggerated 15.7×, coloured by out-of-plane dz with a ±4 mm diverging colourbar. Right: the same dz as a board row × column heatmap (11 × 7 = 77 corners).
- **Takeaway (img_0036, ~4.9 m)**: typical in-plane residual P75 = 2.58 mm, dz within ±4 mm, and the dz heatmap shows a **checkerboard-like alternation with no smooth spatial trend** - i.e. this is per-corner noise, not systematic board warp or a calibration error. That distinction is the whole point of the figure.
- **Verdict**: **report-ready** - `quiver_img_0036_*` is the one to use, since 5 m is the operating stand-off. The arrow-exaggeration factor is stated on the figure, which is essential honesty for a quiver plot.

**`summary_vs_depth_*.png`** (2 files, 92-96 KB) ✅
- **x**: board depth, mean Z (mm, cam0/right frame) 1000-5000. **y**: RMS residual after similarity fit (mm), 0.5-3.0. **Series**: sim_rms_mm (overall scatter) and rms_dz_mm (warp). 4 labelled points.
- **Takeaway**: residual is ~0.7 mm at 2.6 m and rises to ~3.0 mm at 4.9 m. Growth with depth is expected (Z²) and the absolute numbers are 30-100× inside the ±100 mm budget.
- **Verdict**: **report-ready**, though n=4 boards is thin - present it as indicative, and note the y-axis spans only 0.5-3.0 mm so the visual "rise" is 2.3 mm in absolute terms.

### 7.2 `data/2026_07_12_session/validation/results/relative_distance/` - 2026-07-14 12:15

20 files, same 4 boards × 2 extrinsics.

| Group | Count | Size each | Insp. |
|---|---|---|---|
| `hist_img_*.png` | 8 | 69-74 KB | ⚪ |
| `scatter_img_*.png` | 8 | 301-356 KB | ⚪ |
| `summary_error_vs_depth_*.png` | 2 | 84-85 KB | ✅ |
| `summary_planeresidual_vs_depth_*.png` | 2 | 70-72 KB | ⚪ |

- **`summary_error_vs_depth`**: **x**: board depth, mean Z (mm) 1000-5000. **y**: corner-pair distance error (mm), −4 to +3.5. **Series**: bias (signed mean) and scatter (std), 4 labelled points, zero line dotted.
- **Takeaway**: this is the **accuracy/bias** measurement that board-frame Kabsch cannot give (Kabsch re-centres, so its per-axis bias is ~0 by construction). Bias swings from −0.7 mm at 1 m through +2.5 mm at 4.2 m to −4.1 mm at 4.9 m; scatter rises monotonically 0.8 → 3.3 mm. Quote precision from board-frame and accuracy from here, never the other way round.
- **Verdict**: `summary_error_vs_depth_*` **report-ready** (with the n=4 caveat - the bias sign flip between the last two boards is not a trend you can lean on). The 16 per-board hist/scatter files are **diagnostic-only**.

### 7.3 `data/2026_07_11_gym_session/world_registration/triangulated_scatter.png` ✅
- 262 KB · 2026-07-11 18:50
- 3D scatter. **x/y/z**: X / Y / Z (mm, cam0/right camera frame), spanning ~−3000 to +2000 / 0 to 5000 / 2000 to 7000. **Series**: 8 labelled registration points (P1-P7, P9, P10), solid line along the court-line chain, dashed drop lines.
- Title explicitly says **"Blunder check only - NOT the floor-frame transform"**.
- **Takeaway**: the clicked registration points form a plausible straight chain with no gross outlier - it catches a mis-click, nothing more.
- **Verdict**: **diagnostic-only**, and the title correctly says so. Do not present it as a registration-accuracy figure; the 88 mm registration-error story lives in the numbers, not here.

---

## 8. Sync correction

### 8.1 `sync_residual_vs_flight.png` (2 files) ✅ (07_21 inspected, 07_15 ⚪)
- `data/2026_07_15_gym/` 43 KB · 2026-07-16 14:26 · `data/2026_07_21_gym/` 61 KB · 2026-07-25 15:21
- **x**: flight index (0-150). **y**: stereo sync residual (ms), −8.5 to +8.5. **Series**: single scatter, one point per flight.
- **Takeaway**: a beautiful **sawtooth** - residual drifts linearly downward across ~55-75 consecutive flights then jumps back up. That is free-running clock drift accumulating within a capture run and resetting at each restart, and it is bounded within ±8.5 ms (the sync tolerance). Not noise; a fully explained mechanism.
- **Verdict**: **report-ready**. It is the clearest empirical evidence for the free-running-sync decision (§4.3) and the sawtooth makes the mechanism self-evident. Add the ±8.5 ms tolerance as a horizontal band if you re-render.

### 8.2 `data/sync_correction_validation/` (7 files, 38-48 KB, 2026-07-25 15:33) ⚪
### 8.3 `data/sync_correction_validation_tuned_detections/` (8 files, 63-85 KB, 2026-07-25 21:07) ✅ (flight_60 inspected, 7 others ⚪)
- Filenames `flight_{5,20,50,60,92,100,110,120}_shift.png`. The untuned set lacks flight_50; the tuned set has all 8.
- Two panels (cam0, cam1). **x**: u (px), **y**: v (px, inverted so image-down is chart-down). **Series**: raw detections (red) and sync-corrected detections (blue), overlaid.
- **Takeaway (flight_60)**: in cam0 the raw and corrected tracks **coincide exactly** (red fully hidden under blue) while in cam1 there is a visible along-track offset - consistent with the correction being applied to one camera against the other as reference.
- **Verdict**: **diagnostic-only**, both sets. They are per-flight spot-checks confirming the correction ran, at a sample of 7-8 flights. The tuned set supersedes the untuned one.

---

## 9. Per-flight analysis renders (`2026_07_15_gym/.../flight_01/analysis_*`) ⚪ except where noted

14 plot figures under `data/2026_07_15_gym/ball_flights/2 ball contacts ground before plane/flight_01/`. **n = 1 flight** throughout.

- `analysis_1/`, `analysis_2/`, `analysis_3/`: `mag_hist.png` (29-31 KB) + `per_axis.png` (118-159 KB) - three iterations of the same pair, 2026-07-16 to 2026-07-20.
- `analysis_4/` (2026-07-20 19:08): `sweep_error_vs_N.png` ✅ (103 KB), `trajectory_3d.png` (542 KB), `trajectory_3d_camera_frame.png` (546 KB), `trajectory_side.png` (156 KB), `trajectory_side_camera_frame.png` (166 KB), `world_frame_registered_3d.png` (504 KB), `world_frame_registered_3d_2.png` (526 KB), `world_frame_registered_side.png` ✅ (145 KB).

- **`sweep_error_vs_N.png`** ✅: **x**: N (frames in fit window) 3-25, with a **secondary top axis** showing t_extrap (ms) counting down 400→0. **y**: prediction error at target (mm, log). **Series**: curve A = fit on labelled points (model floor) and curve B = fit on detected points (end-to-end). Error falls from ~4×10⁴ mm at N=3 to ~50 mm at N=24; curve B sits above curve A through the mid-range, and the gap between them is the detection penalty.
- **`world_frame_registered_side.png`** ✅: three panels at N=3 / 14 / 24 with the error in each panel title (38095 / 253 / 53 mm). **x**: world x (mm), **y**: world y (mm). **Series**: labelled arc (grey dots, ground truth), fit + extrapolation (blue), fit window (open circles), target (green star), prediction (red ×). At N=3 the extrapolation shoots off to x = −15000 mm and misses entirely; by N=24 the × sits on the star.
- **Verdict**: all **diagnostic-only** - single flight, and superseded by the 158-flight population work. `world_frame_registered_side.png` is the exception worth considering: it is a genuinely good **explanatory** figure for showing a non-specialist reader what "fit N frames then extrapolate" means and why small N fails. If used, relabel it - the panels are model B, and it is one hand-picked flight.

---

## 10. Missing from disk

Two figures are named in the worklogs as having been rendered, but are **not present**:

| Referenced file | Referenced in | Status |
|---|---|---|
| `data/flight_binning/distribution_N5.png` | `2026-07-25_flight_velocity_angle_binner_worklog.md` L383, L949, L1240 | **absent** |
| `data/flight_binning/distribution_N10.png` | same log, L383, L950, L1241 | **absent** |

The log shows them plotted twice - once at 15:53 against the stale untuned detector output (`analysis_3`), and again at 16:04 after the re-run. The surviving files in that folder are `distribution_N20` / `distribution_N30`, both stamped 20:41, i.e. the N grid moved from 5/10 to 20/30 in a later pass and the N5/N10 renders did not survive it. **No result depends on them** - the N-sensitivity question they were built for is answered by `distribution_N_sensitivity.png` at N=20 vs N=30. Not worth regenerating.

Everything else referenced in the worklogs resolves to a file on disk, including `figure4_velocity_error_by_axis.png` (blocked at the 2026-08-05 12:35 checkpoint, then produced at 12:45 after the per-axis Pi re-run; on disk stamped 13:15).

Also checked and **present**: `sync_residual_vs_flight.png` for both sessions, all four `sweep3_exp*_gain4.0_cam*_ballcrops.png`, all `figure{1,2,3}` / `figure{1,2,3,4}` sets named in the task.

---

## 11. Image sets excluded (counts only)

Not catalogued individually, per your instruction. Listed so the totals reconcile.

### `data/detector_tuning/` contact sheets - 4 stages

| Stage | Sheets | Total size | Rendered |
|---|---|---|---|
| `01_round2_mask_v3_trajectory_filter` | 20 | 565 MB | 2026-07-23 17:42-17:45 |
| `02_area30_circ0.3` | 20 | 565 MB | 2026-07-24 10:27-10:30 |
| `03_stride1_thresh16_openk3_area30_circ0.3` | 326 | 8.6 GB | 2026-07-24 11:14-11:23 |
| `12_rect_close_kernel_validation` | 326 | 8.6 GB | 2026-08-03 15:38-15:44 |

Stages 01/02 are the 10-flight spread sample × 2 cameras. Stages 03/12 are the full 163 flights × 2 cameras = 326, matching the labelled-final-point count. The numbering gap (04-11) is sweep-iteration numbering - no `04`-`11` folder is referenced anywhere in the worklogs, so nothing is missing.

### `data/detector_tuning/` inspection crops - 2 stages
`round2_mask_v3_trajectory_filter` 16 crops / 443 KB (2026-07-23); `area30_circ0.3` 18 crops / 495 KB (2026-07-24).

### Everything else
~102,600 raw or rendered images: flight frames, per-flight contact renders in the session directories, checkerboard and registration captures, corner-debug overlays, exposure-sweep ball crops, and mono-cam sample frames.
