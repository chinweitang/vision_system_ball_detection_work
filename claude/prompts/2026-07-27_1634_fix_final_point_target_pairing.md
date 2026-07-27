# 2026-07-27 16:34 — Fix cam0/cam1 target-frame pairing in the final-point labelling tool

**Instructions:** Tell the user to quit the currently-running interactive
`03_label_final_points.py` session first (press `q`/Esc — progress is saved per-label,
so this is safe), THEN paste the block below into a fresh Claude Code session.

---

```
READ FIRST: claude/claude_logs/2026-07-27_final_point_labelling_tool_worklog.md IN
FULL — this is a bug fix on that exact task, not a new one, and you must not repeat
work already verified there (the target queue, the click/zoom/pan/save mechanics,
etc. are already built and correct — only the frame-PAIRING logic needs fixing).

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Fix `src/image_processing/03_manual_centroid_labelling/03_label_final_points.py`:
it currently computes cam0's and cam1's target frame INDEPENDENTLY (each just "last
valid frame for that camera"), with no check that the two frames are actually close
in real time. Same `frame_number` in cam0 and cam1 does NOT mean the same real
instant — this session's measured sync offset drifts continuously up to ±8.3ms
across the 149 flights (per `data/2026_07_21_gym/sync_audit.csv`, already built in
the pixel-velocity sync-correction task). At typical late-flight ball speeds
(~8-10 m/s, and the final point is usually the fastest part of the flight), an
uncorrected several-ms mismatch is tens of mm of true position difference — enough
to contaminate the very ground-truth reference this label exists to provide.

**Verified before writing this task (do not re-verify, trust this)**: checked the 14
flights already labelled (`data/final_point_labels/final_point_labels.csv`,
flight_1-flight_14, all `2026_07_21_gym`) against their real timestamps —
ALL 14 are within an 8.5ms tolerance (worst case flight_1 at -5.05ms). These do NOT
need to be touched, re-verified, or relabelled. The concern is entirely about the
~300+ remaining not-yet-labelled targets, given the confirmed drift trend means later
flights (especially near the two offset-wrap points around flight_57 and flight_136
found in the sync audit) are at real risk of landing outside tolerance if the
independent-selection bug isn't fixed first.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (CONTINUE THE EXISTING WORKLOG)
═══════════════════════════════════════════════════════════════════════════════

This is the same task being fixed — continue appending to
`claude/claude_logs/2026-07-27_final_point_labelling_tool_worklog.md`. Do NOT create
a new log file. Update it continuously as you work.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read the existing worklog in full, then `src/stereo/stereo_flight_sync_table.py`
   (for `load_timestamps()` and the nearest-timestamp bisect-matching logic —
   `nearest_index()` or equivalent) and `src/stereo/pixel_velocity_correction.py`
   (for `DEFAULT_MAX_PAIR_GAP_MS = 8.5` — import this constant, do not redefine a
   new magic number for the same threshold). Do not modify either file.

2. **Fix the target-frame selection in `03_label_final_points.py`**: for each flight,
   cam0's candidate target starts at the same place as today (last valid-range
   frame). Then:
   - Find cam1's nearest-in-real-time frame to that cam0 candidate, restricted to
     cam1's OWN valid range (excluding its stride-margin frames) — reuse the
     existing nearest-timestamp matching, don't reimplement it.
   - Check the resulting Δt against `DEFAULT_MAX_PAIR_GAP_MS`. If within tolerance,
     this (cam0_frame, cam1_frame) pair is the flight's target — done.
   - If NOT within tolerance, step the cam0 candidate one frame earlier (staying
     within cam0's valid range) and repeat, until a pair within tolerance is found.
     The result should be the LATEST cam0 frame that has a well-paired cam1 partner,
     not an arbitrary one.
   - If no pair within tolerance exists anywhere in cam0's valid range (should be
     rare — flag and log clearly, do not silently accept a bad pair for that flight;
     skip it and report which flight(s) this happened to).

3. **Preserve the 14 already-labelled targets untouched**: confirm (don't assume)
   that the existing resume logic — keyed by `(session, flight, cam)` already present
   in `final_point_labels.csv` — still correctly treats flight_1 through flight_14 as
   already-done and skips them, regardless of what the newly-fixed logic would
   recompute for them in isolation. Do not re-derive or overwrite their rows.

4. **Rebuild and verify the queue for every NOT-yet-labelled target** with the fixed
   logic: for each, compute and record the actual Δt of the resulting pair. Report:
   how many targets needed 0 backward steps (cam0's original last-valid-frame worked
   immediately), how many needed 1+ backward steps (and the distribution — e.g. max
   steps needed), and any that couldn't achieve tolerance at all. Do not just trust
   the logic works — show the actual computed numbers, same rigor as the original
   task's "verified all 326 target image paths exist" check.

5. **STOP at the checkpoint** and report the verification results before telling the
   user it's safe to resume labelling. Give them the exact command to relaunch the
   tool.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Modify, re-verify, or overwrite any of the 14 existing rows in
  `data/final_point_labels/final_point_labels.csv` — already confirmed good
- ❌ Modify `stereo_flight_sync_table.py` or `pixel_velocity_correction.py` — reuse
  their logic/constants, don't change them
- ❌ Change the click/zoom/pan/save GUI mechanics, the CSV schema, or the
  queue-navigation UI (`[`/`]`, `<-`/`->`, `s`, `n`, `z`/`0`, `q`/Esc) — only the
  target-frame-selection logic changes
- ❌ Attempt to control or close the user's live interactive GUI session yourself —
  that's a real window on their screen; tell them to quit it, don't try to kill the
  background task programmatically
- ❌ Create a new log file — continue the existing one
- ❌ Commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Rebuilding and verifying the queue for ~312 remaining targets (326 total minus 14
done) is pure arithmetic over already-loaded timestamp data — expect well under a
minute. STOP and investigate if it runs longer.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINT
═══════════════════════════════════════════════════════════════════════════════

After the fix and full re-verification (steps 2-5): STOP, report the backward-step
distribution and any flights that couldn't achieve tolerance, and give the user the
relaunch command. Wait for confirmation before considering this done.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, flag, continue):
- A flight needing several backward steps to find a well-paired cam1 frame — log the
  step count, don't treat it as an error as long as tolerance is eventually met.

Unexpected (STOP immediately):
- A flight where NO frame in cam0's entire valid range has a cam1 partner within
  tolerance — investigate before just skipping it silently, this would suggest a
  bigger problem (e.g. a coverage gap spanning the whole usable range) worth
  understanding, not just working around.
- Any of the 14 already-labelled rows changing value after this fix — would mean the
  "preserve existing labels" logic is broken.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Cam1's target frame is now selected via nearest-real-timestamp matching to cam0's
   candidate, restricted to cam1's valid range, not independently computed
✅ Backward-fallback on cam0's candidate implemented and exercised where needed
✅ Every remaining target's resulting Δt verified against `DEFAULT_MAX_PAIR_GAP_MS`
   (imported, not redefined) — actual numbers shown, not assumed
✅ The 14 already-labelled rows are untouched and still correctly skipped by resume
   logic
✅ No GUI/CSV-schema/navigation behavior changed besides target-frame selection
✅ Existing worklog continued (not a new file), updated in real time
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Read the existing worklog, then stereo_flight_sync_table.py and
   pixel_velocity_correction.py for the reusable pairing logic/constant
2. Fix the target-frame selection in 03_label_final_points.py
3. Verify the 14 existing labels are untouched and still skip correctly
4. Rebuild + verify the queue for all remaining targets, report the numbers
5. Report at the checkpoint with the relaunch command and wait
```