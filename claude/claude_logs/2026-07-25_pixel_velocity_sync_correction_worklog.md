# 2026-07-25 - Pixel-velocity sync correction (error-budget term C)

Related session: continues on from `2026-07-23_ball_detection_rate_tuning_worklog.md`
(detector tuning) but is a separate piece of work - stereo timing/sync correction,
not detection rate. New log file per task instructions.

Task prompt: `claude/prompts/2026-07-25_1515_pixel_velocity_sync_correction.md`.

## Setup

- Read `claude/claude_rules.md`, `claude/context.md` in full (particularly SS4.1
  capture/timestamps, SS4.3 stereo sync, SS4.6 error budget term C), and the
  2026-07-23 detector worklog (skim, reference only).
- Read in full: `src/stereo/stereo_flight_sync_table.py`, `src/stereo/triangulate.py`,
  `detector_core.py` (`run_detection`, `filter_trajectory_outliers`), and the
  `capture_flights_stereo.py` docstring/header.

Key facts confirmed from the code (not re-derived/guessed):
- `timestamps.csv` columns: `cam, frame_index, sensor_timestamp_ns` (one row per
  frame per camera, unpaired at capture time - pairing is explicitly deferred
  downstream, per `capture_flights_stereo.py`'s own docstring: "Pairing (nearest
  timestamp) and the ~7 ms residual centroid correction are done downstream in
  triangulate.py, using the per-flight timestamp CSV." - so this task is literally
  implementing what that docstring already promised).
- `stereo_flight_sync_table.py::analyze_flight()` already does: per-camera median
  period + drop detection, nearest-timestamp bisect pairing (cam0 -> nearest cam1),
  median/MAD orphan rejection (5x MAD cutoff), raw offset, whole-frame-slip vs.
  sub-frame residual split, jitter (pstdev of surviving deltas), longest contiguous
  valid-pair run. `run_session(session_dir)` looks under `<session_dir>/ball_flights`
  for every `timestamps.csv`, writes `sync_audit.csv` + `sync_residual_vs_flight.png`
  under `session_dir` (NOT under `ball_flights`).
- `triangulate.py::triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)` - fisheye
  undistort both point sets, `cv2.triangulatePoints` with P1=[I|0], P2=[R|T], returns
  3D points in the cam0 frame. Pure function, no I/O - confirmed nothing in the repo
  currently calls this on a flight (only calibration/checkerboard scripts use it).
- `detector_core.filter_trajectory_outliers(detections, max_speed_px_per_frame=80.0,
  min_run_length=2, max_passes=5)` operates on a `{frame_number: (u,v)}` dict, returns
  the same shape with outliers removed (de-spike then run-split, see its own
  docstring for why simpler approaches were rejected). This is what Step A of the
  correction module needs to call per-camera before pairing.

## Checkpoint 1 - sync audit of data/2026_07_21_gym

Running `stereo_flight_sync_table.py`'s `run_session()` against
`data/2026_07_21_gym` now. Writes new files `sync_audit.csv` +
`sync_residual_vs_flight.png` directly under `data/2026_07_21_gym/` - does not touch
`data/2026_07_15_gym/`'s existing files.

Ran: `python src/stereo/stereo_flight_sync_table.py data/2026_07_21_gym`.
Wrote `data/2026_07_21_gym/sync_audit.csv` (149 rows) and
`data/2026_07_21_gym/sync_residual_vs_flight.png`. Neither file existed before this
run - confirmed with `ls` first.

### Findings - 2026_07_21_gym (149 flights)

- residual range: -8.29 ms to +8.30 ms
- jitter: 5.6-10.9 us, mean 8.42 us
- drops: 0 across all 149 flights, both cams
- longest valid-pair run: 136-181 (worst flight: flight_4, 136/180)
- `whole_frames` is 0 for every single row - the nearest-timestamp bisect match in
  `analyze_flight()` always resolves the correct neighbor by construction, so no
  flight ever needed a whole-frame correction on top of the sub-frame residual.
- TWO apparent "wraps" in the residual sequence: flight_57->58 (-8.16 -> +8.30 ms) and
  flight_136->137 (-8.29 -> +8.21 ms). Diagnosis: NOT a discontinuity in the real
  underlying timing. `raw_offset_ms` is bounded to (-period/2, +period/2) by
  construction, because it comes from nearest-timestamp bisect matching - once the
  true (unbounded) offset drifts past half a frame period, the "nearest" cam1 frame
  silently becomes the next one over, and the reported offset jumps by exactly one
  frame period (here ~16.6 ms, matching -8.16->+8.30 and -8.29->+8.21 almost
  exactly). The underlying drift is monotonic through both wraps (values decrease
  continuously across each wrap when read as a continuous quantity), consistent
  with a single steady drift direction across the whole session, not two separate
  events.

