# 2026-07-23 18:19 — MIN_AREA x MIN_CIRC sweep for ball detector

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md, then claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md
in full to pick up the history of this task before doing anything else.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Run a MIN_AREA x MIN_CIRC parameter sweep for the stereo 3-frame-diff ball detector,
validate the winner with a full-dataset artifact audit, and record the result —
continuing the tuning work already documented in
claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md.

Context: two tuning rounds are already done this session. Round 1 found
stride=1, diff_threshold=16, open_kernel=3 (close_kernel=30 unchanged) as the winning
mask-generation config via a recall-gated sweep. Round 2 added a trajectory-outlier
filter (max_speed_px_per_frame=80, min_run_length=2) and 7 exclusion-mask zones
derived from a full-163-flight artifact audit, landing at avg_combined_rate=0.8552
(baseline 0.2772) with labeled_recall=0.9259 held (baseline 0.9074). Both numbers are
confirmed in claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md and in
data/detector_tuning/history/results_history.csv — read both before starting.

The next-agreed bottleneck is MIN_AREA=200: across the 10-flight tuning sample, 196
NO_DETECTION frames have a real-looking blob (area 88-200, circ 0.40-0.74 — clearly
distinguishable from noise contours at circ 0.17-0.33) sitting on an otherwise smooth
trajectory, rejected purely by the area cutoff. This task tests a lower MIN_AREA (and
MIN_CIRC alongside it) to recover those frames, but ANY new value must be
re-validated with a full-dataset artifact audit before being accepted — loosening the
area filter risks exposing new small-scale static noise that MIN_AREA=200 was
incidentally screening out. Confirmed with the user: stride=1, thresh=16, open_k=3
carries forward unchanged (not re-tested this round); min_run_length stays at 2 (the
flight_22 two-frame person-detection bug documented in the worklog is intentionally
left unfixed this round).

═══════════════════════════════════════════════════════════════════════════════
LOGGING (LIVE-UPDATE THE EXISTING WORKLOG — DO NOT CREATE A NEW ONE)
═══════════════════════════════════════════════════════════════════════════════

This is a continuation of existing work. Append to
claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md — do NOT create a new
log file for this task.

Update it IMMEDIATELY after each significant step below (config file created, sweep
launched, sweep results in, checkpoint reached, audit launched, audit results in,
exclusion-mask decision made, contact sheets regenerated, history CSV updated) — not
once at the end. Use the same structure/tone as the existing entries in that file
(there's already a strong example to match: see the "MIN_AREA investigation" and
"Sweep gotcha" sections). Include:
- Exact commands/scripts run
- Full config used (all 9 params) for every consequential run
- Key numeric results (avg_combined_rate, labeled_recall) as they come in, not just
  final numbers
- Every decision point and why (e.g. why a given hotspot bin was/wasn't added to
  exclusion_mask.py)
- Anything that didn't work before the thing that did (same "log every attempt"
  standard already used earlier in this file)

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read claude/claude_rules.md, the full worklog
   (claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md), detector_core.py,
   06_param_sweep.py, 07_artifact_audit.py, and 08_generate_contact_sheets.py before
   changing anything, so the new sweep script matches existing conventions exactly
   (FLIGHT_SAMPLE list, labeled-recall-against-labels_uv.csv logic,
   ProcessPoolExecutor usage).

2. Create data/detector_tuning/candidate_config.json, seeded with today's validated
   values:
   {"stride": 1, "diff_threshold": 16, "open_kernel": 3, "close_kernel": 30,
    "min_area": 200, "max_area": 50000, "min_circ": 0.3,
    "max_speed_px_per_frame": 80, "min_run_length": 2}
   This becomes the single source of truth for the "current best" config — it
   replaces the independently-hardcoded copies currently sitting at
   07_artifact_audit.py (lines ~49-50) and 08_generate_contact_sheets.py (line
   ~51-52). Update both scripts to load their config values from this JSON file at
   runtime instead of hardcoding their own copies.
   VERIFY this refactor is behavior-neutral before moving on: re-run both scripts at
   the existing (unchanged) config values and confirm byte-identical output to their
   pre-refactor versions. Log the verification result.

3. Create src/image_processing/02_adjacent_frame_differencing/09_param_sweep_area_circ.py,
   modeled directly on 06_param_sweep.py's structure, but:
   - Loads stride/diff_threshold/open_kernel/close_kernel from
     data/detector_tuning/candidate_config.json instead of hardcoding them.
   - Grids MIN_AREA=[30,50,75,100,150,200] x MIN_CIRC=[0.2,0.25,0.3,0.35] — 24
     combos.
   - Computes meets_recall_gate (labeled_recall >= 0.9074, the established baseline)
     and is_baseline IN-SCRIPT this time — note that 06_param_sweep.py's on-disk CSV
     (data/detector_tuning/sweep_results.csv) has these two columns but the .py
     script itself doesn't produce them (they were added out-of-band last round);
     don't repeat that gap here.
   - Sorts results gate-passing-first, then by avg_combined_rate descending.
   - Writes to data/detector_tuning/sweep_results_min_area_circ.csv (a NEW file —
     see SCOPE - WHAT NOT TO DO below).

4. Run the 24-combo sweep. Report the gate-passing candidates ranked by
   avg_combined_rate, and STOP for my explicit confirmation before treating any combo
   as "the winner" — mirrors the checkpoint that caught the gameable
   stride=2,thresh=8 result in round 1 (it hit combined_rate=1.000 but
   labeled_recall had collapsed to 0.556).

