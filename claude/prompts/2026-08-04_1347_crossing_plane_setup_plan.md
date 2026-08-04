# Crossing-plane setup (claude/prompts/2026-08-04_1240_crossing_plane_setup.md)

## Context

The tape/hinge endpoints are now labelled (6 CSVs, 3 registrations × 2 cams,
under each session's `flight_binning/world_frame_validation/` folder). This
plan executes the prompt itself: triangulate those points, define the
vertical crossing plane + 2×2m aperture per registration, classify every
flight's full-arc Model-C fit as HIT / MISS-HIGH-WIDE / MISS-SHORT, plot the
crossings, and rank ~20 candidates for manual bracket-labelling (a separate,
later task).

Two things surfaced during investigation that change the prompt's literal
geometry plan (confirmed via `world_frame_validate_2026_07_15.py` and the
`*_world_transform.npz` schema):

1. **No absolute floor/world origin exists anywhere in this codebase.**
   `X_world`/`Y_world`/`Z_world` (used by the already-frozen `g_fixed_for` /
   `world_axes_for`) are pure **directions** — `Z_world = -R_wc[:,1]`
   (normalized), `X_world` from the stereo-baseline direction — derived with
   no translation. `T_wc` (checkerboard position) is saved but never
   consumed anywhere. This is deliberate upstream: the existing predictor
   "predicts to the rebounder plane, not the distant floor" specifically to
   avoid ever needing one. Consequence: the prompt's literal "height above
   floor ≈ 0" / "floor z=0" language doesn't map onto anything computable
   as-is.
2. **You pointed out the fix**: everything the task needs — the plane, the
   aperture, and hit/miss classification — can be built entirely *relative
   to the tape points* using world-aligned **directions** (no absolute
   origin needed), and MISS-SHORT doesn't need floor-extrapolation at all —
   just check whether the flight's own **last observed point** has already
   reached the plane's depth. If yes, the full-arc fit is interpolating
   (not extrapolating far), so evaluate it directly for the crossing. If no,
   it's MISS-SHORT, full stop.

This makes the whole pipeline origin-free: every position used below is
either a camera0-frame absolute position (triangulated tape points, fitted
ball positions — same frame, directly comparable) or a world-aligned
*direction* (`X_world`, `Z_world`, and `u` = the tape line's own unit
direction) used only for projections, never translated.

## Resolved design decisions

- **P_near/P_far**: by camera-frame distance to the stereo baseline midpoint
  (`T/2`, cam0 frame, from `calibration_outputs/<session>/.../stereo_extrinsic.npz`).
- **Aperture corners**: pure camera-frame vector arithmetic, no world
  rotation of positions needed — `u = unit(P_far→P_near)` (camera frame),
  `up = Z_world` (direction, camera-frame components) →
  `corner_A=P_far, corner_B=corner_A+2u, corner_C=corner_B+2·up, corner_D=corner_A+2·up`.
- **Plane depth**: mean of the two tape points projected via `X_world` from
  the camera0 origin (a scalar depth, not an absolute "5m from the wall" —
  camera-origin-relative, which is all that's needed since the ball's own
  positions are projected the same way for comparison).
- **Crossing (Y,Z) coordinates**: reported in the aperture's own local frame
  — `Y = (crossing_pos − P_far)·u`, `Z = (crossing_pos − P_far)·up` — so both
  range ~0–2 inside the box. This is what step 6's Y-Z scatter plot needs
  anyway (box drawn at (0,0)-(2,0)-(2,2)-(0,2)).
- **MISS-SHORT**: compare the flight's last observed (triangulated) point's
  `X_world`-projected depth against the plane depth (both camera-origin-
  relative, directly comparable). If short, no crossing is computed at all —
  no floor reference, no extrapolation search needed.
- **Crossing time / root-find**: since MISS-SHORT is already filtered out,
  the fitted arc's `X_world`-projected depth crosses the plane within/just
  beyond the observed window — bisect `predict_fn(params, t)·X_world −
  plane_depth` over a dense `t` grid spanning the observed range (+ small
  margin) to find `t_cross`, then evaluate the full 3D position there.
- **Crossing velocity**: `simulate_drag`/`predict_fn` (frozen) only returns
  position, never velocity. New helper (not a frozen-code edit): finite-
  difference `predict_fn(params, [t_cross, t_cross+1ms])` and divide by 1ms.
- **Tape sanity check adapted**: without an absolute floor, "expect z≈0"
  becomes "the two tape endpoints' `Z_world`-projected heights should agree
  with each other" (a tape lying flat on the floor has both ends at the same
  height, even without knowing what that height is relative to) — this still
  catches a bad click, just not against an external absolute reference.
- **Separation bound**: you clicked ~700mm (not the tape's true ~1m) across
  all three registrations, consistently. Direction/aperture math is
  unaffected (unit vector), but the sanity-check bound moves from the
  prompt's "expect ~1.0m, flag outside 0.85–1.15m" to a band centered on
  ~700mm (soft/diagnostic only, since the true intended length isn't
  independently known here).
- **POST60_STARTS_AT=61 assumption**: already independently validated —
  `all_flights_common.py`'s `REGISTRATION1_MAX_FLIGHT = 60` (flights ≤60 →
  registration1, >60 → registration2) matches the prompt's assumption
  exactly; no need to re-derive.

## Reused (frozen, read-only) building blocks

- `src/stereo/triangulate.py::triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)`
  — undistorts internally, returns cam0-frame 3D points. Pattern to copy:
  `src/registration/validate_triangulation.py` (intrinsics/extrinsics
  loading, click-CSV loading, triangulate call).
