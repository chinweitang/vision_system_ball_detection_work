# 2026-08-04 Crossing-plane setup worklog

Task prompt: `claude/prompts/2026-08-04_1240_crossing_plane_setup.md`
Implementation plan: `claude/prompts/2026-08-04_1347_crossing_plane_setup_plan.md`

## Summary (updated as work progresses)

Status: DONE. 163/163 flights classified (0 skipped): HIT=87, MISS_HIGH_WIDE=20,
MISS_SHORT=56. All 3 registrations passed the separation and axis self-checks.
Outputs in `data/prediction/01_crossing_plane_setup/`: geometry_report.txt,
crossing_classification.csv (163 rows), miss_short_flights.csv (56),
ranked_candidates.csv (20), skipped_flights.csv (0), crossing_scatter_pooled.png
+ 3 per-registration PNGs.

## Log

- [13:47] Tape endpoints (6 CSVs, 3 registrations x 2 cams) already labelled
  in a prior part of this session, reviewed and confirmed by Chin Wei.
  Plan written and approved (see plan file above). Key deviations from the
  original prompt, both agreed with Chin Wei during planning:
  - No absolute floor/world origin exists in this codebase (X_world/Y_world/
    Z_world are pure directions, T_wc unused downstream) -> plane, aperture,
    and MISS-SHORT are all computed relative to the tape points, not an
    absolute floor. MISS-SHORT determined by comparing the flight's last
    observed point's depth to the plane depth (Chin Wei's simplification),
    not by floor-extrapolation.
  - Checkpoint pause after Phase A skipped by request - running Phase A and
    B in one go.
  - Tape separation sanity bound adjusted from ~1.0m to ~700mm (Chin Wei
    confirmed all 3 registrations were clicked at ~700mm, not the tape's
    true ~1m length - direction math unaffected since aperture uses a unit
    vector).
- [13:47] Starting Phase A implementation: new script
  `src/stereo/crossing_plane_classification.py`.
- [13:53:23] Phase A: building geometry for all 3 registrations.
- [13:53:23] === REG_15 (2026_07_15_gym / registration) ===
- [13:53:23]   P_a = (2119.8, 2670.3, 4521.3) mm (cam0 frame)   P_b = (2099.2, 2458.4, 3881.4) mm
- [13:53:23]   separation = 674.5 mm  (expect ~700 +-200, OK)
- [13:53:23]   Z_world height agreement between endpoints = 3.1 mm (adapted floor sanity check)
- [13:53:23]   tape-line angle to Y_world = 0.42 deg (tol 20.0, OK)
- [13:53:23]   tape-line angle to X_world = 89.68 deg (diagnostic, expect close to 90)
- [13:53:23]   P_near = (2099.2, 2458.4, 3881.4)   P_far = (2119.8, 2670.3, 4521.3)
- [13:53:23]   u (P_far->P_near, camera frame) = (-0.0, -0.3, -0.9)
- [13:53:23]   up (Z_world) = (0.0, -1.0, 0.3)
- [13:53:23]   aperture corner_A (=P_far) = (2119.8, 2670.3, 4521.3)
- [13:53:23]   aperture corner_B (+2m along u) = (2058.7, 2041.8, 2623.7)
- [13:53:23]   aperture corner_C (+2m up from B) = (2076.9, 140.2, 3243.2)
- [13:53:23]   aperture corner_D (+2m up from A) = (2138.0, 768.8, 5140.8)
- [13:53:23]   plane depth (mean tape pos . X_world) = 1999.6 mm
- [13:53:23] 
- [13:53:23] === REG_21_1 (2026_07_21_gym / registration1) ===
- [13:53:23]   P_a = (1737.5, 2796.3, 4612.9) mm (cam0 frame)   P_b = (1777.7, 2611.3, 4032.0) mm
- [13:53:23]   separation = 611.0 mm  (expect ~700 +-200, OK)
- [13:53:23]   Z_world height agreement between endpoints = 11.9 mm (adapted floor sanity check)
- [13:53:23]   tape-line angle to Y_world = 5.66 deg (tol 20.0, OK)
- [13:53:23]   tape-line angle to X_world = 84.45 deg (diagnostic, expect close to 90)
- [13:53:23]   P_near = (1777.7, 2611.3, 4032.0)   P_far = (1737.5, 2796.3, 4612.9)
- [13:53:23]   u (P_far->P_near, camera frame) = (0.1, -0.3, -1.0)
- [13:53:23]   up (Z_world) = (0.0, -0.9, 0.3)
- [13:53:23]   aperture corner_A (=P_far) = (1737.5, 2796.3, 4612.9)
- [13:53:23]   aperture corner_B (+2m along u) = (1869.3, 2190.9, 2711.3)
- [13:53:23]   aperture corner_C (+2m up from B) = (1895.9, 298.1, 3356.7)
- [13:53:23]   aperture corner_D (+2m up from A) = (1764.1, 903.5, 5258.3)
- [13:53:23]   plane depth (mean tape pos . X_world) = 1620.4 mm
- [13:53:23] 
- [13:53:23] === REG_21_2 (2026_07_21_gym / registration2) ===
- [13:53:23]   P_a = (1904.0, 2804.8, 4594.5) mm (cam0 frame)   P_b = (1903.0, 2588.6, 3964.7) mm
- [13:53:23]   separation = 665.9 mm  (expect ~700 +-200, OK)
- [13:53:23]   Z_world height agreement between endpoints = 0.9 mm (adapted floor sanity check)
- [13:53:23]   tape-line angle to Y_world = 1.67 deg (tol 20.0, OK)
- [13:53:23]   tape-line angle to X_world = 88.34 deg (diagnostic, expect close to 90)
- [13:53:23]   P_near = (1903.0, 2588.6, 3964.7)   P_far = (1904.0, 2804.8, 4594.5)
- [13:53:23]   u (P_far->P_near, camera frame) = (-0.0, -0.3, -0.9)
- [13:53:23]   up (Z_world) = (0.0, -0.9, 0.3)
- [13:53:23]   aperture corner_A (=P_far) = (1904.0, 2804.8, 4594.5)
- [13:53:23]   aperture corner_B (+2m along u) = (1901.0, 2155.5, 2702.9)
- [13:53:23]   aperture corner_C (+2m up from B) = (1929.6, 264.8, 3354.5)
- [13:53:23]   aperture corner_D (+2m up from A) = (1932.7, 914.1, 5246.1)
- [13:53:23]   plane depth (mean tape pos . X_world) = 1768.6 mm
- [13:53:23] 
- [13:53:23] Geometry report written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\01_crossing_plane_setup\geometry_report.txt
- [13:53:23] Phase B: pooled_k=5.268474e-05, classifying all eligible flights.
- [13:53:23] 163 eligible flights found.
- [13:54:16] Phase A: building geometry for all 3 registrations.
- [13:54:16] === REG_15 (2026_07_15_gym / registration) ===
- [13:54:16]   P_a = (2119.8, 2670.3, 4521.3) mm (cam0 frame)   P_b = (2099.2, 2458.4, 3881.4) mm
- [13:54:16]   separation = 674.5 mm  (expect ~700 +-200, OK)
- [13:54:16]   Z_world height agreement between endpoints = 3.1 mm (adapted floor sanity check)
- [13:54:16]   tape-line angle to Y_world = 0.42 deg (tol 20.0, OK)
- [13:54:16]   tape-line angle to X_world = 89.68 deg (diagnostic, expect close to 90)
- [13:54:16]   P_near = (2099.2, 2458.4, 3881.4)   P_far = (2119.8, 2670.3, 4521.3)
- [13:54:16]   u (P_far->P_near, camera frame) = (-0.0, -0.3, -0.9)
- [13:54:16]   up (Z_world) = (0.0, -1.0, 0.3)
- [13:54:16]   aperture corner_A (=P_far) = (2119.8, 2670.3, 4521.3)
- [13:54:16]   aperture corner_B (+2m along u) = (2058.7, 2041.8, 2623.7)
- [13:54:16]   aperture corner_C (+2m up from B) = (2076.9, 140.2, 3243.2)
- [13:54:16]   aperture corner_D (+2m up from A) = (2138.0, 768.8, 5140.8)
- [13:54:16]   plane depth (mean tape pos . X_world) = 1999.6 mm
- [13:54:16] 
- [13:54:16] === REG_21_1 (2026_07_21_gym / registration1) ===
- [13:54:16]   P_a = (1737.5, 2796.3, 4612.9) mm (cam0 frame)   P_b = (1777.7, 2611.3, 4032.0) mm
- [13:54:16]   separation = 611.0 mm  (expect ~700 +-200, OK)
- [13:54:16]   Z_world height agreement between endpoints = 11.9 mm (adapted floor sanity check)
- [13:54:16]   tape-line angle to Y_world = 5.66 deg (tol 20.0, OK)
- [13:54:16]   tape-line angle to X_world = 84.45 deg (diagnostic, expect close to 90)
- [13:54:16]   P_near = (1777.7, 2611.3, 4032.0)   P_far = (1737.5, 2796.3, 4612.9)
- [13:54:16]   u (P_far->P_near, camera frame) = (0.1, -0.3, -1.0)
- [13:54:16]   up (Z_world) = (0.0, -0.9, 0.3)
- [13:54:16]   aperture corner_A (=P_far) = (1737.5, 2796.3, 4612.9)
- [13:54:16]   aperture corner_B (+2m along u) = (1869.3, 2190.9, 2711.3)
- [13:54:16]   aperture corner_C (+2m up from B) = (1895.9, 298.1, 3356.7)
- [13:54:16]   aperture corner_D (+2m up from A) = (1764.1, 903.5, 5258.3)
- [13:54:16]   plane depth (mean tape pos . X_world) = 1620.4 mm
- [13:54:16] 
- [13:54:16] === REG_21_2 (2026_07_21_gym / registration2) ===
- [13:54:16]   P_a = (1904.0, 2804.8, 4594.5) mm (cam0 frame)   P_b = (1903.0, 2588.6, 3964.7) mm
- [13:54:16]   separation = 665.9 mm  (expect ~700 +-200, OK)
- [13:54:16]   Z_world height agreement between endpoints = 0.9 mm (adapted floor sanity check)
- [13:54:16]   tape-line angle to Y_world = 1.67 deg (tol 20.0, OK)
- [13:54:16]   tape-line angle to X_world = 88.34 deg (diagnostic, expect close to 90)
- [13:54:16]   P_near = (1903.0, 2588.6, 3964.7)   P_far = (1904.0, 2804.8, 4594.5)
- [13:54:16]   u (P_far->P_near, camera frame) = (-0.0, -0.3, -0.9)
- [13:54:16]   up (Z_world) = (0.0, -0.9, 0.3)
- [13:54:16]   aperture corner_A (=P_far) = (1904.0, 2804.8, 4594.5)
- [13:54:16]   aperture corner_B (+2m along u) = (1901.0, 2155.5, 2702.9)
- [13:54:16]   aperture corner_C (+2m up from B) = (1929.6, 264.8, 3354.5)
- [13:54:16]   aperture corner_D (+2m up from A) = (1932.7, 914.1, 5246.1)
- [13:54:16]   plane depth (mean tape pos . X_world) = 1768.6 mm
- [13:54:16] 
- [13:54:16] Geometry report written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\01_crossing_plane_setup\geometry_report.txt
- [13:54:16] Phase B: pooled_k=5.268474e-05, classifying all eligible flights.
- [13:54:16] 163 eligible flights found.
- [13:56:20] Classified 163/163 flights, 0 skipped (0.0%).
- [13:56:20] Classification summary: {'MISS_HIGH_WIDE': 20, 'HIT': 87, 'MISS_SHORT': 56}  (skipped=0, total=163)
- [13:56:20] Per-flight CSV written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\01_crossing_plane_setup\crossing_classification.csv
- [13:56:20] Skipped-flights list written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\01_crossing_plane_setup\skipped_flights.csv
- [13:56:20] Hit a frozen-code edge case during classification: simulate_drag
  (trajectory_fit.py) integrates over (0, max(t_array)) via solve_ivp; a
  single t=0.0 evaluation makes that a zero-length interval, and solve_ivp
  returns sol.y as a list instead of an ndarray in that case, breaking the
  `.T` call. Not a frozen-code bug I'm allowed to fix in place -- worked
  around it in crossing_plane_classification.py instead: use the fit's own
  p0 directly whenever a query time is <=0, and start the bisection
  bracket at t=1e-6 rather than exactly 0.0.
