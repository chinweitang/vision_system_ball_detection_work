# Figure captions

Every caption that was previously drawn onto a figure canvas under
`results/regenerate_figures/`, collected here so it can be typeset in the
document instead.

Each entry gives the original (captioned) PNG, the caption-free `_clean.png`
rendered at 0.8 textwidth / 300 dpi, and the caption text.

**These are generated files.** They come from each script's own caption list
via `clean_figures.write_clean()`, so they cannot drift from the figures. To
refresh, re-run the scripts with `--clean` and then
`python src/regen_2class/build_captions_md.py`.

30 figures. 5 of them never had a caption drawn on the canvas.

---

## `01_chaos_4criterion/figure_chaos_4criterion_primary.png`

- clean render: `01_chaos_4criterion/figure_chaos_4criterion_primary_clean.png`
- caption file: `01_chaos_4criterion/figure_chaos_4criterion_primary.caption.txt`

> Position is a pass criterion again. v_out = e*v_in + (1+e)*u carries no rotation term, so outgoing VELOCITY is independent of contact location - but the ball departs from wherever it was struck, so a
> crossing-position error translates the whole return trajectory by the same amount. Position error and velocity error displace the SAME landing point in the SAME frame and both come from the same Model-C fit
> on the same detected points, so they are correlated in source and add LINEARLY; quadrature would assume an independence that does not hold.
> Total landing-error budget 1000 mm at the player, split EQUALLY between the two terms - a stated budget choice, not a derived result: no physical basis favours either term, and over a 1 s return a static
> offset and an accumulated velocity error are directly commensurable. Position term 500 mm. Velocity term 500 mm / (e x t) with e = 0.68 (published volleyball-on-rigid-surface coefficient of
> restitution, not assumed) and t = 1.0 s -> 735 mm/s applied isotropically to all three world axes.
> position_error_mm and the per-axis velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.
> Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration). Verdict precedence
> first-match-wins: no_response, late, wrong_class, wrong_position, wrong_velocity, success. Where several windows tie at the maximum success rate the LATEST is selected; position never influences that maximisation.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.

## `01_chaos_4criterion/figure_chaos_4criterion_sensitivity.png`

- clean render: `01_chaos_4criterion/figure_chaos_4criterion_sensitivity_clean.png`
- caption file: `01_chaos_4criterion/figure_chaos_4criterion_sensitivity.caption.txt`

> Position is a pass criterion again. v_out = e*v_in + (1+e)*u carries no rotation term, so outgoing VELOCITY is independent of contact location - but the ball departs from wherever it was struck, so a
> crossing-position error translates the whole return trajectory by the same amount. Position error and velocity error displace the SAME landing point in the SAME frame and both come from the same Model-C fit
> on the same detected points, so they are correlated in source and add LINEARLY; quadrature would assume an independence that does not hold.
> Total landing-error budget 500 mm at the player, split EQUALLY between the two terms - a stated budget choice, not a derived result: no physical basis favours either term, and over a 1 s return a static
> offset and an accumulated velocity error are directly commensurable. Position term 250 mm. Velocity term 250 mm / (e x t) with e = 0.68 (published volleyball-on-rigid-surface coefficient of
> restitution, not assumed) and t = 1.0 s -> 368 mm/s applied isotropically to all three world axes.
> position_error_mm and the per-axis velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.
> Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration). Verdict precedence
> first-match-wins: no_response, late, wrong_class, wrong_position, wrong_velocity, success. Where several windows tie at the maximum success rate the LATEST is selected; position never influences that maximisation.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.
> THIS IS A REPORTED SENSITIVITY, NOT THE REQUIREMENT. At a 500 mm total budget the velocity tolerance falls to 368 mm/s, but the Y_width label SD is ~282 mm/s (decision 77),
> so a 368 mm/s isotropic tolerance sits at roughly 1.3x the reference noise floor on the weak axis and the test stops being informative there.

## `02_chaos_landing_error/figure_chaos_landing_error_1000mm.png`

- clean render: `02_chaos_landing_error/figure_chaos_landing_error_1000mm_clean.png`
- caption file: `02_chaos_landing_error/figure_chaos_landing_error_1000mm.caption.txt`

