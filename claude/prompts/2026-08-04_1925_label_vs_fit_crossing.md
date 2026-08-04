READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Validate the full-arc Model-C fit's crossing-plane state (position + velocity) against the independent manual crossing-bracket labels, for the 20 labelled flights. This is the first independent check on whether Model-C's crossing velocity is real.

CONTEXT:
- Manual labels: data\prediction\03_crossing_labels\crossing_labels.csv (232 rows; registration, flight_id, camera, frame_index, frame_timestamp_ms, is_crossing_frame, u_px, v_px, stride, bracket_span_ms). 17 flights at 12 points, 3 flagged/asymmetric: flight_11 (10), flight_119 (10), flight_107 (8).
- This checks the FIT + EXTRAPOLATION, not calibration: labels are triangulated with the SAME frozen calibration as Model-C, so both inherit any calibration/scale error identically. State this - it is not an absolute-truth check, it is "does the full-arc fit's crossing state match an independent local fit of the same 3D points."
- Plane: the triangulated tape plane from 01_ (same per registration). Both Model-C and the label fit must be evaluated at the SAME plane and the same t_cross definition.
- Model-C crossing state: RE-DERIVE from the frozen fit deterministically (same approach as 05_). Verify it reproduces the 01_ crossing_classification cls/duration for these 20 flights; if it does not reproduce, STOP and report.
- Everything frozen, READ only. New numbered subfolder.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED)
═══════════════════════════════════════════════════════════════════════════════

Work log: dev/claude_logs\2026-08-04_[HHMM]_label_vs_fit_crossing.md . Real-time append.
Log per flight: quadratic fit residual, whether symmetric or flagged, and the position/velocity comparison.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

New subfolder: data\prediction\06_label_vs_fit\ . Outputs there.

1. TRIANGULATE FIRST, FIT IN 3D. For each labelled flight:
   - Pair cam0/cam1 labelled points and triangulate each pair to a 3D world point (frozen calibration).
   - Assign each 3D point a single time t from its REAL frame_timestamp_ms (NOT assumed uniform spacing - paired detections skip frames). If cam0/cam1 timestamps differ per pair (free-run offset), use a stated single convention (cam0 time, or pair mean) consistently - state which.
   - Fit THREE independent quadratics x(t), y(t), z(t) in 3D world coords. Do NOT fit in pixel space.

2. RESIDUAL GATE (do this before any comparison):
   - Report each flight's quadratic fit residual (RMS, mm) across its points.
   - Expected within label noise (~10-20mm triangulated). FLAG any flight with residual >> that as a possible mis-click / mis-pair; list it for my inspection and mark it excluded_pending_review. Do not include a spiking-residual flight in the headline comparison.

3. EVALUATE at the crossing:
   - From the label quadratic, read crossing POSITION (Y,Z at plane) and VELOCITY (vx, vy, vz components) at t_cross, WITH a confidence interval on each velocity component from the quadratic fit covariance.
   - Re-derive Model-C crossing position (Y,Z) and velocity (vx,vy,vz) at the same plane/t_cross.

4. COMPARE, position and velocity SEPARATELY (never combined into one 'error'):
   - Position: |label - ModelC| in Y, Z, and total (mm).
   - Velocity: per component vx, vy, vz (mm/s), and speed magnitude, reported as ModelC vs label ± label CI. Attribute the gap honestly: some is label-fit noise (the CI), not all Model-C.

5. REPORT structure (respect the small n):
   - Per-flight table: flight_id, bin, symmetric/flagged, residual, position error (Y,Z,total), velocity error per component vs label CI.
   - POOLED position agreement over clean symmetric flights (n~17) - the meaningful result.
   - POOLED velocity agreement per component with label-noise caveat.
   - Per elevation bin (FLAT/MID/LOB) as INDICATIVE only, n stated per bin - do NOT present confident per-bin velocity numbers off ~5 flights.
   - The 3 asymmetric flights (11,119,107) reported SEPARATELY, flagged lower-confidence velocity, excluded from the headline conclusion.

6. Figures (dataviz, light mode): (a) label vs Model-C crossing position scatter with the aperture box; (b) per-component velocity: Model-C vs label with label CI error bars. Colour by elevation bin.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT assume uniform frame spacing - use real frame_timestamp_ms.
- ❌ Do NOT fit in 2D/pixel space then triangulate - triangulate first, fit in 3D.
- ❌ Do NOT combine position and velocity into one error metric.
- ❌ Do NOT present this as absolute ground truth - it shares calibration with Model-C; it validates the fit, not calibration.
- ❌ Do NOT let the 3 asymmetric flights or any residual-flagged flight drive the conclusion.
- ❌ Do NOT report confident per-bin velocity numbers off ~5 flights - mark per-bin indicative.
- ❌ Do NOT re-fit/re-tune Model-C, re-run classification, or edit frozen code.
- ❌ No git.

IF Model-C re-derivation doesn't reproduce 01_ classification for these 20, or a flight's residual is unexplained: STOP and report, don't push a number through.

═══════════════════════════════════════════════════════════════════════════════
TIMING / GIT / SUCCESS
═══════════════════════════════════════════════════════════════════════════════

~10 min. GIT: Option B - no git.

✅ 20 flights triangulated + 3D quadratic fit, real timestamps, residual reported per flight
✅ Residual gate applied; any spiking flight flagged/held out before comparison
✅ Model-C crossing re-derived + reproduces 01_ (or clean STOP)
✅ Position compared (Y,Z,total); velocity compared per component vx/vy/vz with label CI
✅ Pooled position (n~17) + pooled velocity results; per-bin marked indicative with n
✅ 3 asymmetric flights separated, flagged low-confidence
✅ 2 figures; per-flight CSV + summary in 07_; worklog complete

START WORK