- Intrinsics: `calibration_outputs/cam{0,1}_intrinsics_fisheye.npz` (shared
  across sessions). Extrinsics: `calibration_outputs/2026_07_15/stereo_extrinsic.npz`,
  `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz`.
- World axes/g: `src/stereo/all_flights_common.py` —
  `enumerate_eligible_flights()` (the 163-flight list, source of truth, not
  the binning CSV), `load_session_calib(session)`, `g_fixed_for(session, flight_id)`,
  `world_axes_for(session, flight_id)` (handles the registration1/2 split
  internally), `build_corrected_track(session, flight_id, K0,D0,K1,D1,P0,P1)`
  → `(frame_labels, t_sec, xyz, t_anchor_ns)`, cam0 frame, full arc.
- Model C fit: `src/stereo/trajectory_fit.py` —
  `build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)` →
  `(fit_fn, predict_fn)`; `ransac_fit(t, xyz, fit_fn, predict_fn, min_samples=RANSAC_MIN_SAMPLES["C"], inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM, n_iterations=RANSAC_N_ITERATIONS["C"], random_seed=RANSAC_SEED, frame_numbers=frame_labels)`
  → `res["params"]` reusable directly with `predict_fn` for extrapolation
  (no fitted-window constraint). Pooled K: read
  `data/trajectory_fit_comparison/all_flights/phase1/pooled_k.txt` (plain
  float), same as `rect_vs_ellipse_prediction_comparison.py::load_pooled_k()`.
- Copyable full pattern for "loop all flights, fit, RANSAC, evaluate at a
  target": `src/stereo/rect_vs_ellipse_prediction_comparison.py` (esp.
  `fit_and_predict_c()` lines 128-141) — same shape as needed here, minus
  the fixed-window slicing (this task fits ALL points, no window).
- Launch elevation/speed + quality flag: `data/flight_binning/flight_velocity_angle.csv`
  (columns include `session, flight_id, N_requested, N_used, status,
  speed_m_s, elevation_deg, flag_reason`). Use the `N_requested=30` row per
  flight (more frames → more stable estimate) where `status=="ok"`.

## New code (this task)

One new script, e.g. `src/stereo/crossing_plane_classification.py`, plus a
new output folder `data/prediction/01_crossing_plane_setup/` (first numbered
subfolder there — confirmed empty).

**Phase A (geometry setup):**
1. Load the 6 tape CSVs, triangulate each registration's 2 points (cam0
   frame), report per registration: both points' coords, separation, the
   two points' `Z_world`-height agreement (adapted sanity check).
2. Axis self-check: angle between the tape direction and `Y_world` (STOP
   that registration if >20° — degenerate).
3. Compute P_near/P_far (via baseline-midpoint distance), `u`, aperture
   corners, plane depth (`X_world`-projected mean).
4. Log everything above, then continue straight into Phase B (no pause) —
   the checkpoint gate from the original prompt is skipped by request.

**Phase B (same run, no pause):**
5. For each of the 163 flights (`enumerate_eligible_flights()`), keyed to
   its own registration: `build_corrected_track` → RANSAC-fit Model C on
   ALL points → compare last point's depth to plane depth → MISS-SHORT, or
   root-find `t_cross` → crossing (Y,Z) in local aperture coords + velocity
   (finite-difference) → HIT / MISS-HIGH-WIDE via the 0–2×0–2 box test.
   Log skips (no arc fit) — STOP if >10% of flights fail, per the prompt's
   own error-handling rule.
6. Write per-flight CSV: registration, flight_id, class, crossing_Y,
   crossing_Z, crossing_speed, crossing_vel_xyz, duration_ms, elevation_deg,
   speed_m_s, flag_reason.
7. Plots (load the `dataviz` skill before writing plotting code): pooled +
   per-registration Y-Z scatter, aperture box drawn, points colored by
   class, static PNG, light mode. List MISS-SHORT flights separately.
8. Ranking table: from HIT+MISS-HIGH-WIDE only, score by proximity to
   nearest aperture edge, `duration_ms > 1200`, spread across
   elevation-bins, prefer `flag_reason` empty (include a few flagged,
   especially low-elevation). Surface top ~20 — do not pre-select the final
   15.

Work log per `claude/claude_rules.md` §10: `claude/logs/2026-08-04_HHMM_crossing_plane_setup_worklog.md`,
updated in real time (not written once at the end).

## Verification

- Phase A's logged geometry (triangulation, self-check, aperture corners) is
  the main correctness gate — reviewed after the full run completes, in the
  work log and printed output, since Phase B runs straight through without
  pausing.
- Spot-check 2-3 flights' classification by eye against a quick plot of
  their full trajectory vs the plane/aperture.
- Confirm flight count sums correctly: HIT + MISS-HIGH-WIDE + MISS-SHORT +
  skipped = 163 (or explain any gap).
- Confirm the ranked-candidate table only contains crossers (HIT/MISS-HIGH-WIDE),
  meets the duration filter, and spans elevation bins as requested.

## Out of scope (per the prompt)

- Manual crossing-bracket labelling (next task).
- Arc-fit-vs-labels validation (next task).
- The swept quarter-cylinder criterion (deferred).
- Re-fitting/re-tuning Model C, RANSAC, the detector, or calibration —
  frozen, read-only (except the new full-arc Model-C fit call itself, using
  the existing fit code unchanged).
