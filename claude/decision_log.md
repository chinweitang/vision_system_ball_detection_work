# Decision Log

Key decisions made across this session (stereo ball-detector tuning, plus the
earlier `claude_rules.md` rewrite), each with the reasoning and what was
considered and rejected. Cross-referenced against
`claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md`, which has the
full narrative/evidence for each of these - this file is the compressed,
numbered index.

---

## Detector tuning methodology

**1. Diagnosed the low detection rate as a near-zero relative-motion blind
spot, not underexposure.**
Chose this after numerically checking back/fwd diff magnitude at a known
ball location (max diff ~5-10, below `DIFF_THRESHOLD=20`) and finding good
absolute contrast but almost no frame-to-frame displacement at that instant.
**Alternative considered**: underexposure (my own first read, from a
600px-wide contact-sheet thumbnail that looked all-black). **Rejected**
because cropping the same frame at native resolution around the ball showed
good local contrast (~90-115 grey vs ~40 background) - the "all black" read
was an artifact of viewing a scaled-down thumbnail, not a real signal
problem.

**2. Order to tune parameters: STRIDE first, then DIFF_THRESHOLD+OPEN_KERNEL
jointly, then MIN_AREA/MIN_CIRC, then background subtraction as a last
resort.**
Chose this order because STRIDE is the only lever that fixes the near-zero-
motion blind spot (decision 1) - tuning threshold/kernel/area first would be
tuning around a mask that structurally can't contain the ball at some
instants. **Alternative considered**: tune all parameters simultaneously in
one large grid. **Rejected** as computationally wasteful and harder to
interpret (can't tell which parameter drove an improvement) given the
sequential dependency between them.

**3. Primary tuning metric: `avg_combined_rate` (co-detection in both cams,
same frame) across a spread 10-flight sample, not recall on the one labeled
flight.**
Chose this because triangulation needs both cameras to see the ball in the
same frame - detections that only happen in one camera are useless
downstream. **Alternative considered**: optimize purely for recall against
`flight_01`'s hand-labeled ground truth. **Rejected** because that flight had
already been manually tuned to ~96% and confirmed not to generalize (the
session-wide average sat far lower) - optimizing against it alone would
re-overfit to one easy case.

**4. Recall-GATED ranking (filter to configs meeting a recall floor, THEN
rank by combined_rate) instead of ranking by combined_rate alone.**
Chose this after the naive top-ranked config by raw combined_rate
(`stride=2,thresh=8,open_k=3`) turned out to have collapsed recall (0.556,
down from baseline 0.907) - it was firing on nearly every frame, not finding
the ball more often. **Alternative considered**: rank by combined_rate alone
and trust it. **Rejected** because it's directly gameable by loosening
detection until it fires on everything, real or not.

**5. Trajectory-consistency filter: de-spike (remove isolated implausible
single points) + speed-bounded run split - after two other approaches
failed.**
Chose this because it's grounded in a real physical constraint (a ball can't
move faster than some px/frame) and only ever compares temporally-adjacent
points, so it can't be derailed by how many outliers exist elsewhere in the
sequence. **Alternatives considered and rejected**:
   - *Global degree-2 polyfit + iterative residual trim*: rejected because a
     high enough fraction of severe outliers in the raw data could pull the
     very first least-squares fit badly off course (ordinary least squares
     has no outlier resistance), misclassifying nearly everything as an
     outlier in one bad pass with no way to recover - this collapsed
     multiple flights' cam1 detections to zero.
   - *Compare each point to the position median of its nearby neighbors*:
     rejected because it falsely rejected real, confirmed ball detections
     early in a fast-moving flight, where the ball's own genuine
     displacement across the neighbor window was larger than the rejection
     tolerance - and edge-of-sequence asymmetric windows let a minority of
     interspersed artifacts skew the local median enough to fail the real
     point too.
   - *(Within the winning approach) run-splitting alone without a de-spike
     pre-pass*: rejected because when false positives were frequent enough
     (~every 3 frames), the real trajectory itself fragmented into many
     short runs, each individually shorter than `min_run_length`, and got
     discarded along with the actual artifacts.

