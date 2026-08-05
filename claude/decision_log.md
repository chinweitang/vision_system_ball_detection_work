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

## Final point labelling tool

Cross-referenced against
`claude/claude_logs/2026-07-27_final_point_labelling_tool_worklog.md`.

**44. Fixed `build_target_queue()` to pick each flight's cam0/cam1 target
frames as a real-time-paired pair (via `select_paired_target()`), not each
camera choosing its own "last valid-range frame" independently.**
Chosen after the user flagged that the same `frame_number` in cam0 vs cam1
is not the same real instant (free-running cameras, per-flight sync offset
drifts up to +/-8.3ms) - at final-point ball speeds an uncorrected mismatch
is tens of mm of error, contaminating the exact ground-truth reference the
label exists to provide. **Alternative considered**: leave independent
per-camera selection, since it was already built and the labelling session
was already in progress. **Rejected** once flagged - re-verified against
the real label file (MD5-unchanged before/after) that the fix didn't lose
any of the 19 already-labelled flights, then relaunched.

**45. Killed the old buggy background labelling process (`TaskStop` on
`bs0y0iq7c`) after the user explicitly asked, overriding the general
"don't touch the user's live session" default.**
The user closed the cv2 window via the X button, not `q`/Esc, which doesn't
reliably terminate the underlying Python process (`cv2.waitKeyEx` keeps
blocking) - `tasklist` confirmed PID 46828 was still alive. **Alternative
considered**: leave it running since killing another session's process is
normally out of bounds. **Rejected** because the user explicitly asked for
it, it was orphaned (not being actively used), and it was still running the
confirmed-buggy independent-selection logic - verified the CSV's line
count/MD5 were unchanged after the kill before doing anything else, to
confirm no corruption.

---

## Gravity vs. drag trajectory fitting (+ RANSAC, all-flights generalization)

Cross-referenced against
`claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md`,
which also covers 3 same-worklog follow-up tasks (RANSAC robust fitting,
generalizing to all 163 flights, and axis-decomposed/duration-stratified
error analysis).

**46. Golden-output strategy for the Phase 0 refactor check: capture fresh
baselines by rerunning each of the 4 consumer scripts UNMODIFIED right now,
rather than trying to match numbers quoted from prior worklogs.**
Chosen because this was a fresh session with no access to the exact run
artifacts those old numbers came from. **Alternative considered**: treat a
mismatch against the old worklog numbers as a gate failure. **Rejected** -
a same-environment before/after diff is a stronger correctness check
anyway (guarantees apples-to-apples) and still verifies the actual intent
(refactor is behavior-neutral); confirmed harmless when the fresh
`triangulate_flight.py` run landed on 31.05mm vs. an old worklog's
29.71mm - logged as a visibility note, not a gate failure, since the
underlying detection files may have been regenerated since.

**47. Pooled K-discovery fits a SEPARATE (p0, v0) per flight but a SINGLE
shared K, rather than the literal single `fit_drag_free_k` joint call the
task named.**
A single p0/v0 forced across both physically-unrelated flights would
answer a different, less useful question ("can one trajectory awkwardly
pass through two unrelated arcs") than the real point of pooling ("does
one K work for both flights"). **Alternative considered**: implement the
literal single joint call as specified. **Rejected** as not physically
meaningful; still produces exactly one final K, so it satisfies the actual
intent via an equivalent route - flagged explicitly as a deliberate
substitution, not silently done.

**48. Upgraded scipy in-place (1.7.3 -> 1.13.1) rather than hand-rolling
RK4+LM, when scipy import broke (numpy 2.x removed `np.Inf`, which the old
scipy pin relied on).**
User's explicit choice when asked. **Alternative considered**: hand-roll
RK4 integration + Levenberg-Marquardt to avoid touching the shared
environment (scipy has never been imported elsewhere in `src/`, so no
other code depends on the old pin). **Rejected by the user** in favor of
the simpler upgrade; verified safe via a `load_g_fixed()` smoke test
(`|g_fixed|=9810.00` exact) before proceeding.

**49. RANSAC inlier threshold: kept ONE value (75mm) everywhere (Phase 1
and Phase 2), reverting a same-session attempt to use two different
thresholds per phase.**
The two-threshold idea was based on investigating flight_22's DETECTED
track's full-arc spread, but Phase 1 (K-discovery) only ever fits the
LABELLED track - re-checked and found the labelled track has no
order-of-magnitude outlier cluster at all (a human labeller doesn't
accidentally click a hand; the known contamination is a detector failure
mode). **Alternative considered**: keep the two-threshold split (Phase 1
1500mm / Phase 2 75mm) since it was already reasoned through and matched
an empirically-confirmed gap. **Rejected** after catching that the
investigation used the wrong dataset for what Phase 1 actually computes -
caught before writing it into the real scripts, not after.

**50. Lowered the RANSAC iteration-count formula's own inputs
(`outlier_fraction` 0.3->0.15, `success_prob` 0.999->0.99) instead of
capping iteration count directly, after Model C's projected Phase 2
runtime blew past the task's ~10-minute budget by 3x+ (~30+ min).**
Root cause: each Model C RANSAC iteration is a full nonlinear
`fit_drag_given_k` call (its own internal scipy convergence), so iteration
count multiplies cost far more steeply than for the closed-form A/B
models. **Alternative considered**: just hardcode a lower iteration count
directly. **Rejected** in favor of adjusting the formula's own
probabilistic inputs (0.15 is still ~2x flight_22's true known
contamination rate of ~8%, so still a conservative worst case) - keeps the
iteration count principled/derived rather than an arbitrary cap. Verified
the ~10x speedup by re-timing before running the real sweep, and confirmed
Phase 1's RANSAC results were unchanged by the lower iteration count
(same inlier/outlier split found either way, since the split itself is not
ambiguous for A/C).

**51. All-flights pooled-K search: profiled 1-D search over K (fit p0/v0
per flight per candidate K, sum residuals, then 1-D-search K alone),
NOT a literal monolithic joint `least_squares` fit across all 163 flights'
979 combined parameters.**
The literal interpretation (163 x 6 params + 1 shared k, no analytic
Jacobian) would need finite-difference numerical differentiation - ~979
extra function evaluations to build one Jacobian, each running 163 ODE
integrations - projected at almost certainly hours, not minutes (caught by
projecting before running, the same category of timing mistake as decision
50, applied preemptively this time). **Alternative considered**: run the
literal joint fit as specified, accepting the long runtime. **Rejected**
once the objective was shown to decompose additively over flights for a
fixed K (no cross-flight coupling except through K) - profiling out K is
the exact same optimum via a tractable route, not an approximation, so it
satisfies the same "shared K, separate p0/v0 per flight" description.

**52. Fixed a bug in `build_corrected_track()`: anchor t=0 at the
AVERAGED-timestamp-sorted sequence's own minimum, not at the first pair's
raw cam0 timestamp.**
Root-caused a hard Model C RANSAC failure (every candidate crashed with
"Values in t_eval are not within t_span") to the first pair's averaged
`(t0+t1)/2` time value sometimes coming out negative, depending on which
camera happened to lead for that specific pair - `solve_ivp` requires
`t_eval` within `[0, max(t)]`. **Alternative considered**: none seriously
entertained - this was a straightforward correctness bug once traced (sort
key and zero-anchor need to use the same, correct, time value). Verified
fixed by a direct manual `fit_drag_given_k` call before rerunning the
batch smoke test; noted this could have hit almost any flight (not
flight_01-specific), since it depends on which pair is first and which
camera leads for it.

**53. Whole-frame pairing bug investigation: concluded there was NO code
bug to fix, and reported that honestly rather than forcing a fix or
silently dropping the investigation.**
The task suspected same-`frame_number` pairing was corrupting flight_41/
flight_44's 3D fits (whole-frame misalignment, ~10.5-10.9ms same-index
delta, outside the +/-8.3ms normal bound). Independently re-confirmed the
deltas, then traced the actual code path and found
`build_corrected_track()`/`build_corrected_pairs()` already does
nearest-TIMESTAMP pairing, never same-index pairing - verified empirically
on flight_41 (all 87 pairs use a consistent +1 frame offset, dt_ms
~-5.72mm, well within bound) and spot-checked across the full magnitude
range of all 38 flights exceeding the bound. **Alternative considered**:
implement a fix anyway since the task assumed one was needed, or quietly
report the aggregate results without flagging the discrepancy from the
task's premise. **Rejected both** - the honest "unexpected: no bug found"
answer is what the evidence supported; forcing a fix onto correctly-working
code would be a needless, unrequested change to a pipeline already
validated across 163 flights.

