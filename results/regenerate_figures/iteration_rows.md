# Iteration rows

Fragment-style rows: **Trigger | Change | Measured effect | Cost accepted**.

Every number below was extracted from a CSV on disk by `src/regen_2class/build_iteration_rows.py`; none is typed in by hand. Bracketed markers key to the source list at the end, and the per-row provenance blocks give the exact row and column. Any value not locatable in a CSV is `NOT_FOUND` and is listed under UNRESOLVED.

## 1. Morph close kernel ELLIPSE -> RECT

| | |
|---|---|
| **Trigger** | Detection cost 89.39 ms/frame/cam against the 16.6 ms 60 fps budget - 5.4x over[S1]. The breakdown put 84.051 ms of the 86.66 ms mask cost in morph-close alone[S1]. |
| **Change** | `cv2.MORPH_ELLIPSE` -> `cv2.MORPH_RECT` for the close kernel, size held at 30x30. Shape only; threshold, open kernel, exclusion and the trajectory filter unchanged. |
| **Measured effect** | Mask cost 86.66 -> 7.38 ms per frame (morph-close 84.051 -> 4.768 ms, 17.6x)[S1], median over n=448 pairs. Accuracy on the full 163-flight set: combined rate 0.9667 -> 0.9452, labelled recall 0.925 -> 0.8875[S2][S3]. |
| **Cost accepted** | **-2.15 pp mean combined rate, and it is widespread, not isolated**: 83 of 163 flights regressed >2 pp against only 12 improved (13 if the boundary flight at exactly +2.00 pp, 2026_07_21_gym/flight_69, is counted - which is how the history row's '13 improved' arises), worst -10.23 pp (2026_07_15_gym/flight_17)[S3]. Accepted for the real-time path because detection was the binding constraint; the detector-tuning history records the same change as NOT RECOMMENDED for production[S2]. |

## 2. RANSAC n_iterations 15 -> 3

| | |
|---|---|
| **Trigger** | RANSAC-wrapped Model-C fit measured at 335.3-1175.3 ms across 8 flights, against a 480 ms actuation budget - over budget on the longer flights[S1]. The bare single-shot fit was only 21.9-101.2 ms[S1], so the iteration count, not the fit, was the cost. |
| **Change** | `n_iterations` 15 -> 3 for Model C in the Pi sweep path (`N_ITERATIONS = 3`). Inlier threshold, min samples and seed unchanged. |
| **Measured effect** | **NOT_FOUND** - no CSV records a RANSAC-wrapped Model-C fit timed at 3 iterations. The nearest CSV quantity is the production sweep's `ransac_ms` (median 162.6 ms, max 338.2 ms over n=2481)[S4], but that wraps ALL four LSQ fits over 107 flights, so it is not the same measurement and is not presented as the after-value. |
| **Cost accepted** | NOT_FOUND - the accuracy cost of dropping to 3 iterations is not quantified in any CSV on disk. |

## 3. Serial -> threaded detection

| | |
|---|---|
| **Trigger** | Detection at 88.66-89.80 ms/frame/cam serial, over the 16.6 ms cadence[S1]. Both cameras were detected one after the other despite being independent. |
| **Change** | cam0 and cam1 detected concurrently on two `threading.Thread`s per frame pair, joined before triangulation. Two threads, one per camera. |
| **Measured effect** | Threaded per-pair detect: median 13.71 ms, p95 15.11 ms, max 19.22 ms over n=2481 pairs[S4] - inside the 16.667 ms cadence. **Before-value NOT_FOUND**: the only serial figure in a CSV was measured with the ellipse kernel, so it cannot separate threading from row 1's kernel change. |
| **Cost accepted** | NOT_FOUND as a CSV number. The speedup attributable to threading alone is not recorded in any CSV; the 6 over-cadence frames and the thermal drift note live in a .txt, not a CSV. |

## 4. min_area 200 -> 30

| | |
|---|---|
| **Trigger** | At the baseline min_area=200 / min_circ=0.3 the pipeline reached only combined rate 0.8552 and labelled recall 0.8125[S5] - small ball signatures were being discarded by the area floor. |
| **Change** | `min_area` 200 -> 30 at min_circ held at 0.30, chosen from a 24-combo min_area x min_circ grid[S5]. |
| **Measured effect** | Combined rate 0.8552 -> 0.9751, labelled recall 0.8125 -> 0.9208[S5], on 10 flights with recall over flight_01 + flight_22 (240 points)[S2]. Both metrics improve, so this is the cleanest single-variable win in the set - min_circ is fixed and the row is flagged `is_baseline=True` in the grid. |
| **Cost accepted** | More false-positive surface downstream: the looser floor raised the artifact-audit hotspot count and forced the mask v4 round (row 6). 2 of 24 grid combos failed the recall gate outright[S5], so the area floor could not simply be dropped without checking recall. |

## 5. Trajectory-coherence filter added

| | |
|---|---|
| **Trigger** | The tuned candidate config scored combined rate 0.8740 at recall 0.9259[S6], but that rate was inflated by false positives - static scene artifacts were being counted as detections. |
| **Change** | `filter_trajectory_outliers` added: reject points implying more than max_speed=80 px/frame, and require a run of at least min_run=2 coherent frames. |
| **Measured effect** | Combined rate 0.8740 -> 0.7549 at recall 0.9259 -> 0.9259, on 10 flights[S2]. The rate FALLS by design: the filter removes counted-but-wrong detections, and recall is unchanged, so the drop is false positives leaving. The audit it enabled pooled 1143 rejected points into 13 spatial bins[S7], which is what located the static artifacts. |
| **Cost accepted** | Headline combined rate moved -11.91 pp on a number that was measuring false positives, at zero recall cost. **Confounded**: this history row bundles mask v2 with the filter, so the two cannot be separated - and its per-flight source is recorded as `NOT RECOVERABLE (original CSV overwritten before this history file existed - see worklog prose)`[S2]. |

## 6. Exclusion masks added

| | |
|---|---|
| **Trigger** | The trajectory-filter audit localised rejected points onto a handful of fixed image regions - a wall corner, an exit sign and a light fixture - reappearing across many flights[S7]. |
| **Change** | `exclusion_mask.py` zones, applied inside `compute_mask`: v2 (cam0 wall-corner only) -> v3 (4 zones) -> v4 (12 zones)[S2]. |
| **Measured effect** | v2 -> v3: combined rate 0.7549 -> 0.8552 at recall 0.9259 unchanged[S2]. v3 -> v4 read at a FIXED min_area=30 so it does not absorb row 4: 0.9751 -> 0.9784 combined, 0.9208 -> 0.925 recall[S5][S2]. Audit hotspots 13 -> 9 bins and 126 -> 42 pooled points[S8][S9]. |
| **Cost accepted** | Hand-drawn, scene-specific zones: the masks are tied to these two gym setups and do not transfer. Diminishing returns were explicit - the remaining 9 bins are edge spillover of objects already masked[S9], and refinement was stopped rather than driven to zero. |

---

## Sources

- **[S1]** `results/pi_benchmarking/history/timing_history.csv`
- **[S2]** `results/detector_tuning/history/results_history.csv`
- **[S3]** `results/detector_tuning/rect_vs_ellipse_comparison.csv`
- **[S4]** `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv`
- **[S5]** `results/detector_tuning/sweep_results_min_area_circ.csv`
- **[S6]** `results/detector_tuning/sweep_results.csv`
- **[S7]** `results/detector_tuning/inspection_crops/round2_mask_v3_trajectory_filter/artifact_audit_hotspots.csv`
- **[S8]** `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots_premaskfix.csv`
- **[S9]** `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots.csv`

## Value-level provenance

| row | value | number | file | locator |
|---|---|---|---|---|
| 1 | `ell_total` | 86.66 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `ell_close` | 84.051 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `rect_total` | 7.38 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `rect_close` | 4.768 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `factor` | 17.6 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `npairs` | 448 | `results/pi_benchmarking/history/timing_history.csv` | row stage='compute_mask breakdown...', column headline_numbers |
| 1 | `cadence` | 16.6 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 1 | `overrun` | 5.4 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 1 | `ell_comb` | 0.9667 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-25 (FULL 163-FLIGHT DATASET), avg_combined_rate |
| 1 | `ell_rec` | 0.925 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-25 (FULL 163-FLIGHT DATASET), labeled_recall |
| 1 | `rect_comb` | 0.9452 | `results/detector_tuning/history/results_history.csv` | row date=2026-08-03 (rect close kernel validation), avg_combined_rate |
| 1 | `rect_rec` | 0.8875 | `results/detector_tuning/history/results_history.csv` | row date=2026-08-03 (rect close kernel validation), labeled_recall |
| 1 | `n_flights` | 163 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | row count |
| 1 | `mean_delta` | -2.15 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | mean of delta_pp |
| 1 | `regressed` | 83 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | count delta_pp < -2 |
| 1 | `improved` | 12 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | count delta_pp > +2 |
| 1 | `improved_ge` | 13 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | count delta_pp >= +2 |
| 1 | `boundary` | 2026_07_21_gym/flight_69 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | flight(s) with delta_pp exactly +2.00 |
| 1 | `flagged` | 83 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | count flagged_regression == YES |
| 1 | `worst` | -10.23 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | min delta_pp |
| 1 | `worst_f` | 2026_07_15_gym/flight_17 | `results/detector_tuning/rect_vs_ellipse_comparison.csv` | flight at min delta_pp |
| 2 | `r15` | 335.3-1175.3 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 2 | `bare` | 21.9-101.2 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 2 | `budget` | 480 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 2 | `n_st1` | 8 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end...', column n_flights |
| 2 | `r3` | NOT_FOUND | - | - |
| 2 | `adj_med` | 162.6 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | median of ransac_ms, status=='ok' |
| 2 | `adj_max` | 338.2 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | max of ransac_ms, status=='ok' |
| 2 | `adj_n` | 2481 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | count of status=='ok' rows |
| 3 | `thr_med` | 13.71 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | median of last_pair_detect_ms, status=='ok' |
| 3 | `thr_p95` | 15.11 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | p95 of last_pair_detect_ms, status=='ok' |
| 3 | `thr_max` | 19.22 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | max of last_pair_detect_ms |
| 3 | `thr_n` | 2481 | `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` | count of status=='ok' rows |
| 3 | `serial_ellipse` | 88.66-89.80 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 3 | `serial_mean` | 89.39 | `results/pi_benchmarking/history/timing_history.csv` | row stage='Stage 1 - end-to-end pipeline baseline...', column headline_numbers |
| 3 | `serial_rect` | NOT_FOUND | - | - |
| 4 | `b_comb` | 0.8552 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=200,min_circ=0.3, avg_combined_rate |
| 4 | `b_rec` | 0.8125 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=200,min_circ=0.3, labeled_recall |
| 4 | `a_comb` | 0.9751 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=30,min_circ=0.3, avg_combined_rate |
| 4 | `a_rec` | 0.9208 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=30,min_circ=0.3, labeled_recall |
| 4 | `is_base` | True | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=200,min_circ=0.3, is_baseline |
| 4 | `n_combos` | 24 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row count |
| 4 | `n_gate_fail` | 2 | `results/detector_tuning/sweep_results_min_area_circ.csv` | count meets_recall_gate != True |
| 4 | `n_flights` | 10 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-24 (round 3 sweep), n_flights |
| 4 | `rec_pop` | flight_01 + flight_22 (240 points) | `results/detector_tuning/history/results_history.csv` | row date=2026-07-24 (round 3 sweep), labeled_recall_flights |
| 5 | `b_comb` | 0.8740 | `results/detector_tuning/sweep_results.csv` | row stride=1,diff_threshold=16,open_kernel=3, avg_combined_rate |
| 5 | `b_rec` | 0.9259 | `results/detector_tuning/sweep_results.csv` | row stride=1,diff_threshold=16,open_kernel=3, labeled_recall |
| 5 | `a_comb` | 0.7549 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), avg_combined_rate |
| 5 | `a_rec` | 0.9259 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), labeled_recall |
| 5 | `n_flights` | 10 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), n_flights |
| 5 | `rec_pop` | flight_01 only (54 points) | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), labeled_recall_flights |
| 5 | `artifacts` | NOT RECOVERABLE (original CSV overwritten before this his... | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), artifacts |
| 5 | `delta_pp` | -11.91 | `results/detector_tuning/sweep_results.csv + results/detector_tuning/history/results_history.csv` | avg_combined_rate difference between the two rows above |
| 5 | `v3_bins` | 13 | `results/detector_tuning/inspection_crops/round2_mask_v3_trajectory_filter/artifact_audit_hotspots.csv` | row count |
| 5 | `v3_points` | 1143 | `results/detector_tuning/inspection_crops/round2_mask_v3_trajectory_filter/artifact_audit_hotspots.csv` | sum of total_points |
| 6 | `v2_comb` | 0.7549 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v2 + trajectory filter), avg_combined_rate |
| 6 | `v3_comb` | 0.8552 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v3 (4 zones) + trajectory filter), avg_combined_rate |
| 6 | `v3_rec` | 0.9259 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v3 (4 zones) + trajectory filter), labeled_recall |
| 6 | `v3_at30` | 0.9751 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=30,min_circ=0.3, avg_combined_rate |
| 6 | `v3_at30_rec` | 0.9208 | `results/detector_tuning/sweep_results_min_area_circ.csv` | row min_area=30,min_circ=0.3, labeled_recall |
| 6 | `v4_comb` | 0.9784 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-24 (mask v4, 10-FLIGHT SAMPLE), avg_combined_rate |
| 6 | `v4_rec` | 0.925 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-24 (mask v4, 10-FLIGHT SAMPLE), labeled_recall |
| 6 | `pre_bins` | 13 | `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots_premaskfix.csv` | row count |
| 6 | `post_bins` | 9 | `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots.csv` | row count |
| 6 | `pre_points` | 126 | `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots_premaskfix.csv` | sum of total_points |
| 6 | `post_points` | 42 | `results/detector_tuning/inspection_crops/area30_circ0.3/artifact_audit_hotspots.csv` | sum of total_points |
| 6 | `v3_zones` | 4 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-23 (candidate + mask v3 (4 zones) + trajectory filter), stage |
| 6 | `v4_zones` | 12 | `results/detector_tuning/history/results_history.csv` | row date=2026-07-24 (mask v4, 10-FLIGHT SAMPLE), stage |