**6. Full-dataset artifact audit: pool every point the trajectory filter
rejects across ALL flights, bin spatially, rank by DISTINCT FLIGHT COUNT (not
raw point count) - instead of manually reviewing contact sheets flight by
flight.**
Chose this because the camera rig is fixed, so a genuine static artifact
recurs at nearly the same pixel location across many different flights,
while incidental noise scatters - and ranking by distinct-flight count (not
raw point count) stops one flight with a long-lived artifact from
masquerading as a multi-flight recurring one. **Alternatives considered**:
   - *Manually scroll contact sheets for every flight*: rejected as not
     scaling to 163 flights.
   - *False-positive proxy: treat any detection outside the curated
     `ball_in_frame` range as a false positive*: rejected (before being
     built) because the user pointed out `ball_in_frame` was deliberately
     curated to exclude some real in-frame ball content (e.g. post-bounce),
     so its complement isn't a guaranteed no-ball region - the whole premise
     was invalid.

**7. Exclusion-mask boxes sized from the densest 15px sub-cluster (by
distinct-flight count), not the raw bounding box of all rejected points near
a seed location.**
Chose this after the raw-bounding-box approach for two artifacts (exit sign,
fixture) turned out to overlap 12 and 54 real detections respectively.
**Root cause / alternative rejected**: the raw rejected-point pool was
contaminated by the trajectory filter's OWN false rejections of real ball
frames near those fixtures (decision 5's filter isn't perfect near
overlapping U-ranges) - those wrongly-rejected real points got pooled in as
if they were artifact points, inflating the apparent footprint far beyond
the actual physical object.

**8. MIN_AREA/MIN_CIRC round: lower MIN_AREA specifically (not raise
MIN_CIRC, not touch stride/threshold/kernel again).**
Chose to test lower `MIN_AREA` after finding 196 NO_DETECTION frames (out of
the 10-flight sample) had a real-looking blob (area 88-200, circ 0.40-0.74)
sitting on an otherwise smooth trajectory, rejected purely by the area
cutoff - vs. only 3 frames rejected by circularity. **Alternative
considered**: also re-sweep stride/threshold/kernel this round.
**Rejected/deferred** per explicit scope agreement - those were already
tuned in round 1 and re-testing them wasn't where the evidence pointed.

**9. Recall gate for the MIN_AREA/MIN_CIRC round: gate against the CURRENT
pipeline's own recall, not a recomputed "year-zero" baseline recall.**
The first attempt recomputed what the ORIGINAL untuned config (thresh=20,
no trajectory filter) would score against the newly-expanded 2-flight label
set, getting 0.2417 - a real number, but the wrong reference point. Switched
to gating against the CURRENT full pipeline's own recall at the unchanged
baseline point (0.8125) instead. **Alternative considered**: keep gating at
0.2417 (methodologically defensible - matches how the original 0.9074 was
computed) - the user pushed back on this. **Rejected** because it answers
"was the very first untuned baseline bad" (yes, known) rather than the
actually useful question for this round: "does a new MIN_AREA/MIN_CIRC
choice make things worse than what we already have." A gate that low
(0.2417) passed 24/24 configs, providing no real discrimination.

**10. Labeled recall computed by reading each labeled flight's own per-cam
label CSV directly, not a consolidated `labels_uv.csv`.**
Chose this because only `flight_01` has a consolidated `labels_uv.csv` -
`flight_22` (labeled mid-session) only has its own
`flight_22_cam{0,1}_labels.csv`. Reading directly from the per-cam files
generalizes to any number of labeled flights. **Alternative considered**:
keep relying on `labels_uv.csv` and skip `flight_22`'s labels, or hand-build
a consolidated file for it. **Rejected** as unnecessary extra work/state to
maintain when the per-cam files already have everything needed
(`centroid_x`, `centroid_y`, `diameter_px`).