- [~14:05] Wrote crossing_plane_plots_and_ranking.py: pooled + 3
  per-registration Y-Z scatter plots (dataviz skill conventions -- status
  palette good/warning for HIT/MISS_HIGH_WIDE, marker-shape secondary
  encoding, light-mode chart chrome from references/palette.md), ranked
  candidate table (edge-distance sort, duration>1200ms filter, round-robin
  across 4 elevation bins, flagged flights deprioritized not excluded).
- [~14:06] Verified output row counts: crossing_classification.csv 163 data
  rows, miss_short_flights.csv 56, ranked_candidates.csv 20,
  skipped_flights.csv 0 -- all consistent with the classification summary
  (87+20+56=163). Visually inspected crossing_scatter_pooled.png: HIT
  points cluster inside the aperture box as expected, MISS_HIGH_WIDE points
  scatter outside it (mostly above/left) -- classification logic looks
  correct by eye.
- [~14:06] DONE. Ready for Chin Wei to pick the final 15 candidates from
  ranked_candidates.csv for manual crossing-bracket labelling (next task,
  out of scope here).

## Candidate re-selection (v2) -- new task

Chin Wei flagged the v1 ranking (edge_dist ascending) as wrong for the actual
goal: it filled the list with near-edge lobs and excluded the 41 low-
elevation flat-drive crossers entirely, but flat drives (fast, shallow,
crossing early in descent) are a physically distinct regime from lobs
(steep, near/past apex) and need their own coverage to validate Model-C
crossing-state prediction across regimes. New task: stratify by elevation
into FLAT(&lt;15)/MID(15-45)/LOB(&gt;=45), select for box-position SPREAD within
each stratum (not edge proximity), reserve flight_109 (decision-boundary
probe) + 2-3 flagged flat drives. New script, new output folder
(`data/prediction/02_candidate_reselection/`), 01_ untouched.

- [14:15] Starting: writing crossing_plane_candidate_reselection.py.

- [14:16] Loaded 107 crossers (HIT+MISS_HIGH_WIDE) from crossing_classification.csv.
- [14:16] FLAT bin: 35 crossers (HIT=34, MISS_HIGH_WIDE=1; unflagged=10, flagged=25)
- [14:16] MID bin: 12 crossers (HIT=10, MISS_HIGH_WIDE=2; unflagged=8, flagged=4)
- [14:16] LOB bin: 60 crossers (HIT=43, MISS_HIGH_WIDE=17; unflagged=24, flagged=36)
- [14:17] Reserved: 2026_07_21_gym/flight_109 (bin=LOB, edge_dist=11mm) - boundary probe.
- [14:17] Reserved: 2026_07_21_gym/flight_87 (flagged-FLAT, dist-to-center=43mm) - flat-regime + flag-validity probe.
- [14:17] Reserved: 2026_07_21_gym/flight_13 (flagged-FLAT, dist-to-center=151mm) - flat-regime + flag-validity probe.
- [14:17] Reserved: 2026_07_21_gym/flight_75 (flagged-FLAT, dist-to-center=200mm) - flat-regime + flag-validity probe.
- [14:18] FLAT bin: filled 4 more (target 7, 3 reserved) via box-spread selection.
- [14:18] MID bin: filled 7 more (target 7, 0 reserved) via box-spread selection.
- [14:18] LOB bin: filled 5 more (target 6, 1 reserved) via box-spread selection.
- [14:19] Final selection: 20 candidates, per bin:
    FLAT: 7
    MID: 7
    LOB: 6
