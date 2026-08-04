READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Triangulate the manually-labelled rebounder-plane tape points (3 registrations), define the vertical crossing plane + 2x2m aperture per registration, classify every flight's full-arc Model-C fit against its own registration's plane (hit / miss-high-wide / miss-short), plot the crossings, and rank ~20 candidate flights for crossing-bracket labelling.

CONTEXT:
- Rebounder plane ~5m from thrower, defined per registration by 2 manually-labelled ground tape endpoints (the panel hinge, running laterally in Y), labelled in both cameras. Cameras are SIDE-ON (looking across the flight in Y).
- THREE world frames / registrations, do NOT mix flights across them:
    REG_15     -> data\2026_07_15_gym\flight_binning\world_frame_validation
    REG_21_1   -> data\2026_07_21_gym\flight_binning\world_frame_validation  (registration 1 = pre-60)
    REG_21_2   -> data\2026_07_21_gym\flight_binning\world_frame_validation  (registration 2 = post-60)
- Flight -> registration mapping:
    flights in 2026_07_15_gym            -> REG_15
    flights in 2026_07_21_gym, id <= 60  -> REG_21_1
    flights in 2026_07_21_gym, id >= 61  -> REG_21_2   [PARAM: POST60_STARTS_AT=61, VERIFY at checkpoint]
- Model C (fixed gravity + quadratic drag), detector, RANSAC, calibration, triangulation: all FROZEN. READ only.
- Hit/miss criterion here is the vertical-plane box (screening only). The swept quarter-cylinder is DEFERRED - do NOT implement it.
- All outputs go under a NEW numbered analysis subfolder inside: data\prediction\

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Create work log: dev/logs/2026-08-04_[HHMM]_crossing_plane_setup.md
Follow dev/log_template.md. Append in REAL-TIME after each step.
Include: per-registration triangulation numbers (full output), axis self-check, aperture corners, classification summary table, every decision with options/tradeoffs. Summaries ABOVE verbose; <details> for verbose.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

Create a NEW numbered analysis subfolder under data\prediction\ (e.g. data\prediction\01_crossing_plane_setup\). All outputs go there. Do not modify existing folders.

1. Load the 2 tape endpoints (both cameras) for each of REG_15, REG_21_1, REG_21_2 from the paths above. If any registration lacks 2 points in both cams, STOP and report.

2. Per registration: triangulate both endpoints to 3D world coords. Report, per registration:
   - both endpoints' 3D coords
   - separation (expect ~1.0m)
   - height above floor (expect z ~ 0)
   - mean x (expect ~5m)
   Flag any registration with separation not in 0.85-1.15m, |z|>0.10m, or x not in 4.5-5.5m.

3. AXIS SELF-CHECK (correctness gate). Per registration, compute the tape-line direction in world coords and its angle to the Y axis.
   - within +-20deg of Y -> proceed.
   - otherwise -> STOP, log "tape line not lateral - crossing plane degenerate, geometry/labels wrong", report, do not continue that registration.

4. Per registration, define geometry:
   - Crossing plane = vertical plane (using existing world-up) through the tape line. Report plane mean-x and yaw vs X-axis.
   - Identify P_near = tape endpoint closer to the stereo baseline midpoint (from extrinsics); P_far = the other. u = unit(P_far -> P_near).
   - Aperture (2x2m): corner_A = P_far; corner_B = P_far + 2*u; corner_C = corner_B + 2*up; corner_D = P_far + 2*up.
     (i.e. starts at the far endpoint, runs 2m toward the camera side = 1m tape + 1m past P_near, and 2m up from the floor.)
   - Store and report all 4 corners.

5. For EVERY flight (keyed strictly to its own registration's plane):
   - Fit Model C to ALL detected points of the flight (full arc reference), reusing the frozen fit code. NOT a first-N window.
   - If the arc hits the floor (z=0) BEFORE reaching the plane -> class = MISS-SHORT (no crossing point).
   - Else compute crossing state at the plane: (Y, Z) position and 3D velocity vector.
       inside aperture  -> HIT
       outside aperture -> MISS-HIGH-WIDE
   - Output one row/flight: registration, flight_id, class, crossing_Y, crossing_Z, crossing_speed, crossing_vel_xyz, duration_ms, launch elevation+speed (from existing binning), existing gravity/accel flag.

6. Plots (dataviz skill conventions, static PNG, light mode): Y-Z scatter with the 2x2m aperture rectangle drawn, crossing points colored by class. One pooled + one per registration. List MISS-SHORT flights separately.

7. Rank labelling candidates from crossers only (HIT + MISS-HIGH-WIDE):
   - score by proximity to nearest aperture EDGE (near-edge = high value)
   - require duration > 1200ms
   - spread across launch-elevation bins
   - prefer unflagged, include a few flagged (esp. low-elevation)
   Surface top ~20 as a ranked table. Do NOT pick the final 15 - I will.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT label crossing brackets (manual, next task).
- ❌ Do NOT validate arc-fit-vs-labels (next task).
- ❌ Do NOT implement the swept quarter-cylinder criterion.
- ❌ Do NOT re-fit/re-tune Model C, RANSAC, detector, calibration - frozen, READ only (except the full-arc Model-C fit per flight in step 5, which uses the existing fit code unchanged).
- ❌ Do NOT mix flights across the 3 registrations.
- ❌ No git. No refactor. No "improvements".

IF something else seems needed: STOP, log "considered X, not in scope - asking", report, wait.

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Total ~10-15 min. Load+triangulate+self-check 2-3 min; classify all flights 3-5 min; plots+ranking 3-5 min.
STOP and report if any step >2x expected or stuck >5 min.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINT (correctness gate)
═══════════════════════════════════════════════════════════════════════════════

After step 4, STOP and report: per-registration triangulation, axis self-check, plane yaw, POST60_STARTS_AT assumption, and the 4 aperture corners for each registration. WAIT for my approval before classifying flights (step 5). This is where wrong labels/geometry/boundary would silently poison everything downstream.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log+continue): a few flights with no valid arc fit -> log, skip, count.
Unexpected (STOP): tape line not lateral; a registration failing step-2 bounds; missing/incomplete label file; >10% of flights with no arc fit.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW: Option B - No git (analysis only)
═══════════════════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ 3 registrations triangulated, pass step-2 + step-3 checks (or clean STOP naming the failure)
✅ Aperture corners reported per registration, box starts at far endpoint and extends toward camera side
✅ Every flight classified HIT / MISS-HIGH-WIDE / MISS-SHORT, keyed to correct registration, no cross-frame mixing
✅ Per-flight CSV with crossing position + velocity in data\prediction\[NN]_crossing_plane_setup\
✅ Y-Z plots (pooled + per registration) with aperture drawn
✅ Ranked ~20 candidate table
✅ Work log complete and real-time

START WORK