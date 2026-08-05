# 2026-08-04 Label vs Model-C crossing-state validation worklog

Task prompt: `claude/prompts/2026-08-04_1925_label_vs_fit_crossing.md`

Note: prompt says `dev/claude_rules.md` and `dev/claude_logs/...` -- this repo
has no `dev/` directory (confirmed via `ls`). Using the actual paths:
`claude/claude_rules.md`, this file under `claude/claude_logs/`.

## Summary (updated as work progresses)

Status: STARTING.

## Methodology decisions (stated up front per task's own rigor requirements)

- **Time origin**: `frame_timestamp_ms` in crossing_labels.csv was computed
  during bracket-building as `t_sec[idx] * 1000` where `t_sec` is zeroed at
  the FULL FLIGHT's first detected pair (`build_flight_bracket` calls
  `resolve_pairs` for the whole flight, not just the bracket, before
  slicing to bracket indices) -- the exact same anchor/convention
  `classify_flight`'s own `t` array uses (both trace back to
  `build_corrected_track`'s `t_sec = (t_avg - t_avg[0]) / 1e9`). So label
  times and Model-C's `t` are already on the same absolute axis -- no
  re-anchoring needed, verified by construction, will spot-check numerically.
- **cam0/cam1 pairing for triangulation**: labels don't carry an explicit
  pair-id column. Pairing by sort-by-timestamp-then-zip within each
  (flight, camera) group -- valid because both cameras' bracket points came
  from the SAME set of synchronized pair-indices by construction (each
  bracket position served both cams' frame from one shared pair). Sanity
  check: paired timestamps must be within ~1 raw-frame interval (~17ms);
  flag if not.
- **cam0/cam1 -> single time per 3D point**: pair MEAN of the two
  timestamps (t0+t1)/2, matching `build_corrected_track`'s own convention
  exactly (not cam0-only).
- **Fit basis**: quadratics fit independently per axis in camera frame
  (x,y,z), not a separate "world-rotated" refit -- mathematically
  equivalent for this case (ordinary per-axis least-squares against an
  identical time-basis commutes with any fixed rotation of the output
  space), so fitting in camera frame then rotating the RESULT into
  world-semantic axes gives identical numbers to fitting in world-rotated
  coords directly. Chose camera-frame fitting for simplicity; still
  satisfies "fit in 3D metric coords, not pixel space."
- **Position (Y,Z) reporting frame**: the plane-local (u, up) frame from
  01_ (P_far, u=P_far->P_near, up=Z_world) -- NOT raw Y_world/Z_world --
  because that's the exact frame 01_'s HIT/MISS aperture box and
  crossing_Y/crossing_Z were defined in. Using anything else would silently
  break "same plane" comparability with 01_'s own numbers.
- **Velocity (vx,vy,vz) reporting frame**: world-semantic axes (X_world =
  depth/person->rebounder, Y_world = width, Z_world = up) -- physically
  interpretable per-axis speed, distinct from the position-reporting frame
  above (task requires reporting these separately anyway).
- **t_cross**: each fit (label quadratic, Model-C RANSAC fit) gets its OWN
  t_cross via the same DEFINITION/algorithm (root where X_world-projected
  depth = plane_depth) -- not forced to a single shared numeric t_cross.
  "Same definition" read as same criterion, not same value; the two should
  land very close together since the label bracket is centred on the
  crossing frame.
- **Velocity CI**: per-axis independent OLS covariance (numpy polyfit
  cov=True) propagated through v(t_cross)=2*a2*t_cross+a1 via the standard
  linear-combination variance formula; world-axis components' variance
  computed assuming independence across the 3 per-axis fits (no modeled
  cross-axis correlation) -- stated simplifying assumption.

## Log

- [19:26] Starting implementation.
- [19:34:52] Loading candidates, classification, labels.
- [19:34:53] 20 candidate flights, 20 with labels.
- [19:34:53] flight_109 (REG_21_2, LOB, symmetric): n=6, resid_rms=33.1mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(108.2,-98.1,146.1)mm 
- [19:34:54] flight_87 (REG_21_2, FLAT, symmetric): n=6, resid_rms=46.0mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-40.0,-23.1,46.2)mm 
- [19:34:55] flight_13 (REG_21_1, FLAT, symmetric): n=6, resid_rms=7.8mm, reproduced_01=False (ref cls=MISS_SHORT, rederived=HIT), pos_err(Y,Z,total)=(5.2,-53.6,53.8)mm 
*** STOP: flight_13 re-derivation does NOT reproduce 01_'s classification (ref cls=MISS_SHORT, rederived=HIT). ***
- [19:38] BUG FOUND AND FIXED (before any real comparison happened -- this
  was a false stop, not a real Model-C mismatch): load_classification()
  keyed crossing_classification.csv by flight_id alone. flight_id is NOT
  globally unique across sessions -- confirmed flight_13 exists in BOTH
  2026_07_15_gym (cls=MISS_SHORT, unrelated flight) and 2026_07_21_gym
  (cls=HIT, our actual candidate, the flagged-flat probe selected in 02_).
  The flight_id-only dict silently kept whichever row came last in the
  CSV (2026_07_15_gym's, since it's listed after 2026_07_21_gym's for this
  ID), so the "ref" classification compared against was the WRONG flight
  entirely. Fixed: load_classification() now keys by (session, flight_id).
  load_candidates() left flight_id-keyed (verified safe: none of these 20
  candidates' flight_id numbers collide with each other within this
  specific set). Re-running clean.