> landing_error = |dp| + e*|dv|*t, e = 0.68, t = 1.0 s. A total landing-error allowance at the player of 1000 mm. Because the budget is not split between the two terms, a flight with small
> position error may spend the whole allowance on velocity, corresponding to 1471 mm/s - 5.2x the ~282 mm/s Y_width label SD, so the test remains above the reference noise floor on the
> weak axis. Position and velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.
> |dp| is the crossing-position error magnitude; it is a two-component in-plane distance and that IS its 3D magnitude, because both the predicted and reference crossing points lie on the plane by construction.
> Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration).
> Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_placement, success. Where several windows tie at the maximum success rate the LATEST is selected; landing error never influences that maximisation.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.

## `02_chaos_landing_error/figure_chaos_landing_error_500mm.png`

- clean render: `02_chaos_landing_error/figure_chaos_landing_error_500mm_clean.png`
- caption file: `02_chaos_landing_error/figure_chaos_landing_error_500mm.caption.txt`

> landing_error = |dp| + e*|dv|*t, e = 0.68, t = 1.0 s. A total landing-error allowance at the player of 500 mm. Because the budget is not split between the two terms, a flight with small
> position error may spend the whole allowance on velocity, corresponding to 735 mm/s - 2.6x the ~282 mm/s Y_width label SD, so the test remains above the reference noise floor on the
> weak axis. Position and velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.
> |dp| is the crossing-position error magnitude; it is a two-component in-plane distance and that IS its 3D magnitude, because both the predicted and reference crossing points lie on the plane by construction.
> Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration).
> Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_placement, success. Where several windows tie at the maximum success rate the LATEST is selected; landing error never influences that maximisation.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.

## `02_chaos_landing_error/figure_chaos_landing_error_500mm_large.png`

- clean render: `02_chaos_landing_error/figure_chaos_landing_error_500mm_large_clean.png`
- caption file: `02_chaos_landing_error/figure_chaos_landing_error_500mm_large.caption.txt`

> landing_error = |dp| + e*|dv|*t, e = 0.68, t = 1.0 s. A total landing-error allowance at the player of 500 mm.
> Because the budget is not split between the two terms, a flight with small position error may spend the whole allowance on velocity,
> corresponding to 735 mm/s - 2.6x the ~282 mm/s Y_width label SD, so the test remains above the reference noise floor on the weak axis.
> Position and velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.
> |dp| is the crossing-position error magnitude; it is a two-component in-plane distance and that IS its 3D magnitude, because both the
> predicted and reference crossing points lie on the plane by construction.
> Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's
> +84 ms after. t_obs = min(observation window, duration). Verdict precedence first-match-wins: no_response, late, wrong_class,
> wrong_placement, success. Where several windows tie at the maximum success rate the LATEST is selected.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum
> launch-to-crossing time. A = 72 / 135 / 220 ms are panel tilt moves of 2, 10 and 30 degrees.

## `02_chaos_landing_error/figure_chaos_landing_error_500mm_print.png`

- clean render: `02_chaos_landing_error/figure_chaos_landing_error_500mm_print_clean.png`
- caption file: `02_chaos_landing_error/figure_chaos_landing_error_500mm_print.caption.txt`

> *No caption was drawn on this figure's canvas, so there is none to
> extract. The `_clean.png` differs from the original only in size.*

## `detection_improvement/detection_improvement.png`

- clean render: `detection_improvement/detection_improvement_clean.png`
- caption file: `detection_improvement/detection_improvement.caption.txt`

> Markers only - NO interpolation. The stages are discrete configuration changes, so the x positions are ordinal, not a time axis,
> and a line between two of them would assert a path through configurations that were never run.
> FOUR PANELS BECAUSE THE DENOMINATORS DIFFER. Values may only be compared WITHIN a panel, never across panels:
>   combined rate is a 10-flight sample mean in panel 1 and a 163-flight mean in panel 2;
>   recall is over 54 labelled points (flight_01 only) in panel 3 and 240 points (flight_01 + flight_22) in panel 4.
> The two splits are NOT the same partition: the '+ mask v4 + area30 (sample)' stage carries a 10-flight combined rate but an
> already-240-point recall, so the recall denominator changes one stage earlier than the flight population does.
> ELLIPSE (diamond) and RECT (square) mark the only genuinely like-for-like pair in the file - same 163 flights, same 240 points,
> differing only in the morphological close-kernel shape. Every other adjacent pair also changes config, population or both.
> Dashes on the lower edge mark stages this panel has no value for - sweep and audit rows record no rate, and a row measured on one
> denominator is absent from the other's panel. An empty slot means not measured here, not measured as zero.
> Source: results/detector_tuning/history/results_history.csv, read-only, plotted in the file's own row order. Values in the companion CSV.

