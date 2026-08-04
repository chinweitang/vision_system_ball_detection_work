# crossing_plane_classification.py
#
# claude/prompts/2026-08-04_1240_crossing_plane_setup.md, executed per the
# implementation plan claude/prompts/2026-08-04_1347_crossing_plane_setup_plan.md.
#
# Triangulates the manually-labelled rebounder-plane tape endpoints (3
# registrations), defines a vertical crossing plane + 2x2m aperture per
# registration, fits Model C (frozen) to each flight's FULL arc, and
# classifies every flight as HIT / MISS_HIGH_WIDE / MISS_SHORT against its
# own registration's plane.
#
# Key deviation from the prompt's literal geometry (agreed with Chin Wei
# during planning -- see the plan file above for the full rationale): no
# absolute floor/world origin exists anywhere in this codebase (X_world/
# Y_world/Z_world are pure directions; T_wc is saved but never consumed).
# So everything here is relative to the tape points themselves:
#   - the plane's "depth" is the tape points' mean position projected onto
#     X_world from the camera0 origin (not an absolute "5m from a wall")
#   - MISS_SHORT is decided by comparing each flight's OWN first/last
#     observed point depth to the plane depth (no floor-crossing search)
#   - the crossing point, once a flight is confirmed to reach the plane, is
#     found by bisection WITHIN the observed time range (interpolation, not
#     extrapolation), since "last point already reached the plane" implies
#     the crossing time is inside [0, t_last]
#
# Frozen, read-only: triangulate() / load_calib() (label_vs_detection.py),
# build_corrected_track() / g_fixed_for() / world axes (all_flights_common.py),
# build_model_fit_predict() / ransac_fit() / simulate_drag() (trajectory_fit.py).
# Not modified.

import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for,
    build_corrected_track, SESSIONS, registration_for,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

OUT_DIR = REPO_ROOT / "data" / "prediction" / "01_crossing_plane_setup"
LOG_PATH = REPO_ROOT / "claude" / "logs" / "2026-08-04_1347_crossing_plane_setup_worklog.md"
POOLED_K_TXT = REPO_ROOT / "data" / "trajectory_fit_comparison" / "all_flights" / "phase1" / "pooled_k.txt"
BINNING_CSV = REPO_ROOT / "data" / "flight_binning" / "flight_velocity_angle.csv"

WFV_15 = REPO_ROOT / "data/2026_07_15_gym/flight_binning/world_frame_validation"
WFV_21 = REPO_ROOT / "data/2026_07_21_gym/flight_binning/world_frame_validation"

TAPE_REGISTRATIONS = {
    "REG_15": dict(session="2026_07_15_gym", registration="registration",
                    cam0=WFV_15 / "tape_cam0.csv", cam1=WFV_15 / "tape_cam1.csv"),
    "REG_21_1": dict(session="2026_07_21_gym", registration="registration1",
                       cam0=WFV_21 / "tape_registration1_cam0.csv", cam1=WFV_21 / "tape_registration1_cam1.csv"),
    "REG_21_2": dict(session="2026_07_21_gym", registration="registration2",
                       cam0=WFV_21 / "tape_registration2_cam0.csv", cam1=WFV_21 / "tape_registration2_cam1.csv"),
}
REG_KEY_FOR = {
    ("2026_07_15_gym", "registration"): "REG_15",
    ("2026_07_21_gym", "registration1"): "REG_21_1",
    ("2026_07_21_gym", "registration2"): "REG_21_2",
}

SEPARATION_EXPECT_MM = 700.0   # Chin Wei confirmed ~700mm clicked, not the tape's true ~1m
SEPARATION_TOL_MM = 200.0      # soft band around the observed value (diagnostic only)
AXIS_SELF_CHECK_TOL_DEG = 20.0
APERTURE_SIZE_MM = 2000.0
DURATION_FILTER_MS = 1200.0
N_CANDIDATES = 20
N_ELEVATION_BINS = 4


