READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Re-select 20 crossing flights for manual crossing-bracket labelling, chosen to VALIDATE FIT ACCURACY (position + velocity) across trajectory regimes - NOT by edge proximity. Read the existing classification, stratify crossers by elevation, pick for spread, write a new ranked-candidates CSV and a candidates-only Y-Z scatter.

CONTEXT:
- Input: data\prediction\01_crossing_plane_setup\crossing_classification.csv (163 rows; 107 crossers = HIT + MISS_HIGH_WIDE; 56 MISS_SHORT).
- The PREVIOUS candidate list (ranked_candidates.csv) sorted by edge_dist ascending. That was WRONG for this goal: it filled the list with near-edge lobs and excluded the 41 low-elevation (flat-drive) crossers, which cross mid-box (high edge_dist) but are the higher-crossing-speed regime we most need to validate.
- Goal now: validate that Model-C crossing-state prediction (position + velocity) holds ACROSS elevation regimes, because fit behaviour differs between flat drives (crossing fast, shallow, early in descent) and lobs (crossing steep, near/past apex).
- Everything frozen / READ only. New numbered subfolder for outputs.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Create work log: dev/logs/2026-08-04_[HHMM]_candidate_reselection.md
Follow dev/log_template.md. Append in REAL-TIME. Log the stratum boundaries, how many crossers fall in each, the selection per stratum with reasons, and the final 20 with their elevation / crossing_Y / crossing_Z / speed / flag.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

Create NEW subfolder data\prediction\02_candidate_reselection\. All outputs there. Do not modify 01_ or any frozen code.

1. Load crossing_classification.csv. Keep only crossers (cls in {HIT, MISS_HIGH_WIDE}). Report count.

2. Stratify crossers into 3 elevation bins:
   - FLAT: elevation_deg < 15
   - MID:  15 <= elevation_deg < 45
   - LOB:  elevation_deg >= 45
   Report how many crossers are in each bin, split by HIT vs MISS_HIGH_WIDE and by flagged vs unflagged.

3. Select 20 flights total with these rules, in priority order:
   a. RESERVED deliberate picks (take first, count toward the 20):
      - flight_109 (REG_21_2) - decision-boundary probe (edge_dist ~11mm).
      - 2-3 FLAGGED FLAT drives (elevation<15, flag_reason not null) - double as flag-validity probes and flat-regime coverage. Pick the ones nearest mid-box.
   b. Fill the rest to reach ~6-7 per elevation bin (FLAT / MID / LOB), across all 3 registrations where possible.
   c. WITHIN each bin, select for CROSSING-POSITION SPREAD across the 2x2m box (spread in crossing_Y and crossing_Z) - do NOT sort by edge_dist. Aim to cover centre and edges, low-Z and high-Z.
   d. Prefer unflagged EXCEPT where flagged is needed for flat-regime coverage (many flat crossers are flagged - do not end up with zero flat drives to avoid flags).
   Log any bin that can't reach 6 because too few crossers exist, and report it rather than padding from another bin.

4. Write data\prediction\02_candidate_reselection\ranked_candidates_v2.csv:
   columns: registration, session, flight_id, cls, elevation_bin, elevation_deg, speed_m_s, crossing_Y, crossing_Z, crossing_speed, crossing_vel_xyz, edge_dist, flagged, flag_reason, selection_reason
   (selection_reason = e.g. "FLAT stratum, mid-box spread" / "boundary probe" / "flagged-flat probe")

5. Also write the FULL crosser pool ranked/stratified (all 107) to all_crossers_stratified.csv (same columns minus selection_reason, plus elevation_bin) so I can hand-swap picks if I want.

6. Candidates-only Y-Z scatter: data\prediction\02_candidate_reselection\candidates_scatter.png
   - 2x2m aperture box drawn
   - the 20 candidates plotted, MARKER COLOR = elevation bin (FLAT/MID/LOB), marker shape = HIT vs MISS_HIGH_WIDE
   - annotate the reserved probes (flight_109, flagged-flat)
   - dataviz skill conventions, light mode, static PNG
   Purpose: let me eyeball that the 20 actually span elevation AND box position, not cluster.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT sort or select by edge_dist (that was the previous mistake). edge_dist is output for reference only.
- ❌ Do NOT re-run classification, re-fit, or touch 01_ outputs or frozen code.
- ❌ Do NOT do the actual crossing-bracket labelling (that's manual, next).
- ❌ Do NOT exclude flagged flights wholesale - some are required for flat coverage.
- ❌ No git, no refactor.

IF a rule conflicts (e.g. can't get box spread AND 6 per bin AND all unflagged): prioritise elevation-bin coverage > flat-regime inclusion > box spread > unflagged. Log the tradeoff you made.

═══════════════════════════════════════════════════════════════════════════════
TIMING / GIT
═══════════════════════════════════════════════════════════════════════════════

Total ~5-8 min. GIT: Option B - no git.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ 20 candidates selected, stratified across FLAT/MID/LOB with per-bin counts logged
✅ flight_109 + 2-3 flagged-flat probes present and labelled as such in selection_reason
✅ Selection is by elevation stratum + box spread, NOT edge_dist (verifiable in log)
✅ ranked_candidates_v2.csv (20) + all_crossers_stratified.csv (107) + candidates_scatter.png written to 02_candidate_reselection\
✅ Scatter visibly spans elevation bins and box position
✅ Work log complete, tradeoffs logged

START WORK