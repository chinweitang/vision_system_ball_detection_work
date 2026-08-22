Compute crossing-time convergence across the observation-window sweep and plot it.
Write the code to src/regen_2class/step8_timing_convergence.py and run that file.
No heredocs. All outputs to data/regenerate_figures/.

READ FIRST: claude/claude_rules.md
LOG: claude/claude_logs/2026-08-21_[HHMM]_timing_convergence.md, real-time appends.

DATA
- t_cross_own_ms per (flight, T) from
  data/pi_benchmarking/pipeline_sweep_full_20260804.json
  Present on 2481 of 2568 records; the 87 absences are exactly the fit_failed rows.
- Reference: t_cross_ms from
  data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv
  Verified bit-identical to t_cross_modelc*1000, all 20 labelled flights, so it is
  the full-arc Model-C crossing time and it exists for all 107 flights.
  Do NOT use the sweep's last grid row as the full-arc reference: 58 of 60 LONG
  flights are still accumulating points at T=1250 and have no full-arc row.

CLASSES AND JOIN
SHORT = FLAT union MID (47), LONG = LOB (60). Recompute from the bin column, do
not hardcode. Join on (session, flight) to (session, flight_id). Never on flight
alone - flight_13 exists in two sessions.

COMPUTE
timing_error_ms(flight, T) = t_cross_own_ms(T) - t_cross_ms
Keep it SIGNED. Report separately:
  - signed median and IQR per class per T (shows whether early windows predict
    systematically early or late)
  - absolute-value median, p95 and max per class per T
Rows where t_cross_own_ms is absent are excluded from the statistics but their
count must be printed per class per T.

FIGURE E
Median absolute timing error vs observation window, one line per class, IQR
shaded. Same styling as the position convergence figure. Vertical lines at the
operating windows: SHORT 400 ms, LONG 850 ms. Truncate each class line at its own
maximum launch_to_crossing_ms, computed from the data.
Caption must state this is CONVERGENCE against the full-arc Model-C crossing time,
not accuracy against ground truth.

PRINT
- timing_error_p95 (absolute) at SHORT T=400 and LONG T=850. These size the
  actuator plateau.
- The signed median at those windows, so any systematic early/late bias is visible.
- A table: class, T, n_valid, n_missing, signed_median, abs_median, abs_p95, abs_max.
  Save as CSV.

SEPARATE SMALL JOB, SAME RUN
For the 20 flights in label_vs_fit_per_flight.csv, compute
  t_cross_label*1000 - t_cross_modelc*1000
and report median, p95 and max absolute difference. This is the label-vs-model
full-arc timing agreement and it is currently unmeasured. Note in the log that
t_cross_label comes from an independent local quadratic through 6 manually
labelled points, so it is semi-independent of Model-C, but shares calibration and
detection.

DO NOT
- Re-run any Pi benchmark, capture, detection or fitting job
- Modify any existing file outside data/regenerate_figures/, src/regen_2class/
  and the log dir
- Use the sweep's last grid row as a full-arc reference
- Commit to git

TIMING: under 15 minutes. Stop and report if over 25.