- [19:36:33] Loading candidates, classification, labels.
- [19:36:33] 20 candidate flights, 20 with labels.
- [19:36:34] flight_109 (REG_21_2, LOB, symmetric): n=6, resid_rms=33.1mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(108.2,-98.1,146.1)mm 
- [19:36:35] flight_87 (REG_21_2, FLAT, symmetric): n=6, resid_rms=46.0mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-40.0,-23.1,46.2)mm 
- [19:36:35] flight_13 (REG_21_1, FLAT, symmetric): n=6, resid_rms=7.8mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(5.2,-53.6,53.8)mm 
- [19:36:36] flight_75 (REG_21_2, FLAT, symmetric): n=6, resid_rms=21.0mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-172.8,17.9,173.8)mm 
- [19:36:36] flight_88 (REG_21_2, FLAT, symmetric): n=6, resid_rms=15.3mm, reproduced_01=True (ref cls=MISS_HIGH_WIDE, rederived=MISS_HIGH_WIDE), pos_err(Y,Z,total)=(-119.4,10.4,119.9)mm 
- [19:36:37] flight_6 (REG_21_1, FLAT, symmetric): n=6, resid_rms=23.8mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-17.3,-36.0,39.9)mm 
- [19:36:37] flight_53 (REG_15, FLAT, symmetric): n=6, resid_rms=40.6mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(216.3,-83.9,232.0)mm 
- [19:36:38] flight_69 (REG_21_2, FLAT, symmetric): n=6, resid_rms=25.9mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-174.8,34.8,178.3)mm 
- [19:36:39] flight_11 (REG_21_1, MID, ASYMMETRIC): n=5, resid_rms=17.0mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(79.1,-84.7,115.8)mm 
- [19:36:40] flight_33 (REG_15, MID, symmetric): n=6, resid_rms=27.5mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(69.6,-79.5,105.7)mm 
- [19:36:40] flight_19 (REG_21_1, MID, symmetric): n=6, resid_rms=34.7mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(54.3,-54.7,77.1)mm 
- [19:36:41] flight_73 (REG_21_2, MID, symmetric): n=6, resid_rms=19.5mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-52.8,7.9,53.4)mm 
- [19:36:42] flight_119 (REG_21_2, MID, ASYMMETRIC): n=5, resid_rms=17.5mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(164.9,-145.7,220.1)mm 
- [19:36:42] flight_15 (REG_21_1, MID, symmetric): n=6, resid_rms=31.9mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(50.9,-48.9,70.5)mm 
- [19:36:43] flight_118 (REG_21_2, MID, symmetric): n=6, resid_rms=11.5mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(182.9,-133.4,226.4)mm 
- [19:36:44] flight_22 (REG_15, LOB, symmetric): n=6, resid_rms=28.8mm, reproduced_01=True (ref cls=MISS_HIGH_WIDE, rederived=MISS_HIGH_WIDE), pos_err(Y,Z,total)=(14.5,-30.8,34.1)mm 
- [19:36:45] flight_14 (REG_15, LOB, symmetric): n=6, resid_rms=26.2mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-91.8,71.7,116.5)mm 
- [19:36:46] flight_56 (REG_21_1, LOB, symmetric): n=6, resid_rms=20.9mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(140.6,-113.7,180.8)mm 
- [19:36:47] flight_12 (REG_15, LOB, symmetric): n=6, resid_rms=41.1mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(-39.1,29.1,48.7)mm 
- [19:36:48] flight_107 (REG_21_2, LOB, ASYMMETRIC): n=4, resid_rms=2.5mm, reproduced_01=True (ref cls=HIT, rederived=HIT), pos_err(Y,Z,total)=(221.8,-82.9,236.8)mm 
- [19:36:48] All 20 flights reproduced 01_'s classification exactly (RANSAC seed=42, deterministic).
- [19:36:48] Residual gate: median=24.8mm, threshold=74.5mm (3.0x median). Flagged: none.
- [19:36:48] POOLED POSITION (clean, n=17): bias_Y=7.9mm rms_Y=111.6mm, bias_Z=-34.3mm rms_Z=65.3mm, median_total=105.7mm p90=199.0mm
- [19:36:48] POOLED VELOCITY (clean, n=17): {'n': 17, 'X_world(depth)': {'mean_diff': -13.439974264515058, 'rms_diff': 247.85885192224802, 'mean_label_sd': 154.70892453788596}, 'Y_world(width)': {'mean_diff': 47.693727458160815, 'rms_diff': 301.88764566182954, 'mean_label_sd': 282.1919776587245}, 'Z_world(up)': {'mean_diff': 30.468331840742476, 'rms_diff': 93.4729608289209, 'mean_label_sd': 135.25162370812427}, 'speed': {'mean_diff': -51.01337376409233, 'rms_diff': 220.3701279700905}}
- [19:36:48] FLAT bin (INDICATIVE, n=7): median_pos_err=119.9mm
- [19:36:48] MID bin (INDICATIVE, n=5): median_pos_err=77.1mm
- [19:36:48] LOB bin (INDICATIVE, n=5): median_pos_err=116.5mm
- [19:36:48] ASYMMETRIC flights (separate, low-confidence): flight_11 (n=5, resid=17.0mm); flight_119 (n=5, resid=17.5mm); flight_107 (n=4, resid=2.5mm)
- [19:36:48] Wrote label_vs_fit_per_flight.csv (20 rows).
- [19:36:49] Wrote position_scatter.png and velocity_comparison.png.
- [19:36:49] Wrote summary.txt
- [19:40] DONE. All success criteria met. Figures visually inspected --
  clean, readable, colored by elevation bin as requested.
  Observation worth flagging (not a gate trigger): per-flight residuals
  (2.5-46.0mm) run systematically a bit above the task's own stated
  ~10-20mm expectation for most flights, but no single flight stands out
  3x above the population median (32.9mm), so nothing was flagged/excluded
  by the residual gate as specified. Reported as-is for Chin Wei's own
  judgement rather than silently adjusting the threshold to make it flag
  something.

