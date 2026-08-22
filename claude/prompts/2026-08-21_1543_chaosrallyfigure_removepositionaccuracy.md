NEW FIGURE. Do not modify, overwrite or delete Figures A, D, E, F or G.
This is a revised chaos-rally sweep saved under a new filename.

Write to src/regen_2class/step12_chaos_sweep_3criterion.py and run it.
No heredocs. Output to data/regenerate_figures/ as figure_h_chaos_3criterion.png
and a matching CSV.

RATIONALE, record in the log
Figure F used a four-criterion verdict including wrong_position at 100 mm. That
threshold was derived as a dead-band containment margin around the aperture
perimeter. It is being removed as a separate criterion because it duplicates the
hit/miss classification test: the impulse axis translates the panel along its
surface normal at uniform velocity, so return direction is set by the commanded
panel angle and return speed by the translation velocity, neither of which
depends on where the ball contacts the surface. Crossing position therefore
governs only whether contact occurs, which hit_miss_match already tests.
Position accuracy is now reported as a CAPABILITY, not a pass criterion.

CLASSES AND JOIN - unchanged from Figure F
SHORT = FLAT union MID (47), LONG = LOB (60), recomputed from the bin column.
Join pipeline_sweep_raw.csv on (session, flight) to launch_to_crossing.csv on
(session, flight_id), plus duration_ms from crossing_classification.csv. Never
join on flight alone. Per-axis velocity from figures2/velocity_by_axis_raw.csv.

PER-FLIGHT VERDICT - three criteria, precedence first-match-wins
  no_response     : status != "ok"
  late            : t_obs + latency_ms > launch_to_crossing_ms - A
  wrong_class     : hit_miss_match == False
  wrong_velocity  : any axis error > 1470.6 mm/s
  success         : all pass
where t_obs = min(observation window, duration_ms).
Velocity tolerance is isotropic placement: 1.0 m / (0.68 x 1.0 s).
Note the MINUS in the timing test - chaos rally needs the answer A ms BEFORE
arrival. Deliberate, opposite to target mode's +84 ms.

A in {72, 135, 220} ms - panel tilt moves of 2, 10 and 30 degrees.

FIGURE H
Six stacked-bar panels: SHORT and LONG at each A. Five bands, stacked bottom to
top: success, wrong_velocity, wrong_class, late, no_response. Success on the
floor, matching Figure D.
Colours, fixed, do not run the palette validator:
  success        #1baf7a
  wrong_velocity #e87ba4
  wrong_class    #2a78d6
  late           #4a3aa7
  no_response    #e34948
All 24 observation windows. Truncate each class at its own max
launch_to_crossing_ms. Assert bands sum to class n at every window.
No pooled panel.

PRINT, console and CSV
For each (class, A): best observation window by success rate, and at that window
  all five band counts and success_rate
  position accuracy AS A CAPABILITY: median, p90 and max position_error_mm
  hit_miss agreement rate, with n_fit_failed reported separately
  per-axis velocity bias and scatter RMS
Also report the INDEPENDENT flag count for each criterion at the best window -
how often each test fails on its own, ignoring precedence. The verdict bands
answer "what failed first"; the independent flags answer "how often does each
requirement fail", and the requirements table needs the second.

COMPARISON TABLE
Print Figure F's four-criterion success rates alongside Figure H's
three-criterion rates at each (class, A), with the delta. This quantifies what
removing the position criterion changed, and both numbers go in the report.

SENSITIVITY, print only, no extra figure
Rerun the verdict with wrong_position at 100 mm reinstated at the END of the
precedence chain, after wrong_velocity rather than before it. Report how many
flights fail position alone once everything else has passed. That is the true
containment cost, undistorted by ordering.

DO NOT
- Re-run any Pi benchmark, capture, detection or fitting job
- Modify or overwrite any existing figure
- Change APERTURE_SIZE_MM anywhere
- Hardcode any deadline value
- Commit to git

TIMING: under 20 minutes.