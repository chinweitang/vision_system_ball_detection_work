"""
Validate stereo triangulation accuracy against checkerboard ground truth, at
real operating depth, using held-out boards that were NOT part of the
extrinsic calibration. A checkerboard's corner spacing is exact ground truth
(caliper-measured 67.5mm), so triangulated corner-to-corner distances can be
checked directly against true distances - inter-point distances are
frame-invariant, so no camera->floor (Kabsch) transform is needed. Same logic
as src/registration/validate_triangulation.py, but uses auto-detected
checkerboard corners instead of manually-clicked points, and runs once per
extrinsics solve so old vs new can be compared side by side.

Does NOT solve any camera->floor transform. Distances only.

Reuses (does not reimplement) from src/calibration/extrinsic/solve_extrinsic.py:
    PATTERN_SIZE, SQUARE_SIZE_MM, OBJP, detect_corners(), load_intrinsics(),
    mono_solve_pose(), POSE_OUTLIER_ANGLE_DEG, POSE_OUTLIER_BASELINE_PCT
and from src/stereo/triangulate.py: triangulate_points().

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
    checkerboard_triangulation_validation.txt   (full report, all extrinsics + comparison)
    corner_debug_<idx>_cam0.png / _cam1.png     (corner 0 / corner -1 marked, once per board)
    scatter_<idx>_<extrinsics_tag>.png          (per-board 3D scatter + grid mesh)
    hist_<idx>_<extrinsics_tag>.png             (per-board signed distance-error histogram;
                                                  bias = center, scatter = width)
    summary_error_vs_depth_<extrinsics_tag>.png       (bias & scatter vs depth)
    summary_planeresidual_vs_depth_<extrinsics_tag>.png
"""

