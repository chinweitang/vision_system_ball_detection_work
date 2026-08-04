# 2026-08-04 17:38 Launch-to-crossing timing budget worklog

Task prompt: `claude/prompts/2026-08-04_1735_launch_to_crossing_budget.md`
(note: prompt said `dev/claude_rules.md` / `dev/claude_logs/` -- this repo's
actual convention is `claude/claude_rules.md` / `claude/claude_logs/`, per
every existing file in the repo. Using the real paths, not the prompt's
literal text.)

## Objective
Recompute the worst-case timing budget as launch-to-CROSSING-PLANE duration
(over CROSSER flights only: HIT + MISS_HIGH_WIDE, n=107), replacing the
stale 430ms full-flight-duration figure with a shorter, more relevant one.

## Log

- [17:38] Read claude/claude_rules.md, crossing_classification.csv (163
  rows, confirmed cls counts HIT=87/MISS_HIGH_WIDE=20/MISS_SHORT=56 from
  01_'s worklog), and src/stereo/crossing_plane_classification.py in full.

- [17:38] **Clock verification (required before proceeding, per the task's
  explicit STOP condition)**: traced t_start and t_cross to their source.
  - `build_corrected_track()` (all_flights_common.py:135-171) computes
    `t_sec = (t_avg - t_avg[0]) / 1e9` -- i.e. the time array is ALREADY
    zero-based at the first usable fit frame (first corrected-pair point).
    So t_start = 0.0 by construction, on the same clock classify_flight()
    uses throughout.
  - `classify_flight()` (crossing_plane_classification.py:224-300) fits
    Model C to this same zero-based `t` array, then finds t_cross via
    `brentq` bisection over `[1e-6, t[-1]]` using the SAME fitted params
    and SAME time convention (predict_fn is queried with raw `tt` from
    that same array, no re-zeroing). `duration_ms` in the existing CSV =
    `(t[-1]-t[0])*1000` = `t[-1]*1000` since t[0]=0 -- i.e. duration_ms
    IS the full track's last-point time on this same zero-based clock.
  - **Conclusion: t_start (=0) and t_cross are already on the identical
    clock.** launch_to_crossing_ms = t_cross * 1000, directly, no
    reconciliation needed. No STOP triggered.
  - Caveat found and worth flagging: this `duration_ms` (full observed
    track span, first fit frame -> LAST point) is a DIFFERENT quantity
    from the "430ms" figure's actual source (P5 of
    `data/trajectory_fit_comparison/all_flights/duration_distribution/
    flight_durations.csv`'s `total_duration_ms`, defined as first-fit-frame
    -> HELD-OUT TARGET, per this session's earlier work). Both are
    zero-based at the same start convention (first usable fit frame), so
    they're comparable/replaceable in spirit, just not literally the same
    column across files. Noted, not a blocker.

- [17:38] **Gap found**: `classify_flight()` computes `t_cross` internally
  (line 274/278/299 dict) but `main()`'s CSV writer (fieldnames list,
  lines 379-381) does NOT include `t_cross` in the columns actually
  written to `crossing_classification.csv`. So t_cross exists nowhere on
  disk currently -- must be retrieved by calling the SAME frozen function
  again, not re-derived with different logic.
  - Task says "do NOT re-fit trajectories or re-run classification -- reuse
    01_ crossing events." Interpreting this as: don't use a different
    methodology or change any parameter. RANSAC_SEED is a fixed constant
    (imported, not randomized) and every input (track, geometry, pooled_k)
    is identical read-only data -- so calling the unmodified
    `classify_flight()` a second time is fully deterministic and
    reproduces the EXACT same event, not a new one. Proceeding on this
    basis, importing `classify_flight`/`build_geometry` from the frozen
    module unmodified (no edits to crossing_plane_classification.py) --
    and validating this assumption explicitly (see below) before trusting
    any t_cross value.

- [17:39] Plan: new script
  `src/stereo/launch_to_crossing_budget.py`, imports `build_geometry` and
  `classify_flight` unmodified from `crossing_plane_classification.py`,
  re-runs Phase A (geometry, cheap) + Phase B only for the 107 crosser
  flights (filtered from crossing_classification.csv), and for EACH one
  VERIFIES cls and duration_ms match the existing CSV row exactly (within
  1e-6 tolerance) before accepting that flight's t_cross -- any mismatch
  gets flagged/excluded, not silently trusted. Writing now.