5. Once I confirm a winning MIN_AREA/MIN_CIRC:
   a. Update data/detector_tuning/candidate_config.json's min_area/min_circ to the
      winning values.
   b. Re-run 07_artifact_audit.py (now reading the updated config) across all 163
      flights x 2 cams.
   c. Write results to a NEW file,
      data/detector_tuning/artifact_audit_hotspots_area{MIN_AREA}_circ{MIN_CIRC}.csv
      (fill in the actual winning values in the filename) — do NOT overwrite the
      existing data/detector_tuning/artifact_audit_hotspots.csv, which is the
      MIN_AREA=200 audit and needs to stay as a reference point.
   d. Report any new hotspot bins (distinct_flights >= 3, same gate as before) not
      already covered by the 7 existing exclusion_mask.py zones (5 cam0 + 2 cam1,
      listed in the worklog). Do NOT modify exclusion_mask.py without running the
      same two-step safety process used before (fine-grained ~15px re-bin to isolate
      the dense core away from any false-rejection contamination, then verify ZERO
      real-detection hits in the candidate box before adding it) AND my explicit
      confirmation — this is a judgment call, not automatic.

6. Once the config (and any exclusion-mask additions) are finalized, generate contact
   sheets for the new config using 08_generate_contact_sheets.py, but write them to a
   NEW sibling folder,
   data/detector_tuning/contact_sheets_area{MIN_AREA}_circ{MIN_CIRC}/ (fill in actual
   values) — do NOT touch data/detector_tuning/contact_sheets/, whose 20 sheets have
   already been reviewed by the user.

7. Record the final result:
   - Append ONE new row to data/detector_tuning/history/results_history.csv
     (append-only — do not rewrite existing rows) with the new avg_combined_rate,
     labeled_recall, and a notes string describing the MIN_AREA/MIN_CIRC change.
   - Overwrite data/detector_tuning/candidate_config_validated_results.csv with the
     new per-flight breakdown — this file is already established as "latest state,
     OK to overwrite," no need to ask.
   - Final worklog update summarizing the whole task (per LOGGING section above).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless I explicitly ask later):
- ❌ Overwrite or delete data/detector_tuning/sweep_results.csv (round-1 sweep
  results — no git backup, data/ is gitignored)
- ❌ Overwrite or delete data/detector_tuning/artifact_audit_hotspots.csv (the
  MIN_AREA=200 audit — write new results to a differently-named file instead)
- ❌ Overwrite, delete, or add files into data/detector_tuning/contact_sheets/ (already
  reviewed — new sheets go in a new folder)
- ❌ Modify any other file under data/ or calibration_outputs/ not explicitly listed
  above
- ❌ Modify exclusion_mask.py without running the full safety-check process AND
  getting explicit confirmation first
- ❌ Change min_run_length, max_speed_px_per_frame, stride, diff_threshold, or
  open_kernel — all confirmed to carry forward unchanged this round
- ❌ Attempt to fix the flight_22 de-spike/min_run_length bug — explicitly out of
  scope this round
- ❌ Commit anything to git
- ❌ Create a new worklog file — live-update the existing one only
- ❌ Refactor detector_core.py, 04_stereo_three_frame_diff.py, or 06_param_sweep.py
  beyond what's needed for the config-file load in point 2 above

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report to me and wait for my response

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS
═══════════════════════════════════════════════════════════════════════════════

Checkpoint 1 — after the 24-combo sweep (step 4): STOP, report gate-passing
candidates ranked by avg_combined_rate, wait for me to confirm the winner before
touching candidate_config.json or running the full audit.

Checkpoint 2 — after the full-dataset audit (step 5c-d): STOP, report any new hotspot
bins and your proposed exclusion-mask changes (if any) with the safety-check evidence
behind each, wait for my confirmation before modifying exclusion_mask.py.

Do not proceed past either checkpoint without my explicit go-ahead.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything — just edit/create files and update the worklog.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ data/detector_tuning/candidate_config.json exists and is the single config source
   read by 07_artifact_audit.py and 08_generate_contact_sheets.py
✅ Config-file refactor verified behavior-neutral (byte-identical output at unchanged
   config) before any new MIN_AREA/MIN_CIRC values were tried
✅ data/detector_tuning/sweep_results_min_area_circ.csv exists with all 24 combos,
   correct meets_recall_gate/is_baseline columns computed in-script, sorted
   gate-first then by avg_combined_rate
✅ Winning MIN_AREA/MIN_CIRC was confirmed by the user (Checkpoint 1) before being
   locked in, and its labeled_recall is not a regression vs. 0.9074
✅ Full 163-flight artifact audit was re-run at the winning config, written to a new,
   distinctly-named file — data/detector_tuning/artifact_audit_hotspots.csv
   untouched
✅ Any exclusion_mask.py changes were safety-checked and confirmed by the user
   (Checkpoint 2) before being applied — or none were needed
✅ data/detector_tuning/contact_sheets/ (existing 20 sheets) untouched; new sheets (if
   generated) live in a new folder
✅ data/detector_tuning/history/results_history.csv has exactly one new appended row;
   no existing rows altered
✅ claude/logs/2026-07-23_ball_detection_rate_tuning_worklog.md was updated in
   real-time throughout (not just once at the end), continuing the existing file
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Read claude/claude_rules.md and the full worklog
2. Read detector_core.py, 06_param_sweep.py, 07_artifact_audit.py,
   08_generate_contact_sheets.py
3. Create candidate_config.json, refactor the two scripts to use it, verify
   behavior-neutral, log it
4. Build and run the 09_param_sweep_area_circ.py sweep, log progress as it runs
5. Report results at Checkpoint 1 and wait
6. Continue through audit, Checkpoint 2, contact sheets, and record-keeping per scope
   above, logging in real-time throughout
```
