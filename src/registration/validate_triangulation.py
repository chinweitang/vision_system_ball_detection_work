# validate_triangulation.py
# Validates world-registration triangulation against known ground-truth
# distances from reference_points.txt. Does NOT solve any camera->floor
# transform (Kabsch comes later, separately) - inter-point distances are
# frame-invariant, so triangulated distances (computed in the cam0/right
# CAMERA frame) can be checked directly against the true distances (given in
# the FLOOR frame) without needing that transform first. This is a metric
# accuracy check against independent ground truth, the same logic as the
# baseline-recovery check in solve_extrinsic.py.
#
# Usage:
#   python src/registration/validate_triangulation.py
#   python src/registration/validate_triangulation.py --exclude P8
#       (drop point(s) whose click isn't meaningful, e.g. not visible in one
#       camera, from triangulation and every table/plot below)

import argparse
import csv
import itertools
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.stereo.triangulate import triangulate_points

SESSION_DIR = ROOT / "data/2026_07_11_gym_session/world_registration"
REFERENCE_POINTS_FILE = SESSION_DIR / "reference_points.txt"
CAM0_CSV = SESSION_DIR / "cam0_points.csv"
CAM1_CSV = SESSION_DIR / "cam1_points.csv"

INTRINSICS_DIR = ROOT / "calibration_outputs"
EXTRINSICS_NPZ = ROOT / "calibration_outputs/2026_07_11_session/stereo_extrinsic.npz"

SCATTER_OUT = SESSION_DIR / "triangulated_scatter.png"
REPORT_OUT  = SESSION_DIR / "triangulation_validation.txt"

# Named pairs to spotlight: short in-row / mid in-row / long in-row / cross-row / diagonal.
# True distances are NOT hard-coded here - they're derived from reference_points.txt below.
NAMED_PAIRS = [("P1", "P2"), ("P3", "P5"), ("P1", "P6"), ("P2", "P7"), ("P1", "P10")]

# Physical layout from reference_points.txt (front row + back row + connecting rungs) -
# drawn as lines in the scatter plot purely so a bent row is easy to spot by eye.
ROW_FRONT = ["P1", "P2", "P3", "P4", "P5", "P6"]
ROW_BACK  = ["P7", "P8", "P9", "P10"]
RUNGS     = [("P2", "P7"), ("P3", "P8"), ("P4", "P9"), ("P5", "P10")]

# Verdict tolerances (soft guidance, not strict pass/fail): a named-pair error is
# flagged if it exceeds ~1% of the true distance, with a small-mm floor so short
# spans aren't held to an unrealistically tight absolute tolerance.
NAMED_PAIR_REL_TOL = 0.01   # ~1%
NAMED_PAIR_ABS_FLOOR_MM = 5.0
ALL_PAIRS_MAX_FLAG_MM = 30.0  # "tens of mm" on any single pair


# ---- loading ----------------------------------------------------------------

def load_reference_points(path: Path) -> dict:
    """Parse 'id x y z' rows (skip blanks / '#' comments), mm. Returns {id: np.array([x,y,z])}, file order."""
    points = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        pid, x, y, z = parts[0], float(parts[1]), float(parts[2]), float(parts[3])
        points[pid] = np.array([x, y, z], dtype=np.float64)
    return points


def load_clicks(path: Path) -> dict:
    """Return {point_id: (u, v)} from a labelling-tool CSV."""
    if not path.is_file():
        raise FileNotFoundError(f"Click CSV not found: {path}")
    with open(path, newline="") as f:
        return {r["point_id"]: (float(r["u"]), float(r["v"])) for r in csv.DictReader(f)}


def load_intrinsics(path: Path, label: str):
    if not path.is_file():
        raise FileNotFoundError(f"{label}: intrinsics file not found: {path}")
    data = np.load(path)
    return data["K"].astype(np.float64), data["D"].astype(np.float64)


# ---- plotting -----------------------------------------------------------------