## `detection_improvement_v2/detection_improvement_v2.png`

- clean render: `detection_improvement_v2/detection_improvement_v2_clean.png`
- caption file: `detection_improvement_v2/detection_improvement_v2.caption.txt`

> Markers only - NO lines. The stages are discrete configuration changes, so the x positions are ordinal, not a time axis, and a
> line between two of them would assert a path through configurations that were never run. Stages with no marker recorded no rate.
> DENOMINATORS CHANGE PART-WAY ALONG BOTH SERIES, so neither series is a like-for-like comparison end to end:
>   average combined detection rate is measured on a 10-flight validation sample up to and including '+ mask v4 + area30 (sample)',
>   and on all 163 flights from 'full dataset 163 flights' onward. The step between those two is a change of
>   population, not a change in performance.
>   true detection rate is measured over 54 labelled points on one flight before the round 3 sweep, and 240 labelled
>   points on two flights after it.
> The rect close-kernel stage is excluded from this figure.
> Source: results/detector_tuning/history/results_history.csv, read-only, plotted in the file's own row order.

## `detection_improvement_v3/detection_improvement_v3.png`

- clean render: `detection_improvement_v3/detection_improvement_v3_clean.png`
- caption file: `detection_improvement_v3/detection_improvement_v3.caption.txt`

> combined rate is measured on the validation sample at stages 4-8 and on all 163 flights at stage 9.
> true detection rate is 54 labelled points on one flight at stages 4-7 and 240 points on two flights at stages 8-9.

## `distribution_N30_uniform_markers.png`

- clean render: `distribution_N30_uniform_markers_clean.png`
- caption file: `distribution_N30_uniform_markers.caption.txt`

> *No caption was drawn on this figure's canvas, so there is none to
> extract. The `_clean.png` differs from the original only in size.*

## `figure_h_chaos_3criterion.png`

- clean render: `figure_h_chaos_3criterion_clean.png`
- caption file: `figure_h_chaos_3criterion.caption.txt`

> Position is NOT a pass criterion here. The impulse axis translates the panel along its surface normal at uniform velocity, so return direction is set by the commanded panel angle and return
> speed by the translation velocity - neither depends on where on the surface contact occurs. Crossing position governs only WHETHER contact occurs, which hit_miss_match already tests. Figure F's
> wrong_position band counted that same requirement a second time. Position accuracy is reported as a capability in the companion CSV, not as pass/fail.
> Chaos rally requires the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A. Target mode's test allowed +84 ms AFTER arrival; the sign is opposite and deliberate.
> Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_velocity, success. Bands stack bottom to top as success, wrong_velocity, wrong_class, late, no_response, matching Figure D.
> Where several observation windows achieve the maximum success rate, the latest is selected: reliability is at ceiling across the plateau, so a longer window reduces crossing position error at no cost to success.
> Velocity tolerance is isotropic placement: 1471 mm/s on all three world axes, from 1.0 m / (0.68 x 1.0 s). Velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT ground truth.
> fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72 / 135 / 220 ms are panel tilt moves of 2, 10 and 30 degrees.

## `figureA_margin_vs_cutoff.png`

- clean render: `figureA_margin_vs_cutoff_clean.png`
- caption file: `figureA_margin_vs_cutoff.caption.txt`

> Margin above zero is the time remaining after the prediction is ready and before the ball arrives: the budget available for actuation, read by chaos rally. Margin below zero means the
> answer lands after impact, which target mode tolerates provided the display fires inside the perceptual window. Actuation band edges correspond to panel tilt moves of 2, 10 and 30 degrees
> for a 2 m x 2 m, 20 kg panel rotating about its centre line at 350 Nm output torque, triangular velocity profile, plus 20 ms lumped command and settling.
> margin_p95 = deadline - observation window - p95 latency; deadline is the class minimum launch-to-crossing time rounded down to 10 ms. Verticals mark the LAST grid point at or above each
> threshold, so with a 50 ms grid the true boundary lies between that point and the next. Each class line stops at its own maximum launch-to-crossing time. Pi render and compositor latency is neglected.

## `figureB_position_error_convergence.png`

- clean render: `figureB_position_error_convergence_clean.png`
- caption file: `figureB_position_error_convergence.caption.txt`

