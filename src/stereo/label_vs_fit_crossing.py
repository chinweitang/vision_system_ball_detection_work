# label_vs_fit_crossing.py
#
# claude/prompts/2026-08-04_1925_label_vs_fit_crossing.md. Validates
# Model-C's full-arc-fit crossing-plane state (position + velocity) against
# an INDEPENDENT local 3D quadratic fit through the manual crossing-bracket
# labels (data/prediction/03_crossing_labels/crossing_labels.csv), for the
# 20 labelled flights.
#
# NOT an absolute-truth check: labels are triangulated with the same frozen
# calibration Model-C uses, so both inherit any calibration/scale error
# identically. This validates the FIT + EXTRAPOLATION against an
# independent local sample of the same 3D points, nothing more.
#
# See the worklog (claude/claude_logs/2026-08-04_1925_label_vs_fit_crossing.md)
# for the full methodology-decision rationale (time origin, pairing,
# fit basis, reporting frames, t_cross definition, CI propagation).
#
# Frozen, read-only: label_vs_detection.triangulate/load_calib,
# all_flights_common.load_session_calib, crossing_plane_classification's
# build_geometry/classify_flight/load_pooled_k (all already frozen from
# earlier tasks this session). Not modified.

import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import load_session_calib  # noqa: E402
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.crossing_plane_classification import (  # noqa: E402
    build_geometry, load_pooled_k, classify_flight, TAPE_REGISTRATIONS, load_world_axes,
)

LABELS_CSV = REPO_ROOT / "data" / "prediction" / "03_crossing_labels" / "crossing_labels.csv"
CANDIDATES_CSV = REPO_ROOT / "data" / "prediction" / "02_candidate_reselection" / "ranked_candidates_v2.csv"
CLASSIFICATION_CSV = REPO_ROOT / "data" / "prediction" / "01_crossing_plane_setup" / "crossing_classification.csv"
OUT_DIR = REPO_ROOT / "data" / "prediction" / "06_label_vs_fit"
LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-04_1925_label_vs_fit_crossing.md"

ASYMMETRIC_FLIGHTS = {"flight_11", "flight_119", "flight_107"}
PAIR_TIMESTAMP_TOL_MS = 20.0  # ~1 raw-frame interval at 60fps (16.7ms) + margin
RESIDUAL_FLAG_FACTOR = 3.0    # flag a flight if its residual > this x the median


def log_append(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"{msg}\n")


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ---- loading ------------------------------------------------------------

def load_candidates() -> dict:
    """Keyed by flight_id alone -- SAFE here only because none of these
    20 selected flight_ids collide across sessions (checked: the 5
    REG_15 flight numbers [53,33,22,14,12] don't overlap the 15
    2026_07_21_gym flight numbers among these 20). Flight IDs are NOT
    globally unique across sessions in this dataset (both sessions have,
    e.g., a flight_13) -- see load_classification() below, which DOES hit
    that collision and must key by (session, flight_id)."""
    with open(CANDIDATES_CSV, newline="") as f:
        return {r["flight_id"]: r for r in csv.DictReader(f)}


def load_classification() -> dict:
    """Keyed by (session, flight_id) -- MUST be, not flight_id alone:
    flight_13 exists in BOTH 2026_07_15_gym (MISS_SHORT) and
    2026_07_21_gym (HIT, our actual candidate) in crossing_classification.csv.
    A flight_id-only dict silently picked whichever row came last in the
    file, causing a false 'does not reproduce 01_' STOP on first run --
    caught and fixed here, not a data problem."""
    with open(CLASSIFICATION_CSV, newline="") as f:
        return {(r["session"], r["flight_id"]): r for r in csv.DictReader(f)}


