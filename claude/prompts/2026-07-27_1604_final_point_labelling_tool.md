# 2026-07-27 16:04 — Final-point labelling tool (held-out targets for trajectory-fit comparison)

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md, then claude/context.md §4.9 (Link B / Pattern A)
and §5 (prediction model). Then read claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md
in full — this task reuses that task's flight-eligibility logic and must not
re-derive it independently.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Build a labelling tool + target-frame queue so the user can manually label ONE
"final point" (the ball's true centroid) per flight per camera, across every
eligible flight in BOTH `2026_07_21_gym` and `2026_07_15_gym`, writing to a single
centralized CSV. This supports an upcoming comparison of trajectory-fitting models
(gravity-only vs. gravity+drag): fit each model on early detector points, predict
forward, and score against this held-out labelled point — the actual prediction
target, not a point used in any fit.

**You cannot perform the actual labelling** — the existing labelling tools
(`01_label_frames.py`, `02_label_frames_human_error.py`) are interactive
`cv2.imshow` + mouse-click GUIs that require a human physically clicking a rendered
window; there is no way to drive that non-interactively in this environment. Your
job is to build and verify the tool and the target queue are correct and ready — the
user will run the interactive session themselves afterward to do the actual
clicking.

**Design already decided with the user (do not re-litigate):**
1. Scope: BOTH `2026_07_21_gym` and `2026_07_15_gym` — same flight eligibility as
   `flight_velocity_angle_binner.py` already established (a flight is eligible iff
   it has a tuned-detections CSV under
   `data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/<session>/`
   — 126 flights for `2026_07_21_gym`, 37 for `2026_07_15_gym`, per that task's own
   worklog). **Reuse that script's flight-enumeration logic directly** (import it or
   copy the exact approach) — it already correctly handles `2026_07_15_gym`'s nested
   folder naming quirks (e.g. `"2 ball contacts ground before plane/flight_01"`) and
   the session/flight-number collision between the two sessions (e.g. both sessions
   have a `flight_60`). Do NOT re-derive flight enumeration independently — that's
   exactly the kind of thing that already caused a real bug once this session
   (`10_run_full_dataset.py`'s basename-collision bug, documented in the 2026-07-23
   detector worklog).