> CONVERGENCE against the full-arc Model-C fit, NOT ground truth. This is agreement with the reference fit, not accuracy against labels.
> fit_failed rows excluded from the median. Excluded count per window (ascending) - SHORT: 10,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0
> LONG: 35,15,9,1,0,0,1,1,1,1,0,0,0,0,1,0,1,0,0,0,4,0,1,1.  Denominators: SHORT n=47, LONG n=60.

## `figureB_position_error_convergence_print.png`

- clean render: `figureB_position_error_convergence_print_clean.png`
- caption file: `figureB_position_error_convergence_print.caption.txt`

> *No caption was drawn on this figure's canvas, so there is none to
> extract. The `_clean.png` differs from the original only in size.*

## `figureC_duration_distribution.png`

- clean render: `figureC_duration_distribution_clean.png`
- caption file: `figureC_duration_distribution.caption.txt`

> Launch-to-crossing time, NOT observable track length. Overlaid, not stacked. Dotted verticals mark each class's min / P5 / median / max.
> The earlier n=158 duration figure plotted a different quantity (total observable duration, first usable fit frame to held-out target) on a
> different population (all fitted flights, not crossers only). The two are not comparable. Confusion region of the 45-deg elevation proxy:
> 5 SHORT flights cross later than LONG's minimum (1047.8 ms); SHORT max is 1120.6 ms.

## `figureC_duration_distribution_v2.png`

- clean render: `figureC_duration_distribution_v2_clean.png`
- caption file: `figureC_duration_distribution_v2.caption.txt`

> Launch-to-crossing time, NOT observable track length. Overlaid, not stacked.
> Dotted verticals mark each class's MINIMUM only - the statistic the min-anchored deadline rule uses.
> The earlier n=158 duration figure plotted a different quantity (total observable duration, first usable fit frame to held-out
> target) on a different population (all fitted flights, not crossers only). The two are not comparable.
> Confusion region of the 45-deg elevation proxy: 5 SHORT flights cross later than LONG's minimum (1047.8 ms); SHORT max is 1120.6 ms.

## `figureD_outcome_sweep.png`

- clean render: `figureD_outcome_sweep_clean.png`
- caption file: `figureD_outcome_sweep.caption.txt`

> POOLED is the performance of a system with no regime classifier. SHORT and LONG are the achievable performance if the class were known at prediction time.
> Verdict precedence, first match wins: not answered -> no_response; not in_time -> late; not accurate -> wrong; otherwise success.  in_time = t_obs + latency <= launch_to_crossing + 84 ms,
> t_obs = min(observation window, duration).  accurate = position error < 200 mm, which is CONVERGENCE against the full-arc Model-C fit, NOT ground truth.  fit_failed rows are retained as
> no_response; the denominator is always the panel n.

## `figureD_outcome_sweep_170mm.png`

- clean render: `figureD_outcome_sweep_170mm_clean.png`
- caption file: `figureD_outcome_sweep_170mm.caption.txt`

> POOLED is the performance of a system with no regime classifier. SHORT and LONG are the achievable performance if the class were known at prediction time.
> Verdict precedence, first match wins: not answered -> no_response; not in_time -> late; not accurate -> wrong; otherwise success.  in_time = t_obs + latency <= launch_to_crossing + 84 ms,
> t_obs = min(observation window, duration).  accurate = position error < 170 mm, which is CONVERGENCE against the full-arc Model-C fit, NOT ground truth.  fit_failed rows are retained as
> no_response; the denominator is always the panel n.

## `figureD_outcome_sweep_large.png`

- clean render: `figureD_outcome_sweep_large_clean.png`
- caption file: `figureD_outcome_sweep_large.caption.txt`

> POOLED is the performance of a system with no regime classifier. SHORT and LONG are the achievable performance if the class
> were known at prediction time.
> Verdict precedence, first match wins: not answered -> no_response; not in_time -> late; not accurate -> wrong; otherwise success.
> in_time = t_obs + latency <= launch_to_crossing + 84 ms, t_obs = min(observation window, duration).
> accurate = position error < 200 mm, which is CONVERGENCE against the full-arc Model-C fit, NOT ground truth.
> fit_failed rows are retained as no_response; the denominator is always the panel n.

## `figureD_outcome_sweep_print.png`

- clean render: `figureD_outcome_sweep_print_clean.png`
- caption file: `figureD_outcome_sweep_print.caption.txt`

> *No caption was drawn on this figure's canvas, so there is none to
> extract. The `_clean.png` differs from the original only in size.*