---

## UNRESOLVED

2 value(s) could not be located in any CSV and are emitted as `NOT_FOUND` rather than estimated.

**RANSAC-wrapped Model-C fit time at n_iterations=3**

- Why: no CSV on disk records this quantity. timing_history.csv stops at the 15-iteration stage-1 baseline and its own notes say 'RANSAC n_iterations sweep still pending (Task 2)'.
- Known to exist outside CSV: the production sweep at n_iterations=3 exists only as pipeline_sweep_raw.csv's ransac_ms, which is a DIFFERENT quantity - it wraps all four LSQ fits, not the Model-C RANSAC fit alone, and covers 107 flights rather than stage 1's 8

**serial per-pair detection time at the RECT close kernel**

- Why: no CSV isolates threading from the kernel change. The only serial detection number in a CSV (timing_history.csv stage 1) was measured with the ELLIPSE kernel, so serial-vs-threaded cannot be read off it without also absorbing the 17.6x kernel speedup.
- Known to exist outside CSV: results/pi_benchmarking/parallel_detect_checkpoint_20260804.json and the derived '1.27x vs serial' line in results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/summary.txt - neither is a CSV

---

## Caveats carried from the sources

- **Recall populations differ between rows.** Rows 5 and 6's v2/v3 figures use `flight_01 only (54 points)`; rows 4 and 6's v4 figures use `flight_01 + flight_22 (240 points)`. Recall is NOT comparable across that boundary.
- **Flight populations differ between rows.** Rows 4, 5 and 6 are 10-flight numbers; row 1's accuracy is the full 163-flight set. Only compare within a row.
- **Row 5 is confounded** - the history bundles mask v2 with the trajectory filter in a single entry, and its per-flight CSV is recorded as not recoverable.
- **Row 6's v3 -> v4 step is read at fixed min_area=30** so it does not double-count row 4. The history's own v3 -> v4 comparison (0.8552 -> 0.9784) changes min_area at the same time and is not used here.
- **Hotspot point totals** are the sum of `total_points` over the bins each audit CSV lists. The history prose quotes different totals (181 -> 86) for a wider population of rejected points; that wider count is not in these CSVs and is not reproduced.