**11. Winner for the MIN_AREA/MIN_CIRC sweep: `min_area=30, min_circ=0.30`,
not `min_circ=0.25` (which had marginally higher combined_rate).**
User's explicit call, prioritizing the highest recall in the grid (0.9208)
over a small combined_rate gap (0.9751 vs. 0.9825) - i.e. weighting accuracy
slightly over raw detection count once both were already far above baseline.

---

## Exclusion-mask decisions

**12. Visually confirmed artifacts get masked even at a low distinct-flight
count, if the crop is visually unambiguous (e.g. the cam1 exit sign at only
3 distinct flights).**
Chose to trust direct visual confirmation over the raw statistical proxy in
this specific case. **Alternative considered**: apply a strict minimum
distinct-flight-count threshold uniformly (as used for the initial hotspot
scan). **Rejected** for zones with unambiguous visual confirmation - the
distinct-flight-count heuristic is a proxy for "is this real," and direct
visual evidence is stronger evidence than the proxy when they disagree.

**13. The person's-arm artifact (thrower's release motion) is explicitly
NOT masked, despite being a confirmed false positive.**
Chose to leave this to the trajectory filter alone. **Alternative
considered**: add a spatial exclusion zone for it, same as the static
artifacts. **Rejected** because this region is too close to where the ball's
real trajectory legitimately starts (the launch point) - a spatial mask here
would risk cutting genuine early-flight detections, unlike the static
artifacts which sit in screen regions the ball never legitimately occupies.

**14. Stopped mask refinement after round 3's post-fix re-audit (13
hotspots -> 9) rather than continuing to chase the remaining spillover.**
Joint decision with the user after confirming the remaining 9 hotspots were
NOT new artifact types - just further edge-spillover of the same two
already-masked static objects (their low-contrast edges bleeding further at
a looser threshold) plus the already-accepted person's-arm case.
**Alternative considered**: keep narrowing/adding zones to chase the
remaining spillover. **Rejected** as a diminishing-returns exercise -
chasing progressively smaller spillover of known low-contrast static edges,
with no genuinely new information left to act on.

---

## Infrastructure / process decisions

**15. `candidate_config.json` as the single source of truth for detector
parameters, read by `07_artifact_audit.py`/`08_.../10_...py`, instead of
each script hardcoding its own copy.**
Chose this to eliminate the risk of scripts silently drifting out of sync
with each other (which had already happened once: `sweep_results.csv` had
`meets_recall_gate`/`is_baseline` columns its own generating script didn't
actually compute). **Alternative considered**: keep each script's constants
hardcoded and manually keep them in sync by hand each round. **Rejected** as
exactly the kind of manual-sync process that had already produced a gap.

**16. `candidate_config_validated_results.csv` is "current state, freely
overwritable"; `results_history.csv` is the permanent append-only record.**
Established after `candidate_config_validated_results.csv` was overwritten
once without asking, permanently losing the pre-mask-v3 numbers (only
recoverable from worklog prose, not the CSV itself) - `data/` is entirely
gitignored, so there's no git history to fall back on. **Alternative
considered**: never overwrite `candidate_config_validated_results.csv`,
always create a new versioned file instead. **Rejected** as unnecessary
process overhead once `results_history.csv` exists specifically to preserve
the trend line - the "current state" file can safely stay mutable if the
permanent record lives elsewhere.

**17. Centralized `contact_sheets/<stage>/` and `inspection_crops/<stage>/`
under `data/detector_tuning/`, instead of per-flight `analysis_N` folders
(the `04_stereo_three_frame_diff.py` convention).**
User's call: 163 flights' worth of scattered `analysis_N` folders across 2
session directories is hard to browse; one centralized, stage-named location
is not. **Alternative considered**: keep the existing per-flight-folder
convention for consistency with `04_stereo_three_frame_diff.py`.
**Rejected** in favor of browsability, since this is tuning/diagnostic
output, not the flights' primary data.