import argparse
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
REPORT_PATH = RESULTS_DIR / "checkerboard_triangulation_validation.txt"

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
    same style as solve_extrinsic.save_corner0_debug()."""
    img0 = cv2.imread(str(path0))
    img1 = cv2.imread(str(path1))
    out0 = RESULTS_DIR / f"corner_debug_{idx}_cam0.png"
    out1 = RESULTS_DIR / f"corner_debug_{idx}_cam1.png"
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
    Umeyama (1991) closed-form least-squares similarity fit via SVD: finds
    R, t, (s) minimizing sum_i || s * R @ src_i + t - dst_i ||^2.
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


def board_frame_analysis(tri, emit):
    """
    Fit camera-frame triangulated corners `tri` (77,3) to the known board grid
    OBJP two ways - RIGID (Umeyama, s fixed at 1) and SIMILARITY (Umeyama with
    a free global scale) - and report the fitted scale plus per-axis (board
    frame: x/y in-plane along the grid, z out-of-plane) RMS residual after the
    similarity fit. See the module NOTE on this being a scale/warp diagnostic,
    not an absolute-position validation (it fits to this same board).
    """
    R_rigid, t_rigid, _ = umeyama_alignment(tri, OBJP, with_scale=False)
    resid_rigid = apply_similarity(tri, R_rigid, t_rigid, 1.0) - OBJP
    rms_rigid = float(np.sqrt(np.mean(np.sum(resid_rigid ** 2, axis=1))))

    R_sim, t_sim, s_sim = umeyama_alignment(tri, OBJP, with_scale=True)
    resid_sim = apply_similarity(tri, R_sim, t_sim, s_sim) - OBJP
    rms_sim = float(np.sqrt(np.mean(np.sum(resid_sim ** 2, axis=1))))
    rms_dx = float(np.sqrt(np.mean(resid_sim[:, 0] ** 2)))
    rms_dy = float(np.sqrt(np.mean(resid_sim[:, 1] ** 2)))
    rms_dz = float(np.sqrt(np.mean(resid_sim[:, 2] ** 2)))
    scale_pct = (s_sim - 1.0) * 100.0

    emit("  Board-frame fit (camera-frame triangulated corners -> known board grid):")
    emit(f"    Fitted scale (similarity fit) s = {s_sim:.4f}  ->  triangulated distances are "
         f"{scale_pct:+.2f}% {'long' if scale_pct >= 0 else 'short'}")
    emit(f"    Per-axis RMS residual after similarity fit (board frame): "
         f"dx(in-plane)={rms_dx:.2f} mm, dy(in-plane)={rms_dy:.2f} mm, dz(out-of-plane/warp)={rms_dz:.2f} mm")
    emit(f"    Overall RMS residual: similarity fit={rms_sim:.2f} mm, rigid-only fit={rms_rigid:.2f} mm "
         f"(gap between the two isolates the pure-scale contribution)")
    emit("    NOTE: this measures SCALE + WARP and is frame-invariant / not circular for those; it is "
         "self-referential for absolute board POSE (fit to this same board), so it is NOT an "
         "absolute-position validation.")

    return {
        "scale_pct": scale_pct, "s_sim": s_sim,
        "rms_dx": rms_dx, "rms_dy": rms_dy, "rms_dz": rms_dz,
        "rms_sim": rms_sim, "rms_rigid": rms_rigid,
    }


def save_error_histogram(idx, err_mm, extrinsics_tag, mean_z):
    """Signed distance-error histogram - the headline diagnostic: center = bias, width = scatter."""
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

    out_path = RESULTS_DIR / f"hist_{idx}_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def save_board_scatter(idx, tri, extrinsics_tag, mean_z):
    """3D scatter of the 77 triangulated corners, with grid mesh lines drawn
    from the known (col,row) structure so a bent board is easy to spot."""
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
    ax.set_title(f"Triangulated checkerboard corners - {idx} ({label})\n"
                 f"extrinsics: {extrinsics_tag}, measured mean Z = {mean_z:.0f} mm")

    max_range = np.array([xs.max() - xs.min(), ys.max() - ys.min(), zs.max() - zs.min()]).max() / 2.0
    max_range = max(max_range, 1.0)
    mid_x, mid_y, mid_z = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2, (zs.max() + zs.min()) / 2
    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)

    out_path = RESULTS_DIR / f"scatter_{idx}_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


# ---- per-board analysis -----------------------------------------------------------

def analyze_board(idx, c0, c1, K0, D0, K1, D1, R, T, extrinsics_tag, emit):
    tri = triangulate_points(c0, c1, K0, D0, K1, D1, R, T)  # (77, 3), cam0/right frame

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

    plane_rms = fit_plane_residual_rms(tri)
    mean_z = float(tri[:, 2].mean())

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
    emit(f"  Plane-fit residual RMS (reconstruction warp, no ground truth needed): {plane_rms:.2f} mm")

    board_frame = board_frame_analysis(tri, emit)

    scatter_path = save_board_scatter(idx, tri, extrinsics_tag, mean_z)
    hist_path = save_error_histogram(idx, err, extrinsics_tag, mean_z)
    emit(f"  Saved {scatter_path}")
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
        **board_frame,
    }


# ---- per-extrinsics pooled summary ------------------------------------------------

def save_summary_plots(board_results, extrinsics_tag):
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
    err_path = RESULTS_DIR / f"summary_error_vs_depth_{extrinsics_tag}.png"
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
    plane_path = RESULTS_DIR / f"summary_planeresidual_vs_depth_{extrinsics_tag}.png"
    plt.tight_layout()
    plt.savefig(plane_path, dpi=150)
    plt.close(fig)

    return err_path, plane_path


def analyze_extrinsics(ext_path, boards, K0, D0, K1, D1, emit):
    if not ext_path.is_file():
        raise FileNotFoundError(f"Extrinsics file not found: {ext_path}")
    ext = np.load(ext_path)
    R, T = ext["R"].astype(np.float64), ext["T"].astype(np.float64)
    tag = ext_path.parent.name

    emit("=" * 78)
    emit(f"EXTRINSICS: {tag}  ({ext_path})")
    emit(f"R,T baseline |T| = {np.linalg.norm(T):.2f} mm")
    emit("=" * 78)
    emit("")

    board_results = [
        analyze_board(idx, c0, c1, K0, D0, K1, D1, R, T, tag, emit)
        for idx, (c0, c1, path0, path1) in boards.items()
    ]

    emit("-" * 78)
    emit(f"POOLED SUMMARY - extrinsics: {tag}")
    emit("-" * 78)
    emit(f"  {'board':<10} | {'depth_mm':>9} | {'bias_mm':>9} | {'scatter_mm':>10} | {'RMS_mm':>8} | "
         f"{'p95_mm':>8} | {'fitted_scale_pct':>16} | {'plane_rms_mm':>12}")
    for r in sorted(board_results, key=lambda r: r["mean_z"]):
        emit(f"  {r['idx']:<10} | {r['mean_z']:9.0f} | {r['bias_mm']:+9.2f} | {r['scatter_mm']:10.2f} | "
             f"{r['rms_mm']:8.2f} | {r['p95_mm']:8.2f} | {r['scale_pct']:+16.2f} | {r['plane_rms']:12.2f}")
    emit("")

    err_path, plane_path = save_summary_plots(board_results, tag)
    emit(f"Saved {err_path}")
    emit(f"Saved {plane_path}")
    emit("")

    return tag, board_results


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
                     help=f"Folder to write the report and PNGs into (default: {RESULTS_DIR})")
    return ap.parse_args()


def main():
    global VALIDATION_DIR, CAM0_DIR, CAM1_DIR, RESULTS_DIR, REPORT_PATH

    args = parse_args()
    VALIDATION_DIR = Path(args.validation_dir).resolve()
    CAM0_DIR = VALIDATION_DIR / "cam0"
    CAM1_DIR = VALIDATION_DIR / "cam1"
    RESULTS_DIR = Path(args.results_dir).resolve()
    REPORT_PATH = RESULTS_DIR / "checkerboard_triangulation_validation.txt"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    extrinsics_paths = [Path(p) for p in args.extrinsics] if args.extrinsics else DEFAULT_EXTRINSICS
    extrinsics_paths = [p if p.is_absolute() else (ROOT / p) for p in extrinsics_paths]

    report = []

    def emit(line: str = "") -> None:
        print(line)
        report.append(line)

    emit(f"Checkerboard: {PATTERN_SIZE[0]}x{PATTERN_SIZE[1]} internal corners, "
         f"square size = {SQUARE_SIZE_MM} mm (caliper-measured)")
    emit(f"Validation images: {VALIDATION_DIR}")
    emit(f"Extrinsics under test: {[str(p) for p in extrinsics_paths]}")
    emit("")

    K0, D0 = load_intrinsics(INTRINSICS_DIR / "cam0_intrinsics_fisheye.npz", "cam0 (right)")
    K1, D1 = load_intrinsics(INTRINSICS_DIR / "cam1_intrinsics_fisheye.npz", "cam1 (left)")
    emit("")

    pairs = find_matched_pairs(CAM0_DIR, CAM1_DIR)
    if not pairs:
        raise FileNotFoundError(f"No matched img_*.png pairs found in {CAM0_DIR} and {CAM1_DIR}")
    emit(f"Found {len(pairs)} matched board(s): {[idx for idx, _, _ in pairs]}")
    emit("")

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

    emit("=" * 78)
    emit("CORNER DETECTION + ORDER-SAFETY CHECK "
         f"(reference extrinsics: {extrinsics_paths[0].parent.name})")
    emit("=" * 78)

    boards = {}
    anomalies = []
    for idx, path0, path1 in pairs:
        g0 = cv2.imread(str(path0), cv2.IMREAD_GRAYSCALE)
        g1 = cv2.imread(str(path1), cv2.IMREAD_GRAYSCALE)
        if g0 is None or g1 is None:
            line = f"{idx}: SKIPPED (could not read image)"
            emit(line)
            anomalies.append(line)
            continue

        found0, c0 = detect_corners(g0)
        found1, c1 = detect_corners(g1)
        if not (found0 and found1):
            missing = [n for n, f in (("cam0", found0), ("cam1", found1)) if not f]
            line = f"{idx}: SKIPPED (board not found in {', '.join(missing)})"
            emit(line)
            anomalies.append(line)
            continue

        plausible, best = choose_corner_order(c0, c1, K0, D0, K1, D1, ref_R, ref_T)
        if not plausible:
            line = (f"WARNING: {idx}: SKIPPED (ambiguous corner correspondence - best hypothesis "
                     f"'{best['label']}' still disagrees with the known rig: rotation diff="
                     f"{best['rot_diff']:.2f} deg, baseline diff={best['baseline_pct']:.1f}%, "
                     f"tolerance is {POSE_OUTLIER_ANGLE_DEG} deg / {POSE_OUTLIER_BASELINE_PCT}%)")
            emit(line)
            anomalies.append(line)
            continue

        c1_final = best["corners"]
        if best["label"] == "reversed":
            line = (f"NOTE: {idx}: corner order REVERSED in cam1 to match cam0 (180-degree flip detected; "
                     f"corrected hypothesis: rotation diff={best['rot_diff']:.2f} deg, "
                     f"baseline diff={best['baseline_pct']:.1f}%)")
            emit(line)
            anomalies.append(line)
        else:
            emit(f"{idx}: KEPT (rotation diff={best['rot_diff']:.2f} deg, "
                 f"baseline diff={best['baseline_pct']:.1f}% vs reference rig)")

        save_corner_debug(idx, path0, path1, c0, c1_final)
        boards[idx] = (c0.astype(np.float64), c1_final.astype(np.float64), path0, path1)

    emit("")
    emit(f"Kept {len(boards)}/{len(pairs)} board(s) for analysis.")
    emit("")
    if len(boards) == 0:
        raise SystemExit("No boards survived detection + corner-order safety check - nothing to analyze.")

    # -- Per-extrinsics analysis ---------------------------------------------------
    all_results = {}  # tag -> {board_idx: result_dict}
    for ext_path in extrinsics_paths:
        tag, board_results = analyze_extrinsics(ext_path, boards, K0, D0, K1, D1, emit)
        all_results[tag] = {r["idx"]: r for r in board_results}

    # -- Final cross-extrinsics comparison -----------------------------------------
    if len(all_results) >= 2:
        tags = list(all_results.keys())
        emit("=" * 78)
        emit("FINAL CROSS-EXTRINSICS COMPARISON")
        emit("=" * 78)
        baseline_tag, compare_tag = tags[0], tags[-1]
        board_ids = sorted(boards.keys(), key=lambda idx: all_results[baseline_tag][idx]["mean_z"])

        header = f"  {'board':<10} | {'depth_mm':>9}"
        for t in tags:
            header += (f" | {t + ' bias_mm':>16} | {t + ' scatter_mm':>18} | {t + ' RMS_mm':>14} | "
                       f"{t + ' p95_mm':>14} | {t + ' scale_pct':>16}")
        emit(header)
        for idx in board_ids:
            depth = all_results[tags[0]][idx]["mean_z"]
            row = f"  {idx:<10} | {depth:9.0f}"
            for t in tags:
                r = all_results[t][idx]
                row += (f" | {r['bias_mm']:+16.2f} | {r['scatter_mm']:18.2f} | {r['rms_mm']:14.2f} | "
                        f"{r['p95_mm']:14.2f} | {r['scale_pct']:+16.2f}")
            emit(row)
        emit("")

        # "Deep" = the two boards with the greatest MEASURED depth under the baseline
        # extrinsics - not the nominal ~5m label (see module note: nominal depths are
        # for labelling only, never for gating logic).
        deep_boards = board_ids[-2:]
        emit(f"Deep-board check ({', '.join(deep_boards)}), '{compare_tag}' vs '{baseline_tag}' "
             f"(positive delta = improvement):")
        rms_deltas, bias_deltas = [], []
        for idx in deep_boards:
            base = all_results[baseline_tag][idx]
            comp = all_results[compare_tag][idx]
            d_rms = base["rms_mm"] - comp["rms_mm"]
            d_bias = abs(base["bias_mm"]) - abs(comp["bias_mm"])
            rms_deltas.append(d_rms)
            bias_deltas.append(d_bias)
            emit(f"  {idx} (depth {base['mean_z']:.0f} mm): RMS delta={d_rms:+.2f} mm, "
                 f"|bias| delta={d_bias:+.2f} mm  "
                 f"[{baseline_tag}: RMS={base['rms_mm']:.2f} mm, bias={base['bias_mm']:+.2f} mm  ->  "
                 f"{compare_tag}: RMS={comp['rms_mm']:.2f} mm, bias={comp['bias_mm']:+.2f} mm]")
        emit("")

        rms_improved_both = all(d > 0 for d in rms_deltas)
        bias_improved_both = all(d > 0 for d in bias_deltas)
        rms_worse_both = all(d < 0 for d in rms_deltas)
        bias_worse_both = all(d < 0 for d in bias_deltas)

        if rms_improved_both and bias_improved_both:
            emit(f"VERDICT: '{compare_tag}' reduces both RMS and |bias| on both deep (~5m) boards vs "
                 f"'{baseline_tag}' - clear improvement at depth.")
        elif rms_worse_both and bias_worse_both:
            emit(f"VERDICT: '{compare_tag}' is worse on both RMS and |bias| on both deep (~5m) boards "
                 f"vs '{baseline_tag}' - clear regression at depth.")
        else:
            emit(f"VERDICT: mixed - it's a wash. '{compare_tag}' does NOT consistently reduce both RMS "
                 f"and |bias| across both deep boards vs '{baseline_tag}' (see the per-board deltas "
                 f"above). Do not read a single board's number as the final word.")
        emit("=" * 78)

    REPORT_PATH.write_text("\n".join(report) + "\n")
    print(f"\nFull report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
