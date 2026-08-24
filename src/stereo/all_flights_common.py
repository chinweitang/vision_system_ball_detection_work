# all_flights_common.py
# Shared flight-enumeration / session-config / corrected-pairing utilities
# for the all-163-flight generalization of the gravity-vs-drag comparison.
# See claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Reuses (does not re-derive): label_vs_detection.load_calib/triangulate,
# pixel_velocity_correction.build_corrected_pairs, trajectory_fit.G_MAGNITUDE_MM_S2.

import csv
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.label_vs_detection import load_calib, triangulate  # noqa: E402
from src.stereo.pixel_velocity_correction import build_corrected_pairs  # noqa: E402
from src.stereo.trajectory_fit import G_MAGNITUDE_MM_S2  # noqa: E402

CALIB_DIR = REPO_ROOT / "calibration_outputs"
DETECTIONS_ROOT = (REPO_ROOT / "results" / "detector_tuning" / "detections" /
                    "03_stride1_thresh16_openk3_area30_circ0.3")
FINAL_POINT_LABELS_CSV = REPO_ROOT / "results" / "final_point_labels" / "final_point_labels.csv"

SESSIONS = {
    "2026_07_21_gym": dict(
        extrinsics_path=REPO_ROOT / "calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz",
        detections_dir=DETECTIONS_ROOT / "2026_07_21_gym",
        ball_flights_dir=REPO_ROOT / "data/2026_07_21_gym/ball_flights",
        world_frame_dir=REPO_ROOT / "data/2026_07_21_gym/flight_binning/world_frame_validation",
        registrations=["registration1", "registration2"],
    ),
    "2026_07_15_gym": dict(
        extrinsics_path=REPO_ROOT / "calibration_outputs/2026_07_15/stereo_extrinsic.npz",
        detections_dir=DETECTIONS_ROOT / "2026_07_15_gym",
        ball_flights_dir=REPO_ROOT / "data/2026_07_15_gym/ball_flights",
        world_frame_dir=REPO_ROOT / "data/2026_07_15_gym/flight_binning/world_frame_validation",
        registrations=["registration"],
    ),
}
REGISTRATION1_MAX_FLIGHT = 60  # 2026_07_21_gym only: flights <=60 -> registration1, >60 -> registration2


def _sort_key(flight_id: str):
    m = re.search(r"(\d+)$", flight_id)
    return int(m.group(1)) if m else flight_id


def find_flight_ids(detections_dir: Path) -> list:
    """Flight ids present as BOTH cam0 and cam1 tuned-detector CSVs."""
    cam0_ids = {p.name[:-len("_cam0_detections.csv")] for p in detections_dir.glob("*_cam0_detections.csv")}
    cam1_ids = {p.name[:-len("_cam1_detections.csv")] for p in detections_dir.glob("*_cam1_detections.csv")}
    return sorted(cam0_ids & cam1_ids, key=_sort_key)


def enumerate_eligible_flights() -> list:
    """[(session, flight_id), ...] across both sessions."""
    out = []
    for session, cfg in SESSIONS.items():
        for fid in find_flight_ids(cfg["detections_dir"]):
            out.append((session, fid))
    return out


def registration_for(session: str, flight_id: str) -> str:
    if session == "2026_07_21_gym":
        n = int(re.search(r"(\d+)$", flight_id).group(1))
        return "registration1" if n <= REGISTRATION1_MAX_FLIGHT else "registration2"
    return "registration"


def g_fixed_for(session: str, flight_id: str) -> np.ndarray:
    """g_fixed = 9810 * (-up_vec), mm/s^2, from the session/registration's
    already-validated world-frame transform (same math as
    trajectory_fit.load_g_fixed, generalized to per-session/registration
    npz files instead of one hardcoded path)."""
    cfg = SESSIONS[session]
    reg = registration_for(session, flight_id)
    npz_path = cfg["world_frame_dir"] / f"{reg}_world_transform.npz"
    data = np.load(npz_path)
    up_vec = data["up_vec"] if "up_vec" in data.files else data["Z_world"]
    up_vec = up_vec.astype(np.float64)
    up_vec = up_vec / np.linalg.norm(up_vec)
    return G_MAGNITUDE_MM_S2 * (-up_vec)