**18. Stage folder naming: short slug (e.g. `round2_mask_v3_trajectory_filter`,
`03_stride1_thresh16_openk3_area30_circ0.3`), not the literal stage
description text.**
**Alternative considered**: use the literal stage text as the folder name
(matches `results_history.csv` wording exactly). **Rejected** (user's
choice, via AskUserQuestion) because spaces/`+`/parentheses in folder names
are awkward across tools/shells, and a short slug is still traceable back to
the matching `results_history.csv` row.

**19. The `03_`/`round N` prefix is tracked BY HAND, not auto-derived from
`candidate_config.json`.**
**Alternative considered**: add a `"round"` field to the config JSON and
have scripts auto-derive the full stage name from it (consistent with how
`MIN_AREA`/`MIN_CIRC` are already auto-derived into the folder name).
**Rejected** (user's choice) - "round number" is a documentation/narrative
concept tracking the session's progress, not a property of the detector
config itself.

**20. Individual inspection crops get a `_true_ball`/`_false_positive`
filename suffix, decided ONLY after actually looking at each one - never
inferred from filename, bin position, or distinct-flight count alone.**
Chose this after finding that a low-count hotspot's crop turned out to
genuinely be the ball (not an artifact) on manual inspection, and separately
that another supposedly-obvious "fixture" crop was actually two different
things depending on exact position. **Alternative considered**: label crops
programmatically from the distinct-flight-count/proximity heuristics used to
find them. **Rejected** because that heuristic is a screening tool, not
ground truth - it had already been shown to disagree with reality in both
directions (real ball flagged as suspicious; a person's arm not initially
suspected).

**21. Full-dataset script (`10_run_full_dataset.py`) uses session-qualified
flight IDs (`"<session>/<flight_dir.name>"`), not bare `flight_dir.name`.**
Chose this after discovering the first full-163-flight run silently
overwrote 72 contact sheets on disk and produced indistinguishable duplicate
CSV rows - 36 of `2026_07_15_gym`'s 37 flight numbers collide with a
same-numbered flight in `2026_07_21_gym` (e.g. both have a `flight_22`).
**Alternative considered (and itself partially rejected)**: session prefix +
FULL relative path (including intermediate subfolders, e.g. `"2026_07_15_gym/
2 ball contacts ground before plane/flight_01"`). **Rejected** because for
the one nested flight this produced a 281-character path, over Windows'
260-char `MAX_PATH` limit, silently failing `cv2.imwrite` for both its cams.
Settled on session prefix + `flight_dir.name` only (confirmed no basename
collisions within either session first) - short enough, still unique.

**22. Parallel multiprocessing scripts are always real on-disk `.py` files,
never `python -c` strings or dynamically-loaded modules.**
Learned this the hard way multiple times this session: `ProcessPoolExecutor`
on Windows uses `spawn`, which re-imports the target module by file path in
each worker process - a `python -c` script or an `importlib`-loaded module
with no real backing file can't be re-imported, so worker processes crash
with `PicklingError`/`AttributeError`. **Alternative considered**: use
`python -c` with inline scripts for quick one-off parallel probes (as
initially attempted for several ad hoc investigations). **Rejected** every
time it involved `ProcessPoolExecutor` - had to be rewritten as a real
script file before it would run.

---

## `claude/claude_rules.md` rewrite

**23. Git workflow rule changed to "commits go directly to `main`" (dropping
the mandatory feature-branch workflow).**
Chose this to document actual practice - all 18 commits so far went straight
to `main`, there's only one branch. **Alternative considered**: keep the
feature-branch requirement as aspirational process improvement going
forward. **Rejected** because the task was explicitly to make the rules
match reality for a solo project, not impose new process the user hadn't
asked for.

**24. Added a strict, separate data-protection rule: never overwrite/delete
files under `data/` or `calibration_outputs/` without asking first -
including derived/tuning outputs a script would normally regenerate every
run.**
Justified directly by decision 16 above (the actual overwrite incident) -
`data/` is fully gitignored, so there's no git history to recover a
previous version from, and the user wants to compare results across runs.
**Alternative considered**: fold this into the general "modifying existing
files requires permission" rule rather than calling it out separately.
**Rejected** because the task explicitly asked for this to be a clearly-
flagged, stricter rule than ordinary code-editing - the consequence of
getting it wrong (irrecoverable data loss) is qualitatively worse than the
consequence of an unwanted code edit (which git can undo).

**25. Confirmation gate scaled down: ask first only for genuinely
ambiguous/risky work; exploratory/diagnostic work goes straight in, with
real-time logging substituting for step-by-step approval.**
Justified by how the session's own exploratory work (diagnosing the
detection-rate problem, running sweeps) actually needed to proceed - a
universal "ask before ANY code" gate would have stopped useful investigation
at every step. **Alternative considered**: keep the original file's
universal "verify understanding + list questions + wait for confirmation
before ANY code" requirement. **Rejected** as not matching the user's
actual expressed preference for this kind of work, and directly contradicted
by the "Mandatory Questions Checklist"/"Chin Wei's Preference" sections that
re-encoded the same universal gate elsewhere in the file - those were
removed for internal consistency (decision 25a).

