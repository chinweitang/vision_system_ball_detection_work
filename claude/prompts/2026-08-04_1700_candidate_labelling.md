READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Drive manual crossing-bracket labelling for the 20 v2 candidate flights: for each flight, serve ~6 frames per camera symmetrically bracketing the plane crossing (NOT 5 consecutive), using my existing ball-centroid labeller, and store the labelled 2D points keyed by flight/camera/frame with the crossing frame marked.

CONTEXT:
- Candidates: data\prediction\02_candidate_reselection\ranked_candidates_v2.csv (20 flights, each with registration + flight_id).
- Purpose: these labels are INDEPENDENT ground truth for crossing position AND velocity, to validate the Model-C arc fit. Velocity GT = local fit through the labelled points, so the bracket must (a) span a time base wider than adjacent frames to reduce finite-difference velocity noise, and (b) be SYMMETRIC about the crossing so acceleration bias cancels.
- The plane crossing frame per flight is where the tracked/observed ball depth crosses the plane depth from 01_crossing_plane_setup. Use the existing per-flight crossing info to locate it; if only the arc-fit crossing time exists, map it to the nearest real observed frame.
- Existing labeller: [FILL: path to your ball-centroid labelling script + how it takes an image and returns a click coord]. Reuse it - do NOT write a new labeller.
- Cameras: cam0 + cam1, per the flight's registration session. Do NOT mix registrations.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Create work log: dev/logs/2026-08-04_[HHMM]_crossing_bracket_labelling.md
Follow dev/log_template.md. Append in REAL-TIME after each flight. Log per flight: the crossing frame index, the 6 frame indices served per camera, their stride/timestamps, and whether all 12 (6x2) points were labelled or any skipped.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

New subfolder: data\prediction\03_crossing_labels\. All label output there.

1. Load the 20 candidate flights. For each, resolve its plane-crossing frame (the observed frame nearest the crossing) per camera.

2. For each flight, per camera, build a bracket of 6 frames:
   - STRIDE 2 (every other frame, ~33ms spacing at 60fps) by default -> 6 frames span ~165ms.
   - SYMMETRIC about the crossing frame: 3 before, crossing, ... i.e. choose the 6 so the crossing instant is as close to the centre of the span as possible.
   - PARAM at top of script: N_BRACKET=6, STRIDE=2 (so I can change without hunting).
   - If the crossing is too near the start/end of the observed flight to place a symmetric bracket, log it, place the widest symmetric bracket possible, and flag that flight for my review (do NOT silently make it one-sided).

3. Serve those frames to my existing centroid labeller (reuse it) so I click the ball in each. Both cameras.

4. Store labels to data\prediction\03_crossing_labels\crossing_labels.csv:
   columns: registration, flight_id, camera, frame_index, frame_timestamp_ms, is_crossing_frame (bool), u_px, v_px, stride, bracket_span_ms
   One row per labelled point (target: 20 flights x 2 cams x 6 = 240 rows).

5. After each flight, append a one-line summary to the log and write/update a manifest data\prediction\03_crossing_labels\labelling_manifest.csv: flight_id, n_points_labelled, bracket_symmetric (bool), flagged_for_review (bool).

6. Do NOT triangulate, fit, or compute velocity here - labelling only. Just capture clean 2D clicks with correct frame/timestamp keys.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT write a new labeller - reuse the existing one.
- ❌ Do NOT use 5 consecutive frames - use N_BRACKET=6, STRIDE=2, symmetric.
- ❌ Do NOT triangulate / fit / compute velocity (next task).
- ❌ Do NOT auto-detect the ball to fill in labels - every point is a manual click. If I skip a frame, record it as skipped, do not infer it.
- ❌ Do NOT mix cameras across registration sessions.
- ❌ No git, no frozen-code edits.

IF a flight's crossing can't be symmetrically bracketed, or the crossing frame is ambiguous: STOP that flight, log why, flag it, move on - don't guess.

═══════════════════════════════════════════════════════════════════════════════
TIMING / GIT
═══════════════════════════════════════════════════════════════════════════════

Interactive (my click speed sets the pace). GIT: Option B - no git.
STOP and report if the labeller errors, a flight's frames can't be found, or >3 flights get flagged for asymmetric brackets (suggests the crossing-frame resolution is off).

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ All 20 flights served, 6 frames/camera, symmetric about the crossing (or flagged if not possible)
✅ crossing_labels.csv written, ~240 rows, crossing frame marked per flight/camera, timestamps + stride recorded
✅ labelling_manifest.csv lists every flight with symmetry + review flags
✅ Any flight that couldn't be cleanly bracketed is flagged, not silently fudged
✅ Work log complete per-flight

START WORK