- [14:19] Wrote ranked_candidates_v2.csv (20 rows).
- [14:19] Wrote all_crossers_stratified.csv (107 rows).
- [14:20] Wrote candidates_scatter.png.
- [17:12:52] flight_109 (REG_21_2): t_cross=1.0809s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    *** cam0 frame 110: No frame image for cam0 frame 110 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    *** cam0 frame 112: No frame image for cam0 frame 112 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    *** cam0 frame 114: No frame image for cam0 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    *** cam0 frame 116: No frame image for cam0 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    *** cam0 frame 118: No frame image for cam0 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    *** cam0 frame 120: No frame image for cam0 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam0 -- skipped ***
    cam1: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    *** cam1 frame 110: No frame image for cam1 frame 110 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
    *** cam1 frame 112: No frame image for cam1 frame 112 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
    *** cam1 frame 114: No frame image for cam1 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
    *** cam1 frame 116: No frame image for cam1 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
    *** cam1 frame 118: No frame image for cam1 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
    *** cam1 frame 120: No frame image for cam1 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_109\cam1 -- skipped ***
- [17:12:53] flight_87 (REG_21_2): t_cross=0.5476s, idx_cross=33/6, bracket_pair_indices=[27, 29, 31, 33, 35, 37], symmetric=True, span=199.8ms
    cam0: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
    cam1: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
- [17:12:54] flight_13 (REG_21_1): t_cross=0.6552s, idx_cross=39/6, bracket_pair_indices=[33, 35, 37, 39, 41, 43], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    *** cam0 frame 81: No frame image for cam0 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam0 -- skipped ***
    *** cam0 frame 83: No frame image for cam0 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam0 -- skipped ***
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam0 -- skipped ***
    *** cam0 frame 89: No frame image for cam0 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam0 -- skipped ***
    cam1: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    *** cam1 frame 81: No frame image for cam1 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam1 -- skipped ***
    *** cam1 frame 83: No frame image for cam1 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam1 -- skipped ***
    *** cam1 frame 85: No frame image for cam1 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam1 -- skipped ***
    *** cam1 frame 87: No frame image for cam1 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam1 -- skipped ***
    *** cam1 frame 89: No frame image for cam1 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_13\cam1 -- skipped ***
- [17:12:54] flight_75 (REG_21_2): t_cross=0.6402s, idx_cross=38/6, bracket_pair_indices=[32, 34, 36, 38, 40, 42], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    *** cam0 frame 81: No frame image for cam0 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam0 -- skipped ***
    *** cam0 frame 83: No frame image for cam0 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam0 -- skipped ***
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam0 -- skipped ***
    *** cam0 frame 89: No frame image for cam0 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam0 -- skipped ***
    cam1: frames=[78, 80, 82, 84, 86, 88]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    *** cam1 frame 80: No frame image for cam1 frame 80 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam1 -- skipped ***
    *** cam1 frame 82: No frame image for cam1 frame 82 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam1 -- skipped ***
    *** cam1 frame 84: No frame image for cam1 frame 84 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam1 -- skipped ***
    *** cam1 frame 86: No frame image for cam1 frame 86 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam1 -- skipped ***
    *** cam1 frame 88: No frame image for cam1 frame 88 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_75\cam1 -- skipped ***
- [17:12:55] flight_88 (REG_21_2): t_cross=0.6127s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    *** cam0 frame 81: No frame image for cam0 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam0 -- skipped ***
    *** cam0 frame 83: No frame image for cam0 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam0 -- skipped ***
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam0 -- skipped ***
    cam1: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    *** cam1 frame 81: No frame image for cam1 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam1 -- skipped ***
    *** cam1 frame 83: No frame image for cam1 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam1 -- skipped ***
    *** cam1 frame 85: No frame image for cam1 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam1 -- skipped ***
    *** cam1 frame 87: No frame image for cam1 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_88\cam1 -- skipped ***
- [17:12:56] flight_6 (REG_21_1): t_cross=0.5916s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    *** cam0 frame 89: No frame image for cam0 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    *** cam0 frame 91: No frame image for cam0 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    *** cam0 frame 93: No frame image for cam0 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    *** cam0 frame 95: No frame image for cam0 frame 95 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam0 -- skipped ***
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    *** cam1 frame 85: No frame image for cam1 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
    *** cam1 frame 87: No frame image for cam1 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
    *** cam1 frame 89: No frame image for cam1 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
    *** cam1 frame 91: No frame image for cam1 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
    *** cam1 frame 93: No frame image for cam1 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
    *** cam1 frame 95: No frame image for cam1 frame 95 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_6\cam1 -- skipped ***
- [17:12:57] flight_53 (REG_15): t_cross=0.5823s, idx_cross=34/6, bracket_pair_indices=[28, 30, 32, 34, 36, 38], symmetric=True, span=166.5ms
    cam0: frames=[58, 60, 62, 64, 66, 68]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
    cam1: frames=[59, 61, 63, 65, 67, 69]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
- [17:12:58] flight_69 (REG_21_2): t_cross=0.6201s, idx_cross=35/6, bracket_pair_indices=[29, 31, 33, 35, 37, 39], symmetric=True, span=199.8ms
    cam0: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    *** cam0 frame 81: No frame image for cam0 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam0 -- skipped ***
    *** cam0 frame 83: No frame image for cam0 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam0 -- skipped ***
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam0 -- skipped ***
    cam1: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    *** cam1 frame 81: No frame image for cam1 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam1 -- skipped ***
    *** cam1 frame 83: No frame image for cam1 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam1 -- skipped ***
    *** cam1 frame 85: No frame image for cam1 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam1 -- skipped ***
    *** cam1 frame 87: No frame image for cam1 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_69\cam1 -- skipped ***
- [17:12:59] flight_11 (REG_21_1): t_cross=0.8707s, idx_cross=51/5, bracket_pair_indices=[45, 47, 49, 51, 53], symmetric=False, span=149.9ms
    cam0: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    *** cam0 frame 81: No frame image for cam0 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam0 -- skipped ***
    *** cam0 frame 83: No frame image for cam0 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam0 -- skipped ***
    *** cam0 frame 86: No frame image for cam0 frame 86 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam0 -- skipped ***
    *** cam0 frame 88: No frame image for cam0 frame 88 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam0 -- skipped ***
    *** cam0 frame 90: No frame image for cam0 frame 90 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam0 -- skipped ***
    cam1: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    *** cam1 frame 81: No frame image for cam1 frame 81 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam1 -- skipped ***
    *** cam1 frame 83: No frame image for cam1 frame 83 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam1 -- skipped ***
    *** cam1 frame 86: No frame image for cam1 frame 86 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam1 -- skipped ***
    *** cam1 frame 88: No frame image for cam1 frame 88 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam1 -- skipped ***
    *** cam1 frame 90: No frame image for cam1 frame 90 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_11\cam1 -- skipped ***