def save_scatter(tri_by_id: dict, point_ids: list) -> None:
    """3D scatter of triangulated points (camera frame) - blunder check only, not accuracy."""
    xs = np.array([tri_by_id[pid][0] for pid in point_ids])
    ys = np.array([tri_by_id[pid][1] for pid in point_ids])
    zs = np.array([tri_by_id[pid][2] for pid in point_ids])

    fig = plt.figure(figsize=(9, 8))
    ax = fig.add_subplot(111, projection="3d")

    def line(ids, style):
        if not all(pid in tri_by_id for pid in ids):
            return  # one endpoint excluded - skip rather than draw a misleading chord across the gap
        pts = np.array([tri_by_id[pid] for pid in ids])
        ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], style, linewidth=1, alpha=0.6)

    line(ROW_FRONT, "b-")
    line(ROW_BACK, "b-")
    for a, b in RUNGS:
        line([a, b], "b--")

    ax.scatter(xs, ys, zs, c="red", s=40, depthshade=True)
    for pid in point_ids:
        x, y, z = tri_by_id[pid]
        ax.text(x, y, z, f"  {pid}", fontsize=9)

    ax.set_xlabel("X (mm, cam0/right frame)")
    ax.set_ylabel("Y (mm, cam0/right frame)")
    ax.set_zlabel("Z (mm, cam0/right frame)")
    ax.set_title("Triangulated world-registration points (cam0/right camera frame)\n"
                 "Blunder check only - NOT the floor-frame transform")

    # Equalize axis scales so shape (bent rows, flung points) isn't visually distorted.
    max_range = np.array([xs.max() - xs.min(), ys.max() - ys.min(), zs.max() - zs.min()]).max() / 2.0
    mid_x, mid_y, mid_z = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2, (zs.max() + zs.min()) / 2
    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(mid_y - max_range, mid_y + max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)

    SCATTER_OUT.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(SCATTER_OUT, dpi=150)
    plt.close(fig)


