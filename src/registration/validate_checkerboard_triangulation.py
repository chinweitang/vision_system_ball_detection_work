"""
Validate stereo triangulation accuracy against checkerboard ground truth, at
real operating depth, using held-out boards that were NOT part of the
extrinsic calibration. Runs once per extrinsics solve so old vs new can be
compared side by side. Two independent analyses are produced from the same
triangulated corners:

  1. RELATIVE-DISTANCE analysis (results/relative_distance/): checkerboard
     corner spacing is exact ground truth (caliper-measured 67.5mm), so
     triangulated corner-to-corner distances can be checked directly against
     true distances - inter-point distances are frame-invariant, so no
     camera->floor transform is needed. Same logic as
     src/registration/validate_triangulation.py, but auto-detected corners
     instead of manually-clicked points.

  2. BOARD-FRAME analysis (results/board_frame/): fits the 77 triangulated
     corners (camera frame) onto the KNOWN board grid - once RIGID
     (Kabsch: rotation+translation) and once SIMILARITY (+ a free global
     scale, Umeyama) - to separate SCALE error from WARP/scatter. This is
     self-referential for absolute board pose (it fits to the same board),
     so it is NOT an absolute-position validation - see the NOTE printed
     with every board-frame section.

Neither analysis solves a camera->floor transform.

Reuses (does not reimplement) from src/calibration/extrinsic/solve_extrinsic.py:
    PATTERN_SIZE, SQUARE_SIZE_MM, OBJP, detect_corners(), load_intrinsics(),
    mono_solve_pose(), POSE_OUTLIER_ANGLE_DEG, POSE_OUTLIER_BASELINE_PCT
and from src/stereo/triangulate.py: triangulate_points().
Kabsch/Umeyama are implemented directly here via numpy SVD - no new deps.

CORNER-ORDER SAFETY
solve_extrinsic.py's pose-outlier rejection relies on a median over MANY
calibration poses - with only 4 held-out boards at very different depths
there's no "typical" pose to compare against, so that method doesn't apply
here. Instead, per board, both candidate cam1 corner orderings ("as-detected"
and "reversed", i.e. the 180-degree in-plane relabeling a symmetric-looking
checkerboard can produce) are tested against the KNOWN rig (R, T) from a
reference extrinsics solve via the same mono-solvePnP relative-pose trick
solve_extrinsic.py uses, and whichever ordering is consistent with the known
rig geometry is kept. If neither is consistent, the board is skipped with a
loud warning rather than silently emitting wrong distances. This ordering
decision is made ONCE per board (using the first --extrinsics file as the
reference) and then reused for every extrinsics file evaluated below - the
corner correspondence must be identical across solves for the old-vs-new
comparison to mean anything.

Usage:
    python src/registration/validate_checkerboard_triangulation.py
    python src/registration/validate_checkerboard_triangulation.py \
        --extrinsics calibration_outputs/2026_07_11_session/stereo_extrinsic.npz \
        --extrinsics calibration_outputs/2026_07_12_session/stereo_extrinsic.npz

Inputs:
    data/2026_07_12_session/validation/cam0/img_XXXX.png  (right)
    data/2026_07_12_session/validation/cam1/img_XXXX.png  (left)
    calibration_outputs/cam0_intrinsics_fisheye.npz, cam1_intrinsics_fisheye.npz

Outputs (data/2026_07_12_session/validation/results/):
    corner_debug/corner_debug_<idx>_cam0.png / _cam1.png
        corner 0 / corner -1 marked, once per board - per-run safety artifact
        (overwritten each run), not a result.
    relative_distance/checkerboard_triangulation_validation.txt
    relative_distance/scatter_<idx>_<extrinsics_tag>.png
        3D scatter + grid mesh - BLUNDER-CHECK ONLY (spot a flung point), not
        an accuracy/precision figure.
    relative_distance/hist_<idx>_<extrinsics_tag>.png
        signed distance-error histogram; bias = center, scatter = width.
    relative_distance/summary_error_vs_depth_<extrinsics_tag>.png
    relative_distance/summary_planeresidual_vs_depth_<extrinsics_tag>.png
    board_frame/board_frame_validation.txt
    board_frame/quiver_<idx>_<extrinsics_tag>.png
        in-plane residual quiver (direction/magnitude of dx,dy after the
        similarity fit, arrows exaggerated for visibility, coloured by dz)
        + out-of-plane (dz/warp) heatmap over the grid. THE headline
        structure-diagnostic plot for this analysis.
    board_frame/summary_vs_depth_<extrinsics_tag>.png
        sim_rms_mm (scatter) and rms_dz_mm (warp) vs measured depth.
    board_frame/pooled_summary_<extrinsics_tag>.csv
        CSV of the per-extrinsics pooled-summary table above.
    board_frame/cross_extrinsics_comparison.csv
        CSV of the cross-extrinsics comparison table above.
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.stereo.triangulate import triangulate_points
from src.calibration.extrinsic.solve_extrinsic import (
    PATTERN_SIZE, SQUARE_SIZE_MM, OBJP, detect_corners, load_intrinsics, mono_solve_pose,
    POSE_OUTLIER_ANGLE_DEG, POSE_OUTLIER_BASELINE_PCT,
)

INTRINSICS_DIR = ROOT / "calibration_outputs"
VALIDATION_DIR = ROOT / "data/2026_07_12_session/validation"
CAM0_DIR = VALIDATION_DIR / "cam0"
CAM1_DIR = VALIDATION_DIR / "cam1"

RESULTS_DIR = VALIDATION_DIR / "results"
CORNER_DEBUG_DIR = RESULTS_DIR / "corner_debug"
RELATIVE_DIR = RESULTS_DIR / "relative_distance"
BOARD_FRAME_DIR = RESULTS_DIR / "board_frame"
RELATIVE_REPORT_PATH = RELATIVE_DIR / "checkerboard_triangulation_validation.txt"
BOARD_FRAME_REPORT_PATH = BOARD_FRAME_DIR / "board_frame_validation.txt"

DEFAULT_EXTRINSICS = [
    ROOT / "calibration_outputs/2026_07_11_session/stereo_extrinsic.npz",
    ROOT / "calibration_outputs/2026_07_12_session/stereo_extrinsic.npz",
]

# Labelling only - approximate capture depths, NEVER used to gate any logic below.
NOMINAL_DEPTH_LABEL = {
    "img_0006": "~3 m",
    "img_0026": "~1 m",
    "img_0035": "~5 m",
    "img_0036": "~5 m",
}

DIST_BIN_EDGES_MM = [0, 100, 300, 600, 900]

# Cross-board scale-consistency check: same-sign AND within this many
# percentage-points of each other => a plausible real global scale error,
# rather than per-board noise. A single board's scale is a short-lever,
# noisy, local estimate and must never be over-read alone.
SCALE_CONSISTENCY_SPREAD_TOL_PCT = 1.0

N_CORNERS = PATTERN_SIZE[0] * PATTERN_SIZE[1]


# ---- corner grid helpers ------------------------------------------------------

def corner_col_row(i):
    return i % PATTERN_SIZE[0], i // PATTERN_SIZE[0]


def corner_label(i):
    col, row = corner_col_row(i)
    return f"col{col}row{row}"


def adjacent_index_pairs():
    """Index pairs that are orthogonal, nominal-67.5mm neighbours in the grid
    (horizontal and vertical edges only - not diagonals)."""
    cols, rows = PATTERN_SIZE

    def idx(c, r):
        return r * cols + c

    pairs = []
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                pairs.append((idx(c, r), idx(c + 1, r)))
            if r + 1 < rows:
                pairs.append((idx(c, r), idx(c, r + 1)))
    return pairs


ADJACENT_PAIRS = adjacent_index_pairs()

TRUE_DIST_MATRIX = np.linalg.norm(OBJP[:, None, :] - OBJP[None, :, :], axis=-1)  # (77,77) mm, ground truth
IU = np.triu_indices(N_CORNERS, 1)  # the 2926 unique unordered pairs


# ---- loading / discovery -------------------------------------------------------

def find_matched_pairs(cam0_dir, cam1_dir):
    """Same approach as solve_extrinsic.find_matched_pairs(), parameterized by directory."""
    cam0_paths = {p.stem: p for p in cam0_dir.glob("img_*.png")}
    cam1_paths = {p.stem: p for p in cam1_dir.glob("img_*.png")}

    only_cam0 = sorted(set(cam0_paths) - set(cam1_paths))
    only_cam1 = sorted(set(cam1_paths) - set(cam0_paths))
    if only_cam0:
        print(f"WARNING: {len(only_cam0)} index(es) present in cam0 but not cam1 (skipped): {only_cam0}")
    if only_cam1:
        print(f"WARNING: {len(only_cam1)} index(es) present in cam1 but not cam0 (skipped): {only_cam1}")

    common = sorted(set(cam0_paths) & set(cam1_paths))
    return [(idx, cam0_paths[idx], cam1_paths[idx]) for idx in common]


# ---- corner-order safety --------------------------------------------------------

def rotation_angle_deg(Ra, Rb):
    """Angle (deg) of the relative rotation Ra @ Rb.T - 0 if Ra and Rb agree."""
    Rdiff = Ra @ Rb.T
    return float(np.degrees(np.arccos(np.clip((np.trace(Rdiff) - 1) / 2, -1, 1))))


def choose_corner_order(c0, c1, K0, D0, K1, D1, R_ref, T_ref):
    """
    Test "as-detected" vs "reversed" cam1 corner order against the known rig
    (R_ref, T_ref) via independent mono solvePnP per view (mono_solve_pose,
    reused from solve_extrinsic.py) + the implied cam0->cam1 relative
    transform. Returns (plausible: bool, best: dict) - best holds whichever
    candidate is closer to the known rig geometry, plausible says whether
    that best candidate is close enough to trust.
    """
    imgp0 = c0.astype(np.float64).reshape(-1, 1, 2)
    R0, t0 = mono_solve_pose(imgp0, K0, D0)
    ref_baseline = float(np.linalg.norm(T_ref))

    best = None
    for label, cand_c1 in (("as-detected", c1), ("reversed", c1[::-1])):
        imgp1 = cand_c1.astype(np.float64).reshape(-1, 1, 2)
        R1, t1 = mono_solve_pose(imgp1, K1, D1)
        R_rel = R1 @ R0.T
        T_rel = t1 - R_rel @ t0
        rot_diff = rotation_angle_deg(R_rel, R_ref)
        baseline_pct = 100.0 * abs(np.linalg.norm(T_rel) - ref_baseline) / ref_baseline
        if best is None or rot_diff < best["rot_diff"]:
            best = {"label": label, "corners": cand_c1, "rot_diff": rot_diff, "baseline_pct": baseline_pct}

    plausible = best["rot_diff"] <= POSE_OUTLIER_ANGLE_DEG and best["baseline_pct"] <= POSE_OUTLIER_BASELINE_PCT
    return plausible, best


def save_corner_debug(idx, path0, path1, c0, c1):
    """corner[0] and corner[-1] marked in both views - eyeball correspondence,
    same style as solve_extrinsic.save_corner0_debug(). Per-run safety
    artifact (overwritten every run), not a result."""
    img0 = cv2.imread(str(path0))
    img1 = cv2.imread(str(path1))
    out0 = CORNER_DEBUG_DIR / f"corner_debug_{idx}_cam0.png"
    out1 = CORNER_DEBUG_DIR / f"corner_debug_{idx}_cam1.png"
    for img, corners, out_path in ((img0, c0, out0), (img1, c1, out1)):
        pt0 = tuple(int(v) for v in corners[0])
        pt_last = tuple(int(v) for v in corners[-1])
        cv2.circle(img, pt0, 16, (0, 0, 255), 3)
        cv2.putText(img, "corner 0", (pt0[0] + 20, pt0[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.circle(img, pt_last, 16, (0, 255, 0), 3)
        cv2.putText(img, f"corner {N_CORNERS - 1}", (pt_last[0] + 20, pt_last[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.imwrite(str(out_path), img)
    return out0, out1


# ---- geometry -------------------------------------------------------------------

def fit_plane_residual_rms(points):
    """Least-squares plane through `points` (N,3); RMS orthogonal distance (mm)."""
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    normal = Vt[-1]
    residuals = centered @ normal
    return float(np.sqrt(np.mean(residuals ** 2)))


def umeyama_alignment(src, dst, with_scale):
    """
    Closed-form least-squares alignment via SVD: Kabsch when with_scale=False
    (rotation+translation only), Umeyama (1991) when with_scale=True (adds a
    single free global scale). Finds R, t, (s) minimizing
    sum_i || s * R @ src_i + t - dst_i ||^2.
    src, dst: (N, 3). Returns (R (3,3), t (3,), s (float, 1.0 if with_scale=False)).
    """
    n = src.shape[0]
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_c = src - mu_src
    dst_c = dst - mu_dst

    cov = (dst_c.T @ src_c) / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1.0
    R = U @ S @ Vt

    if with_scale:
        var_src = (src_c ** 2).sum() / n
        s = float(np.trace(np.diag(D) @ S) / var_src)
    else:
        s = 1.0

    t = mu_dst - s * (R @ mu_src)
    return R, t, s


def apply_similarity(points, R, t, s):
    return s * (points @ R.T) + t


# ---- relative-distance plots ------------------------------------------------------

def save_error_histogram(idx, err_mm, extrinsics_tag, mean_z):
    """Signed distance-error histogram - headline relative-distance diagnostic:
    center = bias, width = scatter."""
    bias = float(np.mean(err_mm))
    scatter = float(np.std(err_mm))

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(err_mm, bins=40, color="tab:blue", alpha=0.75, edgecolor="white")
    ax.axvline(bias, color="tab:red", linewidth=2, label=f"bias = {bias:+.2f} mm")
    ax.axvline(bias - scatter, color="tab:orange", linestyle="--", linewidth=1.5,
               label=f"bias -1 std = {bias - scatter:+.2f} mm")
    ax.axvline(bias + scatter, color="tab:orange", linestyle="--", linewidth=1.5,
               label=f"bias +1 std = {bias + scatter:+.2f} mm")
    ax.axvline(0, color="black", linestyle=":", linewidth=1, alpha=0.6)

    label = NOMINAL_DEPTH_LABEL.get(idx, "")
    ax.set_xlabel("signed distance error, triangulated - true (mm)")
    ax.set_ylabel(f"count (of {len(err_mm)} corner pairs)")
    ax.set_title(f"Signed distance-error histogram - {idx} ({label})\n"
                 f"extrinsics: {extrinsics_tag}, measured mean Z = {mean_z:.0f} mm")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    out_path = RELATIVE_DIR / f"hist_{idx}_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def save_board_scatter(idx, tri, extrinsics_tag, mean_z):
    """3D scatter of the 77 triangulated corners, with grid mesh lines drawn
    from the known (col,row) structure. BLUNDER-CHECK ONLY (spot a flung
    point / grossly bent row) - NOT an accuracy/precision figure; see the
    histogram (relative_distance/) and quiver (board_frame/) for that."""
    xs, ys, zs = tri[:, 0], tri[:, 1], tri[:, 2]

    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")

    cols, rows = PATTERN_SIZE
    for r in range(rows):
        row_idx = [r * cols + c for c in range(cols)]
        pts = tri[row_idx]
        ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], "b-", linewidth=0.8, alpha=0.6)
    for c in range(cols):
        col_idx = [r * cols + c for r in range(rows)]
        pts = tri[col_idx]
        ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], "b-", linewidth=0.8, alpha=0.6)

    ax.scatter(xs, ys, zs, c="red", s=20, depthshade=True)
    ax.set_xlabel("X (mm, cam0/right frame)")
    ax.set_ylabel("Y (mm, cam0/right frame)")
    ax.set_zlabel("Z (mm, cam0/right frame)")
    label = NOMINAL_DEPTH_LABEL.get(idx, "")
    ax.set_title(f"Triangulated checkerboard corners - {idx} ({label}) - BLUNDER CHECK ONLY\n"
                 f"extrinsics: {extrinsics_tag}, measured mean Z = {mean_z:.0f} mm")

    max_range = np.array([xs.max() - xs.min(), ys.max() - ys.min(), zs.max() - zs.min()]).max() / 2.0
    max_range = max(max_range, 1.0)
    mid_x, mid_y, mid_z = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2, (zs.max() + zs.min()) / 2
    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)

    out_path = RELATIVE_DIR / f"scatter_{idx}_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ---- board-frame plot -------------------------------------------------------------

def save_residual_quiver(idx, resid, extrinsics_tag, mean_z):
    """
    Headline board-frame structure-diagnostic: in-plane (dx,dy) residual
    quiver after the similarity fit, at each (col,row) grid position, arrows
    exaggerated for visibility and coloured by out-of-plane (dz); plus a dz
    heatmap panel. Purpose: reveal error STRUCTURE - arrows pointing radially
    outward => residual scale, swirl => rotation residual, one-directional
    bow => warp.
    """
    cols, rows = PATTERN_SIZE
    x = OBJP[:, 0]  # board-frame column coordinate, mm
    y = OBJP[:, 1]  # board-frame row coordinate, mm
    dx, dy, dz = resid[:, 0], resid[:, 1], resid[:, 2]

    mag_xy = np.hypot(dx, dy)
    typical = float(np.percentile(mag_xy, 75)) if mag_xy.max() > 1e-9 else 1.0
    exag = (0.6 * SQUARE_SIZE_MM) / max(typical, 1e-6)  # typical (P75) arrow ~= 0.6 grid cells

    fig, (ax_q, ax_dz) = plt.subplots(1, 2, figsize=(14, 6))

    q = ax_q.quiver(x, y, dx * exag, dy * exag, dz, angles="xy", scale_units="xy", scale=1,
                     cmap="coolwarm", width=0.006)
    fig.colorbar(q, ax=ax_q, label="dz, out-of-plane (mm)")
    ax_q.set_xlabel("board X (mm, along columns)")
    ax_q.set_ylabel("board Y (mm, along rows)")
    ax_q.set_title(f"In-plane residual (dx,dy) after similarity fit\n"
                   f"arrows exaggerated {exag:.1f}x (typical |dx,dy| P75 = {typical:.2f} mm)")
    ax_q.set_aspect("equal")
    ax_q.invert_yaxis()
    ax_q.grid(alpha=0.3)

    dz_grid = dz.reshape(rows, cols)
    dz_max = max(float(np.abs(dz).max()), 1e-6)
    im = ax_dz.imshow(dz_grid, origin="upper", cmap="coolwarm", vmin=-dz_max, vmax=dz_max)
    ax_dz.set_xticks(range(cols))
    ax_dz.set_yticks(range(rows))
    ax_dz.set_xlabel("board column index")
    ax_dz.set_ylabel("board row index")
    ax_dz.set_title("Out-of-plane residual dz (warp) over the grid")
    fig.colorbar(im, ax=ax_dz, label="dz (mm)")

    label = NOMINAL_DEPTH_LABEL.get(idx, "")
    fig.suptitle(f"Residual structure after similarity fit - {idx} ({label})\n"
                 f"extrinsics: {extrinsics_tag}, measured mean Z = {mean_z:.0f} mm")
    plt.tight_layout()
    out_path = BOARD_FRAME_DIR / f"quiver_{idx}_{extrinsics_tag}.png"
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ---- per-board analysis: relative-distance -----------------------------------------

def analyze_board_relative(idx, tri, mean_z, plane_rms, extrinsics_tag, emit):
    tri_dist_matrix = np.linalg.norm(tri[:, None, :] - tri[None, :, :], axis=-1)
    true_d = TRUE_DIST_MATRIX[IU]
    tri_d = tri_dist_matrix[IU]
    err = tri_d - true_d              # SIGNED, mm: triangulated - true
    err_pct = 100.0 * err / true_d    # SIGNED, %

    bias_mm = float(np.mean(err))
    scatter_mm = float(np.std(err))
    rms_mm = float(np.sqrt(np.mean(err ** 2)))
    p95_mm = float(np.percentile(np.abs(err), 95))
    abs_mean_mm = float(np.mean(np.abs(err)))
    max_abs_mm = float(np.max(np.abs(err)))
    max_pos = int(np.argmax(np.abs(err)))
    max_pair = (corner_label(IU[0][max_pos]), corner_label(IU[1][max_pos]))

    bias_pct = float(np.mean(err_pct))
    scatter_pct = float(np.std(err_pct))
    rms_pct = float(np.sqrt(np.mean(err_pct ** 2)))
    p95_pct = float(np.percentile(np.abs(err_pct), 95))
    abs_mean_pct = float(np.mean(np.abs(err_pct)))

    a_idx = np.array([p[0] for p in ADJACENT_PAIRS])
    b_idx = np.array([p[1] for p in ADJACENT_PAIRS])
    adj_err = np.abs(tri_dist_matrix[a_idx, b_idx] - TRUE_DIST_MATRIX[a_idx, b_idx])
    adj_mean, adj_max = float(adj_err.mean()), float(adj_err.max())

    furthest_pos = int(np.argmax(true_d))
    fa, fb = IU[0][furthest_pos], IU[1][furthest_pos]
    furthest_true, furthest_tri = float(true_d[furthest_pos]), float(tri_d[furthest_pos])
    furthest_err = furthest_tri - furthest_true

    bin_rows = []
    for lo, hi in zip(DIST_BIN_EDGES_MM[:-1], DIST_BIN_EDGES_MM[1:]):
        mask = (true_d >= lo) & (true_d < hi)
        n = int(mask.sum())
        if n == 0:
            bin_rows.append((lo, hi, 0, float("nan"), float("nan"), float("nan"), float("nan")))
        else:
            b_err = err[mask]
            bin_rows.append((lo, hi, n, float(b_err.mean()), float(b_err.std()),
                              float(np.sqrt(np.mean(b_err ** 2))), float(np.percentile(np.abs(b_err), 95))))

    label = NOMINAL_DEPTH_LABEL.get(idx, "")
    emit(f"--- Board {idx}  (nominal depth {label}, measured mean Z = {mean_z:.0f} mm) "
         f"[extrinsics: {extrinsics_tag}] ---")
    emit(f"  Distance error over all {len(true_d)} corner pairs (signed: triangulated - true):")
    emit(f"    bias (systematic)  = {bias_mm:+6.2f} mm ({bias_pct:+5.2f}%)   "
         f"[+ = triangulated distances run long, - = run short]")
    emit(f"    scatter (std)      = {scatter_mm:6.2f} mm ({scatter_pct:5.2f}%)")
    emit(f"    RMS                = {rms_mm:6.2f} mm ({rms_pct:5.2f}%)")
    emit(f"    p95 |error|        = {p95_mm:6.2f} mm ({p95_pct:5.2f}%)")
    emit(f"    mean |error|       = {abs_mean_mm:6.2f} mm ({abs_mean_pct:5.2f}%)")
    emit(f"    (single worst pair - fragile) max |error| = {max_abs_mm:.2f} mm "
         f"at {max_pair[0]}<->{max_pair[1]}")
    emit(f"  Adjacent-corner (nominal 67.5mm) errors: mean={adj_mean:.2f} mm, max={adj_max:.2f} mm")
    emit(f"  Furthest-apart corner pair ({corner_label(fa)} <-> {corner_label(fb)}): "
         f"triangulated={furthest_tri:.2f} mm, true={furthest_true:.2f} mm, error={furthest_err:+.2f} mm")
    emit("  Error by true separation (signed - a consistent-sign trend growing with separation is a scale bias):")
    emit(f"    {'range_mm':>14} | {'n_pairs':>7} | {'signed_mean_mm':>15} | {'std_mm':>8} | "
         f"{'RMS_mm':>8} | {'p95_mm':>8}")
    for lo, hi, n, bmean, bstd, brms, bp95 in bin_rows:
        if n:
            emit(f"    {f'{lo}-{hi}':>14} | {n:>7} | {bmean:+15.2f} | {bstd:8.2f} | {brms:8.2f} | {bp95:8.2f}")
        else:
            emit(f"    {f'{lo}-{hi}':>14} | {n:>7} | {'n/a':>15} | {'n/a':>8} | {'n/a':>8} | {'n/a':>8}")
    emit(f"  Plane-fit residual RMS (reconstruction warp, no ground truth needed; cross-check against "
         f"rms_dz in the board-frame report): {plane_rms:.2f} mm")

    scatter_path = save_board_scatter(idx, tri, extrinsics_tag, mean_z)
    hist_path = save_error_histogram(idx, err, extrinsics_tag, mean_z)
    emit(f"  Saved {scatter_path}  (blunder check only)")
    emit(f"  Saved {hist_path}")
    emit("")

    return {
        "idx": idx, "mean_z": mean_z,
        "bias_mm": bias_mm, "scatter_mm": scatter_mm, "rms_mm": rms_mm, "p95_mm": p95_mm,
        "abs_mean_mm": abs_mean_mm, "max_abs_mm": max_abs_mm,
        "bias_pct": bias_pct, "scatter_pct": scatter_pct, "rms_pct": rms_pct, "p95_pct": p95_pct,
        "adj_mean": adj_mean, "adj_max": adj_max,
        "furthest_true": furthest_true, "furthest_tri": furthest_tri, "furthest_err": furthest_err,
        "plane_rms": plane_rms,
    }


def save_relative_summary_plots(board_results, extrinsics_tag):
    ordered = sorted(board_results, key=lambda r: r["mean_z"])
    depths = [r["mean_z"] for r in ordered]
    labels = [r["idx"] for r in ordered]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(depths, [r["bias_mm"] for r in ordered], "-o", label="bias (signed mean)")
    ax.plot(depths, [r["scatter_mm"] for r in ordered], "-o", label="scatter (std)")
    ax.axhline(0, color="black", linewidth=0.8, linestyle=":", alpha=0.6)
    for x, y, lbl in zip(depths, [r["bias_mm"] for r in ordered], labels):
        ax.annotate(lbl, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("board depth, mean Z (mm, cam0/right frame)")
    ax.set_ylabel("corner-pair distance error (mm)")
    ax.set_title(f"Distance error (bias & scatter) vs board depth - extrinsics: {extrinsics_tag}")
    ax.legend()
    ax.grid(alpha=0.3)
    err_path = RELATIVE_DIR / f"summary_error_vs_depth_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(err_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(depths, [r["plane_rms"] for r in ordered], "-o", color="tab:purple")
    for x, y, lbl in zip(depths, [r["plane_rms"] for r in ordered], labels):
        ax.annotate(lbl, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("board depth, mean Z (mm, cam0/right frame)")
    ax.set_ylabel("plane-fit residual RMS (mm)")
    ax.set_title(f"Plane-fit residual vs board depth - extrinsics: {extrinsics_tag}")
    ax.grid(alpha=0.3)
    plane_path = RELATIVE_DIR / f"summary_planeresidual_vs_depth_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(plane_path, dpi=150)
    plt.close(fig)

    return err_path, plane_path


# ---- per-board analysis: board-frame -----------------------------------------------

def analyze_board_frame(idx, tri, mean_z, plane_rms, extrinsics_tag, emit):
    """
    Fit camera-frame triangulated corners `tri` (77,3) onto the known board
    grid OBJP two ways - RIGID (Kabsch) and SIMILARITY (Umeyama, +scale) - to
    separate SCALE error from WARP/local scatter. See module docstring NOTE:
    self-referential for absolute board pose, NOT an absolute-position check.
    """
    R_rigid, t_rigid, _ = umeyama_alignment(tri, OBJP, with_scale=False)
    resid_rigid = apply_similarity(tri, R_rigid, t_rigid, 1.0) - OBJP
    rigid_rms_mm = float(np.sqrt(np.mean(np.sum(resid_rigid ** 2, axis=1))))

    R_sim, t_sim, s_sim = umeyama_alignment(tri, OBJP, with_scale=True)
    resid_sim = apply_similarity(tri, R_sim, t_sim, s_sim) - OBJP
    sim_rms_mm = float(np.sqrt(np.mean(np.sum(resid_sim ** 2, axis=1))))
    rms_dx_mm = float(np.sqrt(np.mean(resid_sim[:, 0] ** 2)))
    rms_dy_mm = float(np.sqrt(np.mean(resid_sim[:, 1] ** 2)))
    rms_dz_mm = float(np.sqrt(np.mean(resid_sim[:, 2] ** 2)))
    scale_error_pct = (s_sim - 1.0) * 100.0

    label = NOMINAL_DEPTH_LABEL.get(idx, "")
    emit(f"--- Board {idx}  (nominal depth {label}, measured mean Z = {mean_z:.0f} mm) "
         f"[extrinsics: {extrinsics_tag}] ---")
    emit(f"  Rigid (Kabsch) fit: RMS 3D residual = {rigid_rms_mm:.2f} mm (scale error + warp combined)")
    emit(f"  Similarity (Umeyama) fit: fitted scale s = {s_sim:.4f}  ->  scale_error = "
         f"{scale_error_pct:+.2f}% "
         f"({'reconstruction too LARGE' if scale_error_pct >= 0 else 'reconstruction too SMALL'})")
    emit("  Per-axis RMS residual after similarity fit (board frame - scatter only, NOT bias; see NOTE):")
    emit(f"    rms_dx (along columns, in-plane) = {rms_dx_mm:.2f} mm")
    emit(f"    rms_dy (along rows, in-plane)    = {rms_dy_mm:.2f} mm")
    emit(f"    rms_dz (out-of-plane / warp)     = {rms_dz_mm:.2f} mm   "
         f"(cross-check vs plane-fit residual = {plane_rms:.2f} mm - should agree)")
    emit(f"  Overall RMS residual after similarity fit (warp/scatter only): {sim_rms_mm:.2f} mm")
    emit(f"  (Rigid RMS {rigid_rms_mm:.2f} mm vs similarity RMS {sim_rms_mm:.2f} mm - the gap "
         f"isolates the pure-scale contribution)")
    emit("  NOTE: after a Kabsch/similarity fit the per-axis SIGNED MEAN (bias) is ~0 by construction")
    emit("  (the fit re-centres the point cloud) - so no board-frame per-axis BIAS is reported here,")
    emit("  only RMS scatter. The meaningful SYSTEMATIC term is the fitted SCALE; the meaningful RANDOM")
    emit("  term is the per-axis RMS scatter (dz = warp). This measures SCALE + WARP + local scatter and")
    emit("  is frame-invariant / not circular for those. It IS self-referential for absolute board POSE")
    emit("  (fit to this same board's own grid), so this is NOT an absolute-position validation.")

    quiver_path = save_residual_quiver(idx, resid_sim, extrinsics_tag, mean_z)
    emit(f"  Saved {quiver_path}")
    emit("")

    return {
        "idx": idx, "mean_z": mean_z,
        "sim_rms_mm": sim_rms_mm, "rms_dx_mm": rms_dx_mm, "rms_dy_mm": rms_dy_mm, "rms_dz_mm": rms_dz_mm,
        "scale_error_pct": scale_error_pct, "rigid_rms_mm": rigid_rms_mm, "plane_rms_mm": plane_rms,
    }


def emit_scale_consistency(board_results, extrinsics_tag, emit):
    """
    A single board's fitted scale is a short-lever, local, noisy estimate and
    must NOT be over-read on its own - only agreement ACROSS boards (same
    sign, similar magnitude) is meaningful evidence of a real global
    scale/calibration error, as opposed to per-board noise.
    """
    ordered = sorted(board_results, key=lambda r: r["mean_z"])
    scales = [r["scale_error_pct"] for r in ordered]
    ids = [r["idx"] for r in ordered]

    emit("-" * 78)
    emit(f"CROSS-BOARD SCALE CONSISTENCY CHECK - extrinsics: {extrinsics_tag}")
    emit("-" * 78)
    emit("  A single board's fitted scale is a short-lever, local, noisy estimate - do NOT over-read")
    emit("  it alone. Only cross-board consistency (same sign, similar magnitude) is meaningful.")
    for i, s in zip(ids, scales):
        emit(f"    {i}: scale_error = {s:+.2f}%")

    same_sign = all(s >= 0 for s in scales) or all(s <= 0 for s in scales)
    spread = max(scales) - min(scales)
    consistent = same_sign and spread <= SCALE_CONSISTENCY_SPREAD_TOL_PCT

    if consistent:
        emit(f"  VERDICT: CONSISTENT - all {len(scales)} boards agree in sign with similar magnitude "
             f"(spread={spread:.2f} pct-points <= {SCALE_CONSISTENCY_SPREAD_TOL_PCT} tolerance) -> "
             f"plausible REAL global scale/calibration error, worth investigating.")
    else:
        emit(f"  VERDICT: SCATTERED - signs and/or magnitudes disagree across boards "
             f"(spread={spread:.2f} pct-points) -> scale is most likely NOISE at the per-board level, "
             f"not evidence of a systematic issue.")
    emit("")
    return consistent


def save_board_frame_summary_plot(board_results, extrinsics_tag):
    ordered = sorted(board_results, key=lambda r: r["mean_z"])
    depths = [r["mean_z"] for r in ordered]
    labels = [r["idx"] for r in ordered]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(depths, [r["sim_rms_mm"] for r in ordered], "-o", label="sim_rms_mm (overall scatter)")
    ax.plot(depths, [r["rms_dz_mm"] for r in ordered], "-o", label="rms_dz_mm (warp)")
    for x, y, lbl in zip(depths, [r["sim_rms_mm"] for r in ordered], labels):
        ax.annotate(lbl, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("board depth, mean Z (mm, cam0/right frame)")
    ax.set_ylabel("RMS residual after similarity fit (mm)")
    ax.set_title(f"Board-frame scatter & warp vs board depth - extrinsics: {extrinsics_tag}")
    ax.legend()
    ax.grid(alpha=0.3)

    out_path = BOARD_FRAME_DIR / f"summary_vs_depth_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ---- CSV output --------------------------------------------------------------------

def write_csv(path, header, rows):
    """rows: iterable of sequences, same length/order as header."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