**54. Did not chase flight_41's elevated Phase 2 RANSAC-health-flag rate
(60.3% of rows vs. ~15-18% for comparable flights) further, despite
confirming it's a real (not artifact) outlier.**
Checked and ruled out both suspected causes (the pairing bug from decision
53, and contamination matching the full-arc residual pattern of the
already-masked detector artifacts) - concluded it's most likely flight_41
genuinely having noisier detector output across most of its N range,
tripping the relative lead-time-bucket health check more often. **Alternative
considered**: investigate the specific noise source now, since it's a
confirmed, measurable outlier. **Rejected** per the task's explicit scope
boundary (already carved out an analogous case, flight_42, as a separate
cause not to fold into this fix) - flagged as a candidate for a future,
separate investigation instead.

## Pi real-time benchmark

**55. Benchmark the real detect→triangulate→predict chain as ONE end-to-end
pipeline replay per flight, not two disconnected benchmarks (detection timed
alone, prediction timed alone fed independently-sourced points).**
Chose this because summing separately-measured numbers on paper can't
capture interaction effects (thread/TBB contention, memory pressure) that
only show up when things run together, and because working through the
isolated-benchmark design first caused triangulation to be silently dropped
as a pipeline stage entirely (caught by Chin Wei mid-planning, not by me).
**Alternative considered**: two separate benchmark scripts (one for
`detector_core`, one for `trajectory_fit`), each simpler to write in
isolation. **Rejected** for the reasons above - the combined design cost a
bit more upfront design time but caught the missing-stage bug and produces a
number that actually answers the real question (does the *chain* fit the
budget).

**56. New top-level `src/pi_benchmarking/` folder, not nested inside
`src/image_processing/` or `src/stereo/`.**
Chose this once the benchmark grew to cover both detection AND prediction -
it's a cross-cutting harness that imports from both `image_processing/` and
`stereo/`, not a step within either pipeline stage's own numbered sequence.
**Alternative considered**: add it as a new numbered script inside
`02_adjacent_frame_differencing/` (matches the file's own docstring
convention). **Rejected** once prediction benchmarking was added to scope -
would have made an oddly-placed dependency on `src/stereo/` from inside an
`image_processing/` pipeline-stage folder.

**57. Pi-side code reuses the real, unmodified production modules
(`detector_core.py`, `pixel_velocity_correction.build_corrected_pairs`,
`label_vs_detection.triangulate`, `all_flights_common.*`,
`trajectory_fit.build_model_fit_predict`/`ransac_fit` + its real RANSAC
constants) via a repo-structure-mirroring transfer to the Pi, rather than
duplicating or reimplementing any of their logic.**
Chose this because the whole point of the benchmark is measuring what's
actually deployed/validated, and because `build_corrected_pairs` in
particular contains real tuned sub-frame pixel-velocity-correction logic
that would be risky to silently duplicate and let drift. Required mirroring
`src/`, `calibration_outputs/`, and `data/` at the same relative paths on
the Pi so each module's own internal `REPO_ROOT`-relative path/import logic
resolves with zero code changes. **Alternative considered (and briefly
adopted, then reversed)**: duplicate just `load_calib`/`triangulate`/
`load_timestamps` into a small Pi-only helper module, specifically to avoid
installing `matplotlib` on the Pi (both `label_vs_detection.py` and
`stereo_flight_sync_table.py` import it at module level for unrelated
plotting code). **Rejected/reversed** once the Pi had internet access
anyway (see decision 58) - installing `matplotlib` into the venv was cheap
and let everything be reused unmodified instead, including
`build_corrected_pairs`, which was the one piece not comfortable
duplicating.

**58. Installed `scipy`/`matplotlib` on the Pi via a `--system-site-packages`
venv (`~/benchmark/venv`), not `sudo apt install`.**
Chose this after discovering the Pi had neither package and no internet on
its direct-ethernet link to the laptop. Chin Wei connected the Pi to a phone
hotspot for internet and offered a sudo password in-chat to unblock
`apt install`; that command was blocked by Claude Code's own safety
classifier (piping a plaintext credential into `sudo`) before it ran.
**Alternative considered**: retry the sudo/apt path some other way.
**Rejected** - stopped rather than work around the classifier block, and
the venv approach (needs no sudo at all, `--system-site-packages` inherits
the already-apt-installed `cv2`/`numpy`) turned out to fully avoid the
credential question. The password was never written to any file; flagged to
Chin Wei that it's in this chat's plaintext history regardless.