# ---- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Validate world-registration triangulation against ground truth.")
    ap.add_argument("--exclude", nargs="*", default=[], metavar="POINT_ID",
                     help="Point ID(s) to drop from triangulation/analysis entirely "
                          "(e.g. a point that isn't actually visible in one camera, "
                          "so its click is meaningless). Example: --exclude P8")
    args = ap.parse_args()
    exclude = set(args.exclude)

    report = []

    def emit(line: str = "") -> None:
        print(line)
        report.append(line)

    if not REFERENCE_POINTS_FILE.is_file():
        raise FileNotFoundError(f"Reference points file not found: {REFERENCE_POINTS_FILE}")
    ref = load_reference_points(REFERENCE_POINTS_FILE)
    point_ids = list(ref.keys())  # file order, e.g. P1..P10
    emit(f"Reference points: {len(point_ids)}  ({', '.join(point_ids)})")

    cam0_clicks = load_clicks(CAM0_CSV)
    cam1_clicks = load_clicks(CAM1_CSV)

    ref_set, cam0_set, cam1_set = set(point_ids), set(cam0_clicks), set(cam1_clicks)

    # Sanity checks always run against the FULL reference set, before any --exclude
    # is applied, so a genuinely missing click still fails loudly.
    if cam0_set != cam1_set:
        only0 = sorted(cam0_set - cam1_set)
        only1 = sorted(cam1_set - cam0_set)
        raise SystemExit(
            f"cam0/cam1 click CSVs do not contain the same point IDs.\n"
            f"  only in cam0: {only0}\n"
            f"  only in cam1: {only1}"
        )
    missing = sorted(ref_set - cam0_set)
    if missing:
        raise SystemExit(f"Missing click(s) for point ID(s): {missing} (need all of {point_ids})")
    extra = sorted(cam0_set - ref_set)
    if extra:
        raise SystemExit(f"Click CSVs contain point ID(s) not in reference_points.txt: {extra}")

    emit(f"cam0/cam1 click CSVs: {len(cam0_clicks)}/{len(point_ids)} points each, IDs match reference set. OK.")

    unknown_excludes = exclude - ref_set
    if unknown_excludes:
        raise SystemExit(f"--exclude point ID(s) not found in reference_points.txt: {sorted(unknown_excludes)}")
    if exclude:
        emit(f"Excluding by request (click not meaningful, e.g. not visible in one camera): "
             f"{', '.join(sorted(exclude))}")

    point_ids = [pid for pid in point_ids if pid not in exclude]
    emit("")

    # Order clicks by reference_points.txt order (P1..P10), NOT CSV row order - match by point_id.
    pts0 = np.array([cam0_clicks[pid] for pid in point_ids], dtype=np.float64)
    pts1 = np.array([cam1_clicks[pid] for pid in point_ids], dtype=np.float64)

    K0, D0 = load_intrinsics(INTRINSICS_DIR / "cam0_intrinsics_fisheye.npz", "cam0 (right)")
    K1, D1 = load_intrinsics(INTRINSICS_DIR / "cam1_intrinsics_fisheye.npz", "cam1 (left)")
    if not EXTRINSICS_NPZ.is_file():
        raise FileNotFoundError(f"Extrinsics file not found: {EXTRINSICS_NPZ}")
    ext = np.load(EXTRINSICS_NPZ)
    R, T = ext["R"].astype(np.float64), ext["T"].astype(np.float64)

    tri = triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)  # (N, 3), cam0/right camera frame
    tri_by_id = dict(zip(point_ids, tri))

    def true_dist(a, b):
        return float(np.linalg.norm(ref[a] - ref[b]))

    def tri_dist(a, b):
        return float(np.linalg.norm(tri_by_id[a] - tri_by_id[b]))

    # -- Step 3: named-pair table --------------------------------------------
    named_pairs_active = [(a, b) for a, b in NAMED_PAIRS if a not in exclude and b not in exclude]
    skipped_named = [(a, b) for a, b in NAMED_PAIRS if (a, b) not in named_pairs_active]
    if skipped_named:
        emit(f"Skipping named pair(s) involving an excluded point: {skipped_named}")
        emit("")

    emit("=" * 78)
    emit("NAMED-PAIR DISTANCE CHECK")
    emit("triangulated = camera-frame distance, true = floor-frame distance (frame-invariant)")
    emit("=" * 78)
    emit(f"  {'pair':<10} | {'triangulated_mm':>16} | {'true_mm':>10} | {'error_mm':>10} | {'error_pct':>10}")
    named_results = []
    for a, b in named_pairs_active:
        t_true = true_dist(a, b)
        t_tri = tri_dist(a, b)
        err = t_tri - t_true
        err_pct = 100.0 * err / t_true if t_true else float("nan")
        named_results.append((a, b, t_tri, t_true, err, err_pct))
        emit(f"  ({a},{b})".ljust(12) + f"| {t_tri:16.2f} | {t_true:10.2f} | {err:+10.2f} | {err_pct:+9.2f}%")
    emit("")

    # -- Step 4: per-axis breakdown for the two largest-error named pairs ---
    worst = sorted(named_results, key=lambda r: abs(r[4]), reverse=True)[:2]
    emit("Per-axis breakdown for the 2 largest-error named pairs:")
    emit("  NOTE: the triangulated vector is in the CAM0/RIGHT CAMERA frame; the true")
    emit("  distance is in the FLOOR frame. Per-axis components are NOT directly")
    emit("  comparable until the Kabsch floor-frame solve is done - only the")
    emit("  MAGNITUDES are comparable now. Per-axis is printed to see whether one")
    emit("  camera-frame axis (likely camera depth/Z) dominates the error.")
    for a, b, t_tri, t_true, err, err_pct in worst:
        vec = tri_by_id[b] - tri_by_id[a]
        emit(f"    ({a},{b}): cam-frame vector = "
             f"(x={vec[0]:+9.2f}, y={vec[1]:+9.2f}, z={vec[2]:+9.2f}) mm  "
             f"|vec|={np.linalg.norm(vec):9.2f} mm   true_mm={t_true:9.2f}")
    emit("")

    # -- Step 5: EVERY pair, plus the all-pairs summary ----------------------
    all_pairs = list(itertools.combinations(point_ids, 2))
    pair_rows = []
    for a, b in all_pairs:
        t_true = true_dist(a, b)
        t_tri = tri_dist(a, b)
        err = t_tri - t_true
        err_pct = 100.0 * err / t_true if t_true else float("nan")
        pair_rows.append((a, b, t_tri, t_true, err, err_pct))
    pair_rows.sort(key=lambda r: abs(r[4]), reverse=True)  # worst error first

    emit("=" * 78)
    emit(f"ALL-PAIRS DISTANCE CHECK ({len(all_pairs)} unique pairs, sorted worst-error-first)")
    emit("=" * 78)
    emit(f"  {'pair':<10} | {'triangulated_mm':>16} | {'true_mm':>10} | {'error_mm':>10} | {'error_pct':>10}")
    for a, b, t_tri, t_true, err, err_pct in pair_rows:
        emit(f"  ({a},{b})".ljust(12) + f"| {t_tri:16.2f} | {t_true:10.2f} | {err:+10.2f} | {err_pct:+9.2f}%")
    emit("")

    abs_errors = {(a, b): abs(err) for a, b, t_tri, t_true, err, err_pct in pair_rows}
    mean_abs = float(np.mean(list(abs_errors.values())))
    max_pair, max_abs = max(abs_errors.items(), key=lambda kv: kv[1])
    emit(f"  mean |error| = {mean_abs:.2f} mm")
    emit(f"  max  |error| = {max_abs:.2f} mm   at pair {max_pair}")

    # Per-point average error, to help point at a specific mis-clicked point
    # (rather than just the pair) even if it isn't one of the 5 named pairs.
    point_avg_err = {
        pid: float(np.mean([e for p, e in abs_errors.items() if pid in p]))
        for pid in point_ids
    }
    ranked = sorted(point_avg_err.items(), key=lambda kv: kv[1], reverse=True)
    emit("  Points ranked by average pair error (most-implicated first):")
    for pid, avg in ranked[:3]:
        emit(f"    {pid}: avg |error| over its {len(point_ids) - 1} pairs = {avg:.2f} mm")
    emit("")

    # -- Step 6: 3D scatter for blunder-checking -----------------------------
    save_scatter(tri_by_id, point_ids)
    emit(f"Saved {SCATTER_OUT}")
    emit("")

    # -- Verdict (soft guidance, not dogmatic) -------------------------------
    named_flags = [
        (a, b, err, err_pct) for a, b, t_tri, t_true, err, err_pct in named_results
        if abs(err) > max(NAMED_PAIR_ABS_FLOOR_MM, NAMED_PAIR_REL_TOL * t_true)
    ]
    allpairs_flag = max_abs > ALL_PAIRS_MAX_FLAG_MM

    emit("=" * 78)
    if not named_flags and not allpairs_flag:
        emit("VERDICT: looks healthy. Named-pair errors are within a few mm / ~1%, and")
        emit("the all-pairs max is small - consistent with the ~0.2px reprojection and")
        emit("~850mm baseline already established for this rig.")
    else:
        emit("VERDICT: errors look larger than expected for this rig's established accuracy.")
        if named_flags:
            emit("  Named pairs exceeding tolerance (>~1% or >5mm, whichever is larger):")
            for a, b, err, err_pct in named_flags:
                emit(f"    ({a},{b}): error={err:+.2f} mm ({err_pct:+.2f}%)")
        if allpairs_flag:
            emit(f"  All-pairs max error is {max_abs:.2f} mm at pair {max_pair} - tens of mm")
            emit(f"  on a single pair usually means a mis-click or a cam0/cam1")
            emit(f"  correspondence swap on one of those two points.")
        emit("  Most-implicated point(s) by average pair error: "
             + ", ".join(f"{pid} ({avg:.1f}mm)" for pid, avg in ranked[:2]))
        emit(f"  Also inspect {SCATTER_OUT.name} for a visual outlier (flung point / bent row).")
    emit("=" * 78)

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text("\n".join(report) + "\n")
    print(f"\nFull report written to {REPORT_OUT}")


if __name__ == "__main__":
    main()
