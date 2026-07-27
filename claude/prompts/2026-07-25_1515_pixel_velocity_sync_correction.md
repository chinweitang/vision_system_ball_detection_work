# 2026-07-25 15:15 — Sync audit + pixel-velocity correction for stereo ball flights

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md, then claude/context.md in full (project context —
especially §4.1 capture/timestamps, §4.3 stereo sync, §4.6 error budget term C). Skim
claude/claude_logs/2026-07-23_ball_detection_rate_tuning_worklog.md for the
detector-tuning history this builds on top of (reference only — this task gets its
OWN new log file, see LOGGING below, do not append to that one).

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Build and validate a pixel-velocity sync correction for the free-running stereo
cameras, so that cam0/cam1 ball-centroid detections get aligned to the same real
instant before triangulation — this is error-budget term C
(claude/context.md §4.6: "sync: Δt × ball speed").

Context: the two cameras are NOT hardware-triggered (free-running, §4.3). Each frame
has a real `sensor_timestamp_ns` (captured correctly, confirmed present in every
flight's `timestamps.csv`), but cam0's and cam1's frames are not captured at exactly
the same instant — there's a small residual timing gap between whichever cam0 frame
and cam1 frame you'd naively pair by index. Naively triangulating same-index frames
as if simultaneous introduces an error proportional to (ball's pixel velocity) × (the
timing gap) — exactly term C. `src/stereo/stereo_flight_sync_table.py` already exists
and measures this per flight (offset, jitter, drops) via nearest-timestamp bisect
matching — it has been run for `data/2026_07_15_gym/` (output:
`data/2026_07_15_gym/sync_audit.csv`), where it found the residual DRIFTS almost
linearly across the session (+4.82ms at flight_01 to -6.67ms at flight_60, crossing
zero mid-session) rather than being a fixed per-session constant. It has NEVER been
run against `data/2026_07_21_gym/` — no `sync_audit.csv` exists there yet. Also
important: there is currently NO script anywhere in the repo that triangulates an
actual ball flight (every existing `triangulate_points()` caller works on static
calibration/checkerboard images) — building a minimal one is part of this task, per
decisions below.

**Design decisions already made (do not re-litigate these, they were discussed and
confirmed with the user before this task was written):**
1. Correct **per-flight**, not per-session — re-derive the actual offset from each
   flight's own `timestamps.csv` (same per-flight numbers `stereo_flight_sync_table.py`
   already computes), since the offset is known to drift within a session, not just
   between sessions.
2. Velocity for extrapolation: **simple finite difference** between adjacent *kept*
   (post-filter) detections in the same camera — no smoothing/polynomial fit needed,
   the timing gap being corrected for is sub-frame (a few ms out of ~16.6ms).
3. Correction direction: **always extrapolate whichever frame has the EARLIER
   timestamp forward** to match the later one, using the actual signed Δt for that
   specific pair — NOT a fixed "always correct camera X" rule, since which camera
   leads flips sign mid-session per the drift finding above.
4. Scope **includes** building a minimal flight-triangulation step (using the
   existing `triangulate_points()`) so the correction can be validated quantitatively
   via 3D arc-fit residual, not just visually.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (NEW LOG FILE, REAL-TIME UPDATES)
═══════════════════════════════════════════════════════════════════════════════

This is a new, separate piece of work from the detector-tuning worklog — create a
NEW log file: claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md
(today's date, do NOT append to the 2026-07-23 detector-tuning worklog — that one is
about detection-rate tuning, this one is about stereo sync/timing correction).

Follow the same conventions as the existing worklog (claude/claude_rules.md §10 and
the 2026-07-23 file are the format examples): chronological sections, one per
investigation/decision, each covering what was tried, what was found (including dead
ends and wrong assumptions), why a decision was made, and what's still open.

Update it IMMEDIATELY after each significant step (sync audit run, findings, each
script built, each verification run, checkpoint reached) — not once at the end.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read claude/claude_rules.md, claude/context.md (in full), and skim the detector
   worklog. Then read in full: `src/stereo/stereo_flight_sync_table.py`,
   `src/stereo/triangulate.py`, `src/image_processing/02_adjacent_frame_differencing/
   detector_core.py` (specifically `run_detection()` and `filter_trajectory_outliers()`),
   and the `capture_flights_stereo.py` docstring, so you're working from the actual
   current code, not a re-derived guess of it.

2. **Sync audit of `data/2026_07_21_gym/ball_flights`**: run
   `stereo_flight_sync_table.py`'s `run_session()` (or equivalent invocation) against
   this session. It should produce `data/2026_07_21_gym/sync_audit.csv` and
   `data/2026_07_21_gym/sync_residual_vs_flight.png`, matching the existing
   `2026_07_15_gym` convention exactly (same filenames, same location pattern) — this
   is a NEW file for this session, not an overwrite of anything.
   Report: does this session show the same kind of linear drift as `2026_07_15_gym`,
   or is it closer to a fixed offset? What's the jitter? Any dropped frames? Any
   flights with unusually large residuals worth flagging before building on top of
   this data?