**59. Rolling-refit prediction cost sampled at ~10 evenly-spaced checkpoints
per flight, not every single new point.**
Chose this because an every-point rolling refit would mean 80+ individual
nonlinear fits for the longer flights in the sample - too slow for a first
exploratory Pi run before knowing the per-fit cost at all. **Alternative
considered**: refit at every new point, for the most complete picture.
**Rejected** for this first pass as disproportionate risk of a runaway
first run; the sampled version already showed the cost-vs-N growth trend
clearly (~17ms at k=8 up to ~81ms at k=89 for the longest flight).

**60. Flight sample: 4 flights per session, spread across each session's own
frame-count range (min/p25/p50/p75/max within-session), not 8 flights
pooled and spread across both sessions combined.**
Chose this after the pooled approach skewed 5-of-8 flights toward one
session. **Alternative considered**: pool both sessions' flights together
and take an 8-point spread across the combined distribution.
**Rejected** because it under-represented `2026_07_15_gym` (36 flights) next
to `2026_07_21_gym` (126 flights) - the per-session approach guarantees
both sessions are represented across their own short/medium/long range.

**61. After Stage 1/2 results came back, reconsidered and kept the planned
`compute_mask` internal-phase breakdown, rather than skipping it in favor of
jumping straight to a windowed/ROI detector.**
First suggested skipping it once windowing came up, reasoning that windowing
would cut cost across ALL of `compute_mask`'s bundled sub-steps at once, so
knowing which one dominates wouldn't matter as much. Chin Wei pushed back.
**Rejected the skip** on reflection: it's still cheap, it's what
`claude_rules.md` §5 already prescribes (measure each phase before
optimizing), and it still matters even under a windowing plan - morphology
can have a fixed per-call cost floor that doesn't shrink proportionally with
image area at very small window sizes, so the internal breakdown informs how
far windowing can help before diminishing returns set in, not just whether
it helps at all.

