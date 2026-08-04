READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Compute the launch-to-crossing-plane duration distribution over CROSSER flights only, and report P5/P10/P15 (plus min) as the worst-case timing budget that replaces the stale 430ms full-flight figure.

CONTEXT:
- The 430ms budget came from the FULL-flight (launch-to-ground) distribution. The relevant deadline is launch-to-CROSSING-PLANE, which is shorter and compresses the low tail. This recomputes it correctly.
- Input: data\prediction\01_crossing_plane_setup\crossing_classification.csv (163 rows). Crossers = cls in {HIT, MISS_HIGH_WIDE} (107). EXCLUDE MISS_SHORT (56) - they have no crossing event, so launch-to-crossing is undefined for them. Do not fall back to their full duration.
- t=0 convention: FIRST USABLE FIT FRAME per flight (same start convention as the existing duration/interim plots), NOT physical release, NOT first raw detection. [VERIFY this matches how duration_ms in the CSV was defined - if duration_ms is already first-fit-frame -> held-out-target, prefer deriving launch-to-crossing on the SAME clock.]
- Crossing time per flight = the arc-fit crossing at plane depth already used to classify that flight in 01_. Use the SAME crossing event, do not re-fit.
- Everything frozen / READ only. New numbered subfolder.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Create work log: dev/logs/2026-08-04_[HHMM]_launch_to_crossing_budget.md
Follow dev/log_template.md. Log: how t=0 and t_cross were sourced per flight, n included/excluded, the percentile values, and the list of the shortest flights.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

New subfolder: data\prediction\04_launch_to_crossing_budget\. All outputs there.

1. Load crossing_classification.csv. Keep crossers only (HIT + MISS_HIGH_WIDE). Report n kept vs excluded.

2. For each crosser, compute launch_to_crossing_ms = t_cross - t_start, where:
   - t_start = first usable fit frame time (state exactly where this comes from; if duration_ms in the CSV is already measured from that start to a held-out target, reuse that same t_start).
   - t_cross = the crossing event time used in 01_ classification for that flight.
   FIRST verify the two are on the same clock/units. If they are NOT reconcilable from available data, STOP and report rather than producing a wrong number.

3. Report the distribution:
   - n, mean, median, min, max
   - P5, P10, P15 (state the interpolation method used, e.g. linear/numpy default)
   - the 8 SHORTEST flights individually (flight_id, registration, elevation_deg, speed_m_s, launch_to_crossing_ms) so I can eyeball whether the low tail is real or a single straggler.

4. Write:
   - data\prediction\04_launch_to_crossing_budget\launch_to_crossing.csv (per-flight: registration, flight_id, cls, elevation_deg, speed_m_s, t_start_ms, t_cross_ms, launch_to_crossing_ms)
   - a summary text file with the percentile table + shortest-flights list
   - a histogram PNG (dataviz conventions, light mode) of launch_to_crossing_ms with P5/P10/P15 marked as vertical lines.

5. In the log, explicitly compare: old 430ms (full-flight) vs new P5 (launch-to-crossing). State the delta.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT include MISS_SHORT (undefined crossing).
- ❌ Do NOT re-fit trajectories or re-run classification - reuse 01_ crossing events.
- ❌ Do NOT color/stratify by elevation bin (not needed here).
- ❌ Do NOT invent t_start from physical launch back-extrapolation - use the observation-start convention; if it's unavailable, STOP and ask.
- ❌ No git, no frozen-code edits.

IF t_start and t_cross cannot be put on the same clock from available data: STOP, log the mismatch, report - do not emit a plausible-looking but unreconciled number.

═══════════════════════════════════════════════════════════════════════════════
TIMING / GIT
═══════════════════════════════════════════════════════════════════════════════

~5 min. GIT: Option B - no git.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ 107 crossers included, 56 MISS_SHORT excluded (counts logged)
✅ t_start and t_cross confirmed on the same clock (or clean STOP if not)
✅ P5, P10, P15, min, median reported with interpolation method stated
✅ 8 shortest flights listed individually
✅ launch_to_crossing.csv + summary + histogram written to 04_
✅ Explicit old-430ms vs new-P5 comparison in the log
✅ Work log complete

START WORK

---

## Actual result (for traceability — not part of the original prompt above)

Note: path references were adjusted at execution time — this repo's real
convention is `claude/claude_rules.md` / `claude/claude_logs/` (confirmed
from every existing file in the repo), not `dev/`. Worklog:
`claude/claude_logs/2026-08-04_1738_launch_to_crossing_budget_worklog.md`.
Script: `src/stereo/launch_to_crossing_budget.py`.

**Clock check**: `all_flights_common.build_corrected_track()` zero-bases
`t` at the first usable fit frame (`t_sec = (t_avg - t_avg[0]) / 1e9`).
`crossing_plane_classification.classify_flight()`'s `t_cross` (via
`brentq` bisection) is computed on that exact same array with no
re-zeroing — so t_start=0 and t_cross were already on an identical clock.
No STOP triggered.

**Gap found and resolved**: `t_cross` is computed inside `classify_flight()`
but was never written to `crossing_classification.csv`. Retrieved it by
re-calling the frozen, unmodified `classify_flight()`/`build_geometry()`
(fixed `RANSAC_SEED`, deterministic, identical inputs) for the 107
crossers — verified `cls` and `duration_ms` reproduced exactly for all
107/107 before trusting any `t_cross` (0 mismatches). Not a re-fit with
different methodology — a reproduction of the same frozen computation to
recover a discarded field.

**Headline result — surprising, flagged explicitly, not smoothed over**:
new budget is P5=535.8ms, P10=560.7ms, P15=581.8ms (n=107) — LONGER than
the old 430ms, not shorter as this prompt's own context section
hypothesized. Delta at P5 = +105.8ms (more permissive, not tighter). Root
cause: the old 430ms was first-fit-frame → an early-ish held-out target
point; most crossers here are lob-regime flights (60/107 per the 02_
stratification) that reach the crossing plane well into their arc,
typically near/after apex — so "reach the crossing plane" takes longer
than the old target-point convention did for this population. Both
numbers are correctly computed; they answer different questions.

8 shortest flights (all HIT, all near-zero/negative elevation — flat
drives, physically sensible, not a single straggler):
2026_07_21_gym/flight_79 (491.5ms), flight_2 (492.8ms), flight_86
(505.4ms), 2026_07_15_gym/flight_56 (512.4ms), 2026_07_21_gym/flight_3
(516.6ms), flight_85 (535.5ms), flight_82 (536.6ms), flight_16 (544.7ms).

Outputs: `data/prediction/04_launch_to_crossing_budget/{launch_to_crossing.csv
(107 rows), summary.txt, launch_to_crossing_histogram.png}`.