**25a. Removed the "Mandatory Questions Checklist" and "Chin Wei's
Preference" blocks from the Prompt Clarification Protocol section.**
**Alternative considered**: keep them as supplementary guidance alongside
the scaled-down gate. **Rejected** because both blocks directly re-asserted
"ask before literally anything" in absolute terms, which would have silently
overridden the softened Section 4 rule the moment someone read that section
in isolation.

**26. Did not create a separate `claude/log_template.md`; pointed at the
existing worklog file as the format example instead.**
Direct instruction in the task prompt: don't create a template file unless
it's genuinely trivial to do so, and ask first if one seems warranted.
**Alternative considered**: create a minimal template file anyway, since the
original rules referenced one. **Rejected** per the explicit instruction -
flagged as "out of scope, asking first" rather than created unilaterally.

---

## Pixel-velocity sync correction (error-budget term C)

Cross-referenced against
`claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md`,
which has the full narrative/evidence for each of these.

**27. Use `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz` for
triangulation, not the top-level `calibration_outputs/2026_07_21/stereo_extrinsic.npz`.**
Both exist, committed together 4 minutes apart with no notes distinguishing
them. Chose `test2` for its tighter RMS (0.4087px vs 0.4757px) and baseline
closer to the nominal 850mm (848.91mm vs 853.76mm). **Alternative
considered**: the top-level file (more raw pairs, 25/30 vs 23/24).
**Rejected** in favor of solve quality over raw pair count.