### Comparison to 2026_07_15_gym (existing sync_audit.csv, re-read for this comparison, not re-run)

- 60 flights, residual range -6.67 ms to +4.82 ms (no wrap - never reached the
  half-period boundary), jitter mean 8.76 us, 0 drops, longest_run range 108-181.
- Same qualitative behavior: residual drifts ~continuously across the session
  rather than sitting at a fixed constant. 2026_07_21_gym's session is longer
  (149 vs 60 flights) and its cumulative drift is larger, enough to wrap the
  bounded representation twice, but the underlying phenomenon (slow monotonic
  drift, sub-frame-scale, negligible jitter) is the same.

### Does this change the correction design (Steps 4-6)?

No. The wrap is an artifact of the audit's own per-flight *summary* statistic
(nearest-neighbor-bounded aggregate offset), not a problem for the actual
per-pair correction: Step B pairs each individual cam0 detection with its nearest
cam1 detection by real `sensor_timestamp_ns`, and Step C computes the actual signed
Delta-t directly from those two real timestamps - it never goes through the
audit's bounded/wrapped summary number at all. Decision #1 (correct per-flight,
re-derived from each flight's own timestamps, not a fixed session constant) already
covers this. Proceeding as designed.

**CHECKPOINT 1 - reported to user, waiting for go-ahead before building the
correction module (Step 4).** User said "continue" - proceeding to Step 4.

## Step 4 - src/stereo/pixel_velocity_correction.py

Built `load_detections3()`, `_local_velocity_px_per_ms()` (finite difference
between nearest surviving neighbors in real time, one-sided at run ends, None
if isolated), `build_corrected_pairs()` (Step A: `filter_trajectory_outliers`
per camera -> Step B: nearest-timestamp bisect pairing, reusing
`stereo_flight_sync_table.load_timestamps` -> Step C: shift whichever
timestamp is earlier forward by the pair's actual signed delta-t along its
own local velocity).

## Step 5 - src/stereo/triangulate_flight.py

First script in the repo to triangulate an actual ball flight (confirmed
during setup that none existed). `naive_pairs()` (mode a, same-index, RAW
detections), `paired_only()` (mode b, nearest-timestamp on filtered
detections, no correction), plus mode (c) via `build_corrected_pairs()`.
Degree-2 polyfit per 3D axis vs time, RMS residual per axis + overall.
Loads `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz` specifically
(confirmed baseline recovers 848.91 mm, matching the pre-recorded value) -
NOT the top-level `stereo_extrinsic.npz`, per the task's explicit instruction.

### Bug found and fixed before trusting any numbers

First test (flight_5) gave `paired_only` overall_rms=3385 mm - wildly worse
than `naive` (29.7mm) or `corrected` (44.4mm), which shouldn't happen and
matched the task's own listed "unexpected" red flag (bad-gap pairing).
Diagnosis: cam1's trajectory filter dropped frames 76-78 (coverage gap, not a
filter bug), so cam0 frames 76/78/80/85/89 had no genuine simultaneous cam1
partner nearby in time. Nearest-timestamp bisect still returned *something*
(frame 79, reused for 3 different cam0 frames, gaps up to 166ms) rather than
rejecting a bad match - my pairing code had no maximum-gap guard.