# ---- per-extrinsics analysis --------------------------------------------------------

def analyze_extrinsics(ext_path, boards, K0, D0, K1, D1, emit_rel, emit_bf):
    if not ext_path.is_file():
        raise FileNotFoundError(f"Extrinsics file not found: {ext_path}")
    ext = np.load(ext_path)
    R, T = ext["R"].astype(np.float64), ext["T"].astype(np.float64)
    tag = ext_path.parent.name

    for emit in (emit_rel, emit_bf):
        emit("=" * 78)
        emit(f"EXTRINSICS: {tag}  ({ext_path})")
        emit(f"R,T baseline |T| = {np.linalg.norm(T):.2f} mm")
        emit("=" * 78)
        emit("")

    rel_results, bf_results = [], []
    for idx, (c0, c1, path0, path1) in boards.items():
        tri = triangulate_points(c0, c1, K0, D0, K1, D1, R, T)  # (77, 3), cam0/right frame
        mean_z = float(tri[:, 2].mean())
        plane_rms = fit_plane_residual_rms(tri)

        rel_results.append(analyze_board_relative(idx, tri, mean_z, plane_rms, tag, emit_rel))
        bf_results.append(analyze_board_frame(idx, tri, mean_z, plane_rms, tag, emit_bf))

    emit_rel("-" * 78)
    emit_rel(f"POOLED SUMMARY (relative-distance) - extrinsics: {tag}")
    emit_rel("-" * 78)
    emit_rel(f"  {'board':<10} | {'depth_mm':>9} | {'bias_mm':>9} | {'scatter_mm':>10} | {'RMS_mm':>8} | "
              f"{'p95_mm':>8} | {'plane_rms_mm':>12}")
    for r in sorted(rel_results, key=lambda r: r["mean_z"]):
        emit_rel(f"  {r['idx']:<10} | {r['mean_z']:9.0f} | {r['bias_mm']:+9.2f} | {r['scatter_mm']:10.2f} | "
                  f"{r['rms_mm']:8.2f} | {r['p95_mm']:8.2f} | {r['plane_rms']:12.2f}")
    emit_rel("")
    err_path, plane_path = save_relative_summary_plots(rel_results, tag)
    emit_rel(f"Saved {err_path}")
    emit_rel(f"Saved {plane_path}")
    emit_rel("")

    emit_bf("-" * 78)
    emit_bf(f"POOLED SUMMARY (board-frame) - extrinsics: {tag}")
    emit_bf("-" * 78)
    emit_bf(f"  {'board':<10} | {'depth_mm':>9} | {'sim_rms_mm':>10} | {'rms_dx_mm':>9} | "
             f"{'rms_dy_mm':>9} | {'rms_dz_mm':>9} | {'scale_error_pct':>15} | {'rigid_rms_mm':>12} | "
             f"{'plane_rms_mm':>12}")
    for r in sorted(bf_results, key=lambda r: r["mean_z"]):
        emit_bf(f"  {r['idx']:<10} | {r['mean_z']:9.0f} | {r['sim_rms_mm']:10.2f} | {r['rms_dx_mm']:9.2f} | "
                 f"{r['rms_dy_mm']:9.2f} | {r['rms_dz_mm']:9.2f} | {r['scale_error_pct']:+15.2f} | "
                 f"{r['rigid_rms_mm']:12.2f} | {r['plane_rms_mm']:12.2f}")
    emit_bf("")
    pooled_csv_path = write_csv(
        BOARD_FRAME_DIR / f"pooled_summary_{tag}.csv",
        ["board", "depth_mm", "sim_rms_mm", "rms_dx_mm", "rms_dy_mm", "rms_dz_mm",
         "scale_error_pct", "rigid_rms_mm", "plane_rms_mm"],
        [(r["idx"], r["mean_z"], r["sim_rms_mm"], r["rms_dx_mm"], r["rms_dy_mm"], r["rms_dz_mm"],
          r["scale_error_pct"], r["rigid_rms_mm"], r["plane_rms_mm"])
         for r in sorted(bf_results, key=lambda r: r["mean_z"])],
    )
    emit_bf(f"Saved {pooled_csv_path}")
    emit_scale_consistency(bf_results, tag, emit_bf)
    summary_path = save_board_frame_summary_plot(bf_results, tag)
    emit_bf(f"Saved {summary_path}")
    emit_bf("")

    return tag, rel_results, bf_results