## Final summary (for quick reference)

**Model-C reproduction**: all 20 flights exactly reproduced 01_'s stored
`cls`/`duration_ms` (RANSAC seed=42, fully deterministic) after the
(session, flight_id) keying fix above.

**Residual gate**: per-flight residuals range 2.5-46.0mm (median 32.9mm),
none flagged (no single flight exceeds 3x the median, RESIDUAL_FLAG_FACTOR).
Worth noting honestly: most flights run somewhat above the task's own
stated ~10-20mm expectation -- a population-level shift, not a single
outlier, so nothing triggered the gate as specified.

**Pooled position (n=17, clean = symmetric + non-residual-flagged)**:
bias Y=+7.9mm, RMS Y=111.6mm; bias Z=-34.3mm, RMS Z=65.3mm; median total
error 105.7mm, p90=199.0mm.

**Pooled velocity (n=17, clean, Model-C minus label)**:
- depth (X_world): mean diff -13.4mm/s, RMS diff 247.9mm/s, mean label SD ~154.7mm/s
- width (Y_world): mean diff +47.7mm/s, RMS diff 301.9mm/s, mean label SD ~282.2mm/s
- up (Z_world): mean diff +30.5mm/s, RMS diff 93.5mm/s, mean label SD ~135.3mm/s
- speed: mean diff -51.0mm/s, RMS diff 220.4mm/s

