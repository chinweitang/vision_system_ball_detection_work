# 2026-07-27 gravity vs drag trajectory fitting -- worklog

Task: claude/prompts/2026-07-27_1818_gravity_vs_drag_trajectory_fitting.md

Compare Model A (free gravity, free a), Model B (fixed gravity, linear fit),
Model C (fixed gravity + drag, nonlinear fit) on flight_01/flight_22
(2026_07_15_gym). Phase 0: consolidate fitting code into trajectory_fit.py.
Phase 1: K discovery. Phase 2: prediction-window sweep, 6 curves/flight.

## [setup] Read-first materials

- claude/claude_rules.md: solo project, direct-to-main commits (N/A here, no
  git). Section 4: exploratory/diagnostic work goes straight in, no
  pre-approval gate -- matches this task's "Phase 0 does not pause" framing.
  Data-protection rule: never overwrite/delete files under data/ or
  calibration_outputs/ without asking -- this task only READS existing data/
  files (registration_world_transform.npz, labels, tuned detections) and
  WRITES new script outputs elsewhere, so should not trigger this.
- context.md sec 5 (prediction): gravity + quadratic drag, least-squares fit
  to initial points, coupled 3D (drag depends on |V|), not Kalman-primary --
  matches Model C's spec exactly.
- context.md sec 4.6 (error budget) / Pattern A: fit first N frames -> predict
  -> compare to that flight's own later triangulated points, sweep N~5-25,
  predict to a *short* horizon not the full remaining arc -- this is exactly
  predict_sweep.py's existing methodology being extended, not replaced.
- Read predict_sweep.py, label_vs_detection.py, triangulate_flight.py, and
  flight_velocity_angle_binner.py (the 4th consumer of fit_constant_accel,
  named in the task's Phase 0 step 2) in full.
- Confirmed all needed data exists: registration_world_transform.npz under
  2026_07_15_gym/flight_binning/world_frame_validation/, flight_01 and
  flight_22 label CSVs (per-cam, frame_number,click1_x,...,centroid_x,
  centroid_y,... schema -- NOT the combined frame_index,cam,u,v schema
  label_vs_detection.load_points_csv expects), and tuned detections for both
  flights under data/detector_tuning/detections/03_.../2026_07_15_gym/.
- flight_01 labels: 28 rows/cam (frames 43-... roughly). flight_22: 94
  rows/cam -- much denser/longer track, good for the "full densely-labelled
  arc" Phase 1 requirement.

## [decision] Golden-output strategy for Phase 0 verification

The task's 4 before/after checks reference numbers "already established
earlier this session" in prior worklogs. This is a fresh session/conversation
with no access to those exact run artifacts, so instead: capture golden
output by running each of the 4 scripts UNMODIFIED right now (before moving
any code), then rerun after the refactor and diff against that same
just-captured golden output. This is a stronger check than matching
old-worklog numbers anyway (guarantees an apples-to-apples same-environment
comparison) and still satisfies the actual intent (refactor is
behavior-neutral). Noting this substitution explicitly per the "Considered
doing X, logging as I go" spirit.