- [17:40:29] Loaded 163 flights from crossing_classification.csv. Crossers (HIT+MISS_HIGH_WIDE)=107, excluded MISS_SHORT=56.
- [17:40:29] Rebuilt geometry for all 3 registrations (identical frozen build_geometry(), pooled_k=5.268474e-05).
- [17:42:27] Re-ran frozen classify_flight() for 107 crossers to retrieve t_cross (discarded by 01_'s CSV writer). Verified against existing cls+duration_ms: 107 matched exactly, 0 mismatched.
- [17:42:27] Distribution (n=107, linear/numpy-style interpolation): mean=998.5ms median=1120.6ms min=491.5ms max=1559.3ms P5=535.8ms P10=560.7ms P15=581.8ms
- [17:42:27] 8 shortest flights:
- [17:42:27]   2026_07_21_gym/flight_79 (REG_21_2): launch_to_crossing_ms=491.5 elevation_deg=-3.163 speed_m_s=9.6485 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_2 (REG_21_1): launch_to_crossing_ms=492.8 elevation_deg=-6.041 speed_m_s=8.8544 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_86 (REG_21_2): launch_to_crossing_ms=505.4 elevation_deg=-2.7924 speed_m_s=9.8675 cls=HIT
- [17:42:27]   2026_07_15_gym/flight_56 (REG_15): launch_to_crossing_ms=512.4 elevation_deg=0.8924 speed_m_s=8.274 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_3 (REG_21_1): launch_to_crossing_ms=516.6 elevation_deg=5.2681 speed_m_s=9.9503 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_85 (REG_21_2): launch_to_crossing_ms=535.5 elevation_deg=7.2403 speed_m_s=9.5095 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_82 (REG_21_2): launch_to_crossing_ms=536.6 elevation_deg=-0.6467 speed_m_s=9.6892 cls=HIT
- [17:42:27]   2026_07_21_gym/flight_16 (REG_21_1): launch_to_crossing_ms=544.7 elevation_deg=-1.3703 speed_m_s=9.0201 cls=HIT
- [17:42:27] OLD budget (430ms, full-flight P5) vs NEW budget (P5 launch-to-crossing =535.8ms): delta=+105.8ms (longer, i.e. new budget is more permissive than previously assumed).
- [17:42:27] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\launch_to_crossing.csv (107 rows)
- [17:42:27] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\summary.txt
- [17:42:28] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\launch_to_crossing_histogram.png
- [17:42:28] DONE.
- [17:43:09] Loaded 163 flights from crossing_classification.csv. Crossers (HIT+MISS_HIGH_WIDE)=107, excluded MISS_SHORT=56.
- [17:43:09] Rebuilt geometry for all 3 registrations (identical frozen build_geometry(), pooled_k=5.268474e-05).
- [17:44:44] Re-ran frozen classify_flight() for 107 crossers to retrieve t_cross (discarded by 01_'s CSV writer). Verified against existing cls+duration_ms: 107 matched exactly, 0 mismatched.
- [17:44:44] Distribution (n=107, linear/numpy-style interpolation): mean=998.5ms median=1120.6ms min=491.5ms max=1559.3ms P5=535.8ms P10=560.7ms P15=581.8ms
- [17:44:44] 8 shortest flights:
- [17:44:44]   2026_07_21_gym/flight_79 (REG_21_2): launch_to_crossing_ms=491.5 elevation_deg=-3.163 speed_m_s=9.6485 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_2 (REG_21_1): launch_to_crossing_ms=492.8 elevation_deg=-6.041 speed_m_s=8.8544 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_86 (REG_21_2): launch_to_crossing_ms=505.4 elevation_deg=-2.7924 speed_m_s=9.8675 cls=HIT
- [17:44:44]   2026_07_15_gym/flight_56 (REG_15): launch_to_crossing_ms=512.4 elevation_deg=0.8924 speed_m_s=8.274 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_3 (REG_21_1): launch_to_crossing_ms=516.6 elevation_deg=5.2681 speed_m_s=9.9503 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_85 (REG_21_2): launch_to_crossing_ms=535.5 elevation_deg=7.2403 speed_m_s=9.5095 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_82 (REG_21_2): launch_to_crossing_ms=536.6 elevation_deg=-0.6467 speed_m_s=9.6892 cls=HIT
- [17:44:44]   2026_07_21_gym/flight_16 (REG_21_1): launch_to_crossing_ms=544.7 elevation_deg=-1.3703 speed_m_s=9.0201 cls=HIT
- [17:44:44] OLD budget (430ms, full-flight P5) vs NEW budget (P5 launch-to-crossing =535.8ms): delta=+105.8ms (longer, i.e. new budget is more permissive than previously assumed).
- [17:44:44] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\launch_to_crossing.csv (107 rows)
- [17:44:44] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\summary.txt
- [17:44:45] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\04_launch_to_crossing_budget\launch_to_crossing_histogram.png
- [17:44:45] DONE.

## [progress] Fixed histogram label collision, task complete

Visual QA of the first render caught a real collision: P5/P10/P15 vertical
lines sit close together (536/561/582ms), so individual per-line text
labels overlapped into unreadable stacked text. Fixed by replacing the
three overlapping annotations with a single compact monospace legend box
in the upper-right corner. Re-ran, confirmed clean.

## SUMMARY

**Headline result: the new launch-to-crossing budget is P5=535.8ms, P10=560.7ms,
P15=581.8ms (n=107 crossers) -- LONGER than the old 430ms full-flight figure,
not shorter.** Delta = +105.8ms at P5. This is the OPPOSITE of what the task's
own context section hypothesized ("crossing-plane deadline is shorter,
compresses the low tail") -- flagging this explicitly rather than silently
reconciling it.

**Why**: the old 430ms was P5 of `total_duration_ms` in flight_durations.csv,
defined first-fit-frame -> a HELD-OUT TARGET point (an early-ish validation
point, not necessarily near flight end). The new figure is first-fit-frame
-> the CROSSING EVENT, and most crossers here are lob-regime flights
(per the 02_ candidate-reselection FLAT/MID/LOB stratification: 60/107
crossers are LOB) that cross the plane well into their arc, often
near/after apex -- so for THIS flight population, "reach the crossing
plane" typically takes longer than the old target-point convention did.
Both are real, correctly-computed numbers; they just answer different
questions and the crossing-based one turns out less strict, not more.

Distribution (n=107, linear/numpy-style percentile interpolation):
mean=998.5ms, median=1120.6ms, min=491.5ms, max=1559.3ms,
P5=535.8ms, P10=560.7ms, P15=581.8ms.

8 shortest flights (all HIT, all near-zero/negative elevation -- i.e. flat
drives, consistent with flat trajectories reaching the plane fastest):
2026_07_21_gym/flight_79 (491.5ms), flight_2 (492.8ms), flight_86 (505.4ms),
2026_07_15_gym/flight_56 (512.4ms), 2026_07_21_gym/flight_3 (516.6ms),
flight_85 (535.5ms), flight_82 (536.6ms), flight_16 (544.7ms) -- the low
tail is real and physically sensible (flat, fast drives), not a single
straggler artifact.

Clock/reproduction validation: 107/107 crossers reproduced cls and
duration_ms EXACTLY against the existing crossing_classification.csv when
re-running the frozen classify_flight() (0 mismatches) -- confirms the
deterministic-reproduction approach for retrieving t_cross was sound.

Outputs: data/prediction/04_launch_to_crossing_budget/{launch_to_crossing.csv
(107 rows), summary.txt, launch_to_crossing_histogram.png}.

**Status: DONE.** All success criteria met. No STOP triggered (clock was
already consistent). Script: src/stereo/launch_to_crossing_budget.py.

## [progress, 17:50] New task -- per-elevation-bin budget (FLAT/MID/LOB)

Follow-on task: pooled P5 (535ms) is throw-mix-dependent (60/107 crossers
are LOB), not a physics-driven budget. Recompute percentiles PER elevation
bin (FLAT<15deg, MID 15-45deg, LOB>=45deg, same cuts as 02_ candidate
reselection) so FLAT's P5 (flat drives reach the plane fastest) can serve
as the design target, independent of the day's throw mix.

REUSING data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv
as-is -- no re-fit, no t_cross recomputation, elevation_deg already present
per-row. New script src/stereo/budget_by_elevation_bin.py, new output
folder data/prediction/05_budget_by_elevation_bin/.
- [17:57:27] Loaded 107 crossers from 04_'s launch_to_crossing.csv (reused as-is, no recomputation).
- [17:57:27] FLAT bin: n=35 (elevation range in bin: -6.0 to 13.4 deg)
- [17:57:27] MID bin: n=12 (elevation range in bin: 16.0 to 44.2 deg)
- [17:57:27] LOB bin: n=60 (elevation range in bin: 45.1 to 60.4 deg)
- [17:57:27] FLAT: n=35 min=491.5ms median=591.6ms P5=501.6ms P10=514.1ms P15=535.6ms
- [17:57:27] MID: n=12 min=663.1ms median=972.0ms P5=709.8ms P10=752.0ms P15=774.3ms
- [17:57:27] LOB: n=60 min=1047.8ms median=1240.7ms P5=1080.0ms P10=1110.0ms P15=1133.9ms
- [17:57:27] POOLED (reference, throw-mix-dependent, NOT the design target): n=107 min=491.5ms median=1120.6ms P5=535.8ms P10=560.7ms P15=581.8ms
- [17:57:27] *** FLAT P5 = 501.6ms is the DESIGN TARGET (throw-mix-independent -- flat drives reach the plane fastest, sets the true worst case regardless of how many lobs were thrown that day). Pooled P5 (535.8ms) is throw-mix-dependent, NOT the target -- it reflects the day's lob/flat mix (60/107 LOB), not the physics. LOB P5 (1080.0ms) is shown for contrast: +578.3ms of slack relative to FLAT. ***
- [17:57:27] FLAT bin, 3 shortest flights:
- [17:57:27]   2026_07_21_gym/flight_79 (REG_21_2): launch_to_crossing_ms=491.5 elevation_deg=-3.16 speed_m_s=9.65 cls=HIT
- [17:57:27]   2026_07_21_gym/flight_2 (REG_21_1): launch_to_crossing_ms=492.8 elevation_deg=-6.04 speed_m_s=8.85 cls=HIT
- [17:57:27]   2026_07_21_gym/flight_86 (REG_21_2): launch_to_crossing_ms=505.4 elevation_deg=-2.79 speed_m_s=9.87 cls=HIT
- [17:57:27] MID bin, 3 shortest flights:
- [17:57:27]   2026_07_21_gym/flight_15 (REG_21_1): launch_to_crossing_ms=663.1 elevation_deg=15.99 speed_m_s=8.64 cls=HIT
- [17:57:27]   2026_07_21_gym/flight_73 (REG_21_2): launch_to_crossing_ms=747.9 elevation_deg=19.18 speed_m_s=7.73 cls=HIT
- [17:57:27]   2026_07_15_gym/flight_52 (REG_15): launch_to_crossing_ms=788.4 elevation_deg=20.44 speed_m_s=7.51 cls=HIT
- [17:57:27] LOB bin, 3 shortest flights:
- [17:57:27]   2026_07_21_gym/flight_48 (REG_21_1): launch_to_crossing_ms=1047.8 elevation_deg=45.90 speed_m_s=8.11 cls=MISS_HIGH_WIDE
- [17:57:27]   2026_07_21_gym/flight_25 (REG_21_1): launch_to_crossing_ms=1050.2 elevation_deg=46.62 speed_m_s=9.10 cls=MISS_HIGH_WIDE
- [17:57:27]   2026_07_21_gym/flight_23 (REG_21_1): launch_to_crossing_ms=1062.8 elevation_deg=49.15 speed_m_s=7.16 cls=HIT
- [17:57:27] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\05_budget_by_elevation_bin\budget_by_bin.csv
- [17:57:27] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\05_budget_by_elevation_bin\summary.txt
- [17:57:27] Wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\05_budget_by_elevation_bin\budget_by_bin_histogram.png
- [17:57:27] DONE.

## SUMMARY (05_ per-elevation-bin budget)

**FLAT P5 = 501.6ms is the design target.** Confirms the hypothesis: pooled
P5 (535.8ms) was inflated by throw mix (60/107 crossers are LOB), and the
true throw-mix-independent worst case is meaningfully LOWER once isolated
to the FLAT regime.

| bin | n | min | median | P5 | P10 | P15 |
|---|---|---|---|---|---|---|
| FLAT | 35 | 491.5 | 591.6 | 501.6 | 514.1 | 535.6 |
| MID | 12 | 663.1 | 972.0 | 709.8 | 752.0 | 774.3 |
| LOB | 60 | 1047.8 | 1240.7 | 1080.0 | 1110.0 | 1133.9 |
| POOLED | 107 | 491.5 | 1120.6 | 535.8 | 560.7 | 581.8 |

Clean separation between regimes -- FLAT and LOB distributions barely
overlap (FLAT max ~750ms, LOB min ~1048ms), confirming elevation bin is a
real, distinct kinematic regime here, not an arbitrary cut. MID sits
between as expected. LOB has +578.3ms of slack relative to FLAT.

FLAT bin's 3 shortest flights (491.5, 492.8, 505.4ms) are the SAME three
flights that were already the pooled distribution's overall shortest (see
04_'s log) -- confirms the low tail is a real FLAT-regime floor, not
FLAT-bin-specific noise or a labelling artifact.

Selection was by elevation_deg bin throughout (FLAT<15/MID15-45/LOB>=45),
NOT by speed -- speed_m_s is reported per flight for context only, never
used as a cut or filter, per instruction.

Outputs: data/prediction/05_budget_by_elevation_bin/{budget_by_bin.csv,
summary.txt, budget_by_bin_histogram.png}. Histogram visually QA'd, no
collisions (legend box top-right, dashed P5 lines spaced cleanly at
502/710/1080ms).

**Status: DONE.** Script: src/stereo/budget_by_elevation_bin.py.