def log_append(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


# ---- Phase A: geometry ------------------------------------------------------

def load_clicks(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing tape label file: {path}")
    with open(path, newline="") as f:
        rows = {r["point_id"]: (float(r["u"]), float(r["v"])) for r in csv.DictReader(f)}
    if len(rows) != 2:
        raise SystemExit(f"{path}: expected exactly 2 labelled points, found {len(rows)}")
    return rows


def load_world_axes(session: str, registration: str):
    npz_path = SESSIONS[session]["world_frame_dir"] / f"{registration}_world_transform.npz"
    data = np.load(npz_path)
    return (data["X_world"].astype(np.float64), data["Y_world"].astype(np.float64),
            data["Z_world"].astype(np.float64))


def build_geometry(reg_key: str, cfg: dict) -> dict:
    session, registration = cfg["session"], cfg["registration"]
    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    R, T = P1[:, :3], P1[:, 3]
    baseline_midpoint = (-R.T @ T) / 2.0  # cam1 optical centre in cam0 frame, halved

    cam0_clicks = load_clicks(cfg["cam0"])
    cam1_clicks = load_clicks(cfg["cam1"])
    if set(cam0_clicks) != set(cam1_clicks):
        raise SystemExit(f"{reg_key}: cam0/cam1 point ids differ: {set(cam0_clicks)} vs {set(cam1_clicks)}")
    point_ids = list(cam0_clicks.keys())

    pts0 = np.array([cam0_clicks[pid] for pid in point_ids], dtype=np.float64)
    pts1 = np.array([cam1_clicks[pid] for pid in point_ids], dtype=np.float64)
    tri = triangulate(pts0, pts1, K0, D0, K1, D1, P0, P1)  # (2,3) mm, cam0 frame
    p_a, p_b = tri[0], tri[1]

    separation_mm = float(np.linalg.norm(p_a - p_b))
    sep_ok = abs(separation_mm - SEPARATION_EXPECT_MM) <= SEPARATION_TOL_MM

    X_world, Y_world, Z_world = load_world_axes(session, registration)
    z_a, z_b = float(np.dot(p_a, Z_world)), float(np.dot(p_b, Z_world))
    z_agreement_mm = abs(z_a - z_b)

    tape_dir = p_b - p_a
    tape_dir_unit = tape_dir / np.linalg.norm(tape_dir)
    angle_to_Y_deg = math.degrees(math.acos(np.clip(abs(float(np.dot(tape_dir_unit, Y_world))), -1.0, 1.0)))
    angle_to_X_deg = math.degrees(math.acos(np.clip(abs(float(np.dot(tape_dir_unit, X_world))), -1.0, 1.0)))
    axis_ok = angle_to_Y_deg <= AXIS_SELF_CHECK_TOL_DEG

    d_a = float(np.linalg.norm(p_a - baseline_midpoint))
    d_b = float(np.linalg.norm(p_b - baseline_midpoint))
    p_near, p_far = (p_a, p_b) if d_a < d_b else (p_b, p_a)

    u = p_near - p_far
    u = u / np.linalg.norm(u)
    up = Z_world / np.linalg.norm(Z_world)

    corner_A = p_far
    corner_B = p_far + APERTURE_SIZE_MM * u
    corner_C = corner_B + APERTURE_SIZE_MM * up
    corner_D = p_far + APERTURE_SIZE_MM * up

    plane_depth = float(np.dot((p_a + p_b) / 2.0, X_world))

    geo = dict(
        reg_key=reg_key, session=session, registration=registration,
        p_a=p_a, p_b=p_b, separation_mm=separation_mm, sep_ok=sep_ok,
        z_agreement_mm=z_agreement_mm, angle_to_Y_deg=angle_to_Y_deg,
        angle_to_X_deg=angle_to_X_deg, axis_ok=axis_ok,
        p_near=p_near, p_far=p_far, u=u, up=up, X_world=X_world,
        corner_A=corner_A, corner_B=corner_B, corner_C=corner_C, corner_D=corner_D,
        plane_depth=plane_depth,
    )

    def fmt(v):
        return f"({v[0]:.1f}, {v[1]:.1f}, {v[2]:.1f})"

    lines = [
        f"=== {reg_key} ({session} / {registration}) ===",
        f"  P_a = {fmt(p_a)} mm (cam0 frame)   P_b = {fmt(p_b)} mm",
        f"  separation = {separation_mm:.1f} mm  (expect ~{SEPARATION_EXPECT_MM:.0f} +-{SEPARATION_TOL_MM:.0f}, "
        f"{'OK' if sep_ok else '*** OUT OF BAND ***'})",
        f"  Z_world height agreement between endpoints = {z_agreement_mm:.1f} mm (adapted floor sanity check)",
        f"  tape-line angle to Y_world = {angle_to_Y_deg:.2f} deg (tol {AXIS_SELF_CHECK_TOL_DEG}, "
        f"{'OK' if axis_ok else '*** AXIS SELF-CHECK FAIL ***'})",
        f"  tape-line angle to X_world = {angle_to_X_deg:.2f} deg (diagnostic, expect close to 90)",
        f"  P_near = {fmt(p_near)}   P_far = {fmt(p_far)}",
        f"  u (P_far->P_near, camera frame) = {fmt(u)}",
        f"  up (Z_world) = {fmt(up)}",
        f"  aperture corner_A (=P_far) = {fmt(corner_A)}",
        f"  aperture corner_B (+2m along u) = {fmt(corner_B)}",
        f"  aperture corner_C (+2m up from B) = {fmt(corner_C)}",
        f"  aperture corner_D (+2m up from A) = {fmt(corner_D)}",
        f"  plane depth (mean tape pos . X_world) = {plane_depth:.1f} mm",
        "",
    ]
    for line in lines:
        print(line)
    log_append(line.strip()) if False else None  # bulk-logged by caller
    geo["report_lines"] = lines
    return geo


# ---- Phase B: per-flight classification -------------------------------------

def load_pooled_k() -> float:
    return float(POOLED_K_TXT.read_text().strip())


def load_binning() -> dict:
    """{(session, flight_id): row} preferring N_requested=30 status==ok, else N_requested=20 status==ok."""
    rows = {}
    with open(BINNING_CSV, newline="") as f:
        for r in csv.DictReader(f):
            key = (r["session"], r["flight_id"])
            rows.setdefault(key, {})[r["N_requested"]] = r
    out = {}
    for key, by_n in rows.items():
        row = by_n.get("30") if by_n.get("30", {}).get("status") == "ok" else None
        if row is None and by_n.get("20", {}).get("status") == "ok":
            row = by_n.get("20")
        out[key] = row  # may be None -- caller handles missing
    return out


def dist_to_box_edge(y: float, z: float, size: float = APERTURE_SIZE_MM) -> float:
    if 0.0 <= y <= size and 0.0 <= z <= size:
        return min(y, size - y, z, size - z)
    cy = min(max(y, 0.0), size)
    cz = min(max(z, 0.0), size)
    return math.hypot(y - cy, z - cz)


def classify_flight(session, flight_id, geo, K0, D0, K1, D1, P0, P1, pooled_k):
    track = build_corrected_track(session, flight_id, K0, D0, K1, D1, P0, P1)
    if track is None:
        return dict(status="skipped", reason="no corrected detector track")
    frames, t, xyz, t_anchor_ns = track
    if len(t) < RANSAC_MIN_SAMPLES["C"]:
        return dict(status="skipped", reason=f"only {len(t)} points, need >= {RANSAC_MIN_SAMPLES['C']}")

    g_fixed = g_fixed_for(session, flight_id)
    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)
    try:
        res = ransac_fit(t, xyz, fit_fn, predict_fn, min_samples=RANSAC_MIN_SAMPLES["C"],
                          inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                          n_iterations=RANSAC_N_ITERATIONS["C"], random_seed=RANSAC_SEED,
                          frame_numbers=frames)
    except RuntimeError as e:
        return dict(status="skipped", reason=f"ransac_fit failed: {e}")
    params = res["params"]

    X_world = geo["X_world"]
    depth_start = float(np.dot(xyz[0], X_world))
    depth_end = float(np.dot(xyz[-1], X_world))
    plane_depth = geo["plane_depth"]
    direction = np.sign(plane_depth - depth_start) or 1.0
    has_reached_plane = direction * (depth_end - plane_depth) >= 0

    duration_ms = float(t[-1] - t[0]) * 1000.0

    if not has_reached_plane:
        return dict(status="ok", cls="MISS_SHORT", duration_ms=duration_ms,
                     n_inliers=res["n_inliers"], n_points=len(t))

    # simulate_drag (frozen) integrates over (t0, max(t_array)) via solve_ivp;
    # a single t=0.0 evaluation makes that a zero-length interval, which
    # solve_ivp handles inconsistently (sol.y comes back as a list, not an
    # ndarray) -- not a frozen-code edit, work around it here: use p0
    # directly for the exact-zero case, and keep the bisection bracket's
    # lower end at a tiny epsilon instead of exactly 0.0.
    p0_fit = params[0]

    def depth_at(tt):
        if tt <= 0.0:
            return float(np.dot(p0_fit, X_world)) - plane_depth
        pos = predict_fn(params, np.array([tt]))[0]
        return float(np.dot(pos, X_world)) - plane_depth

    lo, hi = 1e-6, float(t[-1])
    f_lo, f_hi = depth_at(0.0), depth_at(hi)
    if np.sign(f_lo) == np.sign(f_hi) and f_lo != 0.0:
        # Shouldn't happen given has_reached_plane, but guard: fall back to hi.
        t_cross = hi
    elif f_lo == 0.0:
        t_cross = 0.0
    else:
        t_cross = brentq(depth_at, lo, hi, xtol=1e-6)

    def eval_pos(tt):
        if tt <= 0.0:
            return p0_fit
        return predict_fn(params, np.array([tt]))[0]

    crossing_pos = eval_pos(t_cross)
    dt = 1e-3
    t2 = t_cross + dt
    pos2 = eval_pos(t2)
    vel = (pos2 - crossing_pos) / dt
    speed = float(np.linalg.norm(vel))

    p_far, u, up = geo["p_far"], geo["u"], geo["up"]
    cy = float(np.dot(crossing_pos - p_far, u))
    cz = float(np.dot(crossing_pos - p_far, up))
    inside = (0.0 <= cy <= APERTURE_SIZE_MM) and (0.0 <= cz <= APERTURE_SIZE_MM)
    cls = "HIT" if inside else "MISS_HIGH_WIDE"

    return dict(status="ok", cls=cls, duration_ms=duration_ms, crossing_Y=cy, crossing_Z=cz,
                crossing_speed=speed, crossing_vel_xyz=vel.tolist(), t_cross=t_cross,
                n_inliers=res["n_inliers"], n_points=len(t), edge_dist=dist_to_box_edge(cy, cz))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_append("Phase A: building geometry for all 3 registrations.")

    geometries = {}
    for reg_key, cfg in TAPE_REGISTRATIONS.items():
        geo = build_geometry(reg_key, cfg)
        for line in geo["report_lines"]:
            log_append(line)
        if not geo["axis_ok"]:
            log_append(f"*** STOP: {reg_key} axis self-check failed "
                       f"({geo['angle_to_Y_deg']:.2f} deg > {AXIS_SELF_CHECK_TOL_DEG}) - "
                       f"tape line not lateral, crossing plane degenerate. ***")
            raise SystemExit(f"{reg_key}: axis self-check failed, stopping (see log).")
        geometries[reg_key] = geo

    geometry_report_path = OUT_DIR / "geometry_report.txt"
    with open(geometry_report_path, "w") as f:
        for geo in geometries.values():
            f.write("\n".join(geo["report_lines"]) + "\n")
    log_append(f"Geometry report written to {geometry_report_path}")

    pooled_k = load_pooled_k()
    log_append(f"Phase B: pooled_k={pooled_k:.6e}, classifying all eligible flights.")

    binning = load_binning()
    flights = enumerate_eligible_flights()
    log_append(f"{len(flights)} eligible flights found.")

    calib_cache = {}
    per_flight_rows = []
    skipped = []
    for session, flight_id in flights:
        if session not in calib_cache:
            calib_cache[session] = load_session_calib(session)
        K0, D0, K1, D1, P0, P1 = calib_cache[session]

        reg = registration_for(session, flight_id)
        reg_key = REG_KEY_FOR[(session, reg)]
        geo = geometries[reg_key]

        result = classify_flight(session, flight_id, geo, K0, D0, K1, D1, P0, P1, pooled_k)
        if result["status"] == "skipped":
            skipped.append((session, flight_id, result["reason"]))
            log_append(f"SKIP {session}/{flight_id}: {result['reason']}")
            continue

        bin_row = binning.get((session, flight_id))
        elevation_deg = float(bin_row["elevation_deg"]) if bin_row else None
        speed_m_s = float(bin_row["speed_m_s"]) if bin_row else None
        flag_reason = bin_row["flag_reason"] if bin_row else ""

        row = dict(
            registration=reg_key, session=session, flight_id=flight_id, cls=result["cls"],
            crossing_Y=result.get("crossing_Y"), crossing_Z=result.get("crossing_Z"),
            crossing_speed=result.get("crossing_speed"),
            crossing_vel_xyz=result.get("crossing_vel_xyz"),
            duration_ms=result["duration_ms"], elevation_deg=elevation_deg, speed_m_s=speed_m_s,
            flag_reason=flag_reason, n_inliers=result["n_inliers"], n_points=result["n_points"],
            edge_dist=result.get("edge_dist"),
        )
        per_flight_rows.append(row)

    n_total = len(flights)
    n_skip_pct = 100.0 * len(skipped) / n_total if n_total else 0.0
    log_append(f"Classified {len(per_flight_rows)}/{n_total} flights, {len(skipped)} skipped ({n_skip_pct:.1f}%).")
    if n_skip_pct > 10.0:
        log_append("*** STOP: >10% of flights skipped, per prompt error-handling rule. ***")
        raise SystemExit(f">10% of flights skipped ({n_skip_pct:.1f}%), stopping (see log for reasons).")

    counts = {}
    for row in per_flight_rows:
        counts[row["cls"]] = counts.get(row["cls"], 0) + 1
    log_append(f"Classification summary: {counts}  (skipped={len(skipped)}, total={n_total})")

    csv_path = OUT_DIR / "crossing_classification.csv"
    fieldnames = ["registration", "session", "flight_id", "cls", "crossing_Y", "crossing_Z",
                  "crossing_speed", "crossing_vel_xyz", "duration_ms", "elevation_deg", "speed_m_s",
                  "flag_reason", "n_inliers", "n_points", "edge_dist"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in per_flight_rows:
            w.writerow(row)
    log_append(f"Per-flight CSV written to {csv_path}")

    skipped_path = OUT_DIR / "skipped_flights.csv"
    with open(skipped_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight_id", "reason"])
        w.writerows(skipped)
    log_append(f"Skipped-flights list written to {skipped_path}")

    return geometries, per_flight_rows, skipped


if __name__ == "__main__":
    main()
