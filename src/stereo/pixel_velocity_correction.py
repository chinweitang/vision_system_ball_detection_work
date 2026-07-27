#!/usr/bin/env python3
"""pixel_velocity_correction.py

Aligns cam0/cam1 ball-centroid detections to a common real instant before
triangulation. The stereo cameras are free-running (no hardware trigger -
see capture_flights_stereo.py's docstring), so naively pairing frame N of
cam0 with frame N of cam1 assumes simultaneity that doesn't actually hold -
there's a real sub-frame timing gap between them. Triangulating as if they
were simultaneous introduces error proportional to (ball pixel velocity) x
(the timing gap) - error-budget term C (claude/context.md SS4.6).

Pipeline, per flight:
  A. Per-camera trajectory-outlier filtering (detector_core.filter_trajectory_outliers)
     BEFORE anything else, so an artifact detection (e.g. a hand) never
     contaminates the velocity estimate used for correction.
  B. Nearest-timestamp pairing (bisect) between the two cameras' surviving
     detections, using real sensor_timestamp_ns - not frame-index equality.
  C. Sub-frame correction: for each pair, whichever frame has the EARLIER
     real timestamp gets its centroid shifted forward (by that pair's
     actual signed delta-t) along its own locally-estimated pixel velocity
     (finite difference between its nearest surviving neighbors in time -
     no smoothing/polyfit, since the gap being corrected is sub-frame,
     a few ms out of ~16.6 ms). The later frame is left unchanged - it's
     already at the target instant.

Design decisions (confirmed with the user, see
claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md):
  - Correct per-flight, not per-session (the per-session sync audit shows the
    offset drifts within a session, not just between sessions).
  - Correction direction is NOT a fixed "always correct camera X" rule - which
    camera leads flips sign mid-session, so it's decided per-pair from the
    actual signed delta-t.
"""
from pathlib import Path
import sys
import csv
import bisect

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DETECTOR_DIR = REPO_ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
for p in (str(DETECTOR_DIR), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import detector_core as dc  # noqa: E402
from stereo_flight_sync_table import load_timestamps  # noqa: E402


def load_detections3(csv_path):
    """*_detections3.csv -> {frame_number: (u, v)}."""
    dets = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            dets[int(row["frame_number"])] = (float(row["u"]), float(row["v"]))
    return dets


def _local_velocity_px_per_ms(frame, frames_sorted, idx_by_frame, pts, ts_by_frame):
    """Finite-difference velocity (px/ms) at `frame`, from its nearest
    surviving neighbors in time on either side. One-sided at the ends of a
    run. None if `frame` has no usable neighbor (isolated single point)."""
    idx = idx_by_frame[frame]
    prev_f = frames_sorted[idx - 1] if idx > 0 else None
    next_f = frames_sorted[idx + 1] if idx < len(frames_sorted) - 1 else None

    def diff(fa, fb):
        dt_ms = (ts_by_frame[fb] - ts_by_frame[fa]) / 1e6
        if dt_ms == 0:
            return None
        return ((pts[fb][0] - pts[fa][0]) / dt_ms, (pts[fb][1] - pts[fa][1]) / dt_ms)

    if prev_f is not None and next_f is not None:
        return diff(prev_f, next_f)
    if next_f is not None:
        return diff(frame, next_f)
    if prev_f is not None:
        return diff(prev_f, frame)
    return None


DEFAULT_MAX_PAIR_GAP_MS = 8.5  # ~half the ~16.6ms (60fps) frame period. A
# genuine simultaneous cam0/cam1 correspondence should always be found
# within half a frame period of each other (the per-flight sync audit
# confirms measured raw offsets never exceed that - see
# 2026-07-25_pixel_velocity_sync_correction_worklog.md). A per-camera
# coverage gap (e.g. the trajectory filter dropping a run of frames on one
# side) means bisect's "nearest" match can still return something, but it's
# a stale point reused across several cam0 frames, genuinely far away in
# time - triangulating that as if simultaneous produces a garbage 3D point
# that dominates any downstream fit. Reject pairs wider than this instead
# of silently accepting them. (NOT the same threshold as
# stereo_flight_sync_table.py's DROP_GAP_FACTOR, which detects dropped
# frames within a single camera's own sequence - a different problem.)


def build_corrected_pairs(cam0_detections3_csv, cam1_detections3_csv, timestamps_csv,
                           max_speed_px_per_frame=80.0, min_run_length=2,
                           max_pair_gap_ms=DEFAULT_MAX_PAIR_GAP_MS):
    """Returns a list of per-pair dicts ready for triangulate_points():
    cam0_frame, cam1_frame, t0_ns, t1_ns, dt_ms (t0-t1),
    u0_raw/v0_raw/u1_raw/v1_raw, u0_corr/v0_corr/u1_corr/v1_corr, corrected
    (bool - False if no velocity neighbor was available). Pairs whose real
    timestamp gap exceeds `max_pair_gap_ms` are dropped, not corrected -
    see DEFAULT_MAX_PAIR_GAP_MS above."""
    raw0 = load_detections3(cam0_detections3_csv)
    raw1 = load_detections3(cam1_detections3_csv)

    # Step A
    kept0 = dc.filter_trajectory_outliers(raw0, max_speed_px_per_frame, min_run_length)
    kept1 = dc.filter_trajectory_outliers(raw1, max_speed_px_per_frame, min_run_length)

    cam0_entries, cam1_entries = load_timestamps(timestamps_csv)
    ts0 = {f: t for f, t in cam0_entries}
    ts1 = {f: t for f, t in cam1_entries}

    frames0_sorted = sorted(kept0, key=lambda f: ts0[f])
    frames1_sorted = sorted(kept1, key=lambda f: ts1[f])
    idx0_by_frame = {f: i for i, f in enumerate(frames0_sorted)}
    idx1_by_frame = {f: i for i, f in enumerate(frames1_sorted)}
    times1_sorted = [ts1[f] for f in frames1_sorted]

    pairs = []
    for f0 in frames0_sorted:
        t0 = ts0[f0]

        # Step B: nearest cam1 kept frame by real timestamp
        idx = bisect.bisect_left(times1_sorted, t0)
        cands = [i for i in (idx - 1, idx) if 0 <= i < len(times1_sorted)]
        if not cands:
            continue
        best_i = min(cands, key=lambda i: abs(times1_sorted[i] - t0))
        f1 = frames1_sorted[best_i]
        t1 = ts1[f1]

        if abs(t0 - t1) / 1e6 > max_pair_gap_ms:
            continue

        u0, v0 = kept0[f0]
        u1, v1 = kept1[f1]
        u0c, v0c, u1c, v1c = u0, v0, u1, v1
        corrected = False

        # Step C: shift whichever timestamp is earlier forward to the later one
        if t0 != t1:
            if t0 < t1:
                vel = _local_velocity_px_per_ms(f0, frames0_sorted, idx0_by_frame, kept0, ts0)
                shift_ms = (t1 - t0) / 1e6
                if vel is not None:
                    u0c, v0c = u0 + vel[0] * shift_ms, v0 + vel[1] * shift_ms
                    corrected = True
            else:
                vel = _local_velocity_px_per_ms(f1, frames1_sorted, idx1_by_frame, kept1, ts1)
                shift_ms = (t0 - t1) / 1e6
                if vel is not None:
                    u1c, v1c = u1 + vel[0] * shift_ms, v1 + vel[1] * shift_ms
                    corrected = True

        pairs.append({
            "cam0_frame": f0, "cam1_frame": f1,
            "t0_ns": t0, "t1_ns": t1, "dt_ms": (t0 - t1) / 1e6,
            "u0_raw": u0, "v0_raw": v0, "u1_raw": u1, "v1_raw": v1,
            "u0_corr": u0c, "v0_corr": v0c, "u1_corr": u1c, "v1_corr": v1c,
            "corrected": corrected,
        })
    return pairs
