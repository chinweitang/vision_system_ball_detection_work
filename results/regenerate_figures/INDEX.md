# INDEX — `results/regenerate_figures/`

Generated 2026-08-24. Read-only survey: nothing was moved, renamed or deleted.

76 files across the root directory and 11 subfolders. The **Produced by** column
was resolved by grepping `src/` for the literal output path, then (where the path
is assembled from an `OUT_DIR` constant plus an f-string) for the basename and the
f-string stem. `NOT_FOUND` means no script in `src/` writes the path. The **Read by**
column lists other files under `src/` or `results/` that open the file as an input;
a file merely *named in a docstring* is not counted as a read (see notes).

All paths in the tables are relative to `results/regenerate_figures/`; a subfolder
of `.` means the file sits in that directory root. All scripts are under
`src/regen_2class/`.

> ⚠ **One conflict found — reported, not resolved.** `figureA_margin_vs_cutoff.png`
> is written by two different scripts to the same path. See [Conflict](#conflict-one-path-two-producing-scripts).

---

## 1. Files grouped by producing script

### `src/regen_2class/step_3_join.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `two_class_join.csv` | `.` | 553.8 KB | 2026-08-24 11:32 | `step_3_join.py` | common.py (defines load_join); stage_timing_breakdown.py, step9_figure_a_combined.py, step10_chaos_outcome_sweep.py, step11_panel_size_sensitivity.py, step12_chaos_sweep_3criterion.py, step13_chaos_sweep_4criterion.py, step13_chaos_sweep_landing_error.py, step15_figure_c_duration_v2.py, step16_large_text_figures.py, step17_print_size_figures.py, step_4_figure_a_margin.py, step_5_figure_b_convergence.py, step_6_figure_c_duration.py, step_7_figure_d_outcome.py |

### `src/regen_2class/step_4_figure_a_margin.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureA_margin_vs_cutoff.png` | `.` | 169.8 KB | 2026-08-24 11:32 | `step_4_figure_a_margin.py` ⚠ | — |

### `src/regen_2class/step_5_figure_b_convergence.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureB_excluded_counts.csv` | `.` | 2.1 KB | 2026-08-24 11:32 | `step_5_figure_b_convergence.py` | — |
| `figureB_position_error_convergence.png` | `.` | 174.7 KB | 2026-08-24 11:32 | `step_5_figure_b_convergence.py` | — |

### `src/regen_2class/step_6_figure_c_duration.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureC_duration_distribution.png` | `.` | 131.3 KB | 2026-08-24 11:32 | `step_6_figure_c_duration.py` | — |

### `src/regen_2class/step_7_figure_d_outcome.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureD_outcome_sweep.png` | `.` | 182.5 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |
| `figureD_outcome_sweep_170mm.png` | `.` | 180.3 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |
| `outcome_sweep_by_class_T.csv` | `.` | 2.1 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |
| `outcome_sweep_by_class_T_170mm.csv` | `.` | 2.1 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |
| `outcome_sweep_per_flight.csv` | `.` | 340.4 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |
| `outcome_sweep_per_flight_170mm.csv` | `.` | 340.3 KB | 2026-08-24 11:32 | `step_7_figure_d_outcome.py` | — |

### `src/regen_2class/step8_timing_convergence.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureE_timing_convergence.png` | `.` | 163.8 KB | 2026-08-24 11:32 | `step8_timing_convergence.py` | — |
| `label_vs_modelc_timing.csv` | `.` | 1.6 KB | 2026-08-24 11:32 | `step8_timing_convergence.py` | — |
| `timing_convergence_by_class_T.csv` | `.` | 3.0 KB | 2026-08-24 11:32 | `step8_timing_convergence.py` | — |

### `src/regen_2class/step9_figure_a_combined.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureA_margin_vs_cutoff.png` | `.` | 169.8 KB | 2026-08-24 11:32 | `step9_figure_a_combined.py` ⚠ | — |
| `figureA_thresholds.csv` | `.` | 302 B | 2026-08-24 11:32 | `step9_figure_a_combined.py` | — |

### `src/regen_2class/step10_chaos_outcome_sweep.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `chaos_outcome_by_class_A.csv` | `.` | 1006 B | 2026-08-24 11:31 | `step10_chaos_outcome_sweep.py` | — |
| `chaos_outcome_cooccurrence.csv` | `.` | 2.5 KB | 2026-08-24 11:31 | `step10_chaos_outcome_sweep.py` | — |
| `chaos_outcome_sensitivity_100_vs_150.csv` | `.` | 339 B | 2026-08-24 11:31 | `step10_chaos_outcome_sweep.py` | — |
| `figureF_chaos_outcome_sweep.png` | `.` | 275.8 KB | 2026-08-24 11:31 | `step10_chaos_outcome_sweep.py` | — |
| `figureG_velocity_by_axis_twoclass.png` | `.` | 218.7 KB | 2026-08-21 15:00 | `step10_chaos_outcome_sweep.py` | — |

### `src/regen_2class/step11_panel_size_sensitivity.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `panel_size_sensitivity.csv` | `.` | 1.2 KB | 2026-08-24 11:31 | `step11_panel_size_sensitivity.py` | — |

### `src/regen_2class/step12_chaos_sweep_3criterion.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figure_h_chaos_3criterion.csv` | `.` | 2.4 KB | 2026-08-24 11:31 | `step12_chaos_sweep_3criterion.py` | — |
| `figure_h_chaos_3criterion.png` | `.` | 284.4 KB | 2026-08-24 11:31 | `step12_chaos_sweep_3criterion.py` | — |

### `src/regen_2class/step13_chaos_sweep_4criterion.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `bands_by_class_A_window_primary.csv` | `01_chaos_4criterion/` | 5.8 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `bands_by_class_A_window_sensitivity.csv` | `01_chaos_4criterion/` | 5.8 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `comparison_3crit_vs_4crit.csv` | `01_chaos_4criterion/` | 489 B | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `figure_chaos_4criterion_primary.png` | `01_chaos_4criterion/` | 309.1 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `figure_chaos_4criterion_sensitivity.png` | `01_chaos_4criterion/` | 341.3 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `operating_points_primary.csv` | `01_chaos_4criterion/` | 1.4 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |
| `operating_points_sensitivity.csv` | `01_chaos_4criterion/` | 1.4 KB | 2026-08-24 11:31 | `step13_chaos_sweep_4criterion.py` | — |

### `src/regen_2class/step13_chaos_sweep_landing_error.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `bands_by_class_A_window_1000mm.csv` | `02_chaos_landing_error/` | 6.9 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `bands_by_class_A_window_500mm.csv` | `02_chaos_landing_error/` | 6.8 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `comparison_three_schemes.csv` | `02_chaos_landing_error/` | 562 B | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `figure_chaos_landing_error_1000mm.png` | `02_chaos_landing_error/` | 271.0 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `figure_chaos_landing_error_500mm.png` | `02_chaos_landing_error/` | 273.8 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `operating_points_1000mm.csv` | `02_chaos_landing_error/` | 1.2 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `operating_points_500mm.csv` | `02_chaos_landing_error/` | 1.2 KB | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |
| `separate_vs_combined_500.csv` | `02_chaos_landing_error/` | 196 B | 2026-08-24 11:31 | `step13_chaos_sweep_landing_error.py` | — |

### `src/regen_2class/step14_flight_binning_n30_replot.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `distribution_N30_uniform_markers.png` | `.` | 100.7 KB | 2026-08-24 11:32 | `step14_flight_binning_n30_replot.py` | — |

### `src/regen_2class/step15_figure_c_duration_v2.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureC_duration_distribution_v2.png` | `.` | 157.4 KB | 2026-08-24 11:32 | `step15_figure_c_duration_v2.py` | — |

### `src/regen_2class/step16_large_text_figures.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureD_outcome_sweep_large.png` | `.` | 265.8 KB | 2026-08-24 11:32 | `step16_large_text_figures.py` | — |
| `figure_chaos_landing_error_500mm_large.png` | `02_chaos_landing_error/` | 433.6 KB | 2026-08-24 11:32 | `step16_large_text_figures.py` | — |

### `src/regen_2class/step17_print_size_figures.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figureB_position_error_convergence_print.png` | `.` | 188.0 KB | 2026-08-24 11:32 | `step17_print_size_figures.py` | — |
| `figureD_outcome_sweep_print.png` | `.` | 181.0 KB | 2026-08-24 11:32 | `step17_print_size_figures.py` | — |
| `figureG_velocity_by_axis_twoclass_print.png` | `.` | 313.9 KB | 2026-08-24 11:32 | `step17_print_size_figures.py` | — |
| `figure_chaos_landing_error_500mm_print.png` | `02_chaos_landing_error/` | 265.7 KB | 2026-08-24 11:32 | `step17_print_size_figures.py` | — |

### `src/regen_2class/build_iteration_rows.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `iteration_rows.md` | `.` | 19.0 KB | 2026-08-24 11:31 | `build_iteration_rows.py` | — |

### `src/regen_2class/detection_improvement_figure.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `detection_improvement.png` | `detection_improvement/` | 499.6 KB | 2026-08-24 11:31 | `detection_improvement_figure.py` | — |
| `detection_improvement_rows.csv` | `detection_improvement/` | 2.0 KB | 2026-08-24 11:31 | `detection_improvement_figure.py` | — |

### `src/regen_2class/detection_improvement_v2.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `detection_improvement_v2.csv` | `detection_improvement_v2/` | 1.4 KB | 2026-08-24 11:55 | `detection_improvement_v2.py` | — |
| `detection_improvement_v2.png` | `detection_improvement_v2/` | 363.2 KB | 2026-08-24 11:55 | `detection_improvement_v2.py` | — |

### `src/regen_2class/detection_improvement_v3.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `detection_improvement_v3.csv` | `detection_improvement_v3/` | 721 B | 2026-08-24 14:42 | `detection_improvement_v3.py` | — |
| `detection_improvement_v3.png` | `detection_improvement_v3/` | 165.1 KB | 2026-08-24 14:42 | `detection_improvement_v3.py` | — |

### `src/regen_2class/ellipse_vs_rect_resolution.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `ellipse_vs_rect_resolution.txt` | `.` | 8.2 KB | 2026-08-24 11:31 | `ellipse_vs_rect_resolution.py` | — |

### `src/regen_2class/model_comparison_pooled.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `model_comparison_pooled.csv` | `model_comparison_pooled/` | 14.8 KB | 2026-08-24 16:17 | `model_comparison_pooled.py` | — |
| `model_comparison_pooled.png` | `model_comparison_pooled/` | 409.9 KB | 2026-08-24 16:17 | `model_comparison_pooled.py` | — |

### `src/regen_2class/plain_drag_sweep.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `plain_drag_sweep.csv` | `plain_drag_sweep/` | 475.5 KB | 2026-08-24 16:25 | `plain_drag_sweep.py` | ransac_effect_pooled.py, ransac_effect_tail.py |
| `plain_drag_sweep_summary.txt` | `plain_drag_sweep/` | 831 B | 2026-08-24 16:26 | `plain_drag_sweep.py` | — |

### `src/regen_2class/ransac_effect_pooled.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `ransac_effect_pooled.csv` | `ransac_effect_pooled/` | 2.4 KB | 2026-08-24 16:29 | `ransac_effect_pooled.py` | ransac_effect_tail.py (cross-check) |
| `ransac_effect_pooled.png` | `ransac_effect_pooled/` | 197.4 KB | 2026-08-24 16:29 | `ransac_effect_pooled.py` | — |
| `ransac_effect_pooled_summary.txt` | `ransac_effect_pooled/` | 2.1 KB | 2026-08-24 16:29 | `ransac_effect_pooled.py` | — |

### `src/regen_2class/ransac_effect_flight22.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `ransac_effect_flight22.csv` | `ransac_effect_flight22/` | 3.9 KB | 2026-08-24 17:53 | `ransac_effect_flight22.py` | — |
| `ransac_effect_flight22.png` | `ransac_effect_flight22/` | 453.4 KB | 2026-08-24 17:53 | `ransac_effect_flight22.py` | — |

### `src/regen_2class/ransac_effect_tail.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `ransac_effect_p95.png` | `ransac_effect_tail/` | 180.5 KB | 2026-08-24 17:50 | `ransac_effect_tail.py` | — |
| `ransac_effect_tail.csv` | `ransac_effect_tail/` | 3.0 KB | 2026-08-24 17:50 | `ransac_effect_tail.py` | — |
| `ransac_effect_tail.png` | `ransac_effect_tail/` | 181.3 KB | 2026-08-24 17:50 | `ransac_effect_tail.py` | — |
| `ransac_effect_tail_summary.txt` | `ransac_effect_tail/` | 4.3 KB | 2026-08-24 17:50 | `ransac_effect_tail.py` | — |

### `src/regen_2class/ransac_implementation.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `ransac_implementation.txt` | `.` | 6.6 KB | 2026-08-24 16:04 | `ransac_implementation.py` | — |

### `src/regen_2class/reconcile_detection_rates.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `detection_rates_reconciled.txt` | `.` | 5.2 KB | 2026-08-24 11:31 | `reconcile_detection_rates.py` | — |

### `src/regen_2class/stage_timing_breakdown.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `figure_stage_timing_breakdown.png` | `stage_timing/` | 516.7 KB | 2026-08-24 11:31 | `stage_timing_breakdown.py` | — |
| `stage_timing_by_class_window.csv` | `stage_timing/` | 8.7 KB | 2026-08-24 11:31 | `stage_timing_breakdown.py` | — |

### `src/regen_2class/sweep_effects.py`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `sweep_effects.txt` | `.` | 4.4 KB | 2026-08-24 11:56 | `sweep_effects.py` | — |

### `NOT_FOUND` — no producing script in `src/`

| File | Subfolder | Size | Modified | Produced by | Read by |
|---|---|---|---|---|---|
| `drag_coefficient_check.txt` | `.` | 11.3 KB | 2026-08-24 16:40 | **NOT_FOUND** | — |
| `label_derived_classification.csv` | `.` | 2.4 KB | 2026-08-20 20:46 | **NOT_FOUND** | — |
| `sweep_ranges_and_baseline.txt` | `.` | 10.1 KB | 2026-08-24 14:02 | **NOT_FOUND** | — |
| `which_kernel_offline.txt` | `.` | 12.6 KB | 2026-08-24 12:04 | **NOT_FOUND** | — |

---

## 2. Archiving candidates

### 2a. No identified producer (`NOT_FOUND`)

Four files. No script anywhere under `src/` writes these paths — checked against
the full path, the basename, and every f-string stem that could assemble them.

| File | Subfolder | Size | Modified | What the search found instead |
|---|---|---|---|---|
| `drag_coefficient_check.txt` | `.` | 11.3 KB | 2026-08-24 16:40 | Named only in `claude/claude_logs/2026-08-24_1250_drag_coefficient_check.md`, which records it as "the report" — written directly by that session, not by a committed script. |
| `label_derived_classification.csv` | `.` | 2.4 KB | 2026-08-20 20:46 | Named only in `claude/claude_logs/2026-08-20_2043_label_derived_classification.md` and `claude/prompts/2026-08-20_2043_newfigures.md`, both of which give its path as `data/regenerate_figures/…`, not `results/…`. Written directly by that session. |
| `sweep_ranges_and_baseline.txt` | `.` | 10.1 KB | 2026-08-24 14:02 | No occurrence anywhere in `src/` or `claude/` — not even a prose mention. |
| `which_kernel_offline.txt` | `.` | 12.6 KB | 2026-08-24 12:04 | No occurrence anywhere in `src/` or `claude/` — not even a prose mention. |

These four cannot be regenerated by re-running anything in `src/`. Treat them as
originals, not as reproducible outputs.

### 2b. Not read by anything

Only three files in this tree are inputs to other code:

| File | Read by |
|---|---|
| `two_class_join.csv` | 14 scripts, via `common.load_join()` and one direct open in `step_6_figure_c_duration.py` |
| `plain_drag_sweep/plain_drag_sweep.csv` | `ransac_effect_pooled.py`, `ransac_effect_tail.py` |
| `ransac_effect_pooled/ransac_effect_pooled.csv` | `ransac_effect_tail.py` (cross-check) |

The remaining **73 files have no reader**. That is the expected shape for this
directory — these are terminal report deliverables (figures, companion CSVs,
written analyses), so "no reader" on its own is not evidence a file is dead. The
useful signal is *no reader **and** no producer*, which is section 2a's four files.
Full list of the 73, grouped by location:

**(root)**

- `chaos_outcome_by_class_A.csv`
- `chaos_outcome_cooccurrence.csv`
- `chaos_outcome_sensitivity_100_vs_150.csv`
- `detection_rates_reconciled.txt`
- `distribution_N30_uniform_markers.png`
- `drag_coefficient_check.txt`
- `ellipse_vs_rect_resolution.txt`
- `figureA_margin_vs_cutoff.png`
- `figureA_thresholds.csv`
- `figureB_excluded_counts.csv`
- `figureB_position_error_convergence.png`
- `figureB_position_error_convergence_print.png`
- `figureC_duration_distribution.png`
- `figureC_duration_distribution_v2.png`
- `figureD_outcome_sweep.png`
- `figureD_outcome_sweep_170mm.png`
- `figureD_outcome_sweep_large.png`
- `figureD_outcome_sweep_print.png`
- `figureE_timing_convergence.png`
- `figureF_chaos_outcome_sweep.png`
- `figureG_velocity_by_axis_twoclass.png`
- `figureG_velocity_by_axis_twoclass_print.png`
- `figure_h_chaos_3criterion.csv`
- `figure_h_chaos_3criterion.png`
- `iteration_rows.md`
- `label_derived_classification.csv`
- `label_vs_modelc_timing.csv`
- `outcome_sweep_by_class_T.csv`
- `outcome_sweep_by_class_T_170mm.csv`
- `outcome_sweep_per_flight.csv`
- `outcome_sweep_per_flight_170mm.csv`
- `panel_size_sensitivity.csv`
- `ransac_implementation.txt`
- `sweep_effects.txt`
- `sweep_ranges_and_baseline.txt`
- `timing_convergence_by_class_T.csv`
- `which_kernel_offline.txt`

**01_chaos_4criterion**

- `bands_by_class_A_window_primary.csv`
- `bands_by_class_A_window_sensitivity.csv`
- `comparison_3crit_vs_4crit.csv`
- `figure_chaos_4criterion_primary.png`
- `figure_chaos_4criterion_sensitivity.png`
- `operating_points_primary.csv`
- `operating_points_sensitivity.csv`

**02_chaos_landing_error**

- `bands_by_class_A_window_1000mm.csv`
- `bands_by_class_A_window_500mm.csv`
- `comparison_three_schemes.csv`
- `figure_chaos_landing_error_1000mm.png`
- `figure_chaos_landing_error_500mm.png`
- `figure_chaos_landing_error_500mm_large.png`
- `figure_chaos_landing_error_500mm_print.png`
- `operating_points_1000mm.csv`
- `operating_points_500mm.csv`
- `separate_vs_combined_500.csv`

**detection_improvement**

- `detection_improvement.png`
- `detection_improvement_rows.csv`

**detection_improvement_v2**

- `detection_improvement_v2.csv`
- `detection_improvement_v2.png`

**detection_improvement_v3**

- `detection_improvement_v3.csv`
- `detection_improvement_v3.png`

**model_comparison_pooled**

- `model_comparison_pooled.csv`
- `model_comparison_pooled.png`

**plain_drag_sweep**

- `plain_drag_sweep_summary.txt`

**ransac_effect_flight22**

- `ransac_effect_flight22.csv`
- `ransac_effect_flight22.png`

**ransac_effect_pooled**

- `ransac_effect_pooled.png`
- `ransac_effect_pooled_summary.txt`

**ransac_effect_tail**

- `ransac_effect_p95.png`
- `ransac_effect_tail.csv`
- `ransac_effect_tail.png`
- `ransac_effect_tail_summary.txt`

**stage_timing**

- `figure_stage_timing_breakdown.png`
- `stage_timing_by_class_window.csv`

---

## 3. Apparent duplicates and superseded versions

Flagged only. Nothing here was moved, renamed or deleted, and none of it is a
recommendation — several of these pairs are deliberate variants that both belong
in the report.

### 3a. Version chains — later version supersedes earlier

| Chain | Files | Evidence |
|---|---|---|
| Detection improvement, 3 generations | `detection_improvement/detection_improvement.png` + `.csv` → `detection_improvement_v2/detection_improvement_v2.png` + `.csv` → `detection_improvement_v3/detection_improvement_v3.png` + `.csv` | `detection_improvement_v3.py`'s docstring lists five changes from v2 and states "NEW — v1's and v2's files are untouched". Each generation has its own script and its own folder, so all three still regenerate. v3 (2026-08-24 14:42) is the current one. |
| Figure C duration | `figureC_duration_distribution.png` → `figureC_duration_distribution_v2.png` | `step15_figure_c_duration_v2.py` is a replot of frozen `two_class_join.csv` data and prints "original figureC_duration_distribution.png left untouched". The v1 is retained on purpose. |
| Chaos sweep verdict | `figure_h_chaos_3criterion.png` + `.csv` → `01_chaos_4criterion/` (7 files) | `step13_chaos_sweep_4criterion.py`'s docstring argues directly against the three-criterion version ("WHY POSITION RETURNS AS A PASS CRITERION"). `comparison_3crit_vs_4crit.csv` recomputes the 3-criterion numbers internally rather than reading `figure_h_chaos_3criterion.csv`, so the 4-criterion set does not depend on the older files. |

### 3b. Render variants of the same figure — not duplicates

Same numbers, different canvas. Produced by dedicated scripts that import the
original figure's module rather than reimplementing it, so the base figure is a
dependency of the variant's *script*, not a stale copy.

| Base figure | `_large` (step16) | `_print` (step17) |
|---|---|---|
| `figureD_outcome_sweep.png` | `figureD_outcome_sweep_large.png` | `figureD_outcome_sweep_print.png` |
| `02_chaos_landing_error/figure_chaos_landing_error_500mm.png` | `…_500mm_large.png` | `…_500mm_print.png` |
| `figureB_position_error_convergence.png` | — | `figureB_position_error_convergence_print.png` |
| `figureG_velocity_by_axis_twoclass.png` | — | `figureG_velocity_by_axis_twoclass_print.png` |

### 3c. Sensitivity / threshold pairs — both are results, not duplicates

Named alike but computed at different thresholds; discarding either loses the
sensitivity analysis.

| Pair | Difference |
|---|---|
| `figureD_outcome_sweep.png` / `_170mm.png`, `outcome_sweep_by_class_T.csv` / `_170mm.csv`, `outcome_sweep_per_flight.csv` / `_170mm.csv` | `step_7_figure_d_outcome.py` runs twice: `ACCURATE_MM_MAIN = 200.0` (headline, no suffix) and `ACCURATE_MM_SENS = 170.0` (sensitivity). |
| `01_chaos_4criterion/…_primary.*` / `…_sensitivity.*` | Two threshold variants of the four-criterion verdict, tags `primary` and `sensitivity`. |
| `02_chaos_landing_error/…_500mm.*` / `…_1000mm.*` | Two landing-error budgets, tags `500mm` and `1000mm`. |
| `chaos_outcome_sensitivity_100_vs_150.csv` | A sensitivity comparison in its own right, not a copy of `chaos_outcome_by_class_A.csv`. |

### 3d. The four drag / `ransac_effect_*` folders — a chain, not four copies

Four sibling folders with overlapping names, written over one afternoon. They are
sequential stages, and the later ones read the earlier ones, so archiving an
earlier folder breaks a later script:

| Folder | Produced by | Reads |
|---|---|---|
| `plain_drag_sweep/` (16:25) | `plain_drag_sweep.py` | — |
| `ransac_effect_pooled/` (16:29) | `ransac_effect_pooled.py` | `plain_drag_sweep/plain_drag_sweep.csv` |
| `ransac_effect_tail/` (17:50) | `ransac_effect_tail.py` | `plain_drag_sweep/plain_drag_sweep.csv`, `ransac_effect_pooled/ransac_effect_pooled.csv` |
| `ransac_effect_flight22/` (17:53) | `ransac_effect_flight22.py` | neither — reads `results/trajectory_fit_comparison/phase2/` and raw flight data directly |

`ransac_implementation.txt` (16:04) sits at the head of this chain: it is what
`plain_drag_sweep.py` cites as its rationale, though it does not read it.

### 3e. Basename collisions across subfolders

Distinct files that share a filename. They only collide if the tree is ever
flattened — worth knowing before any move.

| Basename | Both live at | Produced by |
|---|---|---|
| `bands_by_class_A_window_*.csv` | `01_chaos_4criterion/` (`_primary`, `_sensitivity`) and `02_chaos_landing_error/` (`_500mm`, `_1000mm`) | `step13_chaos_sweep_4criterion.py` / `step13_chaos_sweep_landing_error.py` — same f-string, different `OUT_DIR` and different tags |
| `operating_points_*.csv` | same two folders, same tag split | same two scripts, same pattern |

---

## Conflict: one path, two producing scripts

**Stopping here rather than guessing.** One output path is written by two
different scripts:

    results/regenerate_figures/figureA_margin_vs_cutoff.png

| Script | Line | Statement |
|---|---|---|
| `src/regen_2class/step_4_figure_a_margin.py` | [20](src/regen_2class/step_4_figure_a_margin.py#L20) | `FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"` — docstring: "Writes figureA_margin_vs_cutoff.png at 150 dpi." |
| `src/regen_2class/step9_figure_a_combined.py` | [31](src/regen_2class/step9_figure_a_combined.py#L31) | `FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"` — docstring: "Overwrites results/regenerate_figures/figureA_margin_vs_cutoff.png. No second figure" |

`step9`'s docstring says it deliberately overwrites `step_4`'s output, so the two
are probably a supersession rather than an accident — but the on-disk copy
(2026-08-24 11:32) carries no marker of which script last wrote it, and both
scripts are still present and runnable. The file is listed under **both** scripts
in section 1 and marked ⚠. Not resolved.

---

## Notes on method

- Three grep passes over `src/`, in order: the literal full path; the basename;
  the f-string stem for paths assembled as `OUT_DIR` plus an f-string. A file was
  only attributed to a script after reading the matching line, not on the filename
  match alone.
- **Prose mentions are not reads.** Two cases were excluded on this basis:
  `plain_drag_sweep.py` cites `ransac_implementation.txt` in a docstring rationale
  but never opens it; `step15_figure_c_duration_v2.py` names
  `figureC_duration_distribution.png` only to say it leaves it untouched.
- **Re-renders are not reads.** `step16_large_text_figures.py` and
  `step17_print_size_figures.py` import the producing modules
  (`step13_chaos_sweep_landing_error`, `step_7_figure_d_outcome`, …) and redraw
  from data; they never open the original PNGs.
- **A summary naming its own siblings is not a read.** The `*_summary.txt` files
  cite the CSV and PNG their own script wrote alongside them.
- `detection_improvement_v3.py` honours a `DETECTION_IMPROVEMENT_V3_OUT`
  environment override; the path indexed here is its default.
- `step_1_classes.py` and `step_2_deadlines.py` write nothing to disk — they only
  print — so neither appears as a producer.
- **The tree changed during the scan.** The first pass saw 70 files; a second pass
  after section 1 was written saw 76. The six additions are `ransac_effect_tail/`
  (4 files, 17:50) and `ransac_effect_flight22/` (2 files, 17:53), together with
  their two new scripts in `src/regen_2class/`. Nothing was removed. This index
  reflects the 76-file state and was rebuilt from it, not patched.
- Repo-wide recursive grep over the working tree times out (OneDrive-backed, large
  data directories). Searches were scoped to `src/`, `results/` and `claude/`. A
  producer living outside those three trees would have been missed.
