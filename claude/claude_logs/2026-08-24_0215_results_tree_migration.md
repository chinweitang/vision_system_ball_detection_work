# Work Log: Split results/ out of data/ for GitHub

**Session:** 2026-08-24_0215
**Status:** Complete

---

## Goal

Separate derived results from raw data so the results can be version-controlled and
pushed to GitHub, while raw captures stay local and gitignored.

## Decisions taken (user, this session)

1. **contact_sheets stays in `data/`.** 19.7 GB on OneDrive; a move would very
   likely trigger a full re-upload, and the folder is gitignored either way.
   `results/detector_tuning/` therefore holds everything EXCEPT contact_sheets.
2. **Logs and prompts under `claude/` are not rewritten.** They record paths that
   were correct when written; rewriting would falsify the record. Only the 41
   scripts under `src/` get new paths.
3. Session capture folders (`2026_07_*`, `calibration_captures`, etc.) stay in
   `data/` as raw data.

## Sizing that drove this

Full `data/` is ~62 GB:

| folder | size | disposition |
|---|--:|---|
| `2026_07_21_gym/` | 28 GB | stays (raw) |
| `detector_tuning/contact_sheets/` | 19.7 GB | **stays** (gitignored) |
| `2026_07_15_gym/` | 13 GB | stays (raw) |
| `2026_07_15_lab_session/` | 1.5 GB | stays (raw) |
| `2026_07_14_session/` | 353 MB | stays (raw) |
| `calibration_captures/` | 121 MB | stays (raw) |
| `2026_07_11_gym_session/`, `2026_07_12_session/` | ~200 MB | stay (raw) |
| everything else (the results) | **~34 MB** | **moves to `results/`** |

~34 MB on top of a 20 MB repo is a non-issue for GitHub. The danger was never the
tables or figures - it was contact_sheets at ~28 MB per file, each individually
UNDER GitHub's 100 MB block, so git would have accepted them one at a time and
bloated the repo permanently before any limit fired.

---

## [02:15] Step 1 - starting, dry run first

Moving is hard to reverse, so the migration script runs in dry-run mode by default
and only acts with `--apply`.

---

## [02:22] Step 2 - dry run exposed a serious flaw in my rewrite

The first `--paths` dry run reported 42 files / 106 lines changed. **Almost all of
those were docstrings and comments, not code.**

The dominant path idiom in this repo is segmented pathlib:

```python
CONFIG_PATH   = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
OUT_DIR       = REPO_ROOT / "data" / "prediction" / "05_budget_by_elevation_bin"
DETECTIONS_ROOT = REPO_ROOT / "data" / "detector_tuning" / "detections" / ...
```

A literal `"data/detector_tuning"` search does not match any of those. So the
rewrite as first written would have:

1. moved the folders,
2. rewritten prose in comments to say `results/`,
3. left **every actual runtime path** still pointing at `data/`,

i.e. silently broken essentially every script while reporting success. Caught by
dry-running and then grepping for `"data"` rather than trusting the dry-run count.

### The Pi case is the sharpest example

`run_pi_benchmark.ps1` copies repo-relative paths onto the Pi to mirror the tree:

```powershell
Copy-Rel "data\detector_tuning\candidate_config.json"
```

That line DOES match the literal pattern, so it would have been rewritten to
`results\...`. But the Pi-side consumer:

```python
CONFIG_PATH = REPO_ROOT / "data" / "detector_tuning" / "candidate_config.json"
```

would NOT have been. The staging script would copy to one path and the Pi script
would read from another - a break that only shows up on the next Pi run.

### Fix: match the segmented form, anchored on "data"

Rewrite `"data" / "<moved>"` -> `"results" / "<moved>"`, requiring `"data"`
IMMEDIATELY before the folder name. That anchor is what keeps these safe:

| pattern | disposition |
|---|---|
| `"data" / "detector_tuning"` | rewritten (moved folder) |
| `"data" / session` | untouched (variable = session capture) |
| `"data" / "2026_07_15_gym"` | untouched (raw capture) |
| `"data" / "2026_07_15_gym" / "flight_binning"` | **untouched** - `flight_binning` here is a per-session subfolder, NOT the top-level results folder of the same name |

That last row is the trap: `flight_binning` exists both as `data/flight_binning/`
(moves) and as `data/<session>/flight_binning/` (stays). Anchoring on `"data"`
immediately preceding is what tells them apart.

---

## [02:31] Step 3 - a THIRD trap: derived contact-sheet paths

`contact_sheets` is never written as a literal path. Three scripts derive it:

```python
CONTACT_SHEETS_DIR = DETECTOR_TUNING_DIR / "contact_sheets" / STAGE
```

Once `DETECTOR_TUNING_DIR` points at `results/`, that expression silently
retargets to `results/detector_tuning/contact_sheets/` - so the next full-dataset
run would have written a **second 19.7 GB** of contact sheets straight into the
git-tracked tree. A .gitignore rule would have stopped the commit but not the
disk usage.

Fixed by pinning the base explicitly in those three scripts
(`08_generate_contact_sheets.py`, `10_run_full_dataset.py`,
`12_run_full_dataset_rect_close_kernel.py`):

```python
REPO_ROOT / "data" / "detector_tuning" / "contact_sheets"
```

recorded as `DERIVED_FIXUPS` in the migration script so it is repeatable, not a
one-off hand edit.

---

## [02:34] Step 4 - `results/` already existed

`git status` showed 4 tracked files under `results/tmp_pipeline_sweep_detections/`
as DELETED, and `results/` on disk was an empty folder.

Investigated rather than assumed:

- committed in `14d068d` ("real time performance analysis")
- the same 4 CSVs sit at `data/tmp_pipeline_sweep_detections/`, **identical apart
  from line endings** (CRLF vs LF)
- `prediction_pipeline_sweep_pi.py` and `..._vaxis.py` ALREADY write to
  `REPO_ROOT / "results" / "tmp_pipeline_sweep_detections"`

So this migration was already half-started: those two scripts had been pointed at
`results/` previously, and the `data/` copies are the stale ones. Moving that
folder restores the tracked files rather than colliding with them, and no rewrite
was needed for those two lines - they already said `results/`.

---

## [02:38] Step 5 - applied and verified

**Moves:** 9 folders wholesale + 6 children of `detector_tuning`.
`contact_sheets` left in place.

**Path rewrite:** 70 files - **85 segmented**, **107 literal**, **3 derived**.
(The original broken version would have done 42 files / 106 lines, almost all
comments.)

**.gitignore:** `data/` still ignored. Added a backstop:

```
results/**/contact_sheets/
```

Verified live with `git check-ignore -v` - a hypothetical
`results/detector_tuning/contact_sheets/x.png` is matched by that rule.

**`--verify` output:** 0 stale `data/` references, all 10 destinations present,
`data/detector_tuning/contact_sheets` still in place, 0 leftovers.

**Smoke test** - 4 scripts re-run end to end, all OK:

| script | exercises |
|---|---|
| `ellipse_vs_rect_resolution.py` | reads results/detector_tuning, writes results/regenerate_figures |
| `detection_improvement_figure.py` | reads results/detector_tuning/history |
| `stage_timing_breakdown.py` | reads results/pi_benchmarking |
| `reconcile_detection_rates.py` | **reads BOTH trees** - results/detector_tuning AND data/<session>/ball_flights label CSVs |

That last one is the real test of the split, and it passes.

**What git would take on:** 681 files, **38 MB**. No file over 10 MB.

---

## Status: COMPLETE (not committed)

Nothing has been committed or pushed - that was not asked for. `git status` will
show the 681 new files under `results/`, the 70 rewritten scripts, and the
`.gitignore` change, ready to review.