3. **STOP at Checkpoint 1** (see below) and report the audit findings before writing
   any correction code — if this session's sync behavior looks meaningfully different
   from what's assumed above (e.g. jitter much larger than ~11µs, or drops
   concentrated in specific flights), that changes the correction design and needs a
   decision, not a silent assumption.

4. **Build the pixel-velocity correction** (new module, e.g.
   `src/stereo/pixel_velocity_correction.py` — reuse the nearest-timestamp bisect
   matching logic from `stereo_flight_sync_table.py` rather than reimplementing it
   from scratch):
   - Input: one flight's cam0 detections (`{frame_number: (u,v)}`, from a
     `*_detections3.csv`), cam1 detections (same shape), and both cameras'
     `timestamps.csv` rows.
   - Step A — per-camera filtering: run `filter_trajectory_outliers()` on each
     camera's raw detections BEFORE anything else, so artifact detections (e.g. a
     hand) never contaminate the velocity estimate used for correction.
   - Step B — pairing: for each cam0 kept-detection frame, find the nearest-in-time
     cam1 kept-detection frame by actual `sensor_timestamp_ns` (bisect/nearest-match,
     not same-index assumption) — this is the "correctly paired by timestamp" step,
     needed regardless of whether any sub-frame correction is applied afterward.
   - Step C — sub-frame correction: for each paired frame, compute the actual signed
     Δt between the two real timestamps. Whichever frame is earlier gets its centroid
     shifted forward by Δt along its own locally-estimated velocity (finite
     difference between its adjacent kept neighbors, in px/ms, accounting for the
     real frame gap between those neighbors — don't assume neighbors are exactly 1
     frame apart if the filter dropped frames in between). The later frame's centroid
     is left unchanged (it's already the target instant).
   - Output: a corrected, paired point-list ready for `triangulate_points()`.

5. **Build a minimal flight-triangulation script** (e.g. `src/stereo/triangulate_flight.py`)
   since none exists yet: load the right calibration for this session —
   `calibration_outputs/cam0_intrinsics_fisheye.npz` /
   `cam1_intrinsics_fisheye.npz` for intrinsics, and
   **`calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz`** for extrinsics.
   IMPORTANT: there are TWO stereo extrinsic solves for this session —
   `calibration_outputs/2026_07_21/stereo_extrinsic.npz` (top-level, 25/30 pairs,
   baseline 853.76mm, RMS 0.4756px) and
   `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz` (23/24 pairs, baseline
   848.91mm, RMS 0.4087px) — both committed together, 4 minutes apart, no notes
   distinguishing them. **Confirmed with the user: use `test2/stereo_extrinsic.npz`**
   (tighter RMS, baseline closer to the nominal 850mm). Do NOT use the top-level one.
   Run `triangulate_points()` on a given flight under 3 modes for comparison:
   (a) naive same-index pairing, no correction (today's implicit baseline),
   (b) nearest-timestamp pairing only, no sub-frame correction,
   (c) nearest-timestamp pairing + sub-frame velocity correction (steps 4A-C).
   For each mode, fit a smooth quadratic-in-time to each 3D axis (x(t), y(t), z(t))
   and report the residual RMS — camera/stereo frame is fine for this, no need for
   world-frame registration, since a rigid transform doesn't change residual-from-fit
   distances.

6. **Validate** on a handful of representative flights (pick a few spanning
   fast/slow and different points in the session, e.g. using the sync audit's own
   offset range to pick some near-zero-offset and some large-offset flights):
   - Visual: for each camera, plot original vs. corrected centroid positions (a
     trajectory plot is fine — doesn't need to be overlaid on the actual frame image)
     with an arrow/line per point showing the shift vector, so a wrong-direction or
     wrong-magnitude bug is visible immediately. Save these plots to a new, clearly
     separate location — do not touch any existing `analysis_3` folder or contact
     sheets.
   - Quantitative: report the 3-mode residual-RMS comparison from step 5 for each
     validated flight. Expect (b) to fix any gross error from whole-frame slip if
     present, and (c) to further reduce residual roughly in proportion to
     velocity × Δt.
   - Sanity-check the correction magnitudes themselves: they should be small (a
     fraction of one frame's pixel displacement, consistent with Δt being a few ms
     out of a ~16.6ms frame period) and should track the audit's per-flight Δt
     (bigger corrections on flights with bigger measured offset).

7. **STOP at Checkpoint 2** and report the full validation (plots + residual table)
   before declaring this done.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Overwrite or delete anything under `data/2026_07_21_gym/ball_flights/<flight>/`
  — `timestamps.csv`, raw frames, `analysis_3/*_detections3.csv`, existing contact
  sheets are all read-only inputs to this task
- ❌ Overwrite `data/2026_07_15_gym/sync_audit.csv` or
  `sync_residual_vs_flight.png` — those are from a different, already-analyzed
  session; leave them as reference
- ❌ Modify `detector_core.py`, `stereo_flight_sync_table.py`, or `triangulate.py` —
  reuse/import from them, don't change their existing logic
- ❌ Build the full Link B / Pattern A pipeline — this task is scoped to the sync
  correction and just enough triangulation to validate it, not the broader
  detection-error or predictor validation work
- ❌ Attempt world-frame registration for the validation step — camera/stereo-frame
  residuals are sufficient per the design above
- ❌ Use `calibration_outputs/2026_07_21/stereo_extrinsic.npz` (the top-level one) —
  use `test2/stereo_extrinsic.npz` only (see step 5)
- ❌ Commit anything to git
- ❌ Create more than the one new log file named in LOGGING above

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

This is I/O-bound analysis work on already-captured data, not a heavy compute sweep
— nothing here should be slow:
- Sync audit (step 2): reads `timestamps.csv` for all ~163 flights x 2 cams —
  expect under a minute or two, well under the 326-job artifact-audit style sweeps
  from the detector-tuning session.
- Correction module + triangulation script (steps 4-5): normal coding/dev iteration,
  no long-running process expected.
- Validation across a handful of flights (step 6): each flight is a few hundred
  frames at most — expect seconds, not minutes, per flight.

STOP and investigate if any single step runs past ~5 minutes with no output change —
that would indicate something is wrong (e.g. an accidental full-dataset loop where a
single-flight one was intended), not that it just needs more time.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS
═══════════════════════════════════════════════════════════════════════════════

Checkpoint 1 — after the sync audit (step 2-3): STOP, report the offset/drift/jitter/
drop findings for `2026_07_21_gym`, compare to the `2026_07_15_gym` drift pattern,
and wait for confirmation that the correction design (steps 4-6) still makes sense
given what the audit actually shows, before writing the correction code.

Checkpoint 2 — after validation (step 6-7): STOP, report the visual overlay plots and
the 3-mode residual-RMS comparison across the sampled flights, and wait for
confirmation before considering this task done.

Do not proceed past either checkpoint without explicit go-ahead.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log and continue, note it, move on):
- A flight missing `timestamps.csv`, `analysis_3/*_detections3.csv`, or with zero
  kept detections after filtering — skip it, log which flight and why, don't let one
  bad flight abort the whole audit/validation run.
- A handful of dropped/duplicate-timestamp frames in `timestamps.csv` (already known
  to happen occasionally per `stereo_flight_sync_table.py`'s drop-counting logic).

Unexpected (STOP immediately, don't guess a workaround):
- `test2/stereo_extrinsic.npz` failing to load, or a triangulated baseline wildly off
  from ~850mm (would indicate the wrong calibration file or a units/frame-convention
  bug, not noise)
- Nearest-timestamp pairing producing matches with a gap larger than one frame period
  (~16.6ms) for a large fraction of frames — would mean the pairing logic itself is
  broken, not just noisy
- Any exception from `triangulate_points()` itself (e.g. shape mismatch) — this
  points at a bug in how points are being assembled before the call, not something to
  paper over

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ `data/2026_07_21_gym/sync_audit.csv` + `sync_residual_vs_flight.png` exist,
   matching the `2026_07_15_gym` convention, and findings were reported at
   Checkpoint 1 before proceeding
✅ `src/stereo/pixel_velocity_correction.py` implements filter → nearest-timestamp
   pairing → signed-Δt forward correction, reusing existing pairing/filtering logic
   rather than duplicating it
✅ `src/stereo/triangulate_flight.py` can triangulate a flight in all 3 modes
   (naive/paired-only/paired+corrected) using the existing `triangulate_points()`
   and `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz` specifically (not
   the top-level one)
✅ Validation was run on multiple representative flights (not just one), with both
   visual overlay plots and the quantitative residual-RMS comparison, reported at
   Checkpoint 2
✅ Correction shift magnitudes are sanity-checked as small and proportional to the
   audit's measured per-flight Δt — not just "code runs," but "the numbers make
   physical sense"
✅ No existing file under `data/2026_07_15_gym/` or any `data/2026_07_21_gym/ball_flights/
   <flight>/` subfolder was modified
✅ New log file claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md
   created and updated in real-time throughout — the 2026-07-23 detector worklog was
   left untouched
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Create claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md
2. Read claude/claude_rules.md, claude/context.md, and skim the detector worklog
3. Read stereo_flight_sync_table.py, triangulate.py, detector_core.py in full, and
   the capture_flights_stereo.py docstring
4. Run the sync audit against data/2026_07_21_gym/ball_flights
5. Report at Checkpoint 1 and wait
6. Build the correction module and the minimal flight-triangulation script (using
   test2/stereo_extrinsic.npz)
7. Validate on multiple representative flights (visual + quantitative)
8. Report at Checkpoint 2 and wait
```