**28. Correct sync per-flight, not per-session — re-derive the offset from
each flight's own timestamps rather than one fixed session-wide constant.**
Justified by the sync audit: residual drifts ~continuously across a session
(`2026_07_15_gym`: +4.82 to -6.67ms; `2026_07_21_gym`: a larger drift that
wraps the audit's bounded representation twice), not sitting at a fixed
value. **Alternative considered**: measure one representative offset per
session and apply it uniformly. **Rejected** because a fixed session
constant would be off by several ms at either end of a drifting session -
exactly the term-C error this task exists to remove.

**29. Correction direction decided per-pair from the actual signed delta-t
(whichever timestamp is earlier gets shifted forward), not a fixed "always
correct camera X" rule.**
Necessary because which camera leads flips sign mid-session (confirmed in
the audit - residual crosses zero within `2026_07_21_gym` itself).
**Alternative considered**: pick whichever camera the session-level average
offset says leads, and always correct that one. **Rejected** since that
would apply the shift backwards for roughly half of any drifting session.

**30. Sub-frame velocity: unsmoothed finite difference between a point's
nearest surviving temporal neighbors, not a fitted/smoothed estimate.**
Chosen because the gap being corrected is sub-frame (a few ms out of
~16.6ms) - deliberately kept simple rather than over-engineered for a
small correction. **Still open, not rejected**: the 2026-07-25 tuned-
detections rerun found the correction sometimes made results worse on
lower-point-count flights, plausibly because one noisy neighbor-pair
estimate has more room to overshoot with sparse data. A smoothed velocity
estimate remains a live option pending further diagnosis - no decision made
either way yet, since the same rerun surfaced two other confounding issues
(decisions 33-34) that need resolving first to even isolate whether the
velocity estimate itself is the problem.

**31. Cross-camera pairing gap cutoff set to half a frame period (8.5ms),
not 1.5x the frame period (25ms).**
First implementation used 25ms, copying `stereo_flight_sync_table.py`'s
`DROP_GAP_FACTOR` convention for detecting dropped frames within one
camera's own sequence. Found wrong by direct testing: on `flight_5`, a
per-camera coverage gap (3 frames dropped by the trajectory filter) let 3
stale nearest-timestamp matches (~16-17ms gaps, under the 25ms cutoff)
through, each reusing the same stale cam1 point for multiple different
cam0 frames - one of them 100mm+ of triangulation error. **Alternative
considered**: keep 25ms, matching the existing convention. **Rejected**
because that threshold answers a different question (dropped frames within
one camera). The correct bound for a genuine cross-camera correspondence is
half the frame period - the sync audit already establishes real offsets
never exceed that range.

**32. `triangulate_flight.py`'s "naive" mode uses RAW (unfiltered)
detections with same-index pairing; "paired_only"/"corrected" use the
per-camera trajectory-filtered set.**
Chose this asymmetry because "naive" represents what the pipeline does
TODAY if nothing changes - today's pipeline doesn't run the trajectory
filter before triangulating. **Alternative considered**: apply the same
filtering to all 3 modes so only pairing/correction differs. **Rejected**
as answering a subtly different, less useful question - "naive" needs to be
the real as-is baseline, not a hypothetical already-filtered one, for the
3-mode comparison to mean anything.

**33. Fixed a stale-data bug: load ball detections from the final-tuned-
detector output (`data/detector_tuning/detections/...`), not each flight's
own `analysis_3/*_detections3.csv`.**
Confirmed directly (`flight_5_cam0`: 19 rows in `analysis_3` vs 37 in the
tuned-detector output) that `analysis_3` was stale, pre-tuning baseline
detector output, not the current ~97%-recall detector. **Alternative
considered**: keep using `analysis_3` since it was already wired up.
**Rejected** once confirmed - validating the sync correction against stale,
sparse detections both understated real point density and (per decision
34) risked confusing a fit-methodology artifact with a property of the
correction itself.

**34. After the tuned-detections rerun showed worse residuals almost
everywhere, investigated the cause rather than concluding "the correction
doesn't help."**
Found that detection SPAN, not just density, grew substantially (e.g.
`flight_60`: 27 frames pre-tuning vs 92 frames tuned - the whole arc
instead of a short late segment). This likely confounds the fit-based
comparison, since a bare quadratic-in-time is a much worse global model
over a full rise-apex-descent arc than over a short segment (context.md's
own physics model needs drag precisely because a pure parabola isn't
sufficient over a full flight). **Alternative considered**: report the
worse numbers as a finding that the correction/pairing doesn't help.
**Rejected** as premature - concluding anything about the correction
method from numbers produced by a validation methodology that may no
longer isolate the thing being tested risks being wrong for an unrelated
reason. No fix decided yet; flagged for the user before proceeding.

**35. Root-caused `flight_50`'s 657mm outlier by checking cam1 specifically
(not just cam0) and viewing the actual contact-sheet frames, rather than
accepting "widest arc in the sample" as sufficient explanation.**
The arc-length theory was tempting (`flight_50`'s u-span was the widest of
the sample) but didn't hold up numerically (only modestly wider than the
next-widest flight, not the 10-20x the residual gap would imply). Checking
cam1's frame-to-frame speed found a single 1121px/frame jump (vs. 9-29
px/frame everywhere else) at frame 116; the contact sheet confirmed the
detector locks onto a person crouched in-frame from that point on, tracked
as if it were the ball. **Alternative considered**: accept the arc-length
theory and move on, since it was a plausible-sounding, cheaper explanation.
**Rejected** because the numbers didn't actually support it, and stopping
there would have missed a real, generalizable finding - the trajectory
filter's `min_run_length` gate doesn't protect against an artifact that
sustains its own internally-smooth run of detections.