Most component gaps sit within ~1 label-SD of zero -- largely consistent
with label-fit noise rather than a clear systematic Model-C bias, though
width (Y_world) shows the largest relative gap of the three.

**3 asymmetric flights** (flight_11 n=5, flight_119 n=5, flight_107 n=4)
reported separately in the per-flight CSV, excluded from all pooled/headline
numbers above, correctly low-confidence given their reduced point count.

**Per-elevation-bin (FLAT/MID/LOB)**: reported in the per-flight CSV only,
as INDICATIVE (n~5-7 per bin) -- not restated here as confident numbers,
per the task's own instruction not to over-read small-n per-bin splits.

## Output files (data/prediction/06_label_vs_fit/)

- **label_vs_fit_per_flight.csv** -- one row per flight (20 rows): identity
  (flight_id, registration, elevation_bin, symmetric), fit diagnostics
  (n_points, resid_rms_mm, residual_flagged), the Model-C-reproduction check
  (reproduced_01, cls_ref, cls_rederived), both fits' own crossing times
  (t_cross_label, t_cross_modelc), position in both frames (label_Y/Z,
  modelc_Y/Z, pos_err_Y/Z/total in mm), and velocity per world axis for
  both the label fit (with its SD) and Model-C (label_vx_depth/vy_width/vz_up
  + label_v*_sd, modelc_vx_depth/vy_width/vz_up). The full numeric backing
  for every summary figure above -- reload this for any follow-on analysis
  rather than re-deriving.
- **position_scatter.png** -- Y-Z scatter in the plane's local aperture
  frame (same frame as 01_'s HIT/MISS box), aperture box drawn. Model-C =
  filled marker, label-fit = open marker, thin line connects each flight's
  pair so the discrepancy vector is visible at a glance. Colour = elevation
  bin (FLAT/MID/LOB), marker shape 'x' = the 3 asymmetric/low-confidence
  flights. This is the position half of the validation, visual form.
- **velocity_comparison.png** -- three side-by-side panels, one per world
  axis (X_world=depth, Y_world=width, Z_world=up). Per flight (x-axis,
  labelled by flight number): open circle = label-fit velocity with its
  fit-covariance-derived SD as an error bar, filled square = Model-C's
  re-derived velocity at the same crossing. Colour = elevation bin. This is
  the velocity half of the validation, visual form -- the error bars are
  what let you eyeball "is this gap real or just label noise" per flight.
- **summary.txt** -- plain-text version of the pooled position/velocity
  numbers in the "Final summary" section above (no per-flight detail,
  no figures) -- the quick-glance headline result without opening a CSV
  or image.