- [17:13:00] flight_33 (REG_15): t_cross=1.1186s, idx_cross=64/6, bracket_pair_indices=[58, 60, 62, 64, 66, 68], symmetric=True, span=199.8ms
    cam0: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    *** cam0 frame 91: No frame image for cam0 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    *** cam0 frame 93: No frame image for cam0 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    *** cam0 frame 97: No frame image for cam0 frame 97 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    *** cam0 frame 99: No frame image for cam0 frame 99 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    *** cam0 frame 101: No frame image for cam0 frame 101 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    *** cam0 frame 103: No frame image for cam0 frame 103 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam0 -- skipped ***
    cam1: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    *** cam1 frame 91: No frame image for cam1 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
    *** cam1 frame 93: No frame image for cam1 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
    *** cam1 frame 97: No frame image for cam1 frame 97 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
    *** cam1 frame 99: No frame image for cam1 frame 99 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
    *** cam1 frame 101: No frame image for cam1 frame 101 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
    *** cam1 frame 103: No frame image for cam1 frame 103 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_33\cam1 -- skipped ***
- [17:13:01] flight_19 (REG_21_1): t_cross=0.8917s, idx_cross=54/6, bracket_pair_indices=[48, 50, 52, 54, 56, 58], symmetric=True, span=166.5ms
    cam0: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    *** cam0 frame 112: No frame image for cam0 frame 112 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    *** cam0 frame 114: No frame image for cam0 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    *** cam0 frame 116: No frame image for cam0 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    *** cam0 frame 118: No frame image for cam0 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    *** cam0 frame 120: No frame image for cam0 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    *** cam0 frame 122: No frame image for cam0 frame 122 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam0 -- skipped ***
    cam1: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    *** cam1 frame 112: No frame image for cam1 frame 112 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
    *** cam1 frame 114: No frame image for cam1 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
    *** cam1 frame 116: No frame image for cam1 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
    *** cam1 frame 118: No frame image for cam1 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
    *** cam1 frame 120: No frame image for cam1 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
    *** cam1 frame 122: No frame image for cam1 frame 122 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_19\cam1 -- skipped ***
- [17:13:02] flight_73 (REG_21_2): t_cross=0.7479s, idx_cross=45/6, bracket_pair_indices=[39, 41, 43, 45, 47, 49], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    *** cam0 frame 85: No frame image for cam0 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    *** cam0 frame 87: No frame image for cam0 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    *** cam0 frame 89: No frame image for cam0 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    *** cam0 frame 91: No frame image for cam0 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    *** cam0 frame 93: No frame image for cam0 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    *** cam0 frame 95: No frame image for cam0 frame 95 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam0 -- skipped ***
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    *** cam1 frame 85: No frame image for cam1 frame 85 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
    *** cam1 frame 87: No frame image for cam1 frame 87 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
    *** cam1 frame 89: No frame image for cam1 frame 89 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
    *** cam1 frame 91: No frame image for cam1 frame 91 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
    *** cam1 frame 93: No frame image for cam1 frame 93 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
    *** cam1 frame 95: No frame image for cam1 frame 95 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_73\cam1 -- skipped ***
- [17:13:03] flight_119 (REG_21_2): t_cross=0.9844s, idx_cross=56/5, bracket_pair_indices=[50, 52, 54, 56, 58], symmetric=False, span=166.5ms
    cam0: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    *** cam0 frame 108: No frame image for cam0 frame 108 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam0 -- skipped ***
    *** cam0 frame 110: No frame image for cam0 frame 110 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam0 -- skipped ***
    *** cam0 frame 114: No frame image for cam0 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam0 -- skipped ***
    *** cam0 frame 116: No frame image for cam0 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam0 -- skipped ***
    *** cam0 frame 118: No frame image for cam0 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam0 -- skipped ***
    cam1: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    *** cam1 frame 108: No frame image for cam1 frame 108 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam1 -- skipped ***
    *** cam1 frame 110: No frame image for cam1 frame 110 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam1 -- skipped ***
    *** cam1 frame 114: No frame image for cam1 frame 114 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam1 -- skipped ***
    *** cam1 frame 116: No frame image for cam1 frame 116 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam1 -- skipped ***
    *** cam1 frame 118: No frame image for cam1 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_119\cam1 -- skipped ***
- [17:13:04] flight_15 (REG_21_1): t_cross=0.6631s, idx_cross=40/6, bracket_pair_indices=[34, 36, 38, 40, 42, 44], symmetric=True, span=166.5ms
    cam0: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    *** cam0 frame 97: No frame image for cam0 frame 97 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    *** cam0 frame 99: No frame image for cam0 frame 99 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    *** cam0 frame 101: No frame image for cam0 frame 101 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    *** cam0 frame 103: No frame image for cam0 frame 103 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    *** cam0 frame 105: No frame image for cam0 frame 105 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    *** cam0 frame 107: No frame image for cam0 frame 107 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam0 -- skipped ***
    cam1: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    *** cam1 frame 97: No frame image for cam1 frame 97 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
    *** cam1 frame 99: No frame image for cam1 frame 99 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
    *** cam1 frame 101: No frame image for cam1 frame 101 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
    *** cam1 frame 103: No frame image for cam1 frame 103 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
    *** cam1 frame 105: No frame image for cam1 frame 105 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
    *** cam1 frame 107: No frame image for cam1 frame 107 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_15\cam1 -- skipped ***
- [17:13:05] flight_118 (REG_21_2): t_cross=1.0810s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    *** cam0 frame 125: No frame image for cam0 frame 125 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    *** cam0 frame 127: No frame image for cam0 frame 127 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    *** cam0 frame 129: No frame image for cam0 frame 129 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    *** cam0 frame 131: No frame image for cam0 frame 131 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    *** cam0 frame 133: No frame image for cam0 frame 133 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    *** cam0 frame 135: No frame image for cam0 frame 135 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam0 -- skipped ***
    cam1: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    *** cam1 frame 125: No frame image for cam1 frame 125 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
    *** cam1 frame 127: No frame image for cam1 frame 127 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
    *** cam1 frame 129: No frame image for cam1 frame 129 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
    *** cam1 frame 131: No frame image for cam1 frame 131 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
    *** cam1 frame 133: No frame image for cam1 frame 133 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
    *** cam1 frame 135: No frame image for cam1 frame 135 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_118\cam1 -- skipped ***
- [17:13:06] flight_22 (REG_15): t_cross=1.4028s, idx_cross=82/6, bracket_pair_indices=[76, 78, 80, 82, 84, 86], symmetric=True, span=216.5ms
    cam0: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    *** cam0 frame 82: No frame image for cam0 frame 82 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam0 -- skipped ***
    *** cam0 frame 84: No frame image for cam0 frame 84 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam0 -- skipped ***
    *** cam0 frame 86: No frame image for cam0 frame 86 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam0 -- skipped ***
    *** cam0 frame 88: No frame image for cam0 frame 88 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam0 -- skipped ***
    *** cam0 frame 92: No frame image for cam0 frame 92 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam0 -- skipped ***
    cam1: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    *** cam1 frame 82: No frame image for cam1 frame 82 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam1 -- skipped ***
    *** cam1 frame 84: No frame image for cam1 frame 84 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam1 -- skipped ***
    *** cam1 frame 86: No frame image for cam1 frame 86 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam1 -- skipped ***
    *** cam1 frame 88: No frame image for cam1 frame 88 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam1 -- skipped ***
    *** cam1 frame 92: No frame image for cam1 frame 92 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_22\cam1 -- skipped ***