# ---- main -------------------------------------------------------------------------

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extrinsics", action="append", default=None, metavar="PATH",
                     help="Path to a stereo_extrinsic.npz to validate. May be passed more than "
                          "once to compare solves side by side. Default: both the 2026-07-11 and "
                          "2026-07-12 session solves.")
    ap.add_argument("--validation-dir", default=str(VALIDATION_DIR),
                     help=f"Folder containing cam0/ and cam1/ held-out board pairs (default: {VALIDATION_DIR})")
    ap.add_argument("--results-dir", default=str(RESULTS_DIR),
                     help=f"Parent folder for results/corner_debug, results/relative_distance and "
                          f"results/board_frame subfolders (default: {RESULTS_DIR})")
    return ap.parse_args()


def main():
    global VALIDATION_DIR, CAM0_DIR, CAM1_DIR
    global RESULTS_DIR, CORNER_DEBUG_DIR, RELATIVE_DIR, BOARD_FRAME_DIR
    global RELATIVE_REPORT_PATH, BOARD_FRAME_REPORT_PATH

    args = parse_args()
    VALIDATION_DIR = Path(args.validation_dir).resolve()
    CAM0_DIR = VALIDATION_DIR / "cam0"
    CAM1_DIR = VALIDATION_DIR / "cam1"
    RESULTS_DIR = Path(args.results_dir).resolve()
    CORNER_DEBUG_DIR = RESULTS_DIR / "corner_debug"
    RELATIVE_DIR = RESULTS_DIR / "relative_distance"
    BOARD_FRAME_DIR = RESULTS_DIR / "board_frame"
    RELATIVE_REPORT_PATH = RELATIVE_DIR / "checkerboard_triangulation_validation.txt"
    BOARD_FRAME_REPORT_PATH = BOARD_FRAME_DIR / "board_frame_validation.txt"
    for d in (CORNER_DEBUG_DIR, RELATIVE_DIR, BOARD_FRAME_DIR):
        d.mkdir(parents=True, exist_ok=True)

    extrinsics_paths = [Path(p) for p in args.extrinsics] if args.extrinsics else DEFAULT_EXTRINSICS
    extrinsics_paths = [p if p.is_absolute() else (ROOT / p) for p in extrinsics_paths]

    report_rel, report_bf = [], []

    def emit_rel(line: str = "") -> None:
        print(line)
        report_rel.append(line)

    def emit_bf(line: str = "") -> None:
        print(line)
        report_bf.append(line)

    def emit_both(line: str = "") -> None:
        print(line)
        report_rel.append(line)
        report_bf.append(line)

    emit_both(f"Checkerboard: {PATTERN_SIZE[0]}x{PATTERN_SIZE[1]} internal corners, "
              f"square size = {SQUARE_SIZE_MM} mm (caliper-measured)")
    emit_both(f"Validation images: {VALIDATION_DIR}")
    emit_both(f"Extrinsics under test: {[str(p) for p in extrinsics_paths]}")
    emit_both("")

    K0, D0 = load_intrinsics(INTRINSICS_DIR / "cam0_intrinsics_fisheye.npz", "cam0 (right)")
    K1, D1 = load_intrinsics(INTRINSICS_DIR / "cam1_intrinsics_fisheye.npz", "cam1 (left)")
    emit_both("")

    pairs = find_matched_pairs(CAM0_DIR, CAM1_DIR)
    if not pairs:
        raise FileNotFoundError(f"No matched img_*.png pairs found in {CAM0_DIR} and {CAM1_DIR}")
    emit_both(f"Found {len(pairs)} matched board(s): {[idx for idx, _, _ in pairs]}")
    emit_both("")

    # -- Detection + corner-order safety, once per board -------------------------
    # Reference extrinsics for the order-check is the FIRST one passed - the
    # ordering decision must be identical across all extrinsics files evaluated
    # below for the old-vs-new comparison to be apples-to-apples (see module
    # docstring).
    if not extrinsics_paths[0].is_file():
        raise FileNotFoundError(f"Extrinsics file not found: {extrinsics_paths[0]}")
    ref_ext = np.load(extrinsics_paths[0])
    ref_R = ref_ext["R"].astype(np.float64)
    ref_T = ref_ext["T"].astype(np.float64)

    emit_both("=" * 78)
    emit_both("CORNER DETECTION + ORDER-SAFETY CHECK "
              f"(reference extrinsics: {extrinsics_paths[0].parent.name})")
    emit_both("=" * 78)

    boards = {}
    for idx, path0, path1 in pairs:
        g0 = cv2.imread(str(path0), cv2.IMREAD_GRAYSCALE)
        g1 = cv2.imread(str(path1), cv2.IMREAD_GRAYSCALE)
        if g0 is None or g1 is None:
            emit_both(f"{idx}: SKIPPED (could not read image)")
            continue

        found0, c0 = detect_corners(g0)
        found1, c1 = detect_corners(g1)
        if not (found0 and found1):
            missing = [n for n, f in (("cam0", found0), ("cam1", found1)) if not f]
            emit_both(f"{idx}: SKIPPED (board not found in {', '.join(missing)})")
            continue

        plausible, best = choose_corner_order(c0, c1, K0, D0, K1, D1, ref_R, ref_T)
        if not plausible:
            emit_both(f"WARNING: {idx}: SKIPPED (ambiguous corner correspondence - best hypothesis "
                      f"'{best['label']}' still disagrees with the known rig: rotation diff="
                      f"{best['rot_diff']:.2f} deg, baseline diff={best['baseline_pct']:.1f}%, "
                      f"tolerance is {POSE_OUTLIER_ANGLE_DEG} deg / {POSE_OUTLIER_BASELINE_PCT}%)")
            continue

        c1_final = best["corners"]
        if best["label"] == "reversed":
            emit_both(f"NOTE: {idx}: corner order REVERSED in cam1 to match cam0 (180-degree flip "
                      f"detected; corrected hypothesis: rotation diff={best['rot_diff']:.2f} deg, "
                      f"baseline diff={best['baseline_pct']:.1f}%)")
        else:
            emit_both(f"{idx}: KEPT (rotation diff={best['rot_diff']:.2f} deg, "
                      f"baseline diff={best['baseline_pct']:.1f}% vs reference rig)")

        save_corner_debug(idx, path0, path1, c0, c1_final)
        boards[idx] = (c0.astype(np.float64), c1_final.astype(np.float64), path0, path1)

    emit_both("")
    emit_both(f"Kept {len(boards)}/{len(pairs)} board(s) for analysis.")
    emit_both("")
    if len(boards) == 0:
        raise SystemExit("No boards survived detection + corner-order safety check - nothing to analyze.")

    # -- Per-extrinsics analysis ---------------------------------------------------
    all_rel = {}  # tag -> {board_idx: result_dict}
    all_bf = {}
    for ext_path in extrinsics_paths:
        tag, rel_results, bf_results = analyze_extrinsics(ext_path, boards, K0, D0, K1, D1, emit_rel, emit_bf)
        all_rel[tag] = {r["idx"]: r for r in rel_results}
        all_bf[tag] = {r["idx"]: r for r in bf_results}

    # -- Final cross-extrinsics comparison: relative-distance ----------------------
    if len(all_rel) >= 2:
        tags = list(all_rel.keys())
        emit_rel("=" * 78)
        emit_rel("FINAL CROSS-EXTRINSICS COMPARISON (relative-distance)")
        emit_rel("=" * 78)
        baseline_tag, compare_tag = tags[0], tags[-1]
        board_ids = sorted(boards.keys(), key=lambda idx: all_rel[baseline_tag][idx]["mean_z"])

        header = f"  {'board':<10} | {'depth_mm':>9}"
        for t in tags:
            header += (f" | {t + ' bias_mm':>16} | {t + ' scatter_mm':>18} | {t + ' RMS_mm':>14} | "
                       f"{t + ' p95_mm':>14}")
        emit_rel(header)
        for idx in board_ids:
            depth = all_rel[tags[0]][idx]["mean_z"]
            row = f"  {idx:<10} | {depth:9.0f}"
            for t in tags:
                r = all_rel[t][idx]
                row += (f" | {r['bias_mm']:+16.2f} | {r['scatter_mm']:18.2f} | {r['rms_mm']:14.2f} | "
                        f"{r['p95_mm']:14.2f}")
            emit_rel(row)
        emit_rel("")

        # "Deep" = the two boards with the greatest MEASURED depth under the baseline
        # extrinsics - not the nominal ~5m label (see module note: nominal depths are
        # for labelling only, never for gating logic).
        deep_boards = board_ids[-2:]
        emit_rel(f"Deep-board check ({', '.join(deep_boards)}), '{compare_tag}' vs '{baseline_tag}' "
                 f"(positive delta = improvement):")
        rms_deltas, bias_deltas = [], []
        for idx in deep_boards:
            base = all_rel[baseline_tag][idx]
            comp = all_rel[compare_tag][idx]
            d_rms = base["rms_mm"] - comp["rms_mm"]
            d_bias = abs(base["bias_mm"]) - abs(comp["bias_mm"])
            rms_deltas.append(d_rms)
            bias_deltas.append(d_bias)
            emit_rel(f"  {idx} (depth {base['mean_z']:.0f} mm): RMS delta={d_rms:+.2f} mm, "
                     f"|bias| delta={d_bias:+.2f} mm  "
                     f"[{baseline_tag}: RMS={base['rms_mm']:.2f} mm, bias={base['bias_mm']:+.2f} mm  ->  "
                     f"{compare_tag}: RMS={comp['rms_mm']:.2f} mm, bias={comp['bias_mm']:+.2f} mm]")
        emit_rel("")

        rms_improved_both = all(d > 0 for d in rms_deltas)
        bias_improved_both = all(d > 0 for d in bias_deltas)
        rms_worse_both = all(d < 0 for d in rms_deltas)
        bias_worse_both = all(d < 0 for d in bias_deltas)

        if rms_improved_both and bias_improved_both:
            emit_rel(f"VERDICT: '{compare_tag}' reduces both RMS and |bias| on both deep (~5m) boards vs "
                     f"'{baseline_tag}' - clear improvement at depth.")
        elif rms_worse_both and bias_worse_both:
            emit_rel(f"VERDICT: '{compare_tag}' is worse on both RMS and |bias| on both deep (~5m) boards "
                     f"vs '{baseline_tag}' - clear regression at depth.")
        else:
            emit_rel(f"VERDICT: mixed - it's a wash. '{compare_tag}' does NOT consistently reduce both RMS "
                     f"and |bias| across both deep boards vs '{baseline_tag}' (see the per-board deltas "
                     f"above). Do not read a single board's number as the final word.")
        emit_rel("=" * 78)

    # -- Final cross-extrinsics comparison: board-frame -----------------------------
    if len(all_bf) >= 2:
        tags = list(all_bf.keys())
        emit_bf("=" * 78)
        emit_bf("FINAL CROSS-EXTRINSICS COMPARISON (board-frame)")
        emit_bf("=" * 78)
        baseline_tag, compare_tag = tags[0], tags[-1]
        board_ids = sorted(boards.keys(), key=lambda idx: all_bf[baseline_tag][idx]["mean_z"])

        header = f"  {'board':<10} | {'depth_mm':>9}"
        for t in tags:
            header += (f" | {t + ' sim_rms_mm':>16} | {t + ' rms_dz_mm':>15} | "
                       f"{t + ' scale_error_pct':>19}")
        emit_bf(header)
        for idx in board_ids:
            depth = all_bf[tags[0]][idx]["mean_z"]
            row = f"  {idx:<10} | {depth:9.0f}"
            for t in tags:
                r = all_bf[t][idx]
                row += (f" | {r['sim_rms_mm']:16.2f} | {r['rms_dz_mm']:15.2f} | "
                        f"{r['scale_error_pct']:+19.2f}")
            emit_bf(row)
        emit_bf("")

        csv_header = ["board", "depth_mm"]
        for t in tags:
            csv_header += [f"{t}_sim_rms_mm", f"{t}_rms_dz_mm", f"{t}_scale_error_pct"]
        csv_rows = []
        for idx in board_ids:
            row_vals = [idx, all_bf[tags[0]][idx]["mean_z"]]
            for t in tags:
                r = all_bf[t][idx]
                row_vals += [r["sim_rms_mm"], r["rms_dz_mm"], r["scale_error_pct"]]
            csv_rows.append(row_vals)
        cross_csv_path = write_csv(BOARD_FRAME_DIR / "cross_extrinsics_comparison.csv", csv_header, csv_rows)
        emit_bf(f"Saved {cross_csv_path}")
        emit_bf("")

        # Focus on the two DEEPEST boards by MEASURED mean-Z (baseline extrinsics),
        # never the nominal ~5m label - see module note on not gating logic on it.
        deep_boards = board_ids[-2:]
        emit_bf(f"Deep-board check ({', '.join(deep_boards)}), '{compare_tag}' vs '{baseline_tag}' "
                f"(positive delta = improvement, i.e. RMS/|scale error| went down):")
        sim_rms_deltas, dz_deltas, scale_deltas = [], [], []
        for idx in deep_boards:
            base = all_bf[baseline_tag][idx]
            comp = all_bf[compare_tag][idx]
            d_sim = base["sim_rms_mm"] - comp["sim_rms_mm"]
            d_dz = base["rms_dz_mm"] - comp["rms_dz_mm"]
            d_scale = abs(base["scale_error_pct"]) - abs(comp["scale_error_pct"])
            sim_rms_deltas.append(d_sim)
            dz_deltas.append(d_dz)
            scale_deltas.append(d_scale)
            emit_bf(f"  {idx} (depth {base['mean_z']:.0f} mm): sim_rms delta={d_sim:+.2f} mm, "
                    f"rms_dz delta={d_dz:+.2f} mm, |scale_error| delta={d_scale:+.2f} pct-points  "
                    f"[{baseline_tag}: sim_rms={base['sim_rms_mm']:.2f} mm, rms_dz={base['rms_dz_mm']:.2f} mm, "
                    f"scale={base['scale_error_pct']:+.2f}%  ->  "
                    f"{compare_tag}: sim_rms={comp['sim_rms_mm']:.2f} mm, rms_dz={comp['rms_dz_mm']:.2f} mm, "
                    f"scale={comp['scale_error_pct']:+.2f}%]")
        emit_bf("")

        sim_improved_both = all(d > 0 for d in sim_rms_deltas)
        sim_worse_both = all(d < 0 for d in sim_rms_deltas)
        dz_improved_both = all(d > 0 for d in dz_deltas)
        dz_worse_both = all(d < 0 for d in dz_deltas)

        if sim_improved_both and dz_improved_both:
            emit_bf(f"VERDICT: '{compare_tag}' reduces both overall scatter (sim_rms) and warp (rms_dz) "
                     f"on both deep boards vs '{baseline_tag}' - clear improvement at depth.")
        elif sim_worse_both and dz_worse_both:
            emit_bf(f"VERDICT: '{compare_tag}' is worse on both scatter and warp on both deep boards vs "
                     f"'{baseline_tag}' - clear regression at depth.")
        else:
            emit_bf(f"VERDICT: mixed - it's a wash. '{compare_tag}' does NOT consistently reduce both "
                     f"scatter (sim_rms) and warp (rms_dz) across both deep boards vs '{baseline_tag}' "
                     f"(see the per-board deltas above). Do not cherry-pick a single improved board.")
        emit_bf("=" * 78)

    RELATIVE_REPORT_PATH.write_text("\n".join(report_rel) + "\n")
    BOARD_FRAME_REPORT_PATH.write_text("\n".join(report_bf) + "\n")
    print(f"\nRelative-distance report written to {RELATIVE_REPORT_PATH}")
    print(f"Board-frame report written to {BOARD_FRAME_REPORT_PATH}")


if __name__ == "__main__":
    main()
