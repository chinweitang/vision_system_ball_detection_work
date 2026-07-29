# 2026-07-28 16:36 — Whole-frame cam0/cam1 misalignment: audit all flights, fix, re-run affected ones

**Instructions:** Copy the block below and paste it into the same Claude Code session
that's been running the gravity-vs-drag trajectory fitting task.

---

```
READ FIRST: claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
IN FULL, particularly the all-flights generalization and the RANSAC health-check
investigation. This is a bug investigation on that same task, not a new one.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Investigating why `flight_41` and `flight_44` (2026_07_21_gym) show unusually broad,
severe RANSAC rejection (flight_41: 152 flagged rows across nearly its whole N range,
all 3 models; flight_44: 33 flagged rows) despite BOTH cameras' own 2D detections
being completely clean (zero frame-to-frame jumps >80px/frame in either camera,
manually confirmed — no visible wrong-object artifact in either contact sheet).

**Root cause already found, needs verification and fixing, not re-discovery**: for
both flights, the same-`frame_number` cam0/cam1 timestamp delta is consistently
~-10.9ms (flight_41) / ~-10.5ms (flight_44) — stable across the whole flight (checked
both the start and end of each), and clearly OUTSIDE the normal ±8.3ms bound (half a
frame period, the physical maximum for ordinary sub-frame drift established
throughout this whole session's sync work). This looks like a **whole-frame
misalignment** — likely a single dropped/duplicated frame in one camera partway
through capture, shifting all subsequent frame numbers by one relative to the other
camera — not the usual small sub-frame drift. Same-`frame_number` pairing would
therefore be combining two genuinely different real instants for these flights,
which would corrupt the triangulated 3D trajectory even though each camera's own 2D
tracking is fine — consistent with everything observed (clean per-camera detections,
broad/severe 3D-level RANSAC rejection). `flight_42` (initially suspected as a third
case in the same nearby group) does NOT show this pattern (delta +5.9ms, normal) —
its smaller/milder flagging has a different, unrelated cause, not in scope here.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

Continue appending to
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md — same
task, do not create a new log file.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. **Verify the finding independently** before trusting it: recompute the
   same-`frame_number` cam0/cam1 timestamp delta for flight_41 and flight_44 directly
   (don't just trust this prompt's numbers) — confirm the ~-10.9ms / ~-10.5ms,
   outside-normal-bound pattern.

2. **Systematically audit ALL 163 flights** for this same signature (same-index delta
   consistently outside ±8.3ms) — this was only found by manually spot-checking 3
   RANSAC-flagged flights; a proper mechanical check across every flight is needed to
   find the FULL set affected, not just the ones that happened to also get
   RANSAC-flagged (a flight with this same misalignment might not always produce a
   severe-enough rejection rate to trip the health-check). Report the complete list.

3. **Check whether the pairing logic actually used in this pipeline
   (`build_corrected_pairs()` / whatever nearest-timestamp search Phase 1/2 actually
   call) correctly resolves this for the affected flights** — i.e. does it find the
   TRUE nearest-in-time cam1 partner (likely frame_number ± 1, with a small
   sub-frame-scale residual once correctly matched), or does something about how
   it's invoked/scoped miss this and fall back to same-index pairing anyway? Trace
   this in the actual code path used, don't assume either way.

4. **If a real gap is found**: fix it, and re-verify on flight_41/flight_44
   specifically (confirm the corrected pairing now produces a small residual delta
   for the true nearest partner, not the ~10ms same-index one).

5. **Re-run Phase 1 (full-arc RANSAC + per-flight K) and Phase 2 (prediction sweep)**
   for ONLY the affected flights found in step 2 (not all 163 — this is a targeted
   re-run, should be fast). Report: did rejection rates/RANSAC health flags improve
   for these flights? Does the fitted trajectory now look physically sensible for
   them?

6. **Report whether this meaningfully affects the aggregate results** — given this
   affects a small number of flights out of 163, a full recompute of the pooled K and
   population-level plots isn't required by this task, but report whether the
   affected flights' corrected fits differ enough from their broken versions that
   re-pooling would plausibly change anything, so a decision can be made on whether
   that's worth doing separately.

7. Update `ransac_rejection_summary.csv`, `ransac_health_flags.csv`, and
   `prediction_sweep_all_flights.csv` for just the affected flights' rows (don't
   regenerate the other 160+ flights' already-correct rows).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Don't re-run all 163 flights — only the ones found to actually have this
  misalignment signature
- ❌ Don't force a full pooled-K recompute — report whether it's warranted, let that
  be a separate decision
- ❌ Don't assume flight_42 has the same cause — it doesn't (already checked, normal
  delta) — if its own cause turns out to matter, flag it separately, don't fold it
  into this fix
- ❌ Don't commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected: other flights beyond flight_41/flight_44 turning up with the same
signature in the step-2 audit — expand the fix/re-run to cover all of them, not just
the original 2.

Unexpected (STOP immediately): the pairing logic appears correct on inspection but
the corrupted delta persists after the "fix" — means the actual root cause is
something other than what's diagnosed here; report the discrepancy rather than
forcing the fix to seem to have worked.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Finding independently verified, not just trusted from this prompt
✅ Full audit across all 163 flights for this signature, not just the 3 spot-checked
✅ Root cause in the actual pairing code path confirmed (or a different explanation
   found and reported honestly)
✅ Fix applied and re-verified only if a real gap was found
✅ Only the affected flights re-run through Phase 1/2, not the full 163
✅ Aggregate-impact question answered (does re-pooling plausibly matter), not forced
✅ Existing worklog continued, updated in real time
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now: verify the flight_41/flight_44 finding, audit all 163 flights for the
same signature, trace the pairing code path, fix if needed, re-run affected flights
only, report.
```