- [17:13:07] flight_14 (REG_15): t_cross=1.2773s, idx_cross=73/6, bracket_pair_indices=[67, 69, 71, 73, 75, 77], symmetric=True, span=216.5ms
    cam0: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    *** cam0 frame 113: No frame image for cam0 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    *** cam0 frame 115: No frame image for cam0 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    *** cam0 frame 118: No frame image for cam0 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    *** cam0 frame 120: No frame image for cam0 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    *** cam0 frame 124: No frame image for cam0 frame 124 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    *** cam0 frame 126: No frame image for cam0 frame 126 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam0 -- skipped ***
    cam1: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    *** cam1 frame 113: No frame image for cam1 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
    *** cam1 frame 115: No frame image for cam1 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
    *** cam1 frame 118: No frame image for cam1 frame 118 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
    *** cam1 frame 120: No frame image for cam1 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
    *** cam1 frame 124: No frame image for cam1 frame 124 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
    *** cam1 frame 126: No frame image for cam1 frame 126 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_14\cam1 -- skipped ***
- [17:13:08] flight_56 (REG_21_1): t_cross=1.2517s, idx_cross=75/6, bracket_pair_indices=[69, 71, 73, 75, 77, 79], symmetric=True, span=166.5ms
    cam0: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    *** cam0 frame 109: No frame image for cam0 frame 109 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    *** cam0 frame 111: No frame image for cam0 frame 111 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    *** cam0 frame 113: No frame image for cam0 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    *** cam0 frame 115: No frame image for cam0 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    *** cam0 frame 117: No frame image for cam0 frame 117 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    *** cam0 frame 119: No frame image for cam0 frame 119 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam0 -- skipped ***
    cam1: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    *** cam1 frame 109: No frame image for cam1 frame 109 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
    *** cam1 frame 111: No frame image for cam1 frame 111 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
    *** cam1 frame 113: No frame image for cam1 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
    *** cam1 frame 115: No frame image for cam1 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
    *** cam1 frame 117: No frame image for cam1 frame 117 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
    *** cam1 frame 119: No frame image for cam1 frame 119 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_56\cam1 -- skipped ***
- [17:13:09] flight_12 (REG_15): t_cross=1.3838s, idx_cross=77/6, bracket_pair_indices=[71, 73, 75, 77, 79, 81], symmetric=True, span=199.8ms
    cam0: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    *** cam0 frame 107: No frame image for cam0 frame 107 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    *** cam0 frame 109: No frame image for cam0 frame 109 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    *** cam0 frame 113: No frame image for cam0 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    *** cam0 frame 115: No frame image for cam0 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    *** cam0 frame 117: No frame image for cam0 frame 117 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    *** cam0 frame 119: No frame image for cam0 frame 119 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam0 -- skipped ***
    cam1: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    *** cam1 frame 107: No frame image for cam1 frame 107 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
    *** cam1 frame 109: No frame image for cam1 frame 109 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
    *** cam1 frame 113: No frame image for cam1 frame 113 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
    *** cam1 frame 115: No frame image for cam1 frame 115 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
    *** cam1 frame 117: No frame image for cam1 frame 117 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
    *** cam1 frame 119: No frame image for cam1 frame 119 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_15_gym\ball_flights\flight_12\cam1 -- skipped ***
- [17:13:10] flight_107 (REG_21_2): t_cross=1.2554s, idx_cross=73/4, bracket_pair_indices=[67, 69, 71, 73], symmetric=False, span=99.9ms
    cam0: frames=[119, 121, 123, 125]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    *** cam0 frame 119: No frame image for cam0 frame 119 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam0 -- skipped ***
    *** cam0 frame 121: No frame image for cam0 frame 121 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam0 -- skipped ***
    *** cam0 frame 123: No frame image for cam0 frame 123 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam0 -- skipped ***
    *** cam0 frame 125: No frame image for cam0 frame 125 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam0 -- skipped ***
    cam1: frames=[120, 122, 124, 126]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    *** cam1 frame 120: No frame image for cam1 frame 120 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam1 -- skipped ***
    *** cam1 frame 122: No frame image for cam1 frame 122 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam1 -- skipped ***
    *** cam1 frame 124: No frame image for cam1 frame 124 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam1 -- skipped ***
    *** cam1 frame 126: No frame image for cam1 frame 126 under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights\flight_107\cam1 -- skipped ***
- [17:18] Dry-run above (build_targets only, no GUI, for debugging) hit a bug:
  frame_path() assumed raw frames live directly under
  flight_dir/cam{0,1}/frame_NNN.png. Wrong -- that dir is a SPARSE subset
  (context frames across the whole capture, big gaps during the actual
  flight); the real per-flight frames live under
  flight_dir/cam{0,1}/ball_in_frame/frame_NNN.png, same convention
  03_label_final_points.py already uses (read as reference earlier but
  didn't carry the convention over correctly the first time). Confirmed by
  direct inspection: flight_15/cam0 frames 095-117 missing from the bare
  cam0/ dir, all present under cam0/ball_in_frame/. Fixed frame_path() to
  check ball_in_frame/ first, bare cam dir as fallback. Only 38/240 targets
  resolved in the broken run (whatever coincidentally existed in the sparse
  outer folder). Re-running clean below.
- [17:15:47] flight_109 (REG_21_2): t_cross=1.0809s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:15:48] flight_87 (REG_21_2): t_cross=0.5476s, idx_cross=33/6, bracket_pair_indices=[27, 29, 31, 33, 35, 37], symmetric=True, span=199.8ms
    cam0: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
    cam1: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
- [17:15:48] flight_13 (REG_21_1): t_cross=0.6552s, idx_cross=39/6, bracket_pair_indices=[33, 35, 37, 39, 41, 43], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    cam1: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
- [17:15:49] flight_75 (REG_21_2): t_cross=0.6402s, idx_cross=38/6, bracket_pair_indices=[32, 34, 36, 38, 40, 42], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    cam1: frames=[78, 80, 82, 84, 86, 88]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
- [17:15:49] flight_88 (REG_21_2): t_cross=0.6127s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
- [17:15:50] flight_6 (REG_21_1): t_cross=0.5916s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
- [17:15:51] flight_53 (REG_15): t_cross=0.5823s, idx_cross=34/6, bracket_pair_indices=[28, 30, 32, 34, 36, 38], symmetric=True, span=166.5ms
    cam0: frames=[58, 60, 62, 64, 66, 68]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
    cam1: frames=[59, 61, 63, 65, 67, 69]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
- [17:15:51] flight_69 (REG_21_2): t_cross=0.6201s, idx_cross=35/6, bracket_pair_indices=[29, 31, 33, 35, 37, 39], symmetric=True, span=199.8ms
    cam0: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
- [17:15:52] flight_11 (REG_21_1): t_cross=0.8707s, idx_cross=51/5, bracket_pair_indices=[45, 47, 49, 51, 53], symmetric=False, span=149.9ms
    cam0: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    cam1: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
- [17:15:53] flight_33 (REG_15): t_cross=1.1186s, idx_cross=64/6, bracket_pair_indices=[58, 60, 62, 64, 66, 68], symmetric=True, span=199.8ms
    cam0: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    cam1: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
- [17:15:54] flight_19 (REG_21_1): t_cross=0.8917s, idx_cross=54/6, bracket_pair_indices=[48, 50, 52, 54, 56, 58], symmetric=True, span=166.5ms
    cam0: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    cam1: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
- [17:15:55] flight_73 (REG_21_2): t_cross=0.7479s, idx_cross=45/6, bracket_pair_indices=[39, 41, 43, 45, 47, 49], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
- [17:15:56] flight_119 (REG_21_2): t_cross=0.9844s, idx_cross=56/5, bracket_pair_indices=[50, 52, 54, 56, 58], symmetric=False, span=166.5ms
    cam0: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    cam1: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
- [17:15:56] flight_15 (REG_21_1): t_cross=0.6631s, idx_cross=40/6, bracket_pair_indices=[34, 36, 38, 40, 42, 44], symmetric=True, span=166.5ms
    cam0: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    cam1: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
