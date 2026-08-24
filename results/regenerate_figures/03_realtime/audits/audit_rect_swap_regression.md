# Rect close-kernel swap — regression audit

Read-only. No figures. Generated 2026-08-24 20:53 by `src/regen_2class/audit_rect_swap_regression.py`.

**Result: PASS.** All seven claims reproduce from source; neither stop
condition fired.

The swap under audit is `MORPH_ELLIPSE` -> `MORPH_RECT` for the 30x30
morph-close structuring element, everything else in the config held fixed.
It buys a large Pi speedup and costs accuracy at both the detection and the
prediction level. Both costs are quantified below.

## 1. Source CSVs

| Role | Path | Rows |
|---|---|---:|
| Ellipse baseline, per flight | `results/detector_tuning/candidate_config_validated_results.csv` | 166 (163 flights + 3 trailer) |
| Rect variant, per flight | `results/detector_tuning/candidate_config_rect_close_results.csv` | 166 (163 flights + 3 trailer) |
| Paired detection delta | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | 163 |
| Downstream prediction delta | `results/trajectory_fit_comparison/rect_vs_ellipse_kernel/rect_vs_ellipse_prediction_comparison.csv` | 163 |
| Downstream pooled summary | `results/trajectory_fit_comparison/rect_vs_ellipse_kernel/pooled_summary.csv` | 3 |
| Headline ledger | `results/detector_tuning/history/results_history.csv` | 12 |

The three detection CSVs name **identical flight sets** (`True`), so the
comparison is paired rather than two independent runs.

The two per-flight CSVs each carry **three trailer rows** — `AVERAGE`,
`LABELED_RECALL (flight_01 + flight_22)` and `CONFIG` — which is why they
are 166 lines for 163 flights. Those rows are excluded from every
per-flight statistic here and read only for the headline rates.

## 2. Definition of the per-flight delta

**Detection level**, from `rect_vs_ellipse_comparison.csv`:

    delta_pp = round((rect_combined_rate - ellipse_combined_rate) * 100, 2)

Verified against the two source CSVs for all 163 flights: **0 arithmetic
mismatches**, **0 rate-copy mismatches**. Sign convention: **negative =
rect is worse**.

**Downstream level**, from `rect_vs_ellipse_prediction_comparison.csv`:

    delta_mm = round(rect_error_mm - ellipse_error_mm, 2)

Verified for all 157 paired flights: **0 mismatches**. The sign convention
is the opposite in meaning to `delta_pp`: **positive = rect is worse**,
because the quantity is an error, not a rate.

## 3. Headline rates (V1, V2)

| Metric | Ellipse | Rect | Delta |
|---|---:|---:|---:|
| Combined detection rate (`AVERAGE`) | 96.67% | 94.52% | -2.15 pp |
| True detection rate (`LABELED_RECALL`) | 92.50% | 88.75% | -3.75 pp |

V1 (96.7% -> 94.5%): **verified**. V2 (92.5% -> 88.8%): **verified** — 88.8 is 88.75
rounded to one decimal.

One precision point worth stating, because "96.7%" is ambiguous on its own:
`AVERAGE` is the **unweighted mean of the 163 per-flight rates** (0.966747 /
0.945236), *not* the pooled points ratio. Pooled over all detections the same
swap reads 96.26% -> 93.83% (10639/11052 -> 10370/11052), a **-2.43 pp** move rather
than -2.15 pp. Both are defensible; they are not the same number.

The denominator is identical in both arms (11052 processable points), so no
part of the drop comes from a changed population.

The true rate is measured on the two labelled flights only
(`flight_01` + `flight_22`, 240 points). `flight_22` is itself one of the
worst-regressing flights at -9.89 pp, which is why the labelled recall falls
further (-3.75 pp) than the all-flight mean (-2.15 pp).

## 4. Per-flight detection bands (V3, V4, V5)

| Band | Count | Claim | Verdict |
|---|---:|---:|:--:|
| worse by more than 2 pp (`delta_pp < -2.00`) | 83 | 83 | match |
| better by more than 2 pp (`delta_pp > +2.00`) | 12 | 12 | match |
| better by 2 pp or more (`delta_pp >= +2.00`) | 13 | 13 | match |

The 12/13 split is a single flight sitting exactly on the boundary:
**`2026_07_21_gym/flight_69` at `delta_pp = +2.00`**. It is the only flight at the threshold, so
"12 better" (strict `>`) and "13 better" (inclusive `>=`) are both correct
readings of the same file; they differ only in whether the boundary counts.

`flagged_regression = YES` appears on **83** rows, exactly matching the
strict worse-than-2 pp count — so the CSV's own flag uses the strict `<`
convention on the losing side.

The ledger's prose in `results_history.csv` says *"only 13 improved >2pp"*.
Recomputed strictly, that is **12**; the prose counts the boundary flight
under a `>` sign that should be `>=`. Off by one flight, which is inside
this audit's tolerance and does not trip the stop condition — but the
ledger sentence is imprecise as written.

Extremes, for context:

| Worst | pp | Best | pp |
|---|---:|---|---:|
| `2026_07_15_gym/flight_17` | -10.23 | `2026_07_21_gym/flight_70` | +4.88 |
| `2026_07_15_gym/flight_22` | -9.89 | `2026_07_21_gym/flight_61` | +4.76 |
| `2026_07_21_gym/flight_2` | -9.67 | `2026_07_21_gym/flight_89` | +4.17 |
| `2026_07_21_gym/flight_50` | -9.30 | `2026_07_15_gym/flight_50` | +3.58 |
| `2026_07_21_gym/flight_63` | -9.09 | `2026_07_21_gym/flight_97` | +2.71 |

