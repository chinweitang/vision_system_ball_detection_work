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

*Scope note: this log covers the whole session (both the detector-tuning
work and the `claude_rules.md` rewrite), numbered continuously rather than
split into separate lists, since both involved genuine decisions with
rejected alternatives. Execution details without a real competing
alternative (e.g. exact pixel margins chosen for a given exclusion zone,
which followed directly from the safety-check data rather than a judgment
call) are covered in the worklog's evidence trail, not repeated here as
numbered decisions.*