2. Target frame = the LAST frame within the detector's valid range for that flight's
   `ball_in_frame` folder, per camera — i.e. `last_raw_frame_index - stride`, where
   `stride` comes from `data/detector_tuning/candidate_config.json` (currently 1).
   This matches `run_detection()`'s own valid loop range (`range(stride, len(frames)
   - stride)`) in `detector_core.py` — 3-frame differencing structurally cannot
   produce a detection at the very first/last `stride` frames, so labelling one of
   those as the "final point" would target a frame the detector could never have
   competed for anyway. Compute this from the RAW frame files in each flight's
   `ball_in_frame` folder (glob `frame_*.png`), not from the tuned-detections CSV —
   the label must be an independent ground-truth point, not constrained by whether
   the detector happened to produce a confident detection there.
3. Output: ONE centralized CSV, `data/final_point_labels/final_point_labels.csv`,
   columns: `session, flight, cam, frame_number, click1_x, click1_y, click2_x,
   click2_y, centroid_x, centroid_y, diameter_px` — the `session`+`flight` columns
   are what prevent `2026_07_21_gym/flight_60` and `2026_07_15_gym/flight_60` (or
   any other cross-session collision) from ever being ambiguous in this file.
4. New script: `src/image_processing/03_manual_centroid_labelling/03_label_final_points.py`
   (next number in that folder's existing convention). Reuse the 2-click ->
   centroid/diameter mechanics, zoom/pan, and immediate crash-safe CSV-append pattern
   from `01_label_frames.py`, and the "visit a queue of specific targets rather than
   every frame in a folder" architecture from `02_label_frames_human_error.py` — this
   task's queue is "one target per (session, flight, cam)" rather than a stratified
   sample within one flight, but the queue-driven navigation pattern is the same
   shape. Do not modify either existing script.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (NEW LOG FILE, REAL-TIME UPDATES)
═══════════════════════════════════════════════════════════════════════════════

Create a NEW log file: `claude/claude_logs/2026-07-27_final_point_labelling_tool_worklog.md`
(new topic — do not append to the detector-tuning, sync-correction, or binner
worklogs). Update it continuously: after reading the reused scripts, after building
the target queue (with counts per session), after building the tool, after each
verification check, and at the final checkpoint.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read `claude/claude_rules.md`, `claude/context.md` §4.9/§5, and the full binner
   worklog. Then read `src/stereo/flight_velocity_angle_binner.py` in full (for its
   flight-enumeration logic — reuse it), `src/image_processing/
   03_manual_centroid_labelling/01_label_frames.py` and `02_label_frames_human_error.py`
   in full (for the click/zoom/pan/save and queue-navigation mechanics — reuse, don't
   modify), and `src/image_processing/02_adjacent_frame_differencing/detector_core.py`'s
   `run_detection()` (to confirm the exact valid-frame-range logic your target-frame
   calculation needs to match).

2. **Build the target queue**: for every eligible flight (per decision #1) x both
   cams, compute the target frame per decision #2. Log the resulting counts (e.g.
   "126 flights x 2 cams = 252 targets for 2026_07_21_gym, 37 x 2 = 74 for
   2026_07_15_gym, 326 total"). Verify every computed target's image file actually
   exists on disk before finalizing the queue — don't assume the arithmetic is right,
   check it.

3. **Build the tool** (`03_label_final_points.py`) per decision #4:
   - Visits the queue in order, one (session, flight, cam, frame_number) target at a
     time, opening on that frame by default.
   - Allow LIMITED navigation around the default target (e.g. a handful of frames
     either side, clamped to the valid detector range from decision #2 — do not let
     navigation wander into the excluded `stride`-margin frames or into the middle of
     the flight) so the user can pick an adjacent clearer frame if the default one is
     ambiguous to click confidently. Whichever frame is actually labelled, record its
     real `frame_number` in the output row — the tool must not force a mismatch
     between the displayed frame and the recorded one.
   - Same 2-click -> centroid/diameter computation as `01_label_frames.py`, same
     immediate-save-per-label (crash-safe, appends to the CSV as each target is
     completed, not batched to the end), same resume-from-first-unlabelled-target
     behavior on restart.
   - A "no ball visible" option per target (matching the existing `n` key
     convention), in case the chosen frame genuinely has no visible ball.
   - Progress indicator across the whole queue (e.g. "[142/326] 2026_07_21_gym
     flight_88 cam1").

4. **Verify without performing the actual labelling** (you cannot click the GUI
   yourself): confirm the script starts, builds its queue correctly, resolves every
   target's image path correctly, and writes a correctly-shaped CSV row structure —
   e.g. by exercising the row-construction/CSV-writing logic directly with a couple
   of synthetic click coordinates in a throwaway test, NOT by claiming to have
   labelled real data. Be explicit in your report about exactly what was verified
   vs. what still requires the user to actually run the tool.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Attempt to fabricate, guess, or auto-generate actual label values (click
  coordinates) for real flights — every real row in `final_point_labels.csv` must
  come from an actual human click via the interactive tool
- ❌ Modify `01_label_frames.py`, `02_label_frames_human_error.py`,
  `flight_velocity_angle_binner.py`, or `detector_core.py` — reuse/import their
  logic, don't change them
- ❌ Re-derive flight eligibility/enumeration independently — reuse the binner's
  exact approach (decision #1)
- ❌ Write into any existing labels file (e.g. flight_01/flight_22's existing
  full-flight label CSVs) — this is a new, separate CSV
- ❌ Overwrite or delete anything under `data/detector_tuning/` or any flight's raw
  frames/`ball_in_frame` folder — all read-only inputs
- ❌ Commit anything to git
- ❌ Create more than the one new log file named in LOGGING above

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Building the queue (I/O over ~163 flights x 2 cams, mostly `glob`/path arithmetic)
should take well under a minute. Building the tool itself is normal coding — no long
-running process expected. STOP and investigate if anything runs past ~5 minutes.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINT
═══════════════════════════════════════════════════════════════════════════════

After building and verifying the tool (steps 2-4): STOP, report the target queue
counts per session/cam, confirm every target image path resolved successfully, show
the verification of the CSV-writing logic, and give the user the exact command to
run the interactive tool themselves. Wait for confirmation this is ready before
considering the task done.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, skip that (flight,cam), continue):
- An eligible flight whose raw `ball_in_frame` folder is missing or empty for one
  camera despite having a tuned-detections CSV (shouldn't happen given how the
  detections were generated, but don't assume — check).

Unexpected (STOP immediately):
- A computed target frame index that doesn't correspond to an actual image file on
  disk for a large fraction of flights — indicates the frame-numbering logic itself
  is wrong, not a per-flight data gap.
- The reused flight-enumeration logic producing a different flight count than the
  binner's own recorded 126/37 — investigate the discrepancy before proceeding, don't
  silently accept a different number.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Target queue built from the reused (not re-derived) flight-eligibility logic,
   matching the binner's 126/37 flight counts per session
✅ Target frame per (flight, cam) correctly excludes the detector's stride-margin
   frames, computed from raw frame files, not from the tuned-detections CSV
✅ Every target's image path verified to exist before finalizing the queue
✅ `03_label_final_points.py` built, reusing existing click/zoom/pan/save/queue
   mechanics rather than duplicating them, writing to
   `data/final_point_labels/final_point_labels.csv` with session+flight+cam columns
✅ CSV-writing/row-construction logic verified via a synthetic test — no fabricated
   real labels
✅ Report is explicit about what was verified vs. what still needs the user to
   actually run the interactive tool
✅ No existing file modified; only new files created
✅ New log file created and updated in real time throughout
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Create the new log file
2. Read claude_rules.md, context.md §4.9/§5, the binner worklog, and the 3 scripts
   to reuse
3. Build and verify the target queue (counts + path checks)
4. Build 03_label_final_points.py, verify CSV-writing logic with synthetic data
5. Report at the checkpoint with the exact command for the user to run themselves
```
