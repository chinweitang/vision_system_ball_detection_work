Extend the outcome sweep to chaos rally with the full four-criterion verdict.
Reuse the Figure D machinery. Write to
src/regen_2class/step10_chaos_outcome_sweep.py and run it. No heredocs.
Output to data/regenerate_figures/.

READ FIRST: claude/claude_rules.md
LOG: append to the existing two-class work log.

FIRST, REPORT BEFORE COMPUTING
State whether per-axis velocity error (X_world, Y_world, Z_world) is available
per flight per observation window, and from which file. If only the scalar
velocity_error_mm_s exists, say so explicitly and use the fallback below.

CLASSES AND JOIN
SHORT = FLAT union MID (47), LONG = LOB (60), recomputed from the bin column.
Join pipeline_sweep_raw.csv on (session, flight) to launch_to_crossing.csv on
(session, flight_id), and crossing_classification.csv for duration_ms. Never join
on flight alone.

PER-FLIGHT VERDICT, precedence first-match-wins
  no_response     : status != "ok"
  late            : t_obs + latency_ms > launch_to_crossing_ms - A
  wrong_class     : hit_miss_match == False
  wrong_position  : position_error_mm >= 100
  wrong_velocity  : any axis outside tolerance
  success         : all pass
where t_obs = min(observation window, duration_ms).

NOTE THE MINUS SIGN in the timing test. Chaos rally needs the answer A ms BEFORE
arrival. Target mode used +84 after. Opposite sign, deliberate.

A in {72, 135, 220} ms - panel tilt moves of 2, 10 and 30 degrees.

VELOCITY TOLERANCES, per axis
  X_world depth  : 6618 mm/s
  Y_world width  : 3676 mm/s
  Z_world up     : 2206 mm/s
Derived as court dimension / (e * T_return) with e = 0.68 and T_return = 1.0 s.
FALLBACK if per-axis is unavailable: test the scalar velocity_error_mm_s against
2206 mm/s, the tightest axis. Record in the log that the conservative fallback
was used.

FIGURE F
Six stacked-bar panels: SHORT and LONG at each A. Six bands in the precedence
order above. All 24 observation windows. Truncate each class at its own max
launch_to_crossing_ms. Assert bands sum to class n at every window.
No pooled panel.

PRINT, console and CSV
For each (class, A): best observation window by success rate, and at that window
  all six band counts and success_rate
  median and p90 position_error_mm
  hit_miss agreement rate, with n_fit_failed reported separately
  per-axis velocity bias and scatter RMS (or the scalar, if that is all there is)
Mark INFEASIBLE where no window achieves any success.
Also print, for each class and A, how often each pair of failure modes co-occurs.

SENSITIVITY
Repeat the whole sweep with position threshold 150 mm instead of 100 mm. Print a
comparison table of best window and success rate at 100 vs 150. No second figure.

VELOCITY FIGURE, TWO CLASSES
Regenerate the existing three-panel per-axis velocity figure under SHORT/LONG.
Keep the per-axis label-precision floor bands and the caption noting X and Z are
validated to label precision (decision 77) while Y_world is UNRESOLVED. Change
the x-axis label to "observation window (ms)". Vertical lines at the chaos
operating windows found above.

DO NOT
- Re-run any Pi benchmark, capture, detection or fitting job
- Hardcode any deadline value
- Modify Figures A, D or E
- Commit to git
- Do NOT use `python - <<'PYEOF'` heredocs for any part of this. Every step goes
  in the script file. The figure must be regenerable from the file alone after
  the session ends.

TIMING: under 25 minutes.