---

## Flight velocity/angle binner

Cross-referenced against
`claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md`,
which has the full narrative/evidence for each of these.

**36. World-frame "up" reference: `solve_world_frame()` (checkerboard-pose
solve), not `world_frame_precision_single.py`'s manually-clicked vertical
line.**
That script's guardrails need a vertical-line CSV produced by an interactive
GUI click tool; no such data exists for either `2026_07_21_gym` or
`2026_07_15_gym` (the only one that exists is for a different, unrelated
session, and world-registration doesn't survive across sessions).
**Alternatives considered (put to the user directly, via AskUserQuestion)**:
(a) eyeball-estimate a vertical-line click myself from viewing the images and
write the CSV directly; (b) have the user do the real manual clicking
themselves, pausing the task until they did. **Rejected**: (a) because a
GUI-free pixel estimate is far less precise than a real click-and-zoom, and
this feeds the "up" reference for every flight's angle number; (b) not
chosen by the user, who picked `solve_world_frame()` instead - already used
elsewhere in this codebase (`predict_sweep.py`) for exactly this purpose, no
manual step required. The guardrail CHECKS themselves (baseline-
perpendicular-to-up angle, weak-axis-must-be-width, corner-residual
precision) were kept, reused unmodified - only the source of `up_vec`
changed.

**37. Validated all 4 world-registration candidate images for
`2026_07_15_gym`, rather than trusting the 2 that already had pre-existing
corner-debug crops as sufficient evidence.**
Only `img_0029`/`img_0030` had leftover corner-debug PNGs from some earlier,
undocumented investigation - suggestive but not conclusive evidence that
`img_0026`/`img_0028` were already ruled out. **Alternative considered**:
skip validating `img_0026`/`img_0028` and assume the pre-existing debug
images meant they'd already been tried and rejected. **Rejected** because
the provenance was ambiguous (no note explaining why only those 2 had
debug crops) and validating is cheap - running it confirmed the guess anyway
(`img_0026`/`img_0028` had no detectable checkerboard at all), but that was
verified, not assumed.

**38. Regenerated detection CSVs at the CURRENT tuned detector config
(`candidate_config.json` + exclusion mask v4), rather than continuing to
feed the binner from each flight's existing `analysis_3/*_detections3.csv`.**
The user pointed out mid-task that `analysis_3` predates the detector-tuning
session entirely - it's the OLD/untuned default config (thresh=20, open_k=7,
min_area=200, no exclusion mask), not the ~0.97-combined-rate tuned config.
**Alternative considered**: keep using `analysis_3` since it was already
wired up and the binner's own `filter_trajectory_outliers()` step provides
some cleanup regardless. **Rejected** once flagged - continuing on stale,
sparse, pre-tuning detections would have silently produced a
worse/misleading distribution and defeated the point of the detector-tuning
work already done.