Fix: added `max_pair_gap_ms` cutoff to both `build_corrected_pairs()` and
`triangulate_flight.paired_only()`. First tried 25ms (~1.5x the ~16.6ms frame
period, copying `stereo_flight_sync_table.py`'s DROP_GAP_FACTOR convention) -
this was still wrong, since 1.5x-period is a threshold for detecting dropped
frames *within one camera's own sequence* (a different problem), not for
judging whether a cross-camera match is genuine. At 25ms, 3 of flight_5's 18
naive matches (76, 78, 80 - all ~16-17ms gaps, just under 25ms) were still
silently reused against the same stale cam1 frame 79. Correct threshold is
half the frame period (~8.3ms, matching exactly why the sync audit's own
raw_offset is bounded to that range) - set `DEFAULT_MAX_PAIR_GAP_MS = 8.5`.
Re-tested flight_5: paired_only dropped to 12 clean pairs (all ~0.2ms gaps,
matching the audit's measured raw offset for this flight), overall_rms=29.71mm
- identical to naive, exactly as expected for a flight with a near-zero
(+0.19ms) offset.

### Step 6 - validation (src/stereo/validate_sync_correction.py)

7 flights spanning the audit's offset range: flight_92 (-0.02ms), flight_5
(+0.19ms), flight_100 (-1.31ms), flight_20 (-2.18ms), flight_110 (-4.28ms),
flight_120 (-5.76ms), flight_60 (+7.92ms). (flight_50/flight_130 from the
original pick either had too few detections or no analysis_3 folder at all -
skipped, substituted flight_100/flight_110/flight_120, all with adequate
cam0/cam1 detection counts.)

Writes to NEW folder `data/sync_correction_validation/` (shift-vector plots
per flight + `residual_comparison.csv`) - does not touch any existing
analysis_3/contact-sheet output.

Results (overall RMS, mm, camera/stereo frame - see full table in
residual_comparison.csv):

| flight | audit offset (ms) | naive | paired_only | corrected | n |
|---|---|---|---|---|---|
| flight_92  | -0.02 | 15.43 | 15.43 | 15.35 | 6  |
| flight_5   | +0.19 | 29.71 | 29.71 | 28.96 | 12 |
| flight_100 | -1.31 | 39.98 | 39.98 | 40.31 | 5  |
| flight_20  | -2.18 | 39.72 | 39.72 | 41.67 | 8  |
| flight_110 | -4.28 | 44.08 | 28.74 | 32.95 | 10 |
| flight_120 | -5.76 | 28.87 | 28.87 | 28.98 | 6  |
| flight_60  | +7.92 | 29.86 | 22.16 | 18.80 | 9  |

Shift-magnitude sanity check (mean/max px shift applied to the earlier-timestamp
point, per flight): tracks the audit's |offset| as expected - flight_92
0.02/0.03px, flight_5 0.32/0.34px, flight_100 1.29/1.44px, flight_20
2.97/3.27px, flight_110 3.53/5.42px, flight_120 7.05/7.87px, flight_60
9.74/11.60px. All sub-frame-scale, none implausibly large. Visual shift plots
(flight_60, flight_110) confirm shift direction is consistent with each
flight's own direction of travel - no wrong-sign/wrong-axis bug visible.

### Honest finding: correction does not uniformly help at low point counts

flight_60 (n=9, largest offset, best coverage) is the clean win the design
predicted: naive 29.86 -> paired_only 22.16 -> corrected 18.80mm, monotonic
improvement, consistent with "bigger correction, bigger gain."

But flight_20 (n=8), flight_100 (n=5), flight_110 (n=10) all show `corrected`
performing *worse* than `paired_only` (flight_110 still much better than
`naive`, but the sub-frame step itself regresses slightly on top of the
pairing gain). flight_120 (n=6) is a wash. Likely cause: the local
finite-difference velocity estimate is single-pair-of-neighbors, no
smoothing (deliberate design choice #2, since the correction itself is
sub-frame-scale) - with only 5-11 kept points in a flight, one noisy
neighbor-velocity estimate has more room to overshoot than it would with
denser data. The z-axis (camera depth, ~matches the world-frame width/weak
axis per context.md SS4.8) dominates overall_rms in every row and is also
where most of the swing between paired_only and corrected shows up - not a
sign of a directional bug (shift plots look correct), just the weak axis
amplifying whatever noise is in the correction on sparser flights.

Not treating this as a bug to fix silently - flagging it as an open finding
for Checkpoint 2, since it changes how confidently "corrected" should be
recommended as the default mode for low-detection-count flights specifically.

**CHECKPOINT 2 - reported to user, waiting for confirmation.**

## Bug found: wrong detections source - rerun with tuned detections

New task prompt: `claude/prompts/2026-07-25_2101_sync_correction_rerun_tuned_detections.md`.
Continuing this same worklog, not a new file, per that prompt's instruction.

Confirmed the claimed bug directly before touching any code:
`data/2026_07_21_gym/ball_flights/flight_5/analysis_3/flight_5_cam0_detections3.csv`
has 19 lines (18 data rows) vs.
`data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/2026_07_21_gym/flight_5_cam0_detections.csv`
has 37 lines (36 data rows) - matches exactly. Confirmed the tuned-detections folder
has 252 files = 126 flights x 2 cams (matches the stated 126/149 availability).
`analysis_3` is genuinely the stale pre-tuning baseline; the correct source is the
final-tuned (MIN_AREA=30, mask v4, trajectory filter, full-163-flight run)
`detector_tuning/detections/...` folder. Same `frame_number,u,v` column format,
confirmed via `head`.

Fix: added `TUNED_DETECTIONS_DIR` + `tuned_detections_paths(flight_name)` to
`triangulate_flight.py` (returns None if a flight has no file there), and changed
`triangulate_flight()` to source `cam0_csv`/`cam1_csv` from that helper instead of
globbing `analysis_3/*_detections3.csv`. Left `pixel_velocity_correction.py`
untouched - `build_corrected_pairs()` already takes the CSV paths as plain
arguments, so it doesn't care which folder they come from; only the caller
(`triangulate_flight.py`) needed to change. Updated `validate_sync_correction.py`'s
pre-flight availability check to use `tuned_detections_paths()` instead of checking
for an `analysis_3` directory.

Code fix applied: `triangulate_flight.py` (added `TUNED_DETECTIONS_DIR`,
`tuned_detections_paths()`, changed `triangulate_flight()`'s path derivation, raises
`FileNotFoundError` for a missing flight instead of the old silent `next()`
`StopIteration` - already caught by `validate_sync_correction.py`'s existing
try/except, so missing flights skip+log rather than crash, no new error handling
needed there). `validate_sync_correction.py`: swapped the `analysis_3`-directory
check for `tuned_detections_paths()`, changed `OUT_DIR` to
`data/sync_correction_validation_tuned_detections/` (new folder, original
`sync_correction_validation/` untouched). `pixel_velocity_correction.py` left
completely unmodified, as expected - it only takes CSV paths as arguments.

Next: re-picking the validation flight sample against tuned-detections
availability.

Checked availability: 126/149 flights have tuned-detections output (matches the
task's stated count). **flight_50 IS available under tuned detections** (was
excluded from the original 7 only for lacking adequate `analysis_3` data) -
confirms the original substitution was itself a symptom of this same bug.
flight_130 is still unavailable (genuinely one of the 23 flights never run through
the tuned production pipeline, not a naming/path issue).

Decision: reuse the exact same 7 flights from the original validation
(flight_92, flight_5, flight_20, flight_100, flight_60, flight_110, flight_120) -
all 7 confirmed available under tuned detections too - plus add flight_50 back in
now that it has real data. This gives a clean apples-to-apples before/after
comparison on identical flights (spanning the full -8.29 to +8.30ms offset range
already) rather than introducing a differently-composed sample, while still
directly answering the flight_50 question. 8 flights total, within the
recommended 7-10 range.

Running validate_sync_correction.py now with the tuned-detections source and the
8-flight sample, output to data/sync_correction_validation_tuned_detections/.

### Results - tuned detections

Point counts jumped as expected (n=36-90 vs the old n=5-12) - the path fix worked.
But the residual-RMS story did NOT simply improve. Full table in
`data/sync_correction_validation_tuned_detections/residual_comparison.csv`; headline
numbers:

| flight | old n (analysis_3) | new n (tuned) | old best mode (rms) | new naive | new paired_only | new corrected |
|---|---|---|---|---|---|---|
| flight_92 | 6 | 74 | 15.35 (corrected) | 32.83 | 32.83 | 32.83 |
| flight_5 | 12 | 36 | 28.96 (corrected) | 31.05 | 31.05 | 31.01 |
| flight_20 | 8 | 50 | 39.72 (naive/paired) | 40.71 | 40.71 | 41.84 |
| flight_100 | 5 | 83 | 39.98 (naive/paired) | 56.08 | 56.08 | 56.85 |
| flight_60 | 9 | 89-90 | 18.80 (corrected) | 37.28 | 53.87 | 48.12 |
| flight_110 | 10 | 74-75 | 28.74 (paired_only) | 52.33 | 41.48 | 44.06 |
| flight_120 | 6 | 84 | 28.87 (naive/paired) | 42.68 | 42.68 | 43.76 |
| flight_50 | (not in original 7) | 78-81 | - | 657.42 | 552.31 | 577.05 |

Every flight's overall RMS got WORSE with more/denser points, not better - and
flight_60 actively reversed: before, both paired_only and corrected beat naive; now
naive beats both. flight_50 is a severe outlier (657mm - 10-20x every other flight).

**Investigated before reporting, not assumed:**
- Checked whether the point-count jump was just density or also DURATION (frame
  span): confirmed it's both. flight_60 old span was frames 101-128 (27 frames,
  late-flight only); new span is 37-128 (92 frames - nearly the WHOLE visible
  flight, consistent with the whole point of the detector-tuning project - recall
  went from ~20% baseline to ~97%). Same pattern on flight_92, flight_50.
- This matters: `fit_quadratic_residual_rms()` fits ONE degree-2-in-time polynomial
  across the ENTIRE set of points per flight. A pure quadratic-in-time is the
  drag-free physics approximation - context.md SS5 models gravity + drag together
  (drag depends on |v|). Fitting a driftless parabola across a short late-flight
  segment (old data) is a much better local approximation than fitting the same
  bare quadratic across the full rise-apex-descent arc (new data). So the residual
  increase across EVERY mode, on EVERY flight, is very likely dominated by "the fit
  model is now wrong for a longer arc" - not by anything about pairing or
  correction. This directly confounds the intended comparison.
- Checked flight_50 specifically for an obvious cause (a single bad/outlier
  detection slipping through the per-camera trajectory filter, same class of bug as
  the flight_12/cam1 hand-pickup case found earlier this session): printed
  frame-by-frame speed between consecutive kept cam0 points - no jump, smooth
  17-31 px/frame increase throughout, consistent with genuine acceleration through
  the frame (foreshortening near the camera). Checked u-span too (widest of the
  sample at 1194.6px vs 815-1024px for the others) - wider, but not 10-20x wider,
  so arc length alone doesn't explain a 10-20x residual jump either. Root cause not
  yet found - not ruling out a stereo cross-camera pairing problem specific to this
  flight (each camera's own 2D trajectory looks smooth individually; a triangulation
  problem would only show up in the combined 3D result, which is exactly what's
  bad here). Flagging as unresolved rather than guessing further.

**Conclusion so far**: the original "correction hurts at low point count" finding
did NOT resolve with denser data - if anything the picture got more mixed (flight_60
flipped direction entirely). But I don't think this new data supports concluding
the correction method itself is bad, either - the comparison is now confounded by a
bigger, unanticipated problem: fitting one whole-arc quadratic per flight is
increasingly a poor model as the tuned detector's much wider frame coverage makes
"the whole arc" a much longer, more curved, more drag-affected span than the
original short-segment test covered. This wasn't anticipated by the rerun task
(which expected the finding might simply resolve with more points) - reporting
before drawing any conclusion or making a gating/smoothing decision.

### flight_50 root cause found (user-prompted)

User was looking at a contact sheet named `2026_07_15_gym_flight_50_cam1_contact.png`
and suspected a hand-pickup artifact - flagged first that this is a DIFFERENT
session's flight_50 (session/flight-number collision, same one
`10_run_full_dataset.py` had to handle via session-qualified IDs) - the sync-
correction task has only ever touched `2026_07_21_gym`'s flight_50. But re-checked
the suspicion against the correct flight/session anyway, since I'd only checked
cam0's smoothness before, never cam1, and never looked at an actual image.