def world_axes_for(session: str, flight_id: str):
    """(X_world, Y_world, Z_world) unit vectors in camera frame, from the
    session/registration's already-validated world-frame transform --
    X_world = person->rebounder (STRONG), Y_world = width (WEAK, the axis
    the +-100mm spec applies to), Z_world = up (STRONG). Per
    world_frame_validate_2026_07_15.py (the script that built these npz
    files), a camera-frame residual vector's world components are plain
    dot products: resid @ X_world / resid @ Y_world / resid @ Z_world --
    no matrix build needed. Reuses registration_for()'s exact existing
    selection logic (same npz g_fixed_for() reads), not rebuilt."""
    cfg = SESSIONS[session]
    reg = registration_for(session, flight_id)
    npz_path = cfg["world_frame_dir"] / f"{reg}_world_transform.npz"
    data = np.load(npz_path)
    X_world = data["X_world"].astype(np.float64)
    Y_world = data["Y_world"].astype(np.float64)
    Z_world = data["Z_world"].astype(np.float64)
    return X_world, Y_world, Z_world


def find_flight_dir(session: str, flight_id: str):
    """Resolves a flight's directory (containing timestamps.csv), searching
    recursively -- flight_01/flight_22 in 2026_07_15_gym live in
    non-standard nested locations, unlike every other flight in either
    session (direct child of ball_flights/)."""
    base = SESSIONS[session]["ball_flights_dir"]
    direct = base / flight_id
    if (direct / "timestamps.csv").is_file():
        return direct
    for cand in base.rglob(flight_id):
        if cand.is_dir() and (cand / "timestamps.csv").is_file():
            return cand
    return None


def load_session_calib(session: str):
    cfg = SESSIONS[session]
    K0, D0, K1, D1, R, T = load_calib(CALIB_DIR, cfg["extrinsics_path"])
    P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = np.hstack([R, T.reshape(3, 1)])
    return K0, D0, K1, D1, P0, P1


def build_corrected_track(session: str, flight_id: str, K0, D0, K1, D1, P0, P1, min_pairs=8):
    """Decision #3: build_corrected_pairs() (filter -> nearest-timestamp
    pairing -> sub-frame correction) BEFORE triangulate(), so early-window
    fitting data is prepared the same way the final-point target is.
    Returns (frame_labels, t_sec, xyz) or None if unavailable/too few pairs."""
    flight_dir = find_flight_dir(session, flight_id)
    if flight_dir is None:
        return None
    ts_csv = flight_dir / "timestamps.csv"
    cfg = SESSIONS[session]
    cam0_csv = cfg["detections_dir"] / f"{flight_id}_cam0_detections.csv"
    cam1_csv = cfg["detections_dir"] / f"{flight_id}_cam1_detections.csv"
    if not (cam0_csv.is_file() and cam1_csv.is_file()):
        return None

    pairs = build_corrected_pairs(cam0_csv, cam1_csv, ts_csv)
    if len(pairs) < min_pairs:
        return None

    # Sort by AVERAGED (cam0,cam1) timestamp, not raw cam0 t0_ns -- a pair's
    # two timestamps aren't identical (that's the whole reason for sub-frame
    # correction), so sorting/anchoring on cam0's own t0_ns can leave the
    # averaged-time sequence non-monotonic or (at the anchor point)
    # negative, and simulate_drag's solve_ivp requires t_eval within
    # [0, max(t)] and implicitly sorted -- caught via a real
    # fit_drag_given_k failure on flight_01 ("Values in t_eval are not
    # within t_span") before trusting any Phase 1 result -- see worklog.
    pairs = sorted(pairs, key=lambda p: (p["t0_ns"] + p["t1_ns"]) / 2.0)
    uv0 = np.array([(p["u0_corr"], p["v0_corr"]) for p in pairs])
    uv1 = np.array([(p["u1_corr"], p["v1_corr"]) for p in pairs])
    xyz = triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)

    t_avg = np.array([(p["t0_ns"] + p["t1_ns"]) / 2.0 for p in pairs])
    t_sec = (t_avg - t_avg[0]) / 1e9
    frame_labels = [p["cam0_frame"] for p in pairs]
    t_anchor_ns = float(t_avg[0])
    return frame_labels, t_sec, xyz, t_anchor_ns


def load_final_point_targets() -> dict:
    """{(session, flight): {"cam0": (u,v,frame_number), "cam1": (u,v,frame_number)}}"""
    out = {}
    with open(FINAL_POINT_LABELS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if not row["centroid_x"] or not row["centroid_y"]:
                continue  # blank click (failed/skipped label) -- caller treats as missing
            key = (row["session"], row["flight"])
            out.setdefault(key, {})[row["cam"]] = (
                float(row["centroid_x"]), float(row["centroid_y"]), int(row["frame_number"]))
    return out