Widespread, not localised: 83 of 163 flights (51%) lose more than 2 pp.

## 5. Downstream prediction error (V6, V7)

### The exact median shift, with sign

Two different quantities are both callable "the median shift", and they
differ by more than an order of magnitude. Stating both:

| Quantity | Value |
|---|---:|
| **Median of the per-flight deltas** (`median(delta_mm)`) | **+0.44 mm** |
| Shift in the pooled median (`median(rect) - median(ellipse)`) | +11.20 mm |
| Mean of the per-flight deltas | +8.90 mm |
| Pooled median, ellipse | 179.34 mm |
| Pooled median, rect | 190.54 mm |

The claimed 0.4 mm is the **first** of these: the median per-flight delta,
**+0.44 mm**, positive meaning rect is worse. That is also the value carried
in `pooled_summary.csv`'s `delta(rect-ellipse)` row (0.44), confirmed here to
be the median of deltas and **not** the difference of the two medians: True.

V6: **verified**.

Reading it correctly matters. A +0.44 mm median shift sounds negligible, and
as a *typical-flight* statement it is: 80 flights get worse and 77 get
better, close to a coin flip. But the mean delta is +8.90 mm and the pooled
median moves +11.20 mm, because the damage is concentrated in a tail rather
than spread across the population.

### The regressing tail (V7)

**7 of 157** flights regress by 250 mm or more:

| Flight | delta (mm) |
|---|---:|
| `2026_07_21_gym/flight_51` | +865.67 |
| `2026_07_21_gym/flight_125` | +425.97 |
| `2026_07_21_gym/flight_37` | +378.21 |
| `2026_07_21_gym/flight_121` | +370.46 |
| `2026_07_21_gym/flight_22` | +332.34 |
| `2026_07_21_gym/flight_44` | +274.67 |
| `2026_07_15_gym/flight_17` | +255.35 |

Range **255.35 to 865.67 mm**, matching the claimed 250-866 band. V7: **verified**.

## 6. Why the populations are 163 and 157

Both levels start from the **same 163 flights** — the detection ids and the
downstream ids are the same set (True). The downstream CSV also carries all
163 rows. The drop to 157 happens inside that file, and is fully explained
by its own `status` / `reason` columns:

| Excluded | n | Reason recorded in the file |
|---|---:|---|
| `fit_failed` | 1 | ransac_fit: no candidate model reached >= min_samples (8) inliers over 15 iterations |
| `skipped` | 5 | missing final-point label (one or both cams) |

    163 flights - 5 skipped - 1 fit_failed = 157

The excluded flights, by name:

- `2026_07_21_gym/flight_41` — fit_failed
- `2026_07_15_gym/flight_13` — skipped
- `2026_07_21_gym/flight_50` — skipped
- `2026_07_21_gym/flight_74` — skipped
- `2026_07_21_gym/flight_80` — skipped
- `2026_07_21_gym/flight_88` — skipped

Critically, **both arms exclude the identical set** (True): no flight is `ok`
under ellipse and failed under rect or vice versa. So the 157-flight
comparison is properly paired, and the exclusions are a property of the
labelling and the RANSAC fit — missing final-point labels, and one flight
where no candidate model reached the minimum sample count — not a
consequence of the kernel swap. The swap cost no flight its fit.

S2 (population explainable from file contents): **satisfied**.

## 7. Migration note — 24 Aug `data/` -> `results/`

The ledger row that carries these headline numbers still records its
artifacts under `data/`:

| Recorded path | State | Resolves at |
|---|---|---|
| `data/detector_tuning/candidate_config_rect_close_results.csv` | **dangling** | `results/detector_tuning/candidate_config_rect_close_results.csv` |
| `data/detector_tuning/rect_vs_ellipse_comparison.csv` | **dangling** | `results/detector_tuning/rect_vs_ellipse_comparison.csv` |
| `data/detector_tuning/contact_sheets/12_rect_close_kernel_validation/` | OK | — |
| `src/image_processing/02_adjacent_frame_differencing/12_run_full_dataset_rect_close_kernel.py` | OK | — |

2 of 4 dangle; 2 resolve one-for-one under `results/`. Note the
migration was **partial** — `contact_sheets/` stayed behind under
`data/detector_tuning/`, so some recorded paths still resolve as written
while their siblings do not. Every source CSV this audit reads was
located under `results/`, not at the path the ledger names.

## 8. Verdicts

| Check | Claimed | Found | Verdict |
|---|---|---|:--:|
| population | 163 | 163 | pass |
| V1 combined 96.7->94.5 | 96.7 -> 94.5 | 96.7 -> 94.5 | pass |
| V2 true 92.5->88.8 | 92.5 -> 88.8 | 92.5 -> 88.8 | pass |
| V3 83 worse >2pp | 83 | 83 | pass |
| V4 12 better >2pp | 12 | 12 | pass |
| V5 13 better >=2pp | 13 | 13 | pass |
| downstream population | 157 | 157 | pass |
| V6 median shift 0.4 mm | 0.4 | +0.44 | pass |
| V7 7 regress 250-866mm | 7 | 7 | pass |

Stop conditions: **S1** (any count off by more than one flight) — not triggered.
**S2** (157 population unexplainable) — not triggered.