## `figureE_timing_convergence.png`

- clean render: `figureE_timing_convergence_clean.png`
- caption file: `figureE_timing_convergence.caption.txt`

> CONVERGENCE against the full-arc Model-C crossing time (t_cross_ms from launch_to_crossing.csv), NOT accuracy against ground truth.
> Each class line is truncated at its own maximum launch_to_crossing_ms (SHORT 1121 ms, LONG 1559 ms); beyond that the window
> exceeds every flight in the class. fit_failed rows carry no t_cross_own_ms and are excluded from the statistics; counts are in timing_convergence_by_class_T.csv.

## `figureF_chaos_outcome_sweep.png`

- clean render: `figureF_chaos_outcome_sweep_clean.png`
- caption file: `figureF_chaos_outcome_sweep.caption.txt`

> Chaos rally requires the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A. Target mode's test allowed +84 ms AFTER arrival; the sign is opposite and deliberate.
> Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_position, wrong_velocity, success. Bands stack bottom to top as success, wrong_velocity, wrong_position, wrong_class, late, no_response,
> matching Figure D's convention of success on the floor. t_obs = min(observation window, duration).
> Velocity tolerance is a PLACEMENT tolerance and is ISOTROPIC - the same 1471 mm/s on all three world axes, from placement tolerance / (e x T_return) = 1.0 m / (0.68 x 1.0 s).
> The earlier per-axis court-dimension tolerances tested only whether the ball stays in play. The game requires the return to land near an intended spot, and a player covers roughly 1 m during a 1 s return flight,
> so 1 m is the point beyond which the intended shot difficulty changes.
> position_error_mm and the velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth. fit_failed rows are retained as no_response; the denominator is always the class n.
> Each class is truncated at its own maximum launch-to-crossing time. A = 72 / 135 / 220 ms correspond to panel tilt moves of 2, 10 and 30 degrees.

## `figureG_velocity_by_axis_twoclass.png`

- clean render: `figureG_velocity_by_axis_twoclass_clean.png`
- caption file: `figureG_velocity_by_axis_twoclass.caption.txt`

> CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth. Shaded grey band is that axis's label-precision floor (decision 77).
> X_world and Z_world are validated to label precision; Y_world's floor is UNRESOLVED - the reference method was never validated on the width axis, so sitting inside that band means
> 'not distinguishable from the reference's own unknown noise', NOT 'accurate to that figure'. Dotted verticals mark each class's chaos operating window at A = 135 ms.

## `figureG_velocity_by_axis_twoclass_print.png`

- clean render: `figureG_velocity_by_axis_twoclass_print_clean.png`
- caption file: `figureG_velocity_by_axis_twoclass_print.caption.txt`

> *No caption was drawn on this figure's canvas, so there is none to
> extract. The `_clean.png` differs from the original only in size.*

## `model_comparison_pooled/model_comparison_pooled.png`

- clean render: `model_comparison_pooled/model_comparison_pooled_clean.png`
- caption file: `model_comparison_pooled/model_comparison_pooled.caption.txt`

> Pooled across all 158 flights. NO duration stratum and NO elevation class applied - every flight contributes to every
> window it has data for. Bands are the interquartile range, lines the median. Log y: the three series span several orders of
> magnitude at short windows, and a linear axis would render the two lower series flat against zero.
> x is DERIVED, not a column: the file's sweep variable is the number of points in the fit window, converted here as
> (points - 1) x 16.65 ms. That frame period is measured from the data - all 158 flights share it with spread 0.0000 ms - so the
> conversion is exact rather than approximate. It is not the same quantity as the file's own lead-time axis, which runs the other way.
> Rows with a blank error were excluded: free gravity 172, fixed gravity 228, fixed gravity + drag 331 (731 of 29769).
> x truncated at 1332 ms, where the contributing count falls below 40 on all three series.
> Contributing count is NOT constant across windows, so series are not always compared on the same subset of flights - at
> 117 ms and 1332 ms in particular. Per-window counts are in the companion CSV.
> Error is measured against each flight's held-out final-point label.
> Source: results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv

## `ransac_effect_flight22/ransac_effect_flight22.png`

- clean render: `ransac_effect_flight22/ransac_effect_flight22_clean.png`
- caption file: `ransac_effect_flight22/ransac_effect_flight22.caption.txt`