- [17:15:57] flight_118 (REG_21_2): t_cross=1.0810s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:15:59] flight_22 (REG_15): t_cross=1.4028s, idx_cross=82/6, bracket_pair_indices=[76, 78, 80, 82, 84, 86], symmetric=True, span=216.5ms
    cam0: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    cam1: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
- [17:16:00] flight_14 (REG_15): t_cross=1.2773s, idx_cross=73/6, bracket_pair_indices=[67, 69, 71, 73, 75, 77], symmetric=True, span=216.5ms
    cam0: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    cam1: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
- [17:16:01] flight_56 (REG_21_1): t_cross=1.2517s, idx_cross=75/6, bracket_pair_indices=[69, 71, 73, 75, 77, 79], symmetric=True, span=166.5ms
    cam0: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    cam1: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
- [17:16:02] flight_12 (REG_15): t_cross=1.3838s, idx_cross=77/6, bracket_pair_indices=[71, 73, 75, 77, 79, 81], symmetric=True, span=199.8ms
    cam0: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    cam1: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
- [17:16:03] flight_107 (REG_21_2): t_cross=1.2554s, idx_cross=73/4, bracket_pair_indices=[67, 69, 71, 73], symmetric=False, span=99.9ms
    cam0: frames=[119, 121, 123, 125]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    cam1: frames=[120, 122, 124, 126]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']

## Crossing-bracket labelling
- [17:16:23] IMPORTANT: 01_'s crossing_classification.csv did not persist a crossing time/frame -- reusing classify_flight() (same frozen fit, same seed/pooled_k) for just these 20 flights to recover t_cross, per the prompt's own explicit fallback. Not touching 01_'s CSV or re-running its 163-flight batch. Labels themselves remain pure manual clicks.
- [17:16:23] Loaded 20 candidate flights from ranked_candidates_v2.csv.
- [17:16:24] flight_109 (REG_21_2): t_cross=1.0809s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:16:25] flight_87 (REG_21_2): t_cross=0.5476s, idx_cross=33/6, bracket_pair_indices=[27, 29, 31, 33, 35, 37], symmetric=True, span=199.8ms
    cam0: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
    cam1: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
- [17:16:25] flight_13 (REG_21_1): t_cross=0.6552s, idx_cross=39/6, bracket_pair_indices=[33, 35, 37, 39, 41, 43], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    cam1: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
- [17:16:26] flight_75 (REG_21_2): t_cross=0.6402s, idx_cross=38/6, bracket_pair_indices=[32, 34, 36, 38, 40, 42], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    cam1: frames=[78, 80, 82, 84, 86, 88]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
- [17:16:27] flight_88 (REG_21_2): t_cross=0.6127s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
- [17:16:28] flight_6 (REG_21_1): t_cross=0.5916s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
- [17:16:28] flight_53 (REG_15): t_cross=0.5823s, idx_cross=34/6, bracket_pair_indices=[28, 30, 32, 34, 36, 38], symmetric=True, span=166.5ms
    cam0: frames=[58, 60, 62, 64, 66, 68]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
    cam1: frames=[59, 61, 63, 65, 67, 69]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
- [17:16:29] flight_69 (REG_21_2): t_cross=0.6201s, idx_cross=35/6, bracket_pair_indices=[29, 31, 33, 35, 37, 39], symmetric=True, span=199.8ms
    cam0: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
- [17:16:30] flight_11 (REG_21_1): t_cross=0.8707s, idx_cross=51/5, bracket_pair_indices=[45, 47, 49, 51, 53], symmetric=False, span=149.9ms
    cam0: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    cam1: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
- [17:16:31] flight_33 (REG_15): t_cross=1.1186s, idx_cross=64/6, bracket_pair_indices=[58, 60, 62, 64, 66, 68], symmetric=True, span=199.8ms
    cam0: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    cam1: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
- [17:16:32] flight_19 (REG_21_1): t_cross=0.8917s, idx_cross=54/6, bracket_pair_indices=[48, 50, 52, 54, 56, 58], symmetric=True, span=166.5ms
    cam0: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    cam1: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
- [17:16:33] flight_73 (REG_21_2): t_cross=0.7479s, idx_cross=45/6, bracket_pair_indices=[39, 41, 43, 45, 47, 49], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
- [17:16:34] flight_119 (REG_21_2): t_cross=0.9844s, idx_cross=56/5, bracket_pair_indices=[50, 52, 54, 56, 58], symmetric=False, span=166.5ms
    cam0: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    cam1: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
- [17:16:35] flight_15 (REG_21_1): t_cross=0.6631s, idx_cross=40/6, bracket_pair_indices=[34, 36, 38, 40, 42, 44], symmetric=True, span=166.5ms
    cam0: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    cam1: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
- [17:16:36] flight_118 (REG_21_2): t_cross=1.0810s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:16:38] flight_22 (REG_15): t_cross=1.4028s, idx_cross=82/6, bracket_pair_indices=[76, 78, 80, 82, 84, 86], symmetric=True, span=216.5ms
    cam0: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    cam1: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
- [17:16:39] flight_14 (REG_15): t_cross=1.2773s, idx_cross=73/6, bracket_pair_indices=[67, 69, 71, 73, 75, 77], symmetric=True, span=216.5ms
    cam0: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    cam1: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
- [17:16:40] flight_56 (REG_21_1): t_cross=1.2517s, idx_cross=75/6, bracket_pair_indices=[69, 71, 73, 75, 77, 79], symmetric=True, span=166.5ms
    cam0: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    cam1: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
- [17:16:42] flight_12 (REG_15): t_cross=1.3838s, idx_cross=77/6, bracket_pair_indices=[71, 73, 75, 77, 79, 81], symmetric=True, span=199.8ms
    cam0: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    cam1: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
- [17:16:43] flight_107 (REG_21_2): t_cross=1.2554s, idx_cross=73/4, bracket_pair_indices=[67, 69, 71, 73], symmetric=False, span=99.9ms
    cam0: frames=[119, 121, 123, 125]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    cam1: frames=[120, 122, 124, 126]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
- [17:16:43] Built 232 label targets (20 flights x 2 cams x up to 6 frames = 240 max).
- [17:16:43] FLAGGED FOR REVIEW (3): flight_11 (asymmetric bracket (5 frames, not full 6)); flight_119 (asymmetric bracket (5 frames, not full 6)); flight_107 (asymmetric bracket (4 frames, not full 6))
- [17:20:47] Quit. 1/232 points labelled overall.
- [17:20:47] Session end: 1/232 points labelled. Manifest written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\03_crossing_labels\labelling_manifest.csv

## Crossing-bracket labelling
- [17:22:54] IMPORTANT: 01_'s crossing_classification.csv did not persist a crossing time/frame -- reusing classify_flight() (same frozen fit, same seed/pooled_k) for just these 20 flights to recover t_cross, per the prompt's own explicit fallback. Not touching 01_'s CSV or re-running its 163-flight batch. Labels themselves remain pure manual clicks.
- [17:22:54] Loaded 20 candidate flights from ranked_candidates_v2.csv.
- [17:22:55] flight_109 (REG_21_2): t_cross=1.0809s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:22:56] flight_87 (REG_21_2): t_cross=0.5476s, idx_cross=33/6, bracket_pair_indices=[27, 29, 31, 33, 35, 37], symmetric=True, span=199.8ms
    cam0: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
    cam1: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
- [17:22:56] flight_13 (REG_21_1): t_cross=0.6552s, idx_cross=39/6, bracket_pair_indices=[33, 35, 37, 39, 41, 43], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    cam1: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
- [17:22:57] flight_75 (REG_21_2): t_cross=0.6402s, idx_cross=38/6, bracket_pair_indices=[32, 34, 36, 38, 40, 42], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    cam1: frames=[78, 80, 82, 84, 86, 88]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
- [17:22:58] flight_88 (REG_21_2): t_cross=0.6127s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
- [17:22:58] flight_6 (REG_21_1): t_cross=0.5916s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
- [17:22:59] flight_53 (REG_15): t_cross=0.5823s, idx_cross=34/6, bracket_pair_indices=[28, 30, 32, 34, 36, 38], symmetric=True, span=166.5ms
    cam0: frames=[58, 60, 62, 64, 66, 68]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
    cam1: frames=[59, 61, 63, 65, 67, 69]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