def load_labels_by_flight() -> dict:
    with open(LABELS_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        out.setdefault(r["flight_id"], {}).setdefault(r["camera"], []).append(r)
    return out


# ---- pairing + triangulation ---------------------------------------------

def pair_cam_points(rows0: list, rows1: list, flight_id: str) -> list:
    r0 = sorted(rows0, key=lambda r: float(r["frame_timestamp_ms"]))
    r1 = sorted(rows1, key=lambda r: float(r["frame_timestamp_ms"]))
    if len(r0) != len(r1):
        raise ValueError(f"{flight_id}: cam0/cam1 label count mismatch ({len(r0)} vs {len(r1)})")
    pairs = list(zip(r0, r1))
    for a, b in pairs:
        dt = abs(float(a["frame_timestamp_ms"]) - float(b["frame_timestamp_ms"]))
        if dt > PAIR_TIMESTAMP_TOL_MS:
            log_append(f"    WARNING {flight_id}: paired label timestamps {dt:.1f}ms apart "
                       f"(cam0 frame_{a['frame_index']} / cam1 frame_{b['frame_index']}) "
                       f"-- larger than expected ({PAIR_TIMESTAMP_TOL_MS}ms), check pairing.")
    return pairs


def triangulate_flight_labels(flight_id: str, cam_labels: dict, session: str) -> tuple:
    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    pairs = pair_cam_points(cam_labels["cam0"], cam_labels["cam1"], flight_id)

    pts0 = np.array([(float(a["u_px"]), float(a["v_px"])) for a, b in pairs], dtype=np.float64)
    pts1 = np.array([(float(b["u_px"]), float(b["v_px"])) for a, b in pairs], dtype=np.float64)
    xyz = triangulate(pts0, pts1, K0, D0, K1, D1, P0, P1)  # (N,3) mm, cam0 frame

    t_sec = np.array([
        (float(a["frame_timestamp_ms"]) + float(b["frame_timestamp_ms"])) / 2.0 / 1000.0
        for a, b in pairs
    ])
    is_crossing = [a["is_crossing_frame"] == "True" or b["is_crossing_frame"] == "True" for a, b in pairs]
    return xyz, t_sec, is_crossing


# ---- 3D quadratic fit + covariance ---------------------------------------

def fit_quadratic_3d(t: np.ndarray, xyz: np.ndarray) -> dict:
    """Independent per-axis quadratic OLS fit (camera frame), with
    parameter covariance for velocity CI propagation. Returns coeffs
    (numpy polyfit order: highest power first) and cov per axis, plus
    residual RMS (3D Euclidean) across the fitted points."""
    coeffs, covs = [], []
    for ax in range(3):
        n = len(t)
        deg = 2
        if n <= deg:
            c = np.polyfit(t, xyz[:, ax], deg=min(deg, n - 1))
            c = np.pad(c, (deg + 1 - len(c), 0))
            cov = np.full((3, 3), np.nan)
        else:
            c, cov = np.polyfit(t, xyz[:, ax], deg=deg, cov=True)
        coeffs.append(c)
        covs.append(cov)

    pred = np.stack([np.polyval(coeffs[ax], t) for ax in range(3)], axis=1)
    resid = np.linalg.norm(xyz - pred, axis=1)
    rms_mm = float(np.sqrt(np.mean(resid ** 2)))
    return dict(coeffs=coeffs, covs=covs, resid_rms_mm=rms_mm, n_points=len(t))


def eval_position(fit: dict, t: float) -> np.ndarray:
    return np.array([np.polyval(fit["coeffs"][ax], t) for ax in range(3)])


def eval_velocity(fit: dict, t: float) -> np.ndarray:
    return np.array([np.polyval(np.polyder(fit["coeffs"][ax]), t) for ax in range(3)])


def eval_velocity_variance_per_axis(fit: dict, t: float) -> np.ndarray:
    """Var(v(t)) for v(t) = 2*a2*t + a1, coeffs ordered [a2,a1,a0] (numpy
    convention) -> gradient wrt [a2,a1,a0] = [2t, 1, 0]."""
    g = np.array([2.0 * t, 1.0, 0.0])
    var = np.empty(3)
    for ax in range(3):
        cov = fit["covs"][ax]
        var[ax] = float(g @ cov @ g) if not np.any(np.isnan(cov)) else np.nan
    return var


def find_t_cross(fit: dict, X_world: np.ndarray, plane_depth: float, t_near: float) -> float:
    """Root of depth(t) = X_world . position(t) - plane_depth = 0, quadratic
    in t -- solved analytically, root nearest t_near (the bracket's own
    crossing-frame time) selected."""
    depth_coeffs = sum(fit["coeffs"][ax] * X_world[ax] for ax in range(3))
    depth_coeffs = depth_coeffs.copy()
    depth_coeffs[-1] -= plane_depth  # constant term
    roots = np.roots(depth_coeffs)
    real_roots = [r.real for r in roots if abs(r.imag) < 1e-6]
    if not real_roots:
        return float("nan")
    return min(real_roots, key=lambda r: abs(r - t_near))


# ---- main per-flight analysis --------------------------------------------

def analyze_flight(flight_id: str, cand_row: dict, labels_by_flight: dict, geometries: dict,
                    classification: dict, pooled_k: float) -> dict:
    session, reg_key = cand_row["session"], cand_row["registration"]
    geo = geometries[reg_key]
    X_world, p_far, u, up = geo["X_world"], geo["p_far"], geo["u"], geo["up"]
    _, Y_world, Z_world = load_world_axes(session, geo["registration"])
    # geo["up"] IS Z_world by construction (build_geometry: up = Z_world / norm) -- sanity check.
    assert np.allclose(up, Z_world / np.linalg.norm(Z_world), atol=1e-9), \
        f"{flight_id}: geo['up'] does not match freshly-loaded Z_world -- geometry inconsistency"

    cam_labels = labels_by_flight[flight_id]
    xyz, t_sec, is_crossing = triangulate_flight_labels(flight_id, cam_labels, session)
    fit = fit_quadratic_3d(t_sec, xyz)

    t_near = t_sec[is_crossing.index(True)] if any(is_crossing) else float(np.median(t_sec))
    t_cross_label = find_t_cross(fit, X_world, geo["plane_depth"], t_near)

    pos_label = eval_position(fit, t_cross_label)
    vel_label = eval_velocity(fit, t_cross_label)
    vel_var_label = eval_velocity_variance_per_axis(fit, t_cross_label)

    label_Y = float(np.dot(pos_label - p_far, u))
    label_Z = float(np.dot(pos_label - p_far, up))
    label_vworld = np.array([float(np.dot(vel_label, ax)) for ax in (X_world, Y_world, Z_world)])
    label_vworld_sd = np.array([
        math.sqrt(max(0.0, sum((axv[i] ** 2) * vel_var_label[i] for i in range(3))))
        for axv in (X_world, Y_world, Z_world)
    ])

    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    result = classify_flight(session, flight_id, geo, K0, D0, K1, D1, P0, P1, pooled_k)

    ref = classification[(session, flight_id)]
    reproduced = (result["status"] == "ok" and result["cls"] == ref["cls"] and
                  abs(result["duration_ms"] - float(ref["duration_ms"])) < 0.5)

    modelc_Y = result.get("crossing_Y")
    modelc_Z = result.get("crossing_Z")
    modelc_vel_cam = np.array(result.get("crossing_vel_xyz")) if result.get("crossing_vel_xyz") else None
    modelc_vworld = (np.array([float(np.dot(modelc_vel_cam, ax)) for ax in (X_world, Y_world, Z_world)])
                      if modelc_vel_cam is not None else None)

    pos_err_Y = pos_err_Z = pos_err_total = None
    if modelc_Y is not None:
        pos_err_Y = label_Y - modelc_Y
        pos_err_Z = label_Z - modelc_Z
        pos_err_total = math.hypot(pos_err_Y, pos_err_Z)

    return dict(
        flight_id=flight_id, registration=reg_key, elevation_bin=cand_row["elevation_bin"],
        symmetric=flight_id not in ASYMMETRIC_FLIGHTS, n_points=fit["n_points"],
        resid_rms_mm=fit["resid_rms_mm"], t_cross_label=t_cross_label,
        t_cross_modelc=result.get("t_cross"), reproduced=reproduced,
        cls_ref=ref["cls"], cls_rederived=result.get("cls"),
        label_Y=label_Y, label_Z=label_Z, modelc_Y=modelc_Y, modelc_Z=modelc_Z,
        pos_err_Y=pos_err_Y, pos_err_Z=pos_err_Z, pos_err_total=pos_err_total,
        label_vworld=label_vworld, label_vworld_sd=label_vworld_sd, modelc_vworld=modelc_vworld,
    )


# ---- pooling / reporting --------------------------------------------------

def pool_position(rows: list) -> dict:
    errs_Y = [r["pos_err_Y"] for r in rows if r["pos_err_Y"] is not None]
    errs_Z = [r["pos_err_Z"] for r in rows if r["pos_err_Z"] is not None]
    errs_T = [r["pos_err_total"] for r in rows if r["pos_err_total"] is not None]
    if not errs_T:
        return dict(n=0)
    return dict(n=len(errs_T),
                bias_Y=float(np.mean(errs_Y)), rms_Y=float(np.sqrt(np.mean(np.square(errs_Y)))),
                bias_Z=float(np.mean(errs_Z)), rms_Z=float(np.sqrt(np.mean(np.square(errs_Z)))),
                mean_total=float(np.mean(errs_T)), median_total=float(np.median(errs_T)),
                p90_total=float(np.percentile(errs_T, 90)))


def pool_velocity(rows: list) -> dict:
    rows = [r for r in rows if r["modelc_vworld"] is not None]
    if not rows:
        return dict(n=0)
    axis_names = ["X_world(depth)", "Y_world(width)", "Z_world(up)"]
    out = dict(n=len(rows))
    for i, name in enumerate(axis_names):
        diffs = [r["modelc_vworld"][i] - r["label_vworld"][i] for r in rows]
        label_sds = [r["label_vworld_sd"][i] for r in rows]
        out[name] = dict(
            mean_diff=float(np.mean(diffs)), rms_diff=float(np.sqrt(np.mean(np.square(diffs)))),
            mean_label_sd=float(np.nanmean(label_sds)),
        )
    modelc_speed = [float(np.linalg.norm(r["modelc_vworld"])) for r in rows]
    label_speed = [float(np.linalg.norm(r["label_vworld"])) for r in rows]
    speed_diffs = [m - l for m, l in zip(modelc_speed, label_speed)]
    out["speed"] = dict(mean_diff=float(np.mean(speed_diffs)),
                        rms_diff=float(np.sqrt(np.mean(np.square(speed_diffs)))))
    return out


def write_per_flight_csv(rows: list, path: Path) -> None:
    fields = ["flight_id", "registration", "elevation_bin", "symmetric", "n_points",
              "resid_rms_mm", "residual_flagged", "reproduced_01", "cls_ref", "cls_rederived",
              "t_cross_label", "t_cross_modelc", "label_Y", "label_Z", "modelc_Y", "modelc_Z",
              "pos_err_Y", "pos_err_Z", "pos_err_total",
              "label_vx_depth", "label_vy_width", "label_vz_up",
              "label_vx_sd", "label_vy_sd", "label_vz_sd",
              "modelc_vx_depth", "modelc_vy_width", "modelc_vz_up"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            row = dict(
                flight_id=r["flight_id"], registration=r["registration"],
                elevation_bin=r["elevation_bin"], symmetric=r["symmetric"], n_points=r["n_points"],
                resid_rms_mm=r["resid_rms_mm"], residual_flagged=r.get("residual_flagged", False),
                reproduced_01=r["reproduced"], cls_ref=r["cls_ref"], cls_rederived=r["cls_rederived"],
                t_cross_label=r["t_cross_label"], t_cross_modelc=r["t_cross_modelc"],
                label_Y=r["label_Y"], label_Z=r["label_Z"], modelc_Y=r["modelc_Y"], modelc_Z=r["modelc_Z"],
                pos_err_Y=r["pos_err_Y"], pos_err_Z=r["pos_err_Z"], pos_err_total=r["pos_err_total"],
                label_vx_depth=r["label_vworld"][0], label_vy_width=r["label_vworld"][1],
                label_vz_up=r["label_vworld"][2], label_vx_sd=r["label_vworld_sd"][0],
                label_vy_sd=r["label_vworld_sd"][1], label_vz_sd=r["label_vworld_sd"][2],
                modelc_vx_depth=r["modelc_vworld"][0] if r["modelc_vworld"] is not None else None,
                modelc_vy_width=r["modelc_vworld"][1] if r["modelc_vworld"] is not None else None,
                modelc_vz_up=r["modelc_vworld"][2] if r["modelc_vworld"] is not None else None,
            )
            w.writerow(row)


# ---- figures (dataviz skill conventions, light mode) -----------------------

COLOR_SURFACE = "#fcfcfb"
COLOR_PRIMARY_INK = "#0b0b0b"
COLOR_SECONDARY_INK = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRIDLINE = "#e1e0d9"
COLOR_BASELINE = "#c3c2b7"
COLOR_FLAT = "#2a78d6"
COLOR_MID = "#eb6834"
COLOR_LOB = "#1baf7a"
BIN_COLOR = {"FLAT": COLOR_FLAT, "MID": COLOR_MID, "LOB": COLOR_LOB}
APERTURE_SIZE_MM = 2000.0


def style_axes(ax):
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(COLOR_BASELINE)
    ax.tick_params(colors=COLOR_MUTED, labelsize=9)
    ax.grid(True, color=COLOR_GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def plot_position_scatter(rows: list, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 7.5), facecolor=COLOR_SURFACE)
    style_axes(ax)
    box = plt.Rectangle((0, 0), APERTURE_SIZE_MM, APERTURE_SIZE_MM, fill=False,
                        edgecolor=COLOR_BASELINE, linewidth=1.5, zorder=1)
    ax.add_patch(box)

    seen = set()
    for r in rows:
        if r["modelc_Y"] is None:
            continue
        color = BIN_COLOR[r["elevation_bin"]]
        marker = "o" if r["symmetric"] else "x"
        label = r["elevation_bin"] if r["elevation_bin"] not in seen else None
        seen.add(r["elevation_bin"])
        ax.scatter(r["modelc_Y"], r["modelc_Z"], s=60, marker=marker, facecolor=color,
                  edgecolor=COLOR_SURFACE, linewidth=0.7, zorder=3, label=label)
        ax.scatter(r["label_Y"], r["label_Z"], s=60, marker=marker, facecolor="none",
                  edgecolor=color, linewidth=1.4, zorder=3)
        ax.plot([r["modelc_Y"], r["label_Y"]], [r["modelc_Z"], r["label_Z"]],
               color=color, linewidth=0.8, alpha=0.5, zorder=2)

    ax.set_xlabel("Y (mm, along tape from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_ylabel("Z (mm, up from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_title("Model-C (filled) vs label-fit (open) crossing position\n"
                "x = asymmetric/flagged flight", color=COLOR_PRIMARY_INK, fontsize=11, loc="left")
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=COLOR_SECONDARY_INK)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=COLOR_SURFACE)
    plt.close(fig)


def plot_velocity_comparison(rows: list, out_path: Path) -> None:
    axis_names = ["X_world\n(depth)", "Y_world\n(width)", "Z_world\n(up)"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 5), facecolor=COLOR_SURFACE)
    rows = [r for r in rows if r["modelc_vworld"] is not None]

    for i, (ax, name) in enumerate(zip(axes, axis_names)):
        style_axes(ax)
        xs = list(range(len(rows)))
        modelc_vals = [r["modelc_vworld"][i] for r in rows]
        label_vals = [r["label_vworld"][i] for r in rows]
        label_sds = [r["label_vworld_sd"][i] for r in rows]
        colors = [BIN_COLOR[r["elevation_bin"]] for r in rows]

        ax.errorbar(xs, label_vals, yerr=label_sds, fmt="none", ecolor=COLOR_MUTED,
                   elinewidth=1.0, capsize=3, zorder=2)
        ax.scatter(xs, label_vals, s=40, marker="o", facecolor="none",
                  edgecolor=colors, linewidth=1.4, zorder=3, label="label" if i == 0 else None)
        ax.scatter(xs, modelc_vals, s=40, marker="s", c=colors, edgecolor=COLOR_SURFACE,
                  linewidth=0.6, zorder=3, label="Model-C" if i == 0 else None)
        ax.set_title(name, color=COLOR_PRIMARY_INK, fontsize=10)
        ax.set_xticks(xs)
        ax.set_xticklabels([r["flight_id"].replace("flight_", "") for r in rows],
                          rotation=90, fontsize=6, color=COLOR_MUTED)
        if i == 0:
            ax.set_ylabel("velocity component (mm/s)", color=COLOR_SECONDARY_INK, fontsize=10)
            ax.legend(loc="best", frameon=False, fontsize=8, labelcolor=COLOR_SECONDARY_INK)

    fig.suptitle("Model-C vs label-fit velocity at crossing, per world axis (error bars = label fit SD)",
                color=COLOR_PRIMARY_INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=COLOR_SURFACE)
    plt.close(fig)


# ---- main -----------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_append(f"- [{ts()}] Loading candidates, classification, labels.")

    candidates = load_candidates()
    classification = load_classification()
    labels_by_flight = load_labels_by_flight()
    pooled_k = load_pooled_k()
    geometries = {reg_key: build_geometry(reg_key, cfg) for reg_key, cfg in TAPE_REGISTRATIONS.items()}

    flight_ids = list(candidates.keys())
    log_append(f"- [{ts()}] {len(flight_ids)} candidate flights, {len(labels_by_flight)} with labels.")
    missing = set(flight_ids) - set(labels_by_flight)
    if missing:
        log_append(f"*** STOP: flights missing labels: {missing} ***")
        raise SystemExit(f"Missing labels for: {missing}")

    rows = []
    for flight_id in flight_ids:
        r = analyze_flight(flight_id, candidates[flight_id], labels_by_flight, geometries,
                           classification, pooled_k)
        rows.append(r)
        log_append(f"- [{ts()}] {flight_id} ({r['registration']}, {r['elevation_bin']}, "
                  f"{'symmetric' if r['symmetric'] else 'ASYMMETRIC'}): "
                  f"n={r['n_points']}, resid_rms={r['resid_rms_mm']:.1f}mm, "
                  f"reproduced_01={r['reproduced']} (ref cls={r['cls_ref']}, rederived={r['cls_rederived']}), "
                  f"pos_err(Y,Z,total)=({r['pos_err_Y']:.1f},{r['pos_err_Z']:.1f},{r['pos_err_total']:.1f})mm "
                  if r["pos_err_total"] is not None else
                  f"- [{ts()}] {flight_id}: no Model-C crossing position (MISS_SHORT re-derivation?)")

        if not r["reproduced"]:
            log_append(f"*** STOP: {flight_id} re-derivation does NOT reproduce 01_'s classification "
                      f"(ref cls={r['cls_ref']}, rederived={r['cls_rederived']}). ***")
            raise SystemExit(f"{flight_id}: Model-C re-derivation mismatch, see log.")

    log_append(f"- [{ts()}] All {len(rows)} flights reproduced 01_'s classification exactly (RANSAC seed=42, deterministic).")

    # -- residual gate --
    residuals = [r["resid_rms_mm"] for r in rows]
    median_resid = float(np.median(residuals))
    threshold = RESIDUAL_FLAG_FACTOR * median_resid
    for r in rows:
        r["residual_flagged"] = r["resid_rms_mm"] > threshold
    flagged_resid = [r["flight_id"] for r in rows if r["residual_flagged"]]
    log_append(f"- [{ts()}] Residual gate: median={median_resid:.1f}mm, threshold={threshold:.1f}mm "
              f"({RESIDUAL_FLAG_FACTOR}x median). Flagged: {flagged_resid or 'none'}.")

    # -- clean pool (symmetric AND not residual-flagged) --
    clean_rows = [r for r in rows if r["symmetric"] and not r["residual_flagged"]]
    asym_rows = [r for r in rows if not r["symmetric"]]
    resid_flagged_rows = [r for r in rows if r["residual_flagged"] and r["symmetric"]]

    pos_pool = pool_position(clean_rows)
    vel_pool = pool_velocity(clean_rows)
    log_append(f"- [{ts()}] POOLED POSITION (clean, n={pos_pool.get('n')}): "
              f"bias_Y={pos_pool.get('bias_Y', float('nan')):.1f}mm rms_Y={pos_pool.get('rms_Y', float('nan')):.1f}mm, "
              f"bias_Z={pos_pool.get('bias_Z', float('nan')):.1f}mm rms_Z={pos_pool.get('rms_Z', float('nan')):.1f}mm, "
              f"median_total={pos_pool.get('median_total', float('nan')):.1f}mm p90={pos_pool.get('p90_total', float('nan')):.1f}mm")
    log_append(f"- [{ts()}] POOLED VELOCITY (clean, n={vel_pool.get('n')}): {vel_pool}")

    # -- per elevation bin, indicative --
    for b in ("FLAT", "MID", "LOB"):
        bin_rows = [r for r in clean_rows if r["elevation_bin"] == b]
        if bin_rows:
            bp = pool_position(bin_rows)
            log_append(f"- [{ts()}] {b} bin (INDICATIVE, n={len(bin_rows)}): "
                      f"median_pos_err={bp.get('median_total', float('nan')):.1f}mm")

    if asym_rows:
        log_append(f"- [{ts()}] ASYMMETRIC flights (separate, low-confidence): "
                  + "; ".join(f"{r['flight_id']} (n={r['n_points']}, resid={r['resid_rms_mm']:.1f}mm)"
                             for r in asym_rows))
    if resid_flagged_rows:
        log_append(f"- [{ts()}] RESIDUAL-FLAGGED (excluded_pending_review): "
                  + "; ".join(r["flight_id"] for r in resid_flagged_rows))

    write_per_flight_csv(rows, OUT_DIR / "label_vs_fit_per_flight.csv")
    log_append(f"- [{ts()}] Wrote label_vs_fit_per_flight.csv ({len(rows)} rows).")

    plot_position_scatter(rows, OUT_DIR / "position_scatter.png")
    plot_velocity_comparison(rows, OUT_DIR / "velocity_comparison.png")
    log_append(f"- [{ts()}] Wrote position_scatter.png and velocity_comparison.png.")

    summary_lines = [
        "LABEL vs MODEL-C CROSSING-STATE VALIDATION",
        "NOT an absolute-truth check -- shares calibration with Model-C; validates fit+extrapolation only.",
        "",
        f"Flights: {len(rows)} total, {len(clean_rows)} clean (symmetric, non-residual-flagged),",
        f"{len(asym_rows)} asymmetric (low-confidence), {len(resid_flagged_rows)} residual-flagged.",
        "",
        "POOLED POSITION (clean, n=%d):" % pos_pool.get("n", 0),
        f"  bias Y={pos_pool.get('bias_Y', float('nan')):.1f}mm  rms Y={pos_pool.get('rms_Y', float('nan')):.1f}mm",
        f"  bias Z={pos_pool.get('bias_Z', float('nan')):.1f}mm  rms Z={pos_pool.get('rms_Z', float('nan')):.1f}mm",
        f"  median total={pos_pool.get('median_total', float('nan')):.1f}mm  p90 total={pos_pool.get('p90_total', float('nan')):.1f}mm",
        "",
        "POOLED VELOCITY (clean, n=%d), Model-C minus label, label-noise caveat applies:" % vel_pool.get("n", 0),
    ]
    for name in ("X_world(depth)", "Y_world(width)", "Z_world(up)"):
        v = vel_pool.get(name, {})
        summary_lines.append(f"  {name}: mean_diff={v.get('mean_diff', float('nan')):.1f}mm/s  "
                             f"rms_diff={v.get('rms_diff', float('nan')):.1f}mm/s  "
                             f"mean_label_sd={v.get('mean_label_sd', float('nan')):.1f}mm/s")
    summary_lines.append(f"  speed: mean_diff={vel_pool.get('speed', {}).get('mean_diff', float('nan')):.1f}mm/s  "
                         f"rms_diff={vel_pool.get('speed', {}).get('rms_diff', float('nan')):.1f}mm/s")
    summary_path = OUT_DIR / "summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n")
    log_append(f"- [{ts()}] Wrote summary.txt")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
