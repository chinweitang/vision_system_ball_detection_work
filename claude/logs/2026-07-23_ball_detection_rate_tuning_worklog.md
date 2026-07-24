# Ball detection rate tuning — worklog

Task: improve the stereo 3-frame-diff ball detector's detection rate
(`src/image_processing/02_adjacent_frame_differencing/04_stereo_three_frame_diff.py`),
which was averaging ~15-20% combined (co-detected in both cams) detection
rate across curated `ball_in_frame` flights in `2026_07_15_gym` and
`2026_07_21_gym`.

## Baseline

- Default params: `STRIDE=1, DIFF_THRESHOLD=20, OPEN_KERNEL=7, CLOSE_KERNEL=30,
  MIN_AREA=200, MAX_AREA=50000, MIN_CIRC=0.3`.
- `data/2026_07_21_gym/ball_flights/detection_rate_summary.csv` avg combined_rate:
  0.151 (126 flights). `2026_07_15_gym`: 0.198 (37 flights).
- One flight has hand-labeled ground truth (manually clicked ball centroids):
  `data/2026_07_15_gym/ball_flights/2 ball contacts ground before plane/flight_01/`
  (`labels_uv.csv`, `flight_01_cam{0,1}_labels.csv` — 27 labeled frames/cam,
  with diameter_px). This flight had already been hand-tuned to ~96% combined
  detection rate and does NOT represent the rest of the dataset (confirmed:
  optimizing against it alone doesn't generalize).

## Diagnosis 1 (WRONG, corrected) — thought it was exposure

Initially inspected `flight_126` (0% combined rate) contact sheets at
600px-wide thumbnail scale and concluded the frames were badly underexposed
(back/fwd diff panels looked all-black). This was WRONG — cropping the same
frames at native resolution around the ball's actual location showed good
local contrast (ball ~90-115 grey vs ~40 background). The "all black" read
was an artifact of viewing a tiny scaled-down thumbnail. Lesson: verify any
visual read against numeric pixel stats before trusting it.

Cross-checked against `data/2026_07_15_gym/exposure_sweep/results/
exposure_summary.csv` (exp1000/1500/3000/5000, gain 4.0): confirmed user's
original choice of exp1000 was sound — at exp5000 a person walking through
frame is clearly, continuously visible (`sweep3_exp5000_gain4.0_cam0_ballcrops.png`),
which would contaminate the diff-based detector with a second moving object.
exp1000 keeps the person mostly invisible while the ball still has usable
contrast.

## Diagnosis 2 (correct) — weak diff signal near-zero relative motion

Numerically checked back/fwd diff magnitude at the ball's known location in
`flight_126` frame_090 (cam0): max diff back=10, fwd=5, min-diff pixels above
threshold(20) = 0. The ball has good ABSOLUTE contrast but very little
FRAME-TO-FRAME displacement at this instant (likely near apex / motion partly
along camera depth axis), so the 3-frame min-diff technique (which relies on
displacement to distinguish object from background) produces almost no
signal there — not fixable by threshold/kernel tuning for that specific
instant, it's a structural blind spot of differencing.

## Plan agreed with user

Order to tune: STRIDE first (fixes near-zero-motion blind spot) → then
DIFF_THRESHOLD + OPEN_KERNEL jointly (mask generation) → MIN_AREA/MIN_CIRC
last (candidate filtering) → static background subtraction only if the above
plateaus (not attempted yet).

Metric: `combined_rate` (co-detected same frame, both cams) across a 10-flight
sample spanning both sessions and the full existing rate range, NOT pure
recall-on-the-one-labeled-flight (already overfit/saturated there). Labeled
flight's recall kept as a secondary regression check (must not get worse).

Discarded idea: "false positive proxy via detections outside `ball_in_frame`"
— invalid, since the user deliberately excluded some in-frame-ball content
(e.g. post-bounce) from `ball_in_frame`, so that complement is NOT a
guaranteed no-ball region.

## 10-flight sample (chosen from detection_rate_summary.csv, spread across rate/session)

- `2026_07_15_gym/2 ball contacts ground before plane/flight_01` (0.960, labeled)
- `2026_07_15_gym/flight_22` (0.000), `flight_55` (0.643)
- `2026_07_21_gym/flight_126` (0.000), `flight_47` (0.000), `flight_59` (0.021),
  `flight_53` (0.100), `flight_60` (0.130), `flight_33` (0.188), `flight_84` (0.731)

## Infrastructure built

- `src/image_processing/02_adjacent_frame_differencing/detector_core.py` —
  detection logic extracted from `04_stereo_three_frame_diff.py` into an
  importable, parameterized function. Verified byte-for-byte identical output
  vs. the original script at default params on flight_1 before trusting it.
- `src/image_processing/02_adjacent_frame_differencing/06_param_sweep.py` —
  grid search (STRIDE x DIFF_THRESHOLD x OPEN_KERNEL, 48 combos) over the
  10-flight sample, parallelized via `ProcessPoolExecutor` (plain OS
  parallelism, not subagents — this is a deterministic repeated-script task,
  not a reasoning task).
- Output: `data/detector_tuning/sweep_results.csv`,
  `data/detector_tuning/inspection_crops/` (real files in the repo, not the
  ephemeral session scratchpad — first pass mistakenly saved crops to the
  scratchpad, which the user can't see/browse; corrected).

## Sweep gotcha: pure combined_rate ranking is gameable

Top-ranked config by raw `avg_combined_rate` was `stride=2, thresh=8,
open_k=3` -> combined_rate=1.000, but `labeled_recall` for that config was
only 0.556 (down from baseline 0.907) — i.e. it was firing on nearly every
frame, not finding the ball more often. Fixed ranking to a recall-GATED
approach: filter to configs where `labeled_recall >= baseline (0.9074)`,
THEN rank by `avg_combined_rate`. Only 6/48 configs passed the gate. Top
survivor: `stride=1, thresh=16, open_k=3` -> combined_rate=0.874,
recall=0.926.

`data/detector_tuning/sweep_results.csv` rebuilt with `meets_recall_gate` /
`is_baseline` columns, sorted gate-passing-first then by combined_rate.

## Visual inspection of the "winning" config found 2 more real problems

1. Cropped `flight_126` cam0 frames 41/44/47 (candidate config) — position
   nearly identical every 3rd frame (~1322,390), breaking an otherwise
   smooth real trajectory. Crop confirmed: NOT the ball, a static wall-corner
   structural edge. This sits just 14px outside an existing exclusion
   rectangle for cam0 (`src/image_processing/exclusion_mask.py`,
   `x in [1000,1456], y in [0,375]`).
   - Verified before extending: checked EVERY existing cam0 detection
     (both sessions, default params) for hits in candidate extension zones.
     `x in [1000,1456], y in [375,450]` had 4 real-looking hits (e.g.
     flight_14 frames 109->110, smooth motion, x~1024-1038) — extending the
     FULL x-range down would have clipped real ball detections.
     `x in [1270,1456], y in [375,425]` had ZERO hits — safe, narrow fix.
   - Added as a SECOND rectangle for cam0 in `EXCLUSION_TRIANGLES` (not
     modifying the existing one). `exclusion_mask.py` updated to support a
     list of polygons per cam (was single-polygon only).
2. Re-ran flight_126 cam0 after the mask fix — a DIFFERENT static artifact
   immediately took over the same frames (41/44/47 now at a new fixed
   location ~1150,635). Cropped it: an exit sign (reflective running-person
   + arrow icon). Confirms whack-a-mole risk of exclusion-mask patching
   alone — motivated building a general trajectory-consistency filter
   instead of / in addition to more masking.
   - Crops saved: `data/detector_tuning/inspection_crops/
     flight126_cam0_frame042_true_ball.png` (real ball, confirmed),
     `flight126_cam0_frame041_false_positive.png`,
     `flight126_cam0_frame044_false_positive.png` (wall corner, pre-mask-fix),
     `flight126_cam0_frame041_false_positive_2.png` (exit sign, post-mask-fix).

## Trajectory-consistency filter — 3 iterations to get right

Added `filter_trajectory_outliers()` to `detector_core.py`. Two earlier
versions were built, tested against known-good/known-bad frames, and
rejected:

1. **Global degree-2 polyfit + iterative residual trim.** Fit one parabola
   to u(frame)/v(frame) across the whole flight, drop residual outliers,
   refit, repeat. FAILED: on `flight_59`/`flight_53`/`flight_84` cam1, this
   collapsed to ZERO kept detections. Cause: with a high enough fraction of
   severe outliers in the raw data, the very FIRST least-squares fit gets
   pulled badly off course by them (ordinary least squares has no outlier
   resistance), and can misclassify nearly everything as an outlier in one
   bad pass with no way to recover.
2. **Local position-median vs. neighbors.** Compare each point to the median
   position of its ~5 nearest neighbors (by index), reject if too far.
   FAILED: falsely rejected real, confirmed ball detections early in
   `flight_126` (frames 39-56) — near the start of a fast-moving trajectory,
   the ball's OWN genuine displacement across a 10-point neighbor window
   (real velocity ~15-20px/frame) was larger than the rejection tolerance,
   PLUS edge-of-sequence asymmetric windows let a minority of interspersed
   artifacts skew the local median enough to fail the real point too.
3. **De-spiking + speed-bounded run split (current, working).** Physical
   argument: a real ball has a bounded frame-to-frame pixel speed; an
   isolated static artifact creates an implausible jump both INTO and OUT OF
   itself. Repeatedly (up to 5 passes) finds a single point whose neighbors
   look implausible relative to it, but whose surrounding points would
   reconnect at a plausible speed if this ONE point were skipped, and drops
   just that point (de-spike). Only after de-spiking, splits any remaining
   implausible jump into runs and keeps runs >= `min_run_length` (default 2).
   - First version of this (run-split WITHOUT the de-spike pre-pass,
     `min_run_length=3`) also failed: with artifacts every ~3 frames, the
     real trajectory fragments into many 2-point runs, each individually
     shorter than min_run_length, and got discarded along with the actual
     artifacts. De-spiking first (compare skip-distance, not just adjacent
     distance) fixes this.
   - Verified: `flight_126` cam0 — all real frames 39,40,42,43,45,46,48,49,
     51,54,55,56 kept; all known artifact frames 41,44,47,50,53,81,118,121,
     122 removed. `flight_59`/`flight_53`/`flight_84` cam1 no longer
     collapse to zero (17-74 kept out of 26-86 raw, reasonable).
   - Constants used: `max_speed_px_per_frame=80` (real observed speeds in
     this dataset run ~5-30px/frame; known false-positive jumps are
     300px/frame+, large margin either side), `min_run_length=2`.
   - Confirmed via user: `ball_in_frame` folders never include a bounce (the
     curated range is a single continuous arc), so no need to handle
     multi-segment/direction-reversal trajectories from bounces.

## Result after mask fix + working trajectory filter (candidate config: stride=1, thresh=16, open_k=3)

- Naive candidate-config-only combined_rate (before mask fix / filter) was
  0.874 — this number was INFLATED by the false positives above (confirmed:
  after cleaning them out, corrected rate dropped to ~0.50, then to 0.755
  once the trajectory filter was fixed to actually work — see below).
- Final validated numbers across the 10-flight sample
  (`data/detector_tuning/candidate_config_validated_results.csv`):
  **avg_combined_rate = 0.7549** (baseline 0.2772, ~2.7x), **labeled_recall =
  0.9259** (baseline 0.9074, holds/slightly improves). No flight collapsed
  to zero; per-flight rates ranged 0.53-1.00, all plausible.
- Config: `stride=1, diff_threshold=16, open_kernel=3, close_kernel=30,
  min_area=200, max_area=50000, min_circ=0.3` + updated
  `exclusion_mask.py` (cam0 second rectangle) + `filter_trajectory_outliers`
  (max_speed_px_per_frame=80, min_run_length=2).

## Full-dataset artifact audit (in progress)

User asked whether to do a manual visual audit of cam1 (only cam0 had been
closely inspected) or make results inspectable by the user too. Decided on a
scalable approach instead of manually scrolling contact sheets flight-by-
flight: since the rig is fixed, a genuine static artifact recurs at nearly
the same pixel location across MANY DIFFERENT flights, while incidental
noise scatters. Built `src/image_processing/02_adjacent_frame_differencing/
07_artifact_audit.py`:
- Runs the candidate config (stride=1, thresh=16, open_k=3) across ALL 163
  flights (both sessions) x both cams.
- Pools every point `filter_trajectory_outliers` rejected, per cam, across
  the whole dataset.
- Bins rejected points spatially (40px bins) and ranks bins by number of
  DISTINCT FLIGHTS contributing a point there (not raw point count, so one
  flight with a long-lived artifact can't masquerade as a multi-flight
  recurring one) - hotspots need >= 3 distinct flights to qualify.
- Outputs `data/detector_tuning/artifact_audit_hotspots.csv` (ranked
  hotspots: cam, bin center, distinct_flights, total_points, one example
  flight/frame/u/v) and one representative crop per hotspot in
  `data/detector_tuning/inspection_crops/` (named
  `hotspot_<cam>_u<u>_v<v>_<flight>_frame<NNN>.png`) for both the user and
  Claude to visually confirm before deciding whether each needs an
  exclusion-mask fix.
- Parallelized with `ProcessPoolExecutor` (163 x 2 = 326 flight/cam jobs),
  run in background - results not yet reviewed as of this worklog entry.

## Full-dataset artifact audit — results

`data/detector_tuning/artifact_audit_hotspots.csv` (13 hotspot bins, >=3
distinct flights each). Visually inspected the crops
(`data/detector_tuning/inspection_crops/hotspot_*.png`) for all the large
ones. Note: the inspection crop filenames/content were initially confusing
to the user (`_true_ball` vs `_false_positive` wasn't obvious without
reading the name) - flagged for future improvement (add in-image text
labels, not yet done).

**3 confirmed real static artifacts** (visually verified, huge distinct-
flight counts - not plausibly coincidence):
- **cam1 wall corner/edge**, bins (1380,420) + (1420,420) = 173 combined
  flight-instances (113+60). The dominant false-positive source overall.
- **cam0 exit sign** (same fixture found earlier in flight_126, now
  confirmed dataset-wide), bin (1140,620) = 76 flights. Adjacent smaller
  bins (1180,620)=12, (1100,620)=9, (1060,620)=5 in the same v-row are
  likely this sign's glow/edges spreading into neighboring bins - need the
  real point-cloud bounding box, not just bin centers, before sizing an
  exclusion zone (in progress, see below).
- **cam0 wall-mounted fixture/panel pair**, bins (1020,660)+(1060,660) = 84
  combined flight-instances (42+42).

**Important side-finding**: the cam0 fixture's screen position (u~1020-1060)
overlaps the U-RANGE that the real ball's descending trajectory passes
through in some flights (same horizontal region, different vertical band).
Checked `flight_1` cam0 frames 148-162 in detail: this interleaves fixture
hits (148,149,150,153: v~644-677, barely moving) with real descending-ball
hits (151,152,155,156,157,158,159,161,162: v climbing 716->902). The
CURRENT trajectory filter got confused here - it wrongly REJECTED real ball
frames 152/155/156 while KEEPING several fixture hits, because de-spiking
only compares immediate list-neighbors regardless of which cluster they
belong to, and this contaminated region has both clusters interleaved.
Conclusion: relying on the trajectory filter alone to sort out this specific
fixture is not enough - it needs to be excluded UPSTREAM via the exclusion
mask so it never becomes a candidate, which should also recover frames like
155 as genuine detections rather than losing them to filter confusion.

**Small/ambiguous hotspots (3-4 distinct flights) - NOT flagged for masking
without individual review**: e.g. cam0 (1060,780)/flight_1/frame155 crop
looked genuinely ball-shaped (round, highlighted, shadow crescent) - turned
out on inspection to BE the real ball (see side-finding above), not a static
artifact. With only 163 flights and broadly similar throw setups across a
session, a few flights' real trajectories coincidentally passing through
similar screen space is plausible and should not be masked out - masking
low-count hotspots risks clipping real detections for little benefit. Only
the 3 high-confidence ones above are being acted on.

User confirmed: proceed with exclusion-mask additions for the 3 confirmed
artifacts (with the same "zero real detections in candidate zone across all
existing analysis_3 data" safety check as the first fix), then re-run the
10-flight sample and generate contact sheets in
`data/detector_tuning/contact_sheets/` for manual visual review.

## Exclusion mask additions — bounding boxes, gotcha, and resolution

First attempt: sized exclusion boxes directly from the raw bounding box of
ALL rejected points near each artifact's approximate seed location (radius-
100px pool around each, across all 163 flights x cam0/cam1, computed via
`bbox_probe.py` in the scratchpad - first ran sequentially/too slow,
re-parallelized with ProcessPoolExecutor). Result: `cam1_wallcorner` u=
[1394,1439] v=[407,431] (tight, clean); but `cam0_exitsign` u=[1043,1187]
v=[572,650] and `cam0_fixture` u=[1003,1090] v=[624,733] were suspiciously
WIDE.

Safety-checked all 3 against every existing analysis_3 detection (both
sessions, default params): wallcorner zone = 0 hits (safe), but
`exitsign` zone = 12 real hits, `fixture` zone = 54 real hits. Root cause:
the raw rejected-point pool for these two was CONTAMINATED by the same
false-rejection bug found in flight_1 (real ball frames like 152/155/156
get mis-rejected by the trajectory filter when a static artifact's u-range
overlaps the real trajectory's u-range) - those wrongly-rejected real points
got pooled in as if they were artifact points, inflating the apparent
footprint to something much bigger than the actual physical object.

Fix: re-pooled with FINER 15px bins and ranked by distinct-flight-count to
find the dense CORE cluster (a real ~6x8cm sign/panel shouldn't have its
detected centroid vary by 150px - the true recurring core is much tighter).
Found:
- `cam0_exitsign` true core: u=[1128,1158] v=[631,640] (41+33 distinct
  flights in the top 2 dense bins)
- `cam0_fixture` true core: u=[1021,1031] v=[645,652] (39 distinct flights)
- a third, smaller cam0 cluster at u=[1043,1054] v=[641,650] (10-26 distinct
  flights) shared between both search radii - not visually identified as a
  specific object yet, but same recurrence signature.

Re-verified all 4 final (padded) zones against every existing detection:
**zero hits for all 4.** Added to `exclusion_mask.py`:
- cam1: `x in [1380,1456], y in [395,445]` (wall corner)
- cam0: `x in [1115,1165], y in [615,648]` (exit sign)
- cam0: `x in [1010,1040], y in [638,655]` (fixture/panel)
- cam0: `x in [1040,1057], y in [638,650]` (third small cluster)

Refactored `detector_core.py` to split `_detect_in_pair` into public
`compute_mask()` and `extract_candidates()` (needed for the contact-sheet
generator's per-frame visualization) - re-verified byte-identical detection
output on flight_1 cam0 after the refactor (still 82 detections, same
frames) before trusting it.

**Verification of the fix:**
- `flight_1` cam0 frames 148-162: ALL now kept, forming one single smooth
  continuous descending trajectory (v: 667->902). The fixture's
  contaminating hits are gone and the previously-mis-rejected real frames
  (152, 155, 156) are recovered - confirms the "exclude upstream, don't rely
  on the filter to sort it out" fix worked as intended.
- `flight_126` cam0: raw count (82) now EQUALS filtered count (82) - the
  trajectory filter has nothing left to reject; both known artifacts are
  excluded before ever becoming candidates.

**Final validated numbers, 10-flight sample** (candidate config + exclusion
mask v3 [4 new zones] + trajectory filter):
**avg_combined_rate = 0.8552** (baseline 0.2772, ~3.1x), **labeled_recall =
0.9259** (baseline 0.9074, holds). Per-flight range now 0.656-1.000, no
flight below two-thirds. Updated
`data/detector_tuning/candidate_config_validated_results.csv` in place with
these numbers (this file, unlike `sweep_results.csv`, is meant to reflect
current best-config state, so overwriting it as the config improves is
intentional).

## Contact sheets generated for manual review

Built `src/image_processing/02_adjacent_frame_differencing/
08_generate_contact_sheets.py` - same 4-row-per-chunk layout as
`04_stereo_three_frame_diff.py` (back diff / fwd diff / AND+morph mask /
detection), using the candidate config, into
`data/detector_tuning/contact_sheets/` (NOT the per-flight `analysis_3`
folders - this is a separate tuning artifact). Color code added on top of
the original style: GREEN circle = kept detection, ORANGE circle =
candidate the trajectory filter rejected as an artifact (shown, not
silently dropped, so it's visible what's being filtered), RED "NO
DETECTION" = no candidate blob that frame.

Ran across all 10 sample flights x 2 cams (20 sheets). Rejection counts are
near-zero everywhere now (as expected, since the 4 confirmed artifacts are
excluded upstream) except `flight_22` (1 rejected on cam0, 2 on cam1) -
small residual, not yet investigated, likely a minor one-off the trajectory
filter is still doing useful work catching.

## User review of contact sheets — 3 issues raised

1. **Visualization regression in `08_generate_contact_sheets.py`**: the
   original `04_stereo_three_frame_diff.py` style outlines the actual best
   blob's contour in green (yellow for other candidates) PLUS a small filled
   dot at the centroid. My version flattened all candidates to gray and drew
   only a generic fixed-size ring at the centroid for the best one, losing
   the real blob shape/size information. FIXED: best candidate's actual
   contour now drawn in status color (green=kept, orange=rejected-as-
   artifact) with a filled centroid dot; other candidates drawn in yellow
   (matching the original convention). Contact sheets regenerated.

2. **`candidate_config_validated_results.csv` was overwritten** without
   confirming with the user first - `data/` is entirely gitignored
   (`.gitignore:184`), so the pre-mask-v3 numbers (avg_combined_rate=0.7549)
   were NOT recoverable from git, only from what had already been written
   into this worklog's prose. Reconstructed what's recoverable into
   `data/detector_tuning/history/results_history.csv` (one row per
   milestone: baseline, naive candidate, mask-v2, mask-v3). Going forward:
   `results_history.csv` is APPEND-ONLY (never overwritten), and
   `candidate_config_validated_results.csv` continues to represent "latest
   full per-flight breakdown" (overwriting THAT is fine since
   results_history.csv now preserves the trend line across versions).

3. **flight_22/cam1 frames 44-45 detect the person, not the ball** - traced
   the raw detections: frame 43 = real ball (834,367); frame 44 = person
   (367,882); frame 45 = person (357,884), very close to 44; frame 48 =
   real ball resuming near where it should be (882,390). Root cause: the
   de-spike filter only removes an ISOLATED single-frame outlier (checks
   "does skipping just this one point reconnect its neighbors at a
   plausible speed"). Frames 44 and 45 are two consecutive false detections
   that are close TO EACH OTHER (tiny inter-frame displacement), so: (a)
   testing 44 alone - skipping it requires 43->45 to reconnect plausibly,
   it doesn't (huge jump) - not removed; (b) testing 45 alone - its
   "previous" is now 44 (already kept since (a) failed), and 44->45 is a
   tiny, perfectly-smooth-looking displacement - not removed either. Then
   the final run-split phase treats [44,45] as their own valid run of
   length 2, which satisfies `min_run_length=2`, so both survive. Genuine
   blind spot: catches isolated single-frame spikes, not a short run of 2+
   mutually-consistent false detections. NOT YET FIXED - two options
   discussed with user, awaiting their preference: (a) raise
   `min_run_length` to 3+ (simple, but risks discarding a genuine 2-frame
   island of real detection elsewhere), or (b) extend de-spike to also test
   removing pairs of consecutive points, not just singles (more targeted,
   more code).

## MIN_AREA investigation — confirmed real bottleneck

User noticed real-looking ball blobs visible in the AND+morph mask panels
on frames marked NO_DETECTION. Investigated: checked flight_22/cam0 frames
1-24 with NO area/circ filtering at all. Frame 4's blob (255.6,550.4,
area=182) sits exactly between frame 3 (242,571) and frame 5 (265,545) - a
perfect smooth interpolation, just 18px^2 under MIN_AREA=200. Same pattern
at frames 14 (area=149.5), 17 (area=92, circ=0.74 - very round), 18
(area=169), 20 (area=88.5, circ=0.74), 21 (area=160.5), 23 (area=195.5,
barely missed) - ALL interpolate smoothly with neighboring confirmed real
detections.

Across the full 10-flight sample: **196 NO_DETECTION frames have a contour
in the 20-200 area range** rejected by MIN_AREA, vs. only 3 rejected by
MIN_CIRC (area>=200 but circ<0.3), and only 1 frame with literally zero
contours at all. MIN_AREA=200 is clearly the dominant remaining bottleneck,
not circularity - confirms user's suspicion. NOT YET ACTIONED - proposed
testing a substantially lower MIN_AREA (e.g. 50) while keeping MIN_CIRC=0.3
(circularity is doing useful discrimination work already: the noise
contours found alongside real ones in this same investigation had circ
0.17-0.33, correctly below 0.3, while real small blobs had circ 0.40-0.74).
IMPORTANT: must re-run `07_artifact_audit.py` at any new MIN_AREA before
committing, since a looser area filter could expose NEW small-scale static
artifacts that MIN_AREA=200 was incidentally screening out as a side
effect, not because they were correctly identified as noise. Awaiting user
go-ahead.

## Not yet reviewed / open questions

- **min_run_length vs. pair-de-spike decision** (flight_22 person-detection
  bug) - awaiting user preference between the two options above.
- **MIN_AREA lowering** - awaiting user go-ahead to test (proposed: try 50,
  keep MIN_CIRC=0.3, re-run 07_artifact_audit.py at the new value to check
  for newly-exposed small artifacts before accepting).
- Regenerated contact sheets (with the fixed blob-shape visualization) not
  yet re-reviewed by user.

- User has not yet manually reviewed the 20 contact sheets in
  `data/detector_tuning/contact_sheets/` - waiting on that feedback before
  going further.
- `flight_22`'s small residual rejections (1 cam0, 2 cam1) not investigated -
  worth a quick look to see if it's a 5th minor artifact or just the filter
  correctly catching an isolated one-off.
- MIN_AREA/MIN_CIRC not touched yet (per the agreed order, these come after
  mask-generation params) - worth a pass once the user signs off on the
  current state.
- Haven't yet re-run the FULL dataset (all 149 + 97 flights, i.e. all 163)
  with the final config/mask/filter - only validated on the 10-flight sample
  so far. Should do a final full run + fresh `analysis_4` output + updated
  `detection_rate_summary.csv` once user signs off, per earlier agreement
  not to overwrite `analysis_3`.
- Static background subtraction (fallback for the near-zero-relative-motion
  blind spot, e.g. apex-of-arc frames) not attempted - only relevant if the
  above still plateaus below what's needed. Current avg_combined_rate 0.855
  is a big jump from baseline 0.277; unclear yet whether user considers this
  sufficient or wants to keep pushing.
- Only cam0 and cam1 static artifacts found via THIS candidate config's
  audit (thresh=16, open_k=3) were checked - if MIN_AREA/MIN_CIRC or the
  config changes further, worth re-running `07_artifact_audit.py` since a
  different config could surface different/additional artifacts.
- MIN_AREA/MIN_CIRC not touched yet (per the agreed order, these come after
  mask-generation params) — worth a pass once the above is locked in.
- Haven't yet re-run the FULL dataset (all 149 + 97 flights) with the new
  config/mask/filter — only validated on the 10-flight sample so far. Should
  do a final full run + fresh `analysis_4` output + updated
  `detection_rate_summary.csv` once user signs off, per earlier agreement
  not to overwrite `analysis_3`.
- Static background subtraction (fallback for the near-zero-relative-motion
  blind spot) not attempted — only relevant if the above still plateaus
  below what's needed.

## Round 3: MIN_AREA x MIN_CIRC sweep (via /plan task)

Continuing from the MIN_AREA investigation above. Ran via a planned task
(`claude/prompts/2026-07-23_1819_min_area_circ_sweep.md`) after rewriting
`claude/claude_rules.md` for this Python project (previous entry's task).

**New input since the task was written**: user hand-labeled `flight_22` too
(`data/2026_07_15_gym/ball_flights/flight_22/flight_22_cam{0,1}_labels.csv`,
93 labeled frames/cam, same per-cam format as flight_01's label file - no
consolidated `labels_uv.csv` for this one). Confirmed with user: use BOTH
flight_01 (27/cam) and flight_22 (93/cam) for labeled recall this round -
240 labeled points total instead of 54.

**Design decisions confirmed with user before running anything:**
1. `09_param_sweep_area_circ.py`'s `evaluate_config()` applies
   `filter_trajectory_outliers()` on top of `run_detection()`'s raw output
   (not raw detections alone like `06_param_sweep.py`, which predates the
   filter) - required for the new numbers to be comparable to the
   0.8552/0.9259 baseline being improved upon.
2. The recall-gate threshold (0.9074) was computed against flight_01's 54
   points only. With the label set now at 240 points, recomputing what the
   untuned baseline config actually scores against the MERGED set and using
   THAT as this round's gate, rather than reusing the stale 0.9074 measured
   on a different/smaller set.

Verified before starting: read `detector_core.py`, `06_param_sweep.py`,
`07_artifact_audit.py`, `08_generate_contact_sheets.py`, `exclusion_mask.py`
directly (not via subagent - task was already fully specified, and this
session had first-hand knowledge of every file having written them earlier)
and confirmed the task's description of current state was accurate: 7
exclusion zones (5 cam0 + 2 cam1), `sweep_results.csv` has
`meets_recall_gate`/`is_baseline` columns but `06_param_sweep.py`'s own code
doesn't compute them (added out-of-band last round), exact current CSV
contents in `results_history.csv`/`candidate_config_validated_results.csv`/
`artifact_audit_hotspots.csv` all matched.

### Step 1: candidate_config.json created

`data/detector_tuning/candidate_config.json`:
```json
{"stride": 1, "diff_threshold": 16, "open_kernel": 3, "close_kernel": 30,
 "min_area": 200, "max_area": 50000, "min_circ": 0.3,
 "max_speed_px_per_frame": 80, "min_run_length": 2}
```
Seeded with the current validated values (matches
`candidate_config_validated_results.csv`'s CONFIG row exactly).

### Step 2: refactored 07_artifact_audit.py and 08_generate_contact_sheets.py

Both now read `stride`/`diff_threshold`/`open_kernel`/`close_kernel`/`min_area`/
`max_area`/`min_circ` from `candidate_config.json` via a small `load_config()`
helper (duplicated in each file rather than added to `detector_core.py` -
task explicitly said not to refactor `detector_core.py` beyond what's needed
here, and it isn't needed at all). Both also now pass
`max_speed_px_per_frame`/`min_run_length` from the config explicitly into
their `filter_trajectory_outliers()` calls, instead of relying on the
function's own defaults happening to match.

**Behavior-neutrality verification - first attempt was WRONG:** initially
compared a fresh scratch run of the refactored `07_artifact_audit.py`
against the on-disk `artifact_audit_hotspots.csv` and got very different
results (8 hotspots now vs. 13 before) - looked like a bug. It wasn't: the
on-disk CSV predates the mask-v3 exclusion zones (it's literally the audit
that led to them being added), so a fresh run correctly finds fewer hotspots
now that those 4 known artifacts are excluded upstream. Comparing against a
stale historical snapshot was the wrong test.

**Correct verification**: built a hardcoded-constants scratch variant of each
script (same logic, config values hardcoded instead of loaded from JSON) and
compared it against the refactored (JSON-loading) scratch variant, BOTH run
fresh against the CURRENT `exclusion_mask.py` - isolating just the refactor's
effect from any mask changes.
- `07`: cam0 51 total rejected points / 4 hotspot bins, cam1 47 points / 4
  bins - IDENTICAL between refactored and hardcoded variants (same bin
  centers, same distinct_flights, same total_points, to the value).
  (ProcessPoolExecutor required a real on-disk script for the hardcoded
  variant too - in-process module monkeypatching doesn't survive into
  Windows spawned worker processes, since they re-import by file path.)
- `08`: ran both variants in-process (no multiprocessing issue here),
  captured stdout, compared print-for-print - `IDENTICAL PRINTED OUTPUT:
  True`, every flight/cam's kept/rejected count matches exactly (e.g.
  flight_01 cam0/cam1: 25/0, flight_22 cam0: 75/1, cam1: 72/2 - also matches
  the counts already recorded from the original run in this worklog).

Both refactors confirmed behavior-neutral.

### Step 3: 09_param_sweep_area_circ.py built

Grids `MIN_AREA=[30,50,75,100,150,200]` x `MIN_CIRC=[0.2,0.25,0.3,0.35]` (24
combos), stride/thresh/open_k/close_k/max_area/max_speed/min_run loaded from
`candidate_config.json` and held fixed. `evaluate_config()` applies
`filter_trajectory_outliers()` on top of `run_detection()` (per the confirmed
design decision). Labeled recall generalized to read directly from each
labeled flight's own `flight_{name}_cam{0,1}_labels.csv` (not `labels_uv.csv`,
which only flight_01 has) - `LABELED_FLIGHT_SUBPATHS` = flight_01 + flight_22.
`meets_recall_gate`/`is_baseline` computed in-script (not left as an
out-of-band gap like round 1's `06_param_sweep.py`).

### Baseline recall recomputation - big, informative surprise

`compute_baseline_recall()` (stride=1,thresh=20,open_k=7,min_area=200,
min_circ=0.3, no trajectory filter) against the merged 240-point label set
(flight_01: 54, flight_22: 186 - confirmed both load correctly, 27+93 labeled
frames/cam each) came out to **0.2417**, nowhere near the old 0.9074.

This makes sense on reflection: `flight_22` was originally picked as one of
the 10 sample flights specifically BECAUSE it had 0.000 combined_rate under
the untuned baseline (see the 10-flight-sample section above) - the old
0.9074 was measured on flight_01 ALONE, which was already a comparatively
easy/well-behaved case. Merging in a flight the baseline essentially fails on
entirely was always going to drag the recall figure down hard - this isn't a
bug, it's an accurate reflection that flight_01 alone was not a representative
baseline measurement.

**Consequence**: the recall gate is now much LESS selective (0.24 vs. 0.91) -
most reasonable configs will clear it easily, unlike round 1 where only 6/48
passed a 0.91 gate. The pass/fail gate alone won't be as useful for catching
a gamed/noisy config this round. Will report the raw `labeled_recall` VALUE
(not just the gate boolean) for every gate-passing candidate at Checkpoint 1,
and weight genuinely high recall (close to the current 0.9259) over merely
"passes a now-loose 0.24 bar" when picking a winner.

### Step 4: 24-combo sweep run - results

Ran `09_param_sweep_area_circ.py` in the background (exit 0). Full 24 rows in
`data/detector_tuning/sweep_results_min_area_circ.csv`.

**Sanity check (per the plan's verification section)**: the `is_baseline` row
(min_area=200, min_circ=0.30) shows `avg_combined_rate=0.8552` - an EXACT
match to the existing validated number, confirming the new script's
combined-rate methodology is correct. Its `labeled_recall=0.8125` does NOT
match the previously-recorded 0.9259 - but this is expected, not a bug: it's
now measured against the merged 240-point set (flight_01+flight_22) instead
of flight_01's 54 points alone, the same reason the recomputed baseline
dropped from 0.9074 to 0.2417 above.

**All 24/24 configs passed the (loose) gate**, as anticipated. Top rows by
avg_combined_rate:

| min_area | min_circ | avg_combined_rate | labeled_recall |
|---|---|---|---|
| 30 | 0.25 | 0.9825 | 0.9042 |
| 30 | 0.20 | 0.9824 | 0.8958 |
| 50 | 0.20 | 0.9802 | 0.8958 |
| 50 | 0.25 | 0.9792 | 0.9042 |
| 30 | 0.30 | 0.9751 | 0.9208 |
| 50 | 0.30 | 0.9719 | 0.9208 |
| ... | | | |
| 200 | 0.30 (baseline) | 0.8552 | 0.8125 |

**Key finding**: `labeled_recall` INCREASES as MIN_AREA decreases (0.81 at
area=200 -> 0.90-0.92 at area=30-50), moving in the SAME direction as
`avg_combined_rate` - the opposite of round 1's gaming pattern (where a high
combined_rate came with collapsed recall). This looks like a genuine
improvement (recovering real small blobs, per the original MIN_AREA
investigation), not noise flooding.

**Flagged to user**: min_area=30 is the loosest value in the tested grid and
it wins outright, with no sign of topping out - this is exactly why the full
audit at Checkpoint 2 matters more than usual this round (an aggressive drop
this large could plausibly expose new small-scale noise the 10-flight sample
didn't catch).

### CHECKPOINT 1 - reported, then user raised 2 good questions before deciding

Reported to user: `min_area=30, min_circ=0.25` as top candidate (best
combined_rate 0.9825, recall 0.9042 near the top of the pack) vs.
`min_area=30, min_circ=0.30` as an alternative trading a little combined_rate
(0.9751) for the highest recall in the grid (0.9208).

**User pushback #1**: "how is 0.2417 possible - the flight_22 contact sheet
centroids look pretty on point?" Confusion was comparing two DIFFERENT
configs: `flight_22_cam0_contact.png` was generated under the CURRENT tuned
pipeline (thresh=16/open_k=3 + trajectory filter + mask v3), which is why it
looks good; the 0.2417 figure specifically measures the YEAR-ZERO untuned
config (thresh=20/open_k=7, no filter) - deliberately meant to look bad, not
a contradiction.

**User pushback #2**: "why no trajectory filter [[in that computation]]?" -
originally justified as historical fidelity to how 0.9074 was first measured
(before the filter existed). Correct on its own terms, but on reflection
answers the wrong question for THIS round's actual gating purpose. Agreed
with user's implicit point and switched the gate: `GATE_RECALL` is now the
CURRENT full pipeline's own recall at (200, 0.3) - i.e. `compute_gate_recall()`
calls the same `run_one_config()` used for every grid point, at the baseline
values - rather than `HISTORICAL_BASELINE_RECALL` (kept, but now FYI-only,
printed but not used for gating). Refactored `09_param_sweep_area_circ.py`:
split `evaluate_config()` into a pure `run_one_config(min_area, min_circ) ->
(avg_combined_rate, labeled_recall)` plus a thin wrapper that adds
`meets_recall_gate`/`is_baseline` using the module-level `GATE_RECALL`
constant (avoids the circular dependency of "the gate needs the sweep's own
result at one particular grid point").

Manually patched `sweep_results_min_area_circ.csv`'s `meets_recall_gate`
column to the corrected 0.8125 threshold first (21/24 pass now, down from
24/24 - `area=200,circ=0.20`/`circ=0.25` correctly dropped out, both scoring
below the current pipeline's own recall). Then re-ran the fixed script to
confirm the code itself produces the same result - caught one more bug in
the process (leftover reference to the renamed `BASELINE_RECALL` variable in
the final print statement, from `sys.exit`-worthy `NameError` after the CSV
had already written correctly) - fixed.

Ranking unaffected by the gate fix - `min_area=30` remains the standout at
every min_circ tested.

**User confirmed the winner**: `min_area=30, min_circ=0.30` (prioritizing
recall: 0.9208, the highest in the grid, over the marginal combined_rate gap
vs. min_circ=0.25).

### Reorganization requests (before proceeding to Checkpoint 2)

User asked for 3 more things while Checkpoint 1 was being resolved:

1. **`results_history.csv`**: add an `artifacts` column pointing to the
   relevant file(s)/folder(s) for each row, and add rows for the SWEEP/AUDIT
   STAGES themselves (not just adopted-config milestones) - e.g. "round 1
   sweep (48 combos)", "full-dataset artifact audit (pre-mask-v3)". Done -
   schema is now `date,stage,avg_combined_rate,labeled_recall,artifacts,notes`;
   added 3 new stage rows (round 1 sweep, pre-mask-v3 audit, round 3 sweep)
   alongside the 4 existing milestone rows, each with its `artifacts` column
   filled in. Verified the file still parses as valid CSV (7 rows, 6 columns)
   after the rewrite.

2. **`contact_sheets/` and `inspection_crops/` reorganized into stage-named
   subfolders** (short slug, per user's AskUserQuestion answer - not the
   literal stage text, which would have awkward `+`/`(`/`)`/spaces in a
   folder name). Moved:
   - `contact_sheets/*.png` (20 files) -> `contact_sheets/round2_mask_v3_trajectory_filter/`
   - `inspection_crops/*.png` (16 files) -> `inspection_crops/round2_mask_v3_trajectory_filter/`
   - `artifact_audit_hotspots.csv` -> `inspection_crops/round2_mask_v3_trajectory_filter/artifact_audit_hotspots.csv`
     (now lives alongside the crops it describes, per user's request)

   Went further: made `07_artifact_audit.py`/`08_generate_contact_sheets.py`
   auto-derive their stage subfolder from the loaded config
   (`STAGE = f"area{MIN_AREA}_circ{MIN_CIRC}"`) instead of writing to a flat
   shared path - so every future run self-organizes correctly without manual
   path redirection each time. **Caught a near-miss in the process**: had
   already launched the FIRST re-run of `07_artifact_audit.py` at the new
   min_area=30 config BEFORE making this change - it would have overwritten
   the just-reorganized... no, actually the STILL-FLAT
   `artifact_audit_hotspots.csv` (the reorg had already moved the OLD one out
   of the way by that point, but the flat-path script would have written a
   new file back to that now-empty top-level location, defeating the
   whole point of organizing by stage). Killed the background task
   (`bpj3hoou2`) before it could write, verified nothing was touched, THEN
   made the auto-derive fix, THEN re-launched.

3. **True_ball/false_positive confirm-deny suffix on every inspection crop
   filename.** Went back and individually visually inspected every crop that
   hadn't already been confirmed earlier in this session (6 of the 16):
   - `hotspot_cam0_u1020_v820_flight_126_frame119` -> **true_ball** (same
     round/highlighted/shadow-crescent signature as the already-confirmed one)
   - `hotspot_cam0_u1060_v620_flight_17_frame068`,
     `hotspot_cam0_u1100_v620_flight_14_frame050`,
     `hotspot_cam0_u1180_v620_flight_13_frame080` -> **false_positive** (same
     wall fixture / exit sign already confirmed elsewhere)
   - `hotspot_cam1_u380_v820_flight_15_frame043`,
     `hotspot_cam1_u380_v860_flight_15_frame048` -> **false_positive**, but a
     NEW category: a person's arm/hand (the thrower's release motion), not a
     static fixture. Flagged as NOT a masking candidate - it's too close to
     where the ball's real trajectory legitimately starts, so excluding that
     region spatially would risk cutting real early-flight detections. Left
     to the trajectory filter to keep handling this one.
   All 16 crops renamed with the confirmed suffix and moved into the
   `round2_mask_v3_trajectory_filter` subfolder together.

### Config locked in, full audit running

Updated `candidate_config.json`: `min_area` 200 -> 30 (min_circ already 0.3,
no change needed there). Launched full 163-flight audit at the new config
(background) - will land automatically in
`data/detector_tuning/inspection_crops/area30_circ0.3/` per the new
auto-derived stage path.

### Round 3 audit results - 13 hotspots, new finding: fixture/sign visible in cam1 too

13 hotspot bins (up from 8 at min_area=200) - expected, since a much looser
area threshold surfaces smaller signals. Investigated every new/unexplained
one via cropped frames before proposing anything (not just bin-center
proximity guessing).

**Key finding**: the exit sign and wall fixture (already known/masked in
cam0) are now ALSO visible from cam1's viewpoint - same physical objects,
different camera angle, previously not sensitive enough to trigger at
min_area=200 on that side.

Derived precise dense-core bounding boxes (same 15px re-bin methodology as
round 2) via `bbox_probe_round3.py` in the scratchpad (parallelized -
`python -c` with `ProcessPoolExecutor` fails on Windows, same
pickling/re-import issue hit before; needs a real on-disk script).

**5 candidate zones, all safety-checked against every existing analysis_3
detection:**
- cam0 exit-sign spillover: x=[1175,1192], y=[605,624] (dist=9, 0 hits)
- cam0 fixture spillover: x=[1070,1090], y=[620,633] (dist=11, 0 hits)
- cam1 wall-corner extension: x=[1385,1400], y=[448,462] (dist=13, 0 hits)
- cam1 fixture (new): x=[1135,1172], y=[684,693] (dist=11, 0 hits after fix -
  see near-miss below)
- cam1 exit sign (new): x=[1238,1270], y=[668,685] (dist=3 only, but
  visually unambiguous - masked despite the lower count)

**Near-miss caught during safety-check**: the cam1 fixture zone's first
draft (v starting at 680) hit ONE real detection -
`flight_53/cam1_detections3.csv` frame 108 at (1153.3, 682.5). Checked
neighboring frames 103/104: speeds of 30.4 and 22.8 px/frame in a consistent
direction - a genuine, smooth real trajectory, not noise. The actual fixture
dense-core bins both start at v=685, so narrowing the zone's floor to v=684
(1px margin) separated them cleanly - zero hits after.

**Not acted on**: a handful of 2-3-distinct-flight cam0 edge points (same
"gap cluster" region, too weak individually to add yet another zone for),
and cam1 points at (380-420, 820-860) - almost certainly the previously-
confirmed person's-arm artifact recurring (same reasoning as round 2: too
close to the real launch trajectory to mask spatially).

### CHECKPOINT 2 - reported, user confirmed

Reported all of the above to user with the full safety-check evidence. User:
manually reviewed every crop in `inspection_crops/area30_circ0.3/` and
confirmed "all the images don't have a ball in" - matches my assessment.
Confirmed: add all 5 zones.

Added to `exclusion_mask.py` (mask v4): cam0 gets 2 more entries (7 total
now), cam1 gets 3 more entries (5 total now) - documented each with the
safety-check evidence directly in the file's comments, same convention as
mask v3.

Relabeled all 13 `area30_circ0.3` crops with confirmed `_false_positive`
suffix.

**Near-catch on the re-verification run itself**: launched
`07_artifact_audit.py` again (to confirm mask v4 cleans things up) before
noticing it would write to the SAME auto-derived `area30_circ0.3` folder,
overwriting the pre-mask-fix `artifact_audit_hotspots.csv` I'd just spent
this whole section producing and labeling. The STAGE auto-derivation
(`area{MIN_AREA}_circ{MIN_CIRC}`) doesn't distinguish "before this round's
mask fix" from "after" within the same area/circ config - a real gap, since
mask changes aren't part of the config JSON. Killed the task before it wrote,
renamed the existing file to `artifact_audit_hotspots_premaskfix.csv` to
preserve it, THEN re-launched. (Crop PNGs were never at risk - the script
only writes crops for hotspots it currently finds, never deletes existing
ones - but the CSV is unconditionally overwritten every run.)

Post-mask-v4 audit re-launched in background to verify the fix.

Updated `results_history.csv` with a new stage row for this audit (per
user's reminder) - `artifacts` points at the premaskfix CSV + crops folder,
`notes` summarizes the finding, the 5 zones, and the near-miss.

### Post-mask-v4 re-audit - confirmed the fix worked, diminishing returns from here

Re-ran the full audit again (after preserving the pre-fix CSV as
`artifact_audit_hotspots_premaskfix.csv`, so this overwrite of the plain-named
file was safe). Result: **13 hotspots -> 9, total rejected points 181 -> 86**
(roughly halved).

Checked the one genuinely new-looking location (`cam0, u=180, v=820`) -
another instance of the already-confirmed person's-arm artifact, just now
also visible on cam0's side (previously only seen on cam1 at u=380-420).
The remaining 8 hotspots were all further edge-spillover of the SAME two
already-masked static objects (fixture, wall corner) - no new artifact
types. Flagged this as a genuine diminishing-returns pattern (chasing
progressively smaller spillover of the same low-contrast static edges) and
recommended stopping mask refinement here. User agreed.

### Contact sheets + final validated numbers

Ran `08_generate_contact_sheets.py` - auto-landed in
`data/detector_tuning/contact_sheets/area30_circ0.3/` (20 sheets, per the
auto-derived stage path).

Recomputed the full 10-flight validated breakdown (same methodology as
before: `run_detection` -> `filter_trajectory_outliers` per flight/cam,
labeled recall now from BOTH flight_01 and flight_22 directly via their own
per-cam label files) and overwrote `candidate_config_validated_results.csv`
(pre-approved as "latest state, OK to overwrite" - user asked mid-task to
confirm this wouldn't lose data; reassured: `results_history.csv` is
specifically the append-only permanent record that exists so this file CAN
safely be overwritten each round).

**Final round 3 result:**
- **avg_combined_rate = 0.9784** (up from mask-v3's 0.8552, +14.4pp)
- **labeled_recall = 0.9250** (flight_01 + flight_22 merged, 240 points -
  comfortably above the 0.8125 gate)
- Per-flight: 5 of 10 sample flights at 1.0000 combined_rate, none below
  0.8958 (flight_59)
- Config: `stride=1, diff_threshold=16, open_kernel=3, close_kernel=30,
  min_area=30, max_area=50000, min_circ=0.3` + `exclusion_mask.py` v4 (7
  cam0 + 5 cam1 = 12 zones total) + `filter_trajectory_outliers`
  (max_speed_px_per_frame=80, min_run_length=2, unchanged)

Appended the final `results_history.csv` row for this milestone (10 rows
total now, all parse correctly as valid CSV) - includes the post-mask-v4
re-audit as its own stage row too, per user's explicit reminder to log the
artifact audit there.

## Session summary (as of this entry)

Overall progress this session: **avg_combined_rate 0.2772 -> 0.9784** (baseline
to current), **labeled_recall 0.9074 (54 pts, flight_01 only) -> 0.9250 (240
pts, flight_01+flight_22)**. Three tuning rounds (mask-generation params,
trajectory filter + artifact audit/exclusion masking, MIN_AREA/MIN_CIRC),
each validated against a 10-flight sample and checked against a full
163-flight audit before being accepted.

## Full-dataset production run (all 163 flights)

User wants to move past the 10-flight validation sample now that tuning is
settled: run the final config on all 163 flights and get a real
`candidate_config_validated_results.csv` covering everything, not just the
sample. Also raised a good design point: `04_stereo_three_frame_diff.py`'s
convention of writing an `analysis_N` folder INSIDE each flight would
scatter 163 folders across 2 session directories - hard to browse. Proposed
instead: keep everything centralized under `data/detector_tuning/`, same as
the sample-flight contact sheets already are.

**Discussed and confirmed with user:**
- Stage folder name: `03_stride1_thresh16_openk3_area30_circ0.3` (only the
  params that actually changed this round - dropped close_kernel/max_speed/
  min_run since those haven't moved) under `contact_sheets/03_.../`.
- `03_` round-number prefix tracked BY HAND, not auto-derived from
  `candidate_config.json` - "round number" is a documentation concept, not a
  property of the detector config.
- `candidate_config_validated_results.csv` gets its contents REPLACED
  (10-flight sample -> full 163-flight breakdown) rather than kept as a
  separate file - it's already established as "current state, freely
  overwritable," and the sample was only ever a fast-iteration proxy during
  tuning, no longer needed now that tuning is settled.
- Parallelize this (unlike `08_generate_contact_sheets.py`, which is
  single-threaded and took a few minutes for just 20 sheets) - scaling that
  linearly to 326 sheets would be too slow. Used the same
  `ProcessPoolExecutor`-per-(flight,cam) pattern as `07_artifact_audit.py`.

Built `src/image_processing/02_adjacent_frame_differencing/
10_run_full_dataset.py`: combines 07's full-dataset enumeration +
parallelization, 08's contact-sheet visualization, and the inline
validated-results-recompute logic from earlier this session, into one
script. Each worker computes+writes its own flight/cam's contact sheet AND
returns its processable-set/kept-detections dict, which the orchestrating
process combines per-flight for combined_rate (needs both cams together) and
aggregates for labeled recall (flight_01 + flight_22).

Launched in background - running now.

## Not yet done / open questions

- `flight_22`'s two-consecutive-false-detection / `min_run_length` bug
  (person briefly detected across 2 frames, slips past the de-spike filter)
  - intentionally left unfixed across rounds 2 and 3, per user's explicit
  scoping decisions each time. Two fix options still on the table: raise
  `min_run_length` to 3+, or extend de-spike to test removing pairs.
- Haven't yet re-run the FULL dataset (all 163 flights) with the final
  config to produce real per-flight `analysis_4` outputs + an updated
  `detection_rate_summary.csv` - all validation so far has been on the
  10-flight sample (by design, to keep iteration fast) plus full-dataset
  artifact AUDITS (which check for false positives, not full detection
  output). This full-dataset production run is the natural next step once
  the user is satisfied with the current state.
- Static background subtraction (fallback for the near-zero-relative-motion
  blind spot, e.g. apex-of-arc frames) not attempted - not yet needed given
  how far combined_rate has come (0.28 -> 0.98).
- A few very-low-count (2-3 distinct flight) spillover hotspots near the
  existing cam0 fixture/exit-sign zones were left unmasked (too weak
  individually) - would resurface if MIN_AREA is lowered further in a future
  round.