- [17:22:59] flight_69 (REG_21_2): t_cross=0.6201s, idx_cross=35/6, bracket_pair_indices=[29, 31, 33, 35, 37, 39], symmetric=True, span=199.8ms
    cam0: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
- [17:23:00] flight_11 (REG_21_1): t_cross=0.8707s, idx_cross=51/5, bracket_pair_indices=[45, 47, 49, 51, 53], symmetric=False, span=149.9ms
    cam0: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    cam1: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
- [17:23:01] flight_33 (REG_15): t_cross=1.1186s, idx_cross=64/6, bracket_pair_indices=[58, 60, 62, 64, 66, 68], symmetric=True, span=199.8ms
    cam0: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    cam1: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
- [17:23:02] flight_19 (REG_21_1): t_cross=0.8917s, idx_cross=54/6, bracket_pair_indices=[48, 50, 52, 54, 56, 58], symmetric=True, span=166.5ms
    cam0: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    cam1: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
- [17:23:02] flight_73 (REG_21_2): t_cross=0.7479s, idx_cross=45/6, bracket_pair_indices=[39, 41, 43, 45, 47, 49], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
- [17:23:03] flight_119 (REG_21_2): t_cross=0.9844s, idx_cross=56/5, bracket_pair_indices=[50, 52, 54, 56, 58], symmetric=False, span=166.5ms
    cam0: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    cam1: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
- [17:23:04] flight_15 (REG_21_1): t_cross=0.6631s, idx_cross=40/6, bracket_pair_indices=[34, 36, 38, 40, 42, 44], symmetric=True, span=166.5ms
    cam0: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    cam1: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
- [17:23:04] flight_118 (REG_21_2): t_cross=1.0810s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [17:23:05] flight_22 (REG_15): t_cross=1.4028s, idx_cross=82/6, bracket_pair_indices=[76, 78, 80, 82, 84, 86], symmetric=True, span=216.5ms
    cam0: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    cam1: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
- [17:23:06] flight_14 (REG_15): t_cross=1.2773s, idx_cross=73/6, bracket_pair_indices=[67, 69, 71, 73, 75, 77], symmetric=True, span=216.5ms
    cam0: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    cam1: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
- [17:23:07] flight_56 (REG_21_1): t_cross=1.2517s, idx_cross=75/6, bracket_pair_indices=[69, 71, 73, 75, 77, 79], symmetric=True, span=166.5ms
    cam0: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    cam1: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
- [17:23:08] flight_12 (REG_15): t_cross=1.3838s, idx_cross=77/6, bracket_pair_indices=[71, 73, 75, 77, 79, 81], symmetric=True, span=199.8ms
    cam0: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    cam1: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
- [17:23:09] flight_107 (REG_21_2): t_cross=1.2554s, idx_cross=73/4, bracket_pair_indices=[67, 69, 71, 73], symmetric=False, span=99.9ms
    cam0: frames=[119, 121, 123, 125]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    cam1: frames=[120, 122, 124, 126]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
- [17:23:09] Built 232 label targets (20 flights x 2 cams x up to 6 frames = 240 max).
- [17:23:09] FLAGGED FOR REVIEW (3): flight_11 (asymmetric bracket (5 frames, not full 6)); flight_119 (asymmetric bracket (5 frames, not full 6)); flight_107 (asymmetric bracket (4 frames, not full 6))
- [17:33:27] Finished flight flight_109 (moved on to flight_87).
- [17:38:34] Finished flight flight_87 (moved on to flight_13).
- [17:39:32] Finished flight flight_13 (moved on to flight_75).
- [17:41:26] Finished flight flight_75 (moved on to flight_88).
- [17:43:11] Finished flight flight_88 (moved on to flight_6).
- [17:44:11] Finished flight flight_6 (moved on to flight_53).
- [17:56:22] Finished flight flight_53 (moved on to flight_69).
- [17:57:33] Finished flight flight_69 (moved on to flight_11).
- [18:11:34] Finished flight flight_11 (moved on to flight_33).
- [18:19:18] Finished flight flight_33 (moved on to flight_19).
- [18:29:26] Finished flight flight_19 (moved on to flight_73).
- [18:30:44] Finished flight flight_73 (moved on to flight_119).
- [18:32:08] Finished flight flight_119 (moved on to flight_15).
- [18:33:54] Quit. 155/232 points labelled overall.
- [18:33:54] Session end: 155/232 points labelled. Manifest written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\03_crossing_labels\labelling_manifest.csv

- [17:55] Discussed with Chin Wei: bracket stride steps through the
  paired-detections list (frames with a valid correspondence-matched
  detection in both cams), not raw camera frame numbers -- confirmed
  intentional, not a bug (occasional bigger real-time gaps between
  "adjacent" bracket frames happen where the automated detector has a
  genuine gap nearby, e.g. flight_60's frames=[60,62,64,66,68,72] skips
  frame 70). Decided NOT to switch to raw-frame/nearest-time snapping --
  would need new stereo-correspondence logic without the existing
  outlier-filter safety net, and would orphan the 155 points already
  labelled under the current scheme for a modest rigor gain.
  REQUIREMENT FOR THE NEXT TASK (velocity-at-crossing from these labels):
  must fit position vs each point's actual frame_timestamp_ms (already
  recorded per row), NOT assume uniform/symmetric time spacing across the
  bracket -- a naive symmetric finite-difference (pos[+3]-pos[-3])/(t[+3]-t[-3])
  would reintroduce the acceleration bias the symmetric bracket was meant
  to cancel, wherever a real gap sits unevenly on one side. Position-at-
  crossing is unaffected either way (direct triangulation of the
  crossing-frame label, independent of bracket spacing).
- [17:56] Resuming labelling from flight_15 (3/12 done).

## Crossing-bracket labelling
- [18:51:19] IMPORTANT: 01_'s crossing_classification.csv did not persist a crossing time/frame -- reusing classify_flight() (same frozen fit, same seed/pooled_k) for just these 20 flights to recover t_cross, per the prompt's own explicit fallback. Not touching 01_'s CSV or re-running its 163-flight batch. Labels themselves remain pure manual clicks.
- [18:51:19] Loaded 20 candidate flights from ranked_candidates_v2.csv.
- [18:51:20] flight_109 (REG_21_2): t_cross=1.0809s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[110, 112, 114, 116, 118, 120]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [18:51:21] flight_87 (REG_21_2): t_cross=0.5476s, idx_cross=33/6, bracket_pair_indices=[27, 29, 31, 33, 35, 37], symmetric=True, span=199.8ms
    cam0: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
    cam1: frames=[60, 62, 64, 66, 68, 72]  timestamps_ms=['449.6', '482.9', '516.2', '549.5', '582.8', '649.4']
- [18:51:21] flight_13 (REG_21_1): t_cross=0.6552s, idx_cross=39/6, bracket_pair_indices=[33, 35, 37, 39, 41, 43], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
    cam1: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['549.5', '582.8', '616.1', '649.4', '682.7', '716.0']
- [18:51:22] flight_75 (REG_21_2): t_cross=0.6402s, idx_cross=38/6, bracket_pair_indices=[32, 34, 36, 38, 40, 42], symmetric=True, span=166.5ms
    cam0: frames=[79, 81, 83, 85, 87, 89]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
    cam1: frames=[78, 80, 82, 84, 86, 88]  timestamps_ms=['532.8', '566.1', '599.4', '632.7', '666.0', '699.3']