**39. New detection-CSV output centralized under
`data/detector_tuning/detections/<stage>/<session>/`, not per-flight
`analysis_4` folders.**
The user asked directly which they should be, offering both options.
**Alternative considered**: per-flight `analysis_4` subfolders (matching
`04_stereo_three_frame_diff.py`'s original convention). **Rejected** in
favor of mirroring decision 17 above (already made, for the same config, by
this same user, one session earlier) - scattering ~150+37 flight folders
across 2 session directories was already rejected as hard to browse in favor
of centralizing under `data/detector_tuning/`, where this config's contact
sheets and validated-results CSV already live.

**40. Fit-window size (N) stayed frame-COUNT-based (moved from (5,10) to
(20,30)), rather than switching to real-time-span-based windows.**
Switching to the tuned (much denser) detector initially made results WORSE,
not better (implausible-accel skip rate 23%->66%) - root-caused to "first N
paired frames" now spanning only ~150ms of real time under the denser
detector (vs. 166-350ms under the old sparse one), too short to resolve
gravity's curvature against noise. **Alternatives considered (put to the
user via AskUserQuestion)**: (a) keep frame-count windowing but raise N to
empirically-verified stable values (20, 30); (b) redefine windows by target
real-time span instead (e.g. "first ~200ms"/"first ~400ms" of paired
frames), robust to future detector-density changes; (c) let the user specify
custom values. User picked (a) - simpler, smaller code change, empirically
verified (N=20 -> 0/29 implausible fits in a 30-flight check) - over (b)'s
more-principled-but-larger refactor.

**41. Multi-session flight list is derived from which tuned-detector
detection CSVs actually exist on disk, not by re-walking/re-enumerating the
raw `ball_flights` folder tree a second time inside the binner.**
`11_generate_detections_csv.py` already resolves the (non-trivial, nested-
subfolder) flight enumeration once per session when generating the CSVs.
**Alternative considered**: re-implement the same nested-folder-safe
enumeration inside the binner itself, and keep writing an explicit
"skipped, missing csv" CSV row for every flight lacking completed
`ball_in_frame` curation (matching the single-session version's behavior).
**Rejected** as needless duplicated logic; changed the observable behavior
as a side effect (uncurated flights are now a single per-session log count
rather than individual CSV rows) - flagged as a real behavior change, not
silently swapped.

**42. Cross-session binning output relocated to a new top-level
`data/flight_binning/`, not left under `data/2026_07_21_gym/flight_binning/`
(where it was first written, single-session).**
The user caught this mid-task: once the binner covered both sessions, its
output no longer belonged under either session's own folder.
**Alternative considered**: leave it where it was (already working, lowest
effort). **Rejected** - user was right, a cross-session artifact nested
under one session's folder is structurally misleading regardless of
convenience. Per-session outputs (world-frame validation) correctly stayed
under each session's own folder, since registration genuinely is a
per-session concept and the binning result isn't.

**43. Diagnosed the post-detector-swap accel-implausibility regression
before reporting a distribution, rather than either reporting the worse
numbers as-is or reverting to the stale detector.**
Implausible-accel skips jumped from 23% to 66% immediately after switching
to the tuned (better) detector - a counter-intuitive direction that could
easily have been mistaken for "the tuned detector introduced a problem."
**Alternatives considered**: (a) report the degraded distribution as the
new, more-accurate answer since it came from better underlying detections;
(b) revert to the stale detector on the theory that it was giving better
numbers. **Rejected both** - (a) would have silently handed over a visibly
worse, unexplained result; (b) would have reverted the exact fix the user
had just asked for, based on a misdiagnosis (the detector wasn't the
problem, the frame-count window's now-changed real-time meaning was).
Diagnosing first (checked real-time span of the fit window across 30
flights, then swept N directly to confirm the mechanism) found the actual
cause and the actual fix (decision 40) - see the worklog's "unexpected: STOP
immediately" reasoning for why this triggered a full stop rather than a
silent proceed.

---

*Scope note: this log covers the whole session (detector tuning, the
`claude_rules.md` rewrite, the pixel-velocity sync-correction task, and the
flight velocity/angle binner task), numbered continuously rather than split
into separate lists, since all four involved genuine decisions with rejected
alternatives. Execution details without a real competing alternative (e.g.
exact pixel margins chosen for a given exclusion zone, which followed
directly from the safety-check data rather than a judgment call) are
covered in the relevant worklog's evidence trail, not repeated here as
numbered decisions.*
