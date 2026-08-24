# Work Log: Post-light-mask artifact contact sheets

**Session:** 2026-08-24_1009
**Status:** In progress

Purpose: produce report-figure evidence for the intermediate detector stage —
ceiling-light mask applied, artifact-audit masks NOT yet applied — showing the
exit sign / wall fixture / wall corner being selected as the ball candidate on
`data/2026_07_21_gym`.

Related: `claude/decision_log.md` §"Exclusion-mask decisions" (#12–#14) and
`src/image_processing/02_adjacent_frame_differencing/07_artifact_audit.py`,
which is where the boxes being disabled here originally came from.

---

## Original Request

> Figure for the report showing the artifacts that were getting picked up
> before the masks were applied — but post flashing-light mask. Run detection
> on `data/2026_07_21_gym` with only the light mask applied, not the other
> masks that came from the artifact audit. Contact sheets into
> `data/detector_tuning/contact_sheets/post_light_mask_artifacts`.

## Settled scope (AskUserQuestion, 10:09)

1. **Flights:** two-pass. Sweep all 149 flights × 2 cams recording detections
   that land inside a currently-disabled artifact box, rank, then build contact
   sheets for only the top ~15 flight/cams.
2. **Mask set:** `cam0[0]` and `cam1[0]` only — the ceiling-light rectangle.
   Everything else off, *including* `cam0[1]` (wall corner x[1270,1456]
   y[375,425]), which predates the audit (2026-07 param sweep, flight_126) but
   is still an artifact mask, not a light mask.
3. **Layout:** unchanged from `08_generate_contact_sheets.py` — 4 rows
   (back diff / fwd diff / AND+morph / detection), green=kept,
   orange=rejected-by-trajectory-filter, yellow=other candidates. No overlay.

**Assumption stated to user:** ellipse close kernel (`detector_core.compute_mask`),
not the rect variant — that is what was in force when the artifact audit ran, so
it is the honest "before" state for this narrative.

## Data-safety check (Section 2 / claude_rules.md)

`data/detector_tuning/contact_sheets/post_light_mask_artifacts/` verified
**empty** at 10:09 before starting — 0 files. Nothing under `data/` or
`calibration_outputs/` will be overwritten. Detection is read-only against
`ball_in_frame/*.png`.

---

## [10:11] Added deliverable (user, mid-task)

> also afterwards, i want to see where all the masks go — like the final set of
> masks overlayed on the images so that i can see them

Second deliverable: render the FULL `EXCLUSION_TRIANGLES` set (all 7 cam0 + 5
cam1 boxes) overlaid on a representative frame per camera, each box labelled
with its provenance (light / param sweep / audit round 2 / audit round 3).
Separate numbered script (`15_`), run after the contact sheets.

---

## [10:12] Step 1 — script 14, the light-mask-only sweep

Writing `14_post_light_mask_artifact_sheets.py`.

Mechanism for disabling the audit boxes: monkey-patch `dc.apply_exclusion`,
the same pattern `compute_mask_rect_close_variant.py` uses for `compute_mask`
(decision #63) — `detector_core.compute_mask` resolves `apply_exclusion` from
its own module namespace at call time, so reassigning `dc.apply_exclusion`
takes effect through `run_detection` without editing `detector_core.py` or
`exclusion_mask.py`. Neither file is modified.

Scoring for "which flight/cams are worth a sheet": for each flight/cam, run
detection light-mask-only, run `filter_trajectory_outliers`, then count how
many raw detections fall inside any *disabled* box (cv2.pointPolygonTest
against the real polygons, not their bounding boxes). Tracked separately:
- `n_hits` — total detections inside a disabled box
- `n_hits_kept` — those the trajectory filter did NOT catch (the damaging
  case: an artifact that survives into the trajectory)
- `n_boxes` — how many DISTINCT disabled boxes this flight/cam hits (a sheet
  showing two different artifact types is worth more as a figure than one
  showing the same box 10 times)

## [10:20] Step 2 - smoke test before the full sweep

Heredoc write of the script failed silently (bash quoting), rewrote via the Write
tool - noting it because the first `ls` showed no file at all, so the "syntax ok"
check never ran.

Single flight/cam check, `flight_13/cam0`:

- `LIGHT_POLYS['cam0']` = `[[(1456,0),(1456,375),(1000,375),(1000,0)]]` - one box,
  the ceiling light. Correct.
- `DISABLED_POLYS`: 6 boxes cam0, 4 boxes cam1. Correct (7 and 5 total, minus the
  light).
- `detector_core.apply_exclusion` resolves to `apply_light_only_exclusion` after
  import - the monkey-patch took.
- Result: 47 frames detected, **3 detections inside disabled box 1**
  (cam0's param-sweep wall corner, x[1270,1456] y[375,425]) at frames 48/70/73,
  all at u~1305 v~390-395. All 3 were caught by the trajectory filter
  (`n_hits_kept=0`).

**Timing:** 2.1 s per flight/cam for a 49-frame flight. 298 jobs, flights up to 93
frames, 20 cores -> expect pass 1 in **2-5 min**. Will investigate if >10 min.

## [10:15] Step 3 - full sweep result

Pass 1 completed in ~2 min. **126 flights** x 2 cams = 252 jobs, not 149 x 2 -
`find_flight_dirs` only counts flights that actually have a populated
`ball_in_frame/`. This matches `07_artifact_audit.py`'s own population
(37 flights in 2026_07_15_gym + 126 here = the 163 quoted throughout the
worklogs), so the flight set is consistent with every earlier stage.

### Headline numbers (light mask only, artifact boxes disabled)

| quantity | value |
|---|---|
| flight/cams with >=1 detection inside a disabled audit box | **245 / 252** |
| total such detections | **1974** |
| of those, detections that SURVIVED the trajectory filter | **25** |

The 1974-vs-25 split is the interesting result for the report: the static
artifacts are picked up as the selected ball candidate constantly, but the
trajectory filter already catches ~98.7% of them. The exclusion masks are
removing the residue the filter cannot catch, not doing the bulk of the work.

Per-flight/cam detail written to
`data/detector_tuning/contact_sheets/post_light_mask_artifacts/artifact_hit_scores.csv`
(every hit frame, its u/v, and which box it falls in).

### Box index -> object (index into `EXCLUSION_TRIANGLES[cam]`)

cam0: 1 wall corner (param sweep) | 2 exit sign | 3 fixture/panel pair |
4 small cluster | 5 exit-sign spillover | 6 fixture spillover
cam1: 1 wall corner | 2 corner extension | 3 wall fixture | 4 exit sign

## [10:28] Step 4 - VISUAL verification of the three cam0 artifact types

Did not take the box labels on trust - cropped the actual frames at the actual
detected u/v (`scratchpad/verify_cam0_artifacts.png`), `flight_59/cam0`:

- frame 029 @ (1302,382) box1 -> **confirmed**: structural wall corner/diagonal
  edge, crosshair sits on the edge.
- frame 047 @ (1129,639) box2 -> **confirmed**: the exit sign, running-person +
  arrow icon, crosshair on the sign.
- frame 081 @ (1029,649) box3 -> **confirmed**: the wall-mounted panel/fixture
  pair, crosshair on the tall white panel.

`flight_59/cam0` therefore shows all three artifact types in one flight/cam and
is the strongest single source for the figure.

Also pulled the rendered `frame_047` detection panel straight out of the sheet
(`scratchpad/verify_sheet_panel.png`) to confirm the annotation path works. It
does - orange contour + centroid on the exit sign, `[IN AUDIT BOX 2] u=1129
v=639`. **And it shows the real ball in the same frame as a yellow
(non-selected) candidate** - i.e. the artifact out-competed the true ball on
area, exactly the failure mode the existing flashing-light figure shows.

### Defect found in the same check

The status text and the frame-name text **overlap** in the detection panel.
Cause: `put_text(vis, status, y=36)` is drawn on the FULL-RES 1456x1088 image
before `scale_to_width`, so it lands at y~15 after the 600/1456 downscale,
colliding with the frame-name drawn at y=18 on the already-scaled panel. This
is inherited from `08_generate_contact_sheets.py`, which has the same defect -
not introduced here - but it makes the panels hard to read as report figures.

Fix (in `14_` only, not touching `08_`): draw contours/circle at full res, then
scale, then draw BOTH text lines on the scaled panel.

## [10:40] Step 5 - mask overlay figure (script 15)

`15_visualise_exclusion_masks.py`. Per camera: full-frame view with all boxes
filled 35% + outlined + numbered, colour-coded by which round added them, plus a
zoomed inset per box. Background = per-pixel median over 120 frames of
`flight_59` (static scene, people/ball/hands removed - which is what the masks
are covering). New folder `data/detector_tuning/mask_overlays/`, nothing
pre-existing there.

Guard: the script hard-fails at import if `PROVENANCE` and `EXCLUSION_TRIANGLES`
have different box counts, so a future box added to `exclusion_mask.py` cannot
silently inherit the wrong label.

**Masked frame area: cam0 11.61% (7 boxes), cam1 9.29% (5 boxes).** Nearly all
of that is the ceiling-light rectangle; the 10 audit boxes together are a tiny
fraction of a percent.

## [10:47] Step 6 - VISUAL check of every box against its label

Re-cropped each box at high zoom with 2.6x gain (`scratchpad/verify_boxes_cam0.png`)
rather than trusting `exclusion_mask.py`'s naming.

**cam1 - all 5 correct.** Box 0 covers both ceiling lamps; 1 and 2 sit on the
wall corner/diagonal edge; 3 sits on the white panel fixture; 4 covers the top
strip of the exit sign.

**cam0 - 5 of 7 correct, 2 loosely named:**

- box 2 "exit sign" - correct, covers the bright white strip at the top of the
  sign housing (the part that actually generates the diff signal), icon below.
- box 3 "wall fixture / panel pair" - correct, on the tall white panel.
- box 4 "small static cluster" - plain wall right of the panel, nothing
  identifiable. Honest label; `exclusion_mask.py` says the same ("not yet
  visually identified as a specific object").
- **box 5** - `exclusion_mask.py` calls it "exit sign, spillover to the right".
  The pixels under it are the **pillar/corner edge** just right of the sign, not
  the sign. Relabelled positionally: "spillover box, right of exit sign".
- **box 6** - `exclusion_mask.py` calls it "fixture's broader footprint". The
  pixels under it are the **banded wall vent between the fixture and the sign**.
  Relabelled: "spillover box, fixture-to-sign wall".

Both boxes are still valid masks - they were sized from a dense rejected-point
sub-cluster and verified for zero real-detection overlap, which does not depend
on naming the object correctly. Only the wording in the figure changed; NO
change made to `exclusion_mask.py` itself, and the box coordinates are untouched.

Also added a 2.6x gain to the insets only (full frame stays true brightness,
noted on the figure) - at native brightness these dark-wall crops show nothing.

## [10:50] BLOCKED - need permission to overwrite (Section 2)

Two fixes are written into the scripts but not rendered, because rendering
overwrites files under `data/` that this task created ~30 min ago:

1. 15 contact sheets in `contact_sheets/post_light_mask_artifacts/` - text
   overlap fix (Step 4).
2. 2 overlays in `mask_overlays/` - box 5/6 relabel + inset gain (Step 6).

Asking before re-rendering.

## [11:05] Step 7 - user chose "write alongside", both sets re-rendered

Permission answer: keep the originals, write corrected copies under new names.
Nothing under `data/` was overwritten or deleted in this task.

To honour that without also rewriting `artifact_hit_scores.csv`, added two CLI
flags to `14_`:

- `--from-csv` - skip pass 1 entirely and re-read the existing ranking from
  `artifact_hit_scores.csv`. Saves the ~2 min re-detection AND leaves the CSV
  untouched, which matters because pass 1 would otherwise rewrite it for a
  change that only affects rendering.
- `--suffix` - output filename suffix (default `_contact`).

`15_` got the same `--suffix` flag.

Rendered with `--from-csv --suffix=_contact_v2` and `--suffix=_exclusion_masks_v2`.
Ranking identical to the first run, as expected from re-reading the same CSV.

### Verification of the corrected output

Pulled frames 047 / 081 / 029 of `flight_59/cam0` back out of
`flight_59_cam0_contact_v2.png` (`scratchpad/verify_v2_panels.png`). Text now
sits on two clean lines. All three panels show the same pattern:

| frame | selected candidate | box | true ball |
|---|---|---|---|
| 047 | exit sign | 2 | present, yellow (non-selected) |
| 081 | wall fixture | 3 | present, yellow (non-selected) |
| 029 | wall corner | 1 | not visible in frame |

Frames 047 and 081 are the strongest single panels for the report: the artifact
beat the real ball on area and was selected, with the real ball sitting right
there as an unselected yellow candidate - the same failure mode as the existing
flashing-light figure, one mask-round later.

Re-checked the corrected cam0 overlay insets: all 7 legible at 2.6x gain, boxes
5 and 6 now labelled for where they sit rather than what they were assumed to
cover.

---

## Deliverables

**`data/detector_tuning/contact_sheets/post_light_mask_artifacts/`**
- `artifact_hit_scores.csv` - all 252 flight/cams scored, every hit frame + u/v + box
- 15 x `<flight>_<cam>_contact.png` - first render (status text overlaps frame name)
- 15 x `<flight>_<cam>_contact_v2.png` - **use these**, text fixed

**`data/detector_tuning/mask_overlays/`**
- `cam{0,1}_exclusion_masks.png` - first render (dark insets, source wording)
- `cam{0,1}_exclusion_masks_v2.png` - **use these**, brightened insets, corrected labels

**`src/image_processing/02_adjacent_frame_differencing/`**
- `14_post_light_mask_artifact_sheets.py`
- `15_visualise_exclusion_masks.py`

Neither `exclusion_mask.py` nor `detector_core.py` was modified.

## Open / not done

- The box 5 / box 6 naming in `exclusion_mask.py` itself is still the original
  wording. Corrected only in the figure script, since editing an existing file
  under `src/` needs permission (Section 2) and the box coordinates are correct
  regardless of naming.
- `08_generate_contact_sheets.py` still has the text-overlap defect. Not touched.
- Only `2026_07_21_gym` was swept, per the request. `2026_07_15_gym`'s 37
  flights would extend the artifact-hit statistics to the full 163 if wanted.

**Status: Complete.**
