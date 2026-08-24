# Worklog: build INDEX.md for results/regenerate_figures/

Task: scan results/regenerate_figures/ recursively, write INDEX.md with per-file
producer (grep src/ for literal output path) and consumers (other files under
src/ or results/ that read it). No files to be moved/renamed/deleted.

## Steps

- [1800] Scanned tree: 70 files, 9 subdirs (incl. root level).
  Subdirs: 01_chaos_4criterion, 02_chaos_landing_error, detection_improvement,
  detection_improvement_v2, detection_improvement_v3, model_comparison_pooled,
  plain_drag_sweep, ransac_effect_pooled, stage_timing.
  src/ has 123 .py files across calibration, image_processing, pi_benchmarking,
  regen_2class, registration, stereo.

- [1805] Pass 1: grepped src/ for each file's literal full path. 24/70 matched.
  Pass 2: grepped src/ for each basename. Raised coverage to ~55/70.
  Pass 3: grepped f-string stems (`f"bands_by_class_A_window_{tag}.csv"` etc.)
  for the remainder. Resolved the 01_/02_ chaos sets and the figureD/outcome_sweep
  set to step13_* and step_7_figure_d_outcome.py.
- [1807] Four files still unresolved after all three passes:
  label_derived_classification.csv, drag_coefficient_check.txt,
  sweep_ranges_and_baseline.txt, which_kernel_offline.txt.
  The first two are referenced only in claude/claude_logs/ (written directly by
  a past session, no script). The last two appear nowhere in src/ or claude/.
  All four -> NOT_FOUND.
- [1808] Note: repo-wide grep (`grep -r .`) times out at 2 min — OneDrive-backed
  tree with large data dirs. Restricted all searches to src/ and claude/.

- [1815] Disambiguated every basename that matched more than one script, by
  reading the hit line rather than trusting the filename match:
  - two_class_join.csv    -> WRITTEN by step_3_join.py; common.py holds
    JOIN_CSV/load_join() and 13 step scripts read through it.
  - plain_drag_sweep.csv  -> written by plain_drag_sweep.py; read by
    ransac_effect_pooled.py and ransac_effect_tail.py.
  - ransac_effect_pooled.csv -> written by ransac_effect_pooled.py; read by
    ransac_effect_tail.py (cross-check).
  - ransac_implementation.txt -> written by ransac_implementation.py;
    plain_drag_sweep.py only CITES it in a docstring, does not read it.
  - figureC_duration_distribution.png -> written by step_6; step15 only names it
    in prose ("left untouched").
  - bands_by_class_A_window_*.csv / operating_points_*.csv -> same basenames in
    both step13_* scripts, but different OUT_DIRs (01_ vs 02_) and different
    tags, so no actual collision.
  - step16/step17 re-render by IMPORTING the producing modules; they do not read
    the original PNGs.
- [1817] *** ONE CONFLICT FOUND (STOP condition) ***
  figureA_margin_vs_cutoff.png is written by TWO scripts to the same path:
    src/regen_2class/step_4_figure_a_margin.py:20   FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"
    src/regen_2class/step9_figure_a_combined.py:31  FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"
  step9's docstring says it "Overwrites" step_4's file. Not guessing which one
  the on-disk copy came from - reported, not resolved.
- [1818] Verified OUT_DIR constants for every subfolder-writing script and the
  f-string tags (primary/sensitivity, 500mm/1000mm, ""/"_170mm").
  step_1_classes.py and step_2_deadlines.py write nothing to disk.

- [1830] Section 1 written and reconciled 1:1 against the on-disk list (71 rows,
  70 unique paths, the extra row being the figureA conflict).
- [1835] *** TREE CHANGED MID-TASK *** Re-ran find after writing section 1:
  77 files now (was 70 + INDEX.md = 71). Six files appeared, none disappeared:
    ransac_effect_flight22/ransac_effect_flight22.csv   17:53
    ransac_effect_flight22/ransac_effect_flight22.png   17:53
    ransac_effect_tail/ransac_effect_p95.png            17:50
    ransac_effect_tail/ransac_effect_tail.csv           17:50
    ransac_effect_tail/ransac_effect_tail.png           17:50
    ransac_effect_tail/ransac_effect_tail_summary.txt   17:50
  Both producers exist and were found by literal-path grep:
    ransac_effect_flight22.py, ransac_effect_tail.py (both new in src/ too).
  Neither set is read by anything (only self-references from its own summary).
  Not a deletion or a move - my first `find` simply predated them. Rebuilding
  the whole INDEX from the current tree rather than patching it.

- [1845] Rebuilt INDEX.md from the 76-file tree. 515 lines.
  Section 1: 77 table rows = 76 files + the one duplicated row for the figureA
  conflict. Reconciled 1:1 against `find` in both directions - no unmapped file,
  no mapped file missing.
  Section 2: 2a = 4 NOT_FOUND files; 2b = 73 files with no reader (only 3 files
  in the whole tree are inputs to other code).
  Section 3: 3a version chains, 3b render variants, 3c sensitivity pairs,
  3d the drag/ransac folder chain, 3e basename collisions.
  Plus a Conflict section and Notes on method.
- [1846] Integrity check: `git status --porcelain` on the directory shows zero
  modified/deleted entries - only untracked additions. Nothing was moved,
  renamed or deleted.

## Result

results/regenerate_figures/INDEX.md written. One STOP condition hit and reported
rather than guessed: figureA_margin_vs_cutoff.png has two producing scripts.
Awaiting the user's decision on which files to move and where.