**62. Prioritized a RANSAC `n_iterations` sweep ahead of building the
windowed/ROI detector, despite windowing having larger theoretical upside
for the detection-budget problem specifically.**
Chose this ordering because the RANSAC lever is low-risk (changes how many
random subsamples are tried, not what the detector looks at or what RANSAC
fundamentally computes - doesn't touch the already-validated detection
accuracy at all) and well-quantified (the iteration-count-vs-success-
probability tradeoff is already a formula in `trajectory_fit.py`,
previously used once already - decision 50 - to keep the offline Phase 2
sweep within budget). **Alternative considered**: go straight to the
windowed detector first, since detection is the larger of the two budget
overruns (~5.3x vs RANSAC's ~2x+ for long flights). **Rejected** for now -
windowing needs a real accuracy sanity-check (a mis-placed/too-tight search
window can miss real ball positions the validated full-frame detector
would have caught) and a two-mode acquire/track implementation, both bigger
asks than a parameter sweep against existing code, with freeze on 9 Aug.

**63. Confirmed empirically (not just theorized) that morph-close's
elliptical 30x30 kernel is the real-time bottleneck, via a same-input,
same-size, shape-only A/B test on the Pi (elliptical vs rectangular
`cv2.MORPH_CLOSE`, production path untouched, rect result discarded after
timing).**
Chose a same-size shape-only swap specifically to isolate SHAPE as the
variable (not conflate it with a size change, which would leave the real
cause ambiguous). Result: ellipse 84.05ms median vs rect 4.77ms median (a
17.6x difference) on identical input, on real Pi hardware. **Alternative
considered**: trust the [Likely] theoretical explanation from the earlier
discussion (OpenCV's running-min/max optimization for rectangular kernels,
not available for elliptical ones) without measuring it. **Rejected** per
Chin Wei's explicit pushback (decision 61) and `claude_rules.md` §5 - now
[Certain], not [Likely]: kernel shape, not size, is the dominant driver.
Swapping to `cv2.MORPH_RECT` at the same 30x30 size would bring total mask
cost from ~86ms to ~7.4ms - inside the 16.6ms budget on its own. This is
now the highest-leverage, best-evidenced fix identified so far, though
whether a rectangular structuring element preserves the exclusion-mask
false-positive-suppression behavior well enough to keep detection accuracy
close to the validated 0.9208 recall / 0.9751 combined rate is NOT yet
checked - a real open question before recommending the swap for production,
not an assumption to skip.

**64. Validated the rect-close-kernel Pi-speed fix (decision 63) against the
exact original full-163-flight accuracy methodology before recommending it,
rather than treating the 17.6x timing win as sufficient justification on its
own.**
Chose to rerun the real `10_run_full_dataset.py` methodology (same metrics,
same 163-flight set, same labeled flights) with only the one change
(`MORPH_ELLIPSE`->`MORPH_RECT` on the close kernel, via monkey-patching
`detector_core.compute_mask` from a new script rather than editing the
file), and to check PER-FLIGHT regressions (2pp threshold), not just the
pooled average - directly because a pooled average can hide a kernel-shape
artifact that only shows up on specific flights. **Result: REGRESSION, not
free.** avg_combined_rate 0.9667->0.9452 (-2.15pp), labeled_recall
0.9250->0.8875 (-3.75pp), and critically, 83 of 163 flights (51%) regressed
more than 2pp - not concentrated in one identifiable trajectory-geometry
bucket as originally hypothesized, and one of the two labeled flights
(`flight_22`) is among the worst-hit. **Alternative considered**: accept the
Pi timing win as reason enough to recommend the swap, treat accuracy
validation as a follow-up task if time permits. **Rejected** - `close_kernel`
and the exclusion-mask/min_area/min_circ tuning were all validated together
as one system (see decisions 1-11); changing one piece without re-checking
the whole system risks exactly the kind of silent regression this project's
own recall-gated tuning methodology (decision 4) was built to catch.
Conclusion: the rect-kernel swap is NOT recommended for production as-is:
it fixes the Pi timing problem but breaks the already-validated detection
accuracy, and would need further work (e.g. retuning `min_area`/`min_circ`
for rect's differently-shaped blob edges) before being viable on its own
merits, not a straight swap.

**65. Measured the rect-close-kernel fix's effect on Model C prediction
error (the actually load-bearing metric) directly, at a fixed 430ms window,
rather than stopping at the detection-accuracy regression (decision 64) and
assuming it propagates downstream.**
Chose a fixed TIME window (430ms — deliberately the same value as the
full-population P5 flight duration computed earlier this session, not a
coincidence) rather than the usual N-sweep, since the question here is "one
representative operating point," not a full lead-time curve. Reused
`trajectory_model_prediction_sweep_all_flights.py`'s exact held-out-target
methodology (target triangulation, frame-exclusion-for-leakage, RANSAC
fallback) rather than re-deriving it. **Result: population-level impact is
negligible** (pooled median error 179.3mm ellipse vs 190.5mm rect, delta
median 0.4mm) — RANSAC and the trajectory-consistency filter absorb almost
all of the detection-accuracy regression found in decision 64. **But not
uniformly**: 7 of 157 flights (~4.5%) show real regressions (250-866mm,
above the ~250mm noise floor — cross-checked against
`prediction_error_summary_table.csv`'s own Model C numbers, not just
trusted as given) that RANSAC only partially compensates for (its
rejected-fraction rises on 6 of these 7, correctly flagging more outliers,
but the surviving fit is still worse). Which flights land in this bad 4.5%
is NOT predictable from detection-rate-regression severity alone — only 1
of the 4 worst DETECTION-regression flights (decision 64) is among the 7
worst PREDICTION-regression flights. **Alternative considered**: treat
decision 64's detection-accuracy finding as sufficient grounds to reject
the rect-kernel fix outright, without checking whether it survives to the
metric that actually matters. **Rejected** — would have thrown out a fix
that turns out to be mostly fine, missing the more precise (and more
useful) finding that the real risk is a small, currently-unidentified-by-
detection-rate-alone subset of flights, not the fix in general. Caught a
real flight-ID collision risk in passing: `2026_07_21_gym/flight_22` (a
genuine +332mm regression) is a DIFFERENT flight from
`2026_07_15_gym/flight_22` (the originally-flagged detection-regression
flight, only +22mm here) — same number, different session, the exact
collision class `10_run_full_dataset.py` already guards against elsewhere;
stayed session-qualified throughout specifically to avoid this trap.
Conclusion updated from decision 64's "not recommended as-is": the rect
fix's DOWNSTREAM cost is smaller and more localized than the raw detection
numbers suggested, but a real minority-case risk remains unidentified and
unexplained (why these 7 flights specifically, not others) — worth
understanding before shipping, not yet a clean "it's fine."

**66. Traced the flight_51/flight_125 prediction regressions stage-by-stage
(detection -> filtering/pairing -> triangulation -> RANSAC -> fit) instead
of stopping at "RANSAC's rejected_frac rose, so it must be compensating"
(decision 65's surface-level read).**
Chose to reuse `build_corrected_track_from_dir`/`target_time_sec` directly
from `rect_vs_ellipse_prediction_comparison.py` (import, not a 3rd
duplicate) and rerun the real RANSAC call for both variants to get the full
`accepted_frames`/`rejected_frames`/`n_inliers` detail decision 65's
pooled-CSV columns didn't carry. **Result: the divergence is NOT primarily
from bad individual detections or triangulation error** — both stay small
(2D deltas mostly sub-few-pixels; 3D median deltas 15-20mm) and the
existing trajectory-consistency filter already catches the rare wild
single-frame outlier (flight_125's 711px cam1 case, excluded before
triangulation). **The real break is RANSAC's accepted-inlier SET
reshuffling substantially** (Jaccard overlap 0.33-0.36, both flights) when
run against a slightly smaller/different candidate pool (23-26 points, not
hundreds) — a different winning combination, not individually-bad points,
drives the final 250-865mm gap. **Alternative considered**: treat decision
65's rejected_frac finding (rect rejects more, "RANSAC is compensating") as
the full explanation and stop there. **Rejected** — rejected_frac rising is
consistent with RANSAC correctly flagging more candidate points as
suspect, but doesn't by itself explain why the SURVIVING fit is still
substantially worse; the accepted-set-composition angle is the actual
mechanism, and it's a materially different (and more useful) finding: this
is about candidate-pool robustness margin at low N, not about RANSAC
"failing" to detect noise. Relevant to the earlier RANSAC-iteration-count
theory discussion too — a small candidate pool limits how much iteration
count alone can buy you, since the problem is which points are AVAILABLE
to sample from, not just how many random draws are attempted.

**67. Precomputed each flight's fit window ONCE (track/target/triangulation)
and only re-ran the RANSAC call itself across the n_iterations x seed grid,
rather than rebuilding the window 22,500 times.**
Chose this after recognizing the window-building work (triangulation,
pairing, target lookup) is identical across all 150 (n_iterations, seed)
combinations for a given flight -- only the RANSAC call varies. Cut the
grid's redundant work from 22,500 window-builds to 150. **Alternative
considered**: run the full per-combination pipeline every time, matching
the structure of the per-flight scripts used elsewhere in this task.
**Rejected** as needlessly wasteful once the redundancy was noticed --
confirmed via a timing pilot first anyway (117 min projected serial even
with this optimization) before committing to the full run, in keeping with
the project's own measure-before-running-long-jobs convention.

**68. RANSAC n_iterations sweep result: accuracy is essentially flat from
n_iterations=3 to 25 (median error 193.6mm -> 189.8mm, <4mm total change),
while wall-clock time scales almost perfectly linearly (295ms -> 1861ms,
6.3x) -- strong evidence n_iterations can be cut substantially from the
production value of 15 with near-zero accuracy cost.**
Verified via a full 150-flight x 6-n_iterations x 25-seed grid (22,367
successful runs), not a small sample -- directly answers the question from
the earlier RANSAC-theory discussion (decision log entries around the
success-probability formula) with real data rather than the formula's
theoretical prediction alone. **Did not stop at the flat aggregate median**:
also checked seed-to-seed spread per flight (boxplot rule vs population),
found 73 (n_iterations,flight) combinations flagged as unstable, several of
which (flight_121, flight_122, flight_38, flight_45, flight_46) stay
flagged even at n_iterations=25 -- more iterations does not fix them,
ruling out "just needs more tries" as the explanation. **Connects directly
to decision 66**: `2026_07_21_gym/flight_22` and `flight_125` (two of Task
B's pipeline-divergence flights) are flagged here too, using plain ellipse
detections with no rect kernel involved -- these flights are RANSAC-fragile
independent of kernel choice, consistent with decision 66's "candidate-pool
robustness margin at low N" mechanism, not something specific to the
rect-kernel investigation. **Alternative considered**: report only the
pooled median/IQR table as sufficient justification for cutting
n_iterations. **Rejected** — would have missed that a specific, identifiable
subset of flights doesn't behave like the population average, which matters
for an honest recommendation (cutting iterations is safe for MOST flights,
not uniformly all of them).

**69. Re-aggregated the 7-flight structurally-unstable subset on its own
(not just as the red series in Figure 2) to directly answer whether
n_iterations=3 is safe for it specifically -- found the subset's
instability is NOT an iteration-count problem at all.**
Chose to compute the subset's own seed-to-seed spread trend (median-of-
per-flight-std across n_iterations), and compare its n=25->n=3 widening
ratio against a freshly-computed population baseline, rather than
inferring an answer from Figure 2's visual shape alone. **Result: the
subset's seed-std (137-201mm) is 5-8.5x the population's (19-41mm) at
EVERY n_iterations tested, including n=25** -- and its own widening ratio
going from 25 to 3 iterations (1.47x) is smaller, proportionally, than the
population's own widening (2.15x). **Alternative considered**: assume
(reasonably, from first principles) that a fragile subset would show
*worse* degradation than the population as iterations drop, and recommend
keeping n_iterations higher for these flights as a safety margin.
**Rejected once measured** — the data shows the opposite: this subset is
already maximally unstable regardless of iteration count, so more
iterations buys it nothing, and cutting iterations costs it nothing
additional either (median error was actually LOWER at n=3 than n=25,
260.1mm vs 301.4mm). Directly confirms decision 66's candidate-pool
diagnosis from a second, independent angle: the fix for these 7 flights is
not "run RANSAC more," it's identifying and handling them separately
(a fast pre-flight-quality check, e.g.), since no amount of extra search
resolves a fundamentally too-small/too-marginal candidate pool.


Decision 70: RANSAC n_iterations reduced from 15 to 3

Context: Pi benchmark (Stage 1) found RANSAC at n_iterations=15 costing 
up to ~1170ms on longer flights, exceeding available compute budget. 
Investigated whether iteration count could be safely cut.

Evidence:
- Full sweep (150 flights, duration>=430ms, n_iterations in 
  [3,5,7,10,15,25], 25 seeds each, 22367 successful runs): population 
  median error flat across the entire range (193.6mm at N=3 vs 189.8mm 
  at N=25, <4mm spread) — accuracy cost of cutting iterations is 
  negligible at the population level.
- Population seed-to-seed spread (std dev) does grow as N decreases 
  (19.0mm at N=25 -> 40.8mm at N=3, ~2.15x), confirming iteration 
  count does have the expected theoretical effect on reproducibility 
  — but the absolute magnitude stays small next to the ~250mm 
  established detection-error noise floor at this operating point.
- Wall-clock time scales linearly with N (~75-98ms/iteration, laptop 
  timing): N=3 -> 295.5ms vs N=15 -> 1162.7ms median, a ~3.9x saving.
- Re-aggregated the same data for the 7-flight structurally-unstable 
  subset (flagged via boxplot-outlier rule, stays flagged through 
  N=25): seed-std for this subset (137-201mm) does NOT show the same 
  smooth widening-as-N-decreases pattern the population shows (only 
  1.47x widening N=25->N=3, vs population's 2.15x) — it is already 
  5-8.5x the population's spread AT EVERY iteration count tested, 
  including N=25. This subset's instability is not iteration-count-
  driven.

Decision: adopt n_iterations=3 in production. Justification: costs the 
well-behaved population (143/150 flights) negligible accuracy for a 
~3.9x compute saving, directly addressing the Pi timing overrun. Costs 
the 7-flight fragile subset nothing ADDITIONAL — they are unreliable 
at N=25 already, for a different reason (small/marginal candidate 
pool, per decision 66's pipeline-divergence diagnosis), so no amount 
of iteration count fixes them.

Caveat: fragile-subset finding is based on n=7 flights — framed as 
"consistent with the candidate-pool hypothesis," not a proven general 
law. This subset needs a separate mechanism (pre-check on candidate 
pool size, or a more robust fitting strategy) — flagged as a distinct 
open item, not resolved by this decision. Inlier-distance-threshold 
sweep (next) tests whether a different RANSAC lever helps this 
subset specifically.

**70. Swept RANSAC's inlier distance threshold (production 75mm, verified
single-source-of-truth before starting) to test whether the 7-flight
unstable subset is threshold-limited -- found threshold DOES affect inlier-
set consistency (Jaccard) but does NOT fix, and actually worsens, accuracy.**
Chose to store `accepted_frames` per run (not just `n_inliers`) specifically
so pairwise Jaccard overlap across the 25 seeds could be computed per
(flight, threshold) -- the only way to directly test "does loosening the
threshold stabilize which points get picked," rather than inferring it
indirectly from error alone. **Result**: mean Jaccard overlap across the 7
flights rises substantially and consistently with a looser threshold
(0.573 at 50mm -> 0.878 at 150mm, every individual flight trending the same
way) -- so threshold is NOT irrelevant to inlier-set selection, contradicting
a naive reading of decision 66 as "threshold doesn't matter at all."
**But** the unstable subset's median error gets WORSE as threshold loosens
(288.4mm at 50mm -> 260.1mm at production's 75mm, the best point in the
sweep -> 328.4mm at 150mm) -- rising Jaccard does not coincide with better
accuracy, the opposite happens. **Alternative considered**: treat the rising
Jaccard trend alone as evidence that loosening the threshold is a viable
fix and recommend it. **Rejected** once the error trend was checked
alongside it (exactly what the task required stating explicitly, not just
reporting Jaccard in isolation) -- loosening the threshold trades
instability for being CONSISTENTLY WRONG (more, farther-off points admitted
into the inlier pool), not a real fix. Refines decision 66 rather than
overturning it: threshold and small candidate-pool size are two symptoms of
the same underlying shortage of good points for these flights, not
independent levers -- and production's 75mm already sits near this
subset's best empirical point in the sweep, so there's no free win
available by retuning it either.

**71. Remeasured the rect-branch full detection cost directly on the Pi
instead of continuing to rely on the assembled 9.78ms estimate -- confirmed
accurate, no correction needed.** Context: the 9.78ms/frame/camera figure
used in the throughput check had been assembled from two separate
measurement runs (diff/contours timing from the ellipse-branch script,
mask-only timing from decision 63's rect-branch script), not one direct
end-to-end measurement -- a real risk before using it for a further design
decision (the two-axis sweep, decision 72). **Result** (Pi, n=448 frame-pairs
across the same 8-flight sample, single continuous timed block per pair:
diff->threshold->rect-morph-open->rect-morph-close->exclusion->
contours+moments): median=9.794ms, p95=9.986ms, mean=9.814ms. Delta vs the
9.78ms estimate: +0.014ms (+0.1%) -- confirmed accurate, well within noise.
**Alternative considered**: skip remeasurement and proceed directly to the
sweep on the existing estimate. **Rejected** -- cheap to verify (one Pi
script, ~1 min runtime) and the sweep's headline result depends on this
number being right; verifying first is strictly safer than trusting an
assembled figure for a downstream decision. Output:
data/pi_benchmarking/rect_total_results_20260803.json.

**72. Two-axis Pi sweep (fit window W vs full pipeline cost/error, rect
kernel, serial cams, RANSAC n_iterations=3) -- run to find the largest W
satisfying the 430ms actuation budget. Result: detection compute, not
RANSAC, is now the dominant real-time bottleneck, and NO swept W clears the
budget at p95.** Swept W in [150,200,250,300,350,400,430]ms on the Pi, full
pipeline per flight (detect cam0+cam1 serial -> triangulate -> RANSAC-fit
Model C -> predict position+velocity), against 150 flights
(duration>=430ms), with two independent velocity-error estimates per the
task spec: method (a) full-trajectory self-consistency check, method (b)
genuinely independent 2-3-point finite difference. Confirmed before running
that the existing Model C fit code retains full 6D ODE state (position +
velocity) at query time, not just position (`trajectory_fit.py:77-104`
returns only `sol.y[:3].T`, discarding velocity -- required writing a
verified mirror, `simulate_drag_with_velocity`, that keeps `sol.y[3:]` too,
rather than assuming the existing code already exposed it).

**Bug caught before trusting results**: first pilot run showed detect_sum_ms
roughly HALF of the value implied by decision 71's confirmed 9.794ms/frame
baseline. Root cause: per-flight warmup (5 untimed pairs/camera, matching
every earlier Pi benchmark script's convention) left the per-frame timing
dict missing entries for those 5 frames; summing real per-frame times for a
small-W window that overlapped the untimed range silently defaulted missing
frames to 0.0 -- a systematic undercount that got WORSE for smaller W,
biasing the sweep toward making small W look more affordable than it really
is (a real design-decision-distorting bug, not cosmetic). **Fix**: replaced
per-flight warmup with a one-time global cache warmup before the flight
loop, so every frame of every flight is genuinely timed. Verified the fix
post-repair: per-frame detect cost across all pilot flights/W values came
out 9.50-9.59ms, consistent with decision 71's 9.794ms baseline (small
residual plausibly thermal/run-to-run variance, not a systematic bias) --
confirmed correct before running the full 150-flight sweep.

**Result** (150/150 flights succeeded, no errors): largest W with
MEDIAN(W+compute)<=430ms is W=150ms (418.2ms median, but 436.1ms at p95 --
already over budget at the tail). **No swept W satisfies the p95 criterion
at all** -- even the smallest W's tail exceeds 430ms, and the gap widens
sharply with W (W=430ms: 1052.2ms median, 1075.9ms p95, ~2.4x over budget).
At the W=150ms headline point: position error median=409.1mm (IQR 344.6mm),
velocity error method(a)=362.3mm/s (IQR 349.3), method(b)=6960.5mm/s (IQR
7805.0) -- all substantially worse than the W=430ms fixed-window numbers
used throughout the rest of this session (192.2mm position error), because
few points are available this early.

**Root cause, and this reverses this session's own earlier framing**:
detect_sum dominates compute at every W (191ms of 268ms total at W=150,
71%; 494ms of 622ms at W=430, 79%) -- RANSAC (n_iterations=3, decision 70)
is a MINORITY cost throughout (76-132ms), not the bottleneck. Per-point cost
is serial-both-cams at ~19ms/point (2x the confirmed ~9.5-9.8ms/cam rect
baseline), and this compounds: N points needed costs ~19ms*N of real
wall-clock detection time, which grows faster than the observation window W
itself. This sharpens the earlier throughput check (which evaluated the
~19.5ms serial-both-cam cost against the single-frame 16.6ms/60fps budget
and called it "sufficient") -- that check did not evaluate the CUMULATIVE
effect of the per-frame deficit compounding across an entire fit window's
worth of frames. Flagged as a genuine gap in the earlier check's scope, not
silently reconciled.

**Velocity methods (a) and (b) DIVERGE meaningfully, per the task's explicit
instruction not to collapse them**: pooled medians 195.0mm/s (a) vs
6119.0mm/s (b), a 31.4x ratio; method (b) has 2.3% (21/915) extreme outliers
>10x its own median from small-dt finite-difference amplification, as
anticipated. Method (a) is inherently optimistic (same model, more data,
self-consistency not independent ground truth); method (b) is genuinely
independent but far noisier. True velocity accuracy is not asserted as
either number -- reported as an open, unresolved gap.

**Alternative considered**: treat RANSAC n_iterations as the primary lever
still worth tuning further, since that was this session's dominant prior
finding. **Rejected once measured** -- this sweep shows detection, not
RANSAC, is now the binding constraint at every tested W; further RANSAC
iteration cuts would yield only marginal additional savings against a
~70-80%-detection-dominated total.

**Status: NOT a passing result.** No W in the swept range satisfies the
design budget's p95 criterion; W=150ms narrowly satisfies the median
criterion only, with materially worse position/velocity error than the
fixed W=430ms numbers used elsewhere this session. This is now the primary
open problem for the remaining time to the 9 Aug freeze -- ahead of further
RANSAC tuning, since RANSAC is no longer the dominant cost. Windowed/ROI
detection (deferred earlier this session, decision 61's priority list) is
the most direct lever on the actual bottleneck now identified.

Outputs: data/pi_benchmarking/two_axis_full_20260803.json (raw, 150
flights), data/pi_benchmarking/two_axis_sweep/{two_axis_sweep_raw.csv (1050
rows), two_axis_sweep_summary_by_W.csv (7 rows), figures/figure{1,2,3}_*.png}.

**73. Recomputed the design timing budget as launch-to-CROSSING-PLANE
duration (crossers only, n=107) instead of the stale 430ms full-flight
figure -- result: P5=535.8ms, LONGER than 430ms, not shorter as
hypothesized.** Context: 430ms was P5 of full-flight duration
(launch-to-held-out-target) across ALL 158 flights; the real deadline is
launch-to-CROSSING (only defined for the 107 crossers, HIT+MISS_HIGH_WIDE
-- MISS_SHORT excluded, no crossing event). **Clock check performed before
computing anything**: `build_corrected_track()` zero-bases t at the first
usable fit frame; `classify_flight()`'s `t_cross` (brentq bisection) is
computed on that same array with no re-zeroing -- t_start=0 and t_cross
already share a clock, no reconciliation needed. **Gap found**: t_cross is
computed in `classify_flight()` but never persisted to
`crossing_classification.csv`'s columns -- retrieved by re-calling the
frozen, unmodified `classify_flight()`/`build_geometry()` (fixed
RANSAC_SEED, deterministic) for the 107 crossers, verifying cls+duration_ms
reproduced exactly (107/107 matched, 0 mismatches) before trusting any
t_cross value -- a reproduction of the same frozen computation to recover a
discarded field, not a re-fit. **Result**: P5=535.8ms, P10=560.7ms,
P15=581.8ms, median=1120.6ms -- LONGER than 430ms (delta +105.8ms),
because most crossers here are lob-regime flights (60/107) that reach the
plane well into their arc, typically near/after apex, later than the old
target-point convention's typical point. 8 shortest flights are all flat,
near-zero-elevation drives (491-545ms) -- a real, physically sensible low
tail. Outputs: data/prediction/04_launch_to_crossing_budget/.

**74. Split the launch-to-crossing budget by elevation regime
(FLAT/MID/LOB) -- pooled P5 was throw-mix-contaminated; FLAT P5=501.6ms is
the real, throw-mix-independent design target.** Context: decision 73's
pooled P5 (535.8ms) reflects how many lobs vs flats were thrown that
session (60/107 LOB), not the physics -- flat drives reach the plane
fastest and should set the true worst case regardless of throw mix.
Reused decision 73's launch_to_crossing.csv as-is (no re-fit, no t_cross
recomputation), same elevation cuts as `02_candidate_reselection`
(FLAT<15deg, MID 15-45deg, LOB>=45deg). **Result**: FLAT P5=501.6ms (n=35),
MID P5=709.8ms (n=12), LOB P5=1080.0ms (n=60) -- clean separation between
regimes (FLAT max ~750ms, LOB min ~1048ms, barely overlapping), confirming
elevation bin is a real distinct kinematic regime here, not an arbitrary
cut. FLAT's 3 shortest flights are the SAME 3 that topped the POOLED
distribution's low tail in decision 73 -- confirms the low tail is a real
FLAT-regime floor, not binning noise. Selection was by elevation_deg
throughout, never by speed (speed reported for context only). Outputs:
data/prediction/05_budget_by_elevation_bin/.

**75. Corrected the detection-timing model from batched-after-window (decision
72's framing) to concurrent-with-capture, and measured real threaded
per-pair detect on the Pi: 1.27x speedup, 13.578ms median -- BELOW the
16.667ms cadence, but with far less margin than assumed.** Context: decision
72's two-axis sweep modeled detection as happening AFTER a fit window
closes (`W + compute`), finding NO W under 430ms cleared budget. The user
identified this as the wrong model -- frames arrive at a fixed 16.666ms
cadence regardless of detect speed, and if per-pair detect (parallelized
across cam0/cam1) stays under that cadence, detection is fully hidden under
capture with zero backlog. This had never been measured -- only the SERIAL
per-pair cost (~19ms, decision 72) was known. **Measured for real** (Pi,
n=488 pairs, 8-flight sample, same frames timed both ways in one run for a
fair comparison): SERIAL median=17.309ms; THREADED (Python `threading`,
wall-clock around the join, not summed per-thread times) median=13.578ms,
p95=14.973ms -- **speedup only 1.27x**, well under the 1.7x bar that would
indicate clean parallelism. **Root cause**: Pi's OpenCV build is
TBB-parallel internally (confirmed via `cv2.getBuildInformation()`), so two
Python threads each issuing TBB-parallel cv2 calls partially CONTEND for
the same underlying thread pool rather than getting a clean ~2x from
independent camera work -- a real, measured effect, not a formality.
Multiprocessing fallback (auto-triggered since speedup was under
threshold) was WORSE than serial (0.62x) -- IPC/pickling overhead for the
~1.5MB grayscale frames dominates at this call size. **Headline: 13.578ms
median IS below the 16.667ms cadence (capture-bound, no backlog)**, but the
margin (~3ms median, ~1.7ms at p95) is much tighter than the prompt's own
framing assumed (~9.5ms, implicitly expecting near-linear 2x off the known
single-camera cost) -- flagged explicitly at the checkpoint rather than
letting it surface only in aggregate figures later. Output:
data/pi_benchmarking/parallel_detect_checkpoint_20260804.json.

**76. Full Pi prediction-pipeline sweep (concurrent-with-capture, 107
crossers x 24 cutoff times t) -- the v1 universal 490ms deadline is met
with real margin for FLAT/MID, and latency NEVER binds in any regime at any
t; RANSAC, not detection, dominates latency throughout.** Built on decision
75's confirmed capture-bound regime: latency(t) = last-pair detect +
triangulate + RANSAC-fit + predict + one 16.667ms frame lag (3-frame-diff
lag), every term measured on the Pi, not assumed. Reference crossing state
(position/velocity/HIT-MISS) reused directly from decision 73's frozen
`crossing_classification.csv` -- NOT recomputed -- so accuracy here is a
CONVERGENCE result (early-cutoff fit vs full-arc reference), explicitly
labelled as a placeholder throughout (manual crossing-bracket labels not
ready yet). Early-cutoff crossing search generalizes `classify_flight()`'s
bisection (interpolation-only, valid there since the full track spans the
crossing) to bracket-expansion EXTRAPOLATION past the window's own last
point, since early cutoffs haven't reached the plane yet within their own
observed window. Velocity computed via the SAME finite-difference approach
`classify_flight()` itself uses (verified from source: dt=1e-3s forward
diff, not true ODE state) for genuine apples-to-apples comparability with
the reference. **Data gap caught and fixed before the full run**: 2 of the
107 crossers (`2026_07_21_gym/flight_74`, `flight_88`) were outside the
duration>=430ms population already on the Pi from decision 72's transfer --
crossing-plane reachability and duration>=430ms are correlated but not
identical selection criteria. Transferred the 2 missing flights' frame data
(~85MB) before re-running.

**Result, 107/107 flights succeeded, n_airborne matches decision 74's bin
populations exactly at every t (FLAT=35, MID=12, LOB=60)**:

| bin | n_airborne@490 | n_fit_ok@490 | HIT/MISS acc | pos_err med mm | latency med ms | binding @490ms |
|---|---|---|---|---|---|---|
| FLAT | 35 | 35 | 100.0% | 38.8 | 176.3 | neither binds |
| MID | 12 | 12 | 100.0% | 85.5 | 194.7 | neither binds |
| LOB | 60 | 59 | 94.9% | 156.3 | 202.3 | error-bound (latency has slack) |

Median latency tops out at ~320ms even at t=1250ms (LOB) -- nowhere close
to 490ms at ANY regime or cutoff time, directly reversing decision 72's
batched-model conclusion. Detection's contribution to latency is a
near-constant ~13-19ms throughout; RANSAC grows from ~80ms (t=150) to
~300ms+ (t=1250) and is the actual driver. Per-bin t_min (median
error<100mm AND accuracy>=90%, both provisional): FLAT=300ms, MID=350ms,
LOB=700ms -- all comfortably inside each regime's own real budget from
decision 74 (FLAT/MID/LOB P5=502/710/1080ms), the concrete case for a v2
regime-adaptive window: LOB could use ~700ms instead of the v1-universal
490ms and stay well inside its own ~1080ms true deadline, buying
materially better accuracy (156mm->~90mm) essentially for free. Detection
diagnostics pooled across the full run: median=13.707ms, p95=15.108ms,
p99=15.404ms, max=19.224ms -- all under cadence even at the tail; only 6
individual pairs (of several thousand) exceeded cadence across the whole
run. Thermal-drift check (first- vs last-quartile flights processed):
delta=-1.452ms -- no evidence of throttling over the ~14min run.

**Alternative considered**: keep decision 72's batched-detection latency
model and conclude no W/t is viable. **Rejected** -- the user identified
the batching assumption as physically wrong for the real capture pipeline;
once corrected and measured (decision 75), the pessimistic conclusion does
not hold. **Caveat restated**: every accuracy/error number is CONVERGENCE
vs a full-arc reference, not ground truth -- this analysis needs re-running
once manual crossing-bracket labels exist. Outputs:
data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/
{pipeline_sweep_raw.csv (2568 rows), pipeline_sweep_summary_by_bin_T.csv
(72 rows), summary.txt, figures/figure{1,2,3}_*.png}.

**77. First real ground-truth check: Model-C's re-derived crossing state vs
20 manually-labelled crossing brackets -- median position error 105.7mm,
velocity gaps mostly within ~1 label-SD of zero.** Context: decisions 73-76
all relied on the full-arc Model-C fit as the accuracy REFERENCE
(explicitly labelled "convergence, not ground truth" throughout, since
manual crossing-bracket labels weren't ready) -- this closes that gap for
the 20 candidate flights selected in `02_candidate_reselection` and
manually labelled in `03_crossing_labels`. Ran in parallel to decisions
75-76's Pi work (separate session/task, worklog
`claude/claude_logs/2026-08-04_1925_label_vs_fit_crossing.md`, prompt
`claude/prompts/2026-08-04_1925_label_vs_fit_crossing.md`).

**Methodology** (stated up front per the task's own rigor requirements,
each independently verifiable in the worklog): time origin verified by
construction to already share `classify_flight()`'s absolute clock (both
trace back to `build_corrected_track`'s zero-basing) -- no re-anchoring
needed. Per-axis quadratics fit to the manually-labelled bracket points
(camera frame, mathematically equivalent to world-rotated fitting for this
case). Position compared in the SAME plane-local (u,up) aperture frame
01_'s HIT/MISS box and `crossing_Y`/`crossing_Z` were defined in (not raw
world axes) -- required for "same plane" comparability. Velocity compared
in world-semantic axes (depth/width/up), with per-axis OLS covariance
propagated into a label-fit SD via the standard linear-combination
variance formula, so component gaps can be judged against label-fit noise,
not just compared as bare numbers. Each fit (label quadratic, Model-C
RANSAC) found its OWN `t_cross` via the same depth-root-crossing
definition, not forced to a shared value.

**Bug caught before any real comparison happened** (a false stop, not a
real Model-C mismatch): `load_classification()` keyed
`crossing_classification.csv` by `flight_id` alone -- not globally unique
across sessions (`flight_13` exists in both `2026_07_15_gym`, cls=
MISS_SHORT, and `2026_07_21_gym`, cls=HIT, the actual flagged-flat probe
candidate from `02_`) -- silently compared against the WRONG flight's
reference. Fixed by keying `(session, flight_id)`; re-ran clean. Same class
of bug this project's tooling has been bitten by and fixed before
(session-qualification, referenced in decision 65's worklog).

**Result**: all 20/20 flights exactly reproduced `01_`'s stored
`cls`/`duration_ms` (RANSAC seed=42, deterministic) after the keying fix --
Model-C's classification is fully reproducible, not a source of
discrepancy here. Residual gate (3x population median): none flagged,
though per-flight residuals (2.5-46.0mm, median 32.9mm) run somewhat above
the task's own stated ~10-20mm expectation as a population-level shift, not
a single outlier -- reported as-is, not silently adjusted to force a flag.

**Pooled position (n=17, clean = symmetric + not residual-flagged)**: bias
Y=+7.9mm, RMS Y=111.6mm; bias Z=-34.3mm, RMS Z=65.3mm; median total error
105.7mm, p90=199.0mm. **Pooled velocity (n=17, Model-C minus label)**: depth
mean diff -13.4mm/s (RMS 247.9, label SD ~154.7); width mean diff +47.7mm/s
(RMS 301.9, label SD ~282.2, the largest relative gap of the three); up
mean diff +30.5mm/s (RMS 93.5, label SD ~135.3); speed mean diff -51.0mm/s
(RMS 220.4). Most component gaps sit within ~1 label-SD of zero --
largely consistent with label-fit noise rather than a clear systematic
Model-C bias. 3 asymmetric-bracket flights (flight_11 n=5, flight_119 n=5,
flight_107 n=4) reported separately, excluded from pooled numbers as
lower-confidence given the reduced point count. Per-elevation-bin split
(FLAT n=7 median=119.9mm, MID n=5 median=77.1mm, LOB n=5 median=116.5mm)
reported as INDICATIVE only in the per-flight CSV, not restated as
confident numbers given n~5-7 per bin.

**This is a genuinely positive result for the pipeline's real-world
validity**: a ~106mm median position error and velocity gaps mostly inside
1 label-SD directly supports treating decision 76's convergence-based
accuracy numbers as a reasonable proxy for ground truth, at least for this
20-flight sample -- not proof the two are interchangeable at scale, but a
real, first check rather than an assumption. Should be revisited once more
flights are manually labelled (n=20 here vs the 107-crosser population
decision 76 swept).

Outputs: `data/prediction/06_label_vs_fit/{label_vs_fit_per_flight.csv
(20 rows, full numeric backing for every summary number above),
position_scatter.png (Y-Z aperture-frame scatter, label vs Model-C paired
per flight, coloured by elevation bin), velocity_comparison.png (3 panels,
one per world axis, label-fit points with SD error bars vs Model-C points),
summary.txt (plain-text headline numbers)}` -- all 4 files verified present
on disk (sizes 8.5KB/85KB/121KB/0.8KB) before writing this entry.

---

*Scope note: this log covers the whole session (detector tuning, the
`claude_rules.md` rewrite, the pixel-velocity sync-correction task, the
flight velocity/angle binner task, the final-point labelling tool, the
gravity-vs-drag trajectory fitting task with its RANSAC/all-flights/
axis-decomposition follow-ons, and the Pi real-time benchmark task),
numbered continuously rather than split into separate lists, since all of
these involved genuine decisions with rejected alternatives. Execution
details without a real competing alternative (e.g. exact pixel margins
chosen for a given exclusion zone, which followed directly from the
safety-check data rather than a judgment call) are covered in the relevant
worklog's evidence trail, not repeated here as numbered decisions.*