> flight_22 only. All three series use the SAME trajectory model - gravity held fixed, quadratic drag added. What differs is the
> source of the fitted points and whether RANSAC is applied, nothing else.
> The hand-labelled series is the PLAIN fit, not a RANSAC one: the contrast being drawn is RANSAC vs no RANSAC on DETECTED points,
> and applying it to the reference as well would blur that.
> x is real elapsed time between the first and last frame of each fit window, from this flight's own per-frame sensor timestamps
> (cam0/cam1 mean). It is NOT the nominal 16.652 ms/frame constant the source pipeline uses; on this flight the two agree to about
> 6 microseconds over the longest window, so the distinction is one of provenance rather than a correction.
> Shaded band: confirmed hand-pickup frames 44-47, converted to the same ms axis (699-749 ms).
> Windows where any series had no value are excluded from ALL THREE, so the x set is identical by construction - N=[8, 9]
>    dropped, where the RANSAC fit produced no value.
> Log y: the series span several orders of magnitude at short windows.
> Sources: results/trajectory_fit_comparison/phase2/prediction_sweep.csv
>          results/trajectory_fit_comparison/phase2/prediction_sweep_ransac.csv

## `ransac_effect_pooled/ransac_effect_pooled.png`

- clean render: `ransac_effect_pooled/ransac_effect_pooled_clean.png`
- caption file: `ransac_effect_pooled/ransac_effect_pooled.caption.txt`

> Model C (fixed gravity + quadratic drag), 158 flights, 9923 matched (flight, window) cells. Median line, shaded IQR, 100 ms bins.
> Both series share an identical key set; the only difference is the robustifier. Bins outside 0-1500 ms fall below 100 cells and are not plotted.

## `ransac_effect_tail/ransac_effect_p95.png`

- clean render: `ransac_effect_tail/ransac_effect_p95_clean.png`
- caption file: `ransac_effect_tail/ransac_effect_p95.caption.txt`

> Model C, 158 flights, 9592 exactly paired (flight, window) cells in 100 ms bins. Not smoothed.
> 331 cells where the RANSAC fit recorded no value are dropped from BOTH series so the pairing stays exact. Bins under 100 cells are not plotted.

## `ransac_effect_tail/ransac_effect_tail.png`

- clean render: `ransac_effect_tail/ransac_effect_tail_clean.png`
- caption file: `ransac_effect_tail/ransac_effect_tail.caption.txt`

> Model C, 158 flights, 9592 exactly paired (flight, window) cells in 100 ms bins. Not smoothed.
> 331 cells where the RANSAC fit recorded no value are dropped from BOTH series so the pairing stays exact. Bins under 100 cells are not plotted.

## `stage_timing/figure_stage_timing_breakdown.png`

- clean render: `stage_timing/figure_stage_timing_breakdown_clean.png`
- caption file: `stage_timing/figure_stage_timing_breakdown.caption.txt`

> Stack order is pipeline order, bottom to top. Frame lag is a FIXED 16.667 ms constant (one frame at 60 Hz), not a measurement. PNG decode is untimed.
> Two column names from the raw CSV mislead: ransac_ms wraps ALL the least-squares fitting, not just the RANSAC call, and is 61-83% of median latency.
> predict_ms contains NO fitting - only the crossing solve and state evaluation. triangulate_ms is real but invisible: at worst 0.07% of median latency.
> The per-ROW identity stage sum + 16.667 = latency_ms is exact (residual 0.0003 ms on all 2481 ok rows), but neither the median nor the p95 of a sum
> equals the sum of the medians or p95s, so the stack and the dashed measured line need not meet, and do not.
> MEDIAN panels: stack minus measured stays within 3.4 ms (1.3% of latency) and takes BOTH signs - 27 of 48 cells low, 21 high.
> P95 panels: the stack runs HIGH in 43 of 48 cells, by up to 9.5 ms (5.1%), because the stages do not hit their p95 on the same flight.
> It is not a strict upper bound either - 5 cells sit below the measured p95, by at most 1.1 ms. Read the dashed line, not the stack top.
> Percentiles are over status=='ok' rows only; fit_failed rows carry no timing. n_ok ranges 25-60 and 17 of 48 cells rest on a partial population,
> because a short window can fail to fit on flights that fit at a long one. Per-cell n_ok and n_fit_failed are in the companion CSV.
> Class is from the full flight record, 45 deg elevation cut. ransac_ms is NOT compared here against stage 1's ransac_fit_ms: that benchmark ran 15
> RANSAC iterations against this sweep's production 3, so the two are different quantities.