- [18:51:22] flight_88 (REG_21_2): t_cross=0.6127s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[77, 79, 81, 83, 85, 87]  timestamps_ms=['516.2', '549.5', '582.8', '616.1', '649.4', '682.7']
- [18:51:23] flight_6 (REG_21_1): t_cross=0.5916s, idx_cross=36/6, bracket_pair_indices=[30, 32, 34, 36, 38, 40], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['499.6', '532.9', '566.2', '599.5', '632.8', '666.1']
- [18:51:23] flight_53 (REG_15): t_cross=0.5823s, idx_cross=34/6, bracket_pair_indices=[28, 30, 32, 34, 36, 38], symmetric=True, span=166.5ms
    cam0: frames=[58, 60, 62, 64, 66, 68]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
    cam1: frames=[59, 61, 63, 65, 67, 69]  timestamps_ms=['482.9', '516.2', '549.5', '582.8', '616.1', '649.4']
- [18:51:24] flight_69 (REG_21_2): t_cross=0.6201s, idx_cross=35/6, bracket_pair_indices=[29, 31, 33, 35, 37, 39], symmetric=True, span=199.8ms
    cam0: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
    cam1: frames=[75, 77, 81, 83, 85, 87]  timestamps_ms=['482.9', '516.2', '582.8', '616.1', '649.4', '682.7']
- [18:51:25] flight_11 (REG_21_1): t_cross=0.8707s, idx_cross=51/5, bracket_pair_indices=[45, 47, 49, 51, 53], symmetric=False, span=149.9ms
    cam0: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
    cam1: frames=[81, 83, 86, 88, 90]  timestamps_ms=['749.3', '782.6', '832.6', '865.9', '899.2']
- [18:51:26] flight_33 (REG_15): t_cross=1.1186s, idx_cross=64/6, bracket_pair_indices=[58, 60, 62, 64, 66, 68], symmetric=True, span=199.8ms
    cam0: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
    cam1: frames=[91, 93, 97, 99, 101, 103]  timestamps_ms=['982.5', '1015.8', '1082.4', '1115.7', '1149.0', '1182.3']
- [18:51:26] flight_19 (REG_21_1): t_cross=0.8917s, idx_cross=54/6, bracket_pair_indices=[48, 50, 52, 54, 56, 58], symmetric=True, span=166.5ms
    cam0: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
    cam1: frames=[112, 114, 116, 118, 120, 122]  timestamps_ms=['799.3', '832.6', '865.9', '899.2', '932.5', '965.8']
- [18:51:27] flight_73 (REG_21_2): t_cross=0.7479s, idx_cross=45/6, bracket_pair_indices=[39, 41, 43, 45, 47, 49], symmetric=True, span=166.5ms
    cam0: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
    cam1: frames=[85, 87, 89, 91, 93, 95]  timestamps_ms=['649.4', '682.7', '716.0', '749.3', '782.6', '815.9']
- [18:51:28] flight_119 (REG_21_2): t_cross=0.9844s, idx_cross=56/5, bracket_pair_indices=[50, 52, 54, 56, 58], symmetric=False, span=166.5ms
    cam0: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
    cam1: frames=[108, 110, 114, 116, 118]  timestamps_ms=['849.3', '882.6', '949.2', '982.5', '1015.8']
- [18:51:28] flight_15 (REG_21_1): t_cross=0.6631s, idx_cross=40/6, bracket_pair_indices=[34, 36, 38, 40, 42, 44], symmetric=True, span=166.5ms
    cam0: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
    cam1: frames=[97, 99, 101, 103, 105, 107]  timestamps_ms=['566.2', '599.5', '632.8', '666.1', '699.4', '732.7']
- [18:51:29] flight_118 (REG_21_2): t_cross=1.0810s, idx_cross=65/6, bracket_pair_indices=[59, 61, 63, 65, 67, 69], symmetric=True, span=166.5ms
    cam0: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
    cam1: frames=[125, 127, 129, 131, 133, 135]  timestamps_ms=['982.5', '1015.8', '1049.1', '1082.4', '1115.7', '1149.0']
- [18:51:30] flight_22 (REG_15): t_cross=1.4028s, idx_cross=82/6, bracket_pair_indices=[76, 78, 80, 82, 84, 86], symmetric=True, span=216.5ms
    cam0: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
    cam1: frames=[79, 82, 84, 86, 88, 92]  timestamps_ms=['1282.2', '1332.2', '1365.5', '1398.8', '1432.1', '1498.7']
- [18:51:31] flight_14 (REG_15): t_cross=1.2773s, idx_cross=73/6, bracket_pair_indices=[67, 69, 71, 73, 75, 77], symmetric=True, span=216.5ms
    cam0: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
    cam1: frames=[113, 115, 118, 120, 124, 126]  timestamps_ms=['1165.6', '1198.9', '1248.9', '1282.2', '1348.8', '1382.1']
- [18:51:32] flight_56 (REG_21_1): t_cross=1.2517s, idx_cross=75/6, bracket_pair_indices=[69, 71, 73, 75, 77, 79], symmetric=True, span=166.5ms
    cam0: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
    cam1: frames=[109, 111, 113, 115, 117, 119]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9', '1282.2', '1315.5']
- [18:51:33] flight_12 (REG_15): t_cross=1.3838s, idx_cross=77/6, bracket_pair_indices=[71, 73, 75, 77, 79, 81], symmetric=True, span=199.8ms
    cam0: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
    cam1: frames=[107, 109, 113, 115, 117, 119]  timestamps_ms=['1248.9', '1282.2', '1348.8', '1382.1', '1415.4', '1448.7']
- [18:51:34] flight_107 (REG_21_2): t_cross=1.2554s, idx_cross=73/4, bracket_pair_indices=[67, 69, 71, 73], symmetric=False, span=99.9ms
    cam0: frames=[119, 121, 123, 125]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
    cam1: frames=[120, 122, 124, 126]  timestamps_ms=['1149.0', '1182.3', '1215.6', '1248.9']
- [18:51:34] Built 232 label targets (20 flights x 2 cams x up to 6 frames = 240 max).
- [18:51:34] FLAGGED FOR REVIEW (3): flight_11 (asymmetric bracket (5 frames, not full 6)); flight_119 (asymmetric bracket (5 frames, not full 6)); flight_107 (asymmetric bracket (4 frames, not full 6))
- [18:57:33] Finished flight flight_15 (moved on to flight_118).
- [18:59:11] Finished flight flight_118 (moved on to flight_22).
- [19:00:48] Finished flight flight_22 (moved on to flight_14).
- [19:02:29] Finished flight flight_14 (moved on to flight_56).
- [19:07:27] Finished flight flight_56 (moved on to flight_12).
- [19:08:45] Finished flight flight_12 (moved on to flight_107).
- [19:09:26] Quit. 232/232 points labelled overall.
- [19:09:26] Session end: 232/232 points labelled. Manifest written to C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\prediction\03_crossing_labels\labelling_manifest.csv
- [18:xx] Labelling COMPLETE. 232/232 targets labelled across all 20 flights
  (17 at full 12/12; flight_11 and flight_119 at their reduced 10/10
  symmetric-as-possible bracket; flight_107 at 8/8). crossing_labels.csv
  and labelling_manifest.csv both final. Next task (out of scope here):
  triangulate the labelled 2D points per flight/cam, fit local
  position+velocity at the crossing frame using each point's actual
  frame_timestamp_ms (not assumed uniform spacing -- see note above), and
  compare against the Model-C fit's own crossing_Y/crossing_Z/crossing_vel_xyz
  from crossing_classification.csv.