Checked cam1's kept-point speed sequence for `2026_07_21_gym/flight_50`: frame
115->116 jumps from (1369.5, 681.8) to (263.4, 799.5), speed=1121.6 px/frame (vs.
9-29 px/frame everywhere else in the flight) - then frames 117-123 continue
smoothly from the NEW location. Cropped and viewed
`data/detector_tuning/contact_sheets/03_stride1_thresh16_openk3_area30_circ0.3/
2026_07_21_gym_flight_50_cam1_contact.png` frames 112-121 to confirm visually:
frames 112-115 show the real ball (small dot, top-right, drifting steadily);
frame 116 onward locks onto the person crouched by the fence barrier, bottom-left,
tracked as if it were the ball through frame 121+.

Root cause: NOT a single-frame spike (which `filter_trajectory_outliers`'s de-spike
pass would catch) - the person's hand/arm forms its OWN internally-smooth run
(116-123, 8 frames), long enough to clear `min_run_length=2`, so the run-splitting
step keeps it as a legitimate second segment rather than rejecting it. This is the
same failure mode as the flight_12/cam1 hand-pickup case found earlier in the
detector-tuning session (`2026-07-23_ball_detection_rate_tuning_worklog.md`) - there
it only showed up as a visual contact-sheet annoyance; here it's the first time it's
actually corrupted a downstream quantitative fit (triangulating ball+person together
as one "flight").

This explains flight_50's 657mm outlier specifically, but does NOT explain why
every OTHER flight also got worse (checked cam0 on flight_60/flight_92 earlier -
smooth throughout, no jump) - that remains the separate whole-arc-quadratic-fit
mismatch. Two distinct, stacked problems, not one:
  1. Fit methodology (all flights) - single quadratic over a full arc is a worse
     model now that detections span the whole flight, not a short segment.
  2. Trajectory-filter gap (specific flights, flight_50 confirmed) - a false
     positive that sustains >= min_run_length frames of its own smooth motion is
     indistinguishable, to the current filter, from a real second segment.

Reported both to user with root cause for #2. Still not deciding next steps -
holding at the checkpoint.
