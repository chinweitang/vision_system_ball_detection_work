# label_vs_detection.py
# Compare manually labelled ball centroids against detector centroids for ONE
# flight, via stereo triangulation. Fisheye model throughout (cv2.fisheye.*).
#
# Deliberately NOT included in this version:
#   - sync correction between cam0/cam1 (frames are paired by raw frame_index)
#   - world-frame registration (everything stays in cam0's camera frame)
#
# Usage:
#   python label_vs_detection.py --labels labels_uv.csv --detections detections_uv.csv
#          --calib calibration_outputs --extrinsics calibration_outputs/2026_07_15/stereo_extrinsic.npz
#          --out OUT_DIR
#
# --labels / --detections schema (identical): frame_index, cam, u, v
#   cam in {0,1}; u,v are RAW distorted pixels, OpenCV convention
#   (origin top-left, x right, y down).
#
# --calib is a directory containing cam0_intrinsics_fisheye.npz and
# cam1_intrinsics_fisheye.npz. The extrinsics file is passed separately via
# --extrinsics because, in this project's calibration_outputs/ layout, the
# stereo extrinsics live in a dated subfolder alongside intrinsics from other
# sessions -- there is no single "the extrinsics file" to discover unambiguously
# by scanning --calib, so it must be named explicitly.

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FRAME_DT = 16.652e-3  # s per frame, as given

# ---- validation-gate expectations (see VALIDATION GATE section of main()) ----
FOCAL_LO, FOCAL_HI   = 1500.0, 1900.0   # px
BASELINE_EXPECT_MM   = 853.89
REPROJ_MEDIAN_MAX_PX = 1.0
ACCEL_HARD_LO, ACCEL_HARD_HI = 5.0, 20.0    # m/s^2 -- outside this, chain is broken
ACCEL_NOMINAL_LO, ACCEL_NOMINAL_HI = 9.8, 11.0


def gate_stop(msg):
    print(f"\n*** VALIDATION GATE FAILED: {msg}")
    print("*** Stopping before the label-vs-detection comparison. Pass --force to override.")
    sys.exit(1)


# ---- I/O ---------------------------------------------------------------

def load_points_csv(path):
    """frame_index,cam,u,v -> {cam: {frame_index: (u, v)}}"""
    pts = {0: {}, 1: {}}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            cam = int(row["cam"])
            fi = int(row["frame_index"])
            pts[cam][fi] = (float(row["u"]), float(row["v"]))
    return pts


def load_calib(calib_dir: Path, extrinsics_path: Path):
    d0 = np.load(calib_dir / "cam0_intrinsics_fisheye.npz")
    d1 = np.load(calib_dir / "cam1_intrinsics_fisheye.npz")
    K0, D0 = d0["K"].astype(np.float64), d0["D"].astype(np.float64).reshape(4, 1)
    K1, D1 = d1["K"].astype(np.float64), d1["D"].astype(np.float64).reshape(4, 1)

    de = np.load(extrinsics_path)
    print(f"extrinsics file: {extrinsics_path}")
    print(f"  keys: {de.files}")
    for k in de.files:
        arr = de[k]
        print(f"    {k}: shape={getattr(arr, 'shape', None)}  value={arr}")

    R = de["R"].astype(np.float64)
    T = de["T"].astype(np.float64).reshape(3)

    # Direction of R,T: this npz stores first_camera/second_camera labels.
    # cv2.stereoCalibrate's convention (which produced this file) is that
    # R,T map points from the FIRST camera's frame into the SECOND camera's
    # frame:  X_second = R @ X_first + T.
    first_cam  = str(de["first_camera"])  if "first_camera"  in de.files else "?"
    second_cam = str(de["second_camera"]) if "second_camera" in de.files else "?"
    print(f"  first_camera={first_cam}  second_camera={second_cam}")
    print("  => concluded R,T map cam0 -> cam1 (X_cam1 = R @ X_cam0 + T), "
          "since first_camera=cam0 and second_camera=cam1 per the stereoCalibrate convention.")

    return K0, D0, K1, D1, R, T


# ---- geometry -----------------------------------------------------------

def undistort_normalized(pts_uv, K, D):
    """Nx2 raw distorted pixels -> Nx2 normalised camera-frame coords."""
    pts = np.asarray(pts_uv, dtype=np.float64).reshape(-1, 1, 2)
    und = cv2.fisheye.undistortPoints(pts, K, D)  # no R, no P -> normalised coords
    return und.reshape(-1, 2)


def triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1):
    """uv0/uv1: Nx2 raw pixel coords (paired, same frames) -> Nx3 points in cam0 frame."""
    n0 = undistort_normalized(uv0, K0, D0)
    n1 = undistort_normalized(uv1, K1, D1)
    X = cv2.triangulatePoints(P0, P1, n0.T, n1.T)   # 4xN
    X = (X[:3] / X[3]).T                            # Nx3
    return X


def project_fisheye(xyz, K, D, rvec, tvec):
    obj = np.asarray(xyz, dtype=np.float64).reshape(-1, 1, 3)
    img, _ = cv2.fisheye.projectPoints(obj, rvec, tvec, K, D)
    return img.reshape(-1, 2)


def fit_parabola_axis(t, p):
    """p(t) = p0 + v0*t + 0.5*a*t^2, least squares. Returns (p0, v0, a)."""
    A = np.stack([np.ones_like(t), t, 0.5 * t ** 2], axis=1)
    coef, *_ = np.linalg.lstsq(A, p, rcond=None)
    return coef


# ---- summary txt ---------------------------------------------------------

def write_summary_txt(path, header_desc, final_frames, label_common, det_common,
                       n_label0, n_label1, n_det0, n_det1, diff, mag, xyz_label_all):
    """Human-readable companion to label_vs_detection.csv / mag_hist.png /
    per_axis.png -- shape/bias descriptions are derived from this run's own
    numbers (tail-ratio, SD-vs-mean), not hardcoded to any one dataset."""
    mean_mag, median_mag = float(np.mean(mag)), float(np.median(mag))
    sd_mag = float(np.std(mag))
    rms_mag = float(np.sqrt(np.mean(mag ** 2)))
    p95_mag = float(np.percentile(mag, 95))
    frac_over_100 = float(np.mean(mag > 100.0))
    tail_ratio = mean_mag / median_mag if median_mag > 0 else float("inf")

    if tail_ratio > 3:
        shape_note = ("Long tail: the median is modest, but the mean/RMS are several "
                       "times higher, i.e. most frames are reasonably close but a "
                       "substantial minority are wildly off.")
    elif tail_ratio > 1.5:
        shape_note = ("Mild tail: mean/RMS run somewhat above the median -- a handful "
                       "of frames are worse than the bulk, but not by an order of "
                       "magnitude.")
    else:
        shape_note = ("Tight cluster: mean and median are close together, so error is "
                       "fairly consistent across frames rather than driven by a few "
                       "outliers.")

    axis_lines, biased_axes = [], []
    for i, name in enumerate(("dx", "dy", "dz")):
        m, s = float(np.mean(diff[:, i])), float(np.std(diff[:, i]))
        axis_lines.append(f"  {name}: mean = {m:+.0f} mm   SD = {s:.0f} mm")
        if abs(m) > s:
            biased_axes.append(name)
    if biased_axes:
        bias_note = (f"{', '.join(biased_axes)} show a signed mean exceeding their own "
                     "SD: a consistent directional bias, not just scatter.")
    else:
        bias_note = ("SD dominates the mean on every axis: this is scatter, not a "
                     "consistent directional bias.")

    n_dropped_final = len(label_common) - len(final_frames)

    text = f"""LABEL vs DETECTION COMPARISON -- summary
{header_desc}
Produced by: src/stereo/label_vs_detection.py
Full per-frame data: label_vs_detection.csv (this folder)
Plots: mag_hist.png, per_axis.png (this folder)

WHAT WAS COMPARED
------------------
Manually labelled ball centroids vs. detector centroids, each independently
triangulated to 3D (cam0 camera frame, mm, no world-frame registration, no
cam0/cam1 sync correction). Compared only on frames present in both cameras
AND in both the label and detection sets: {len(final_frames)} frames
(label frames: cam0={n_label0} cam1={n_label1}, common={len(label_common)};
detection frames: cam0={n_det0} cam1={n_det1}, common={len(det_common)};
{n_dropped_final} labelled-common frame(s) had no matching detection).

RESULTS
-------
n frames compared: {len(final_frames)}

mag = |xyz_det - xyz_label|, mm:
  median   = {median_mag:.0f} mm
  mean     = {mean_mag:.0f} mm
  SD       = {sd_mag:.0f} mm
  RMS      = {rms_mag:.0f} mm
  95th pct = {p95_mag:.0f} mm

  -> {shape_note}

fraction of frames with mag > 100 mm: {frac_over_100:.4f}  ({int(round(frac_over_100 * len(mag)))} / {len(mag)})

Per-axis signed error (det - label), camera frame, mm:
{chr(10).join(axis_lines)}

  -> {bias_note}

Labelled depth (z) range: {xyz_label_all[:, 2].min():.0f} - {xyz_label_all[:, 2].max():.0f} mm
"""
    with open(path, "w") as f:
        f.write(text)
    print(f"-> {path}")


# ---- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Label vs detection centroid comparison via triangulation.")
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True,
                     help="Dir containing cam0_intrinsics_fisheye.npz / cam1_intrinsics_fisheye.npz")
    ap.add_argument("--extrinsics", type=Path, required=True,
                     help="Path to the stereo extrinsics npz (R, T).")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--force", action="store_true",
                     help="Proceed past a failed validation gate anyway.")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    K0, D0, K1, D1, R, T = load_calib(args.calib, args.extrinsics)
    P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = np.hstack([R, T.reshape(3, 1)])
    rvec1, _ = cv2.Rodrigues(R)

    # ---- VALIDATION GATE (a, b) ----
    print("\n--- VALIDATION GATE ---")
    print(f"a) K0 diag: fx={K0[0,0]:.2f} fy={K0[1,1]:.2f}   K1 diag: fx={K1[0,0]:.2f} fy={K1[1,1]:.2f}"
          f"   (expect {FOCAL_LO:.0f}-{FOCAL_HI:.0f} px)")
    focals_bad = not all(FOCAL_LO <= v <= FOCAL_HI for v in (K0[0, 0], K0[1, 1], K1[0, 0], K1[1, 1]))
    if focals_bad:
        print("   -> OUTSIDE expected range.")

    baseline = np.linalg.norm(T)
    print(f"b) baseline = norm(T) = {baseline:.3f} mm  (expect ~{BASELINE_EXPECT_MM} mm)")
    baseline_bad = abs(baseline - BASELINE_EXPECT_MM) > 50.0

    if (focals_bad or baseline_bad) and not args.force:
        gate_stop("K focal length and/or baseline outside expected range (see a/b above).")
    elif focals_bad or baseline_bad:
        print("   (--force set: continuing despite the above.)")

    # ---- load points ----
    labels = load_points_csv(args.labels)
    dets   = load_points_csv(args.detections)

    n_label0, n_label1 = len(labels[0]), len(labels[1])
    label_common = sorted(set(labels[0]) & set(labels[1]))
    print(f"\nlabels:     cam0={n_label0} cam1={n_label1}  "
          f"common(both cams)={len(label_common)}  "
          f"(dropped cam0-only={n_label0 - len(label_common)}, "
          f"cam1-only={n_label1 - len(label_common)})")

    n_det0, n_det1 = len(dets[0]), len(dets[1])
    det_common = sorted(set(dets[0]) & set(dets[1]))
    print(f"detections: cam0={n_det0} cam1={n_det1}  "
          f"common(both cams)={len(det_common)}  "
          f"(dropped cam0-only={n_det0 - len(det_common)}, "
          f"cam1-only={n_det1 - len(det_common)})")

    final_frames = sorted(set(label_common) & set(det_common))
    print(f"paired (label common) & (detection common) = {len(final_frames)}  "
          f"(dropped label-common-only={len(label_common) - len(final_frames)}, "
          f"detection-common-only={len(det_common) - len(final_frames)})")

    if not final_frames:
        gate_stop("No frames survive pairing -- nothing to compare.")

    # ---- triangulate labels over ALL label_common frames (for gate c/d) ----
    label_uv0 = np.array([labels[0][fi] for fi in label_common])
    label_uv1 = np.array([labels[1][fi] for fi in label_common])
    xyz_label_all = triangulate(label_uv0, label_uv1, K0, D0, K1, D1, P0, P1)

    # ---- VALIDATION GATE (c): label reprojection error ----
    reproj0_all = project_fisheye(xyz_label_all, K0, D0, np.zeros(3), np.zeros(3))
    reproj1_all = project_fisheye(xyz_label_all, K1, D1, rvec1, T)
    err0_all = np.linalg.norm(reproj0_all - label_uv0, axis=1)
    err1_all = np.linalg.norm(reproj1_all - label_uv1, axis=1)
    reproj_median = float(np.median(np.concatenate([err0_all, err1_all])))
    print(f"\nc) label reprojection error: median={reproj_median:.4f} px  "
          f"(cam0 median={np.median(err0_all):.4f}, cam1 median={np.median(err1_all):.4f})  "
          f"(expect ~0.2 px)")
    if reproj_median > REPROJ_MEDIAN_MAX_PX and not args.force:
        gate_stop("Label reprojection error > 1 px -- extrinsics convention or undistort is wrong.")
    elif reproj_median > REPROJ_MEDIAN_MAX_PX:
        print("   (--force set: continuing despite the above.)")

    # ---- VALIDATION GATE (d): gravity fit on labelled points ----
    # Positions are in mm (T is in mm), so the raw fit coefficient is mm/s^2;
    # convert to m/s^2 for comparison against gravity.
    t_all = np.array([fi * FRAME_DT for fi in label_common])
    accel_mm = np.array([fit_parabola_axis(t_all, xyz_label_all[:, ax])[2] for ax in range(3)])
    accel_mag = float(np.linalg.norm(accel_mm)) / 1000.0
    print(f"d) |a| from parabola fit on labelled points: {accel_mag:.3f} m/s^2  "
          f"(expect {ACCEL_NOMINAL_LO}-{ACCEL_NOMINAL_HI}, gravity + drag)")
    if not (ACCEL_HARD_LO <= accel_mag <= ACCEL_HARD_HI) and not args.force:
        gate_stop("Fitted |a| far from gravity -- the triangulation chain is broken.")
    elif not (ACCEL_HARD_LO <= accel_mag <= ACCEL_HARD_HI):
        print("   (--force set: continuing despite the above.)")
    elif not (ACCEL_NOMINAL_LO <= accel_mag <= ACCEL_NOMINAL_HI):
        print("   (outside nominal band but within tolerance -- continuing.)")

    print("--- END VALIDATION GATE ---\n")

    # ---- triangulate detections + labels restricted to final_frames ----
    det_uv0 = np.array([dets[0][fi] for fi in final_frames])
    det_uv1 = np.array([dets[1][fi] for fi in final_frames])
    xyz_det = triangulate(det_uv0, det_uv1, K0, D0, K1, D1, P0, P1)

    label_idx = {fi: i for i, fi in enumerate(label_common)}
    keep = [label_idx[fi] for fi in final_frames]
    xyz_label = xyz_label_all[keep]
    err0 = err0_all[keep]
    err1 = err1_all[keep]

    diff = xyz_det - xyz_label
    mag = np.linalg.norm(diff, axis=1)

    # ---- write CSV ----
    csv_path = args.out / "label_vs_detection.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame_index",
                    "label_x", "label_y", "label_z",
                    "det_x", "det_y", "det_z",
                    "dx", "dy", "dz", "mag",
                    "reproj_px_cam0", "reproj_px_cam1"])
        for i, fi in enumerate(final_frames):
            w.writerow([fi,
                        f"{xyz_label[i,0]:.4f}", f"{xyz_label[i,1]:.4f}", f"{xyz_label[i,2]:.4f}",
                        f"{xyz_det[i,0]:.4f}", f"{xyz_det[i,1]:.4f}", f"{xyz_det[i,2]:.4f}",
                        f"{diff[i,0]:.4f}", f"{diff[i,1]:.4f}", f"{diff[i,2]:.4f}", f"{mag[i]:.4f}",
                        f"{err0[i]:.4f}", f"{err1[i]:.4f}"])
    print(f"-> {csv_path}")

    # ---- mag_hist.png (full range, no clipping) ----
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(mag, bins=30)
    ax.set_xlabel("|xyz_det - xyz_label| (mm)")
    ax.set_ylabel("count")
    ax.set_title(f"Label vs detection centroid error, n={len(mag)}")
    fig.tight_layout()
    fig.savefig(args.out / "mag_hist.png", dpi=150)
    plt.close(fig)
    print(f"-> {args.out / 'mag_hist.png'}")

    # ---- per_axis.png ----
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    labels_ax = ["dx (mm)", "dy (mm)", "dz (mm)"]
    for i, a in enumerate(axes):
        a.plot(final_frames, diff[:, i], marker="o", linestyle="-", markersize=3)
        a.axhline(0, color="k", linewidth=0.5)
        a.set_ylabel(labels_ax[i])
    axes[-1].set_xlabel("frame_index")
    fig.suptitle("Per-axis signed error (det - label), camera frame")
    fig.tight_layout()
    fig.savefig(args.out / "per_axis.png", dpi=150)
    plt.close(fig)
    print(f"-> {args.out / 'per_axis.png'}")

    # ---- stdout summary ----
    print("\n--- SUMMARY ---")
    print(f"n frames compared: {len(mag)}")
    print(f"mag:  median={np.median(mag):.3f}  mean={np.mean(mag):.3f}  SD={np.std(mag):.3f}  "
          f"RMS={np.sqrt(np.mean(mag**2)):.3f}  95th pct={np.percentile(mag, 95):.3f}  (mm)")
    for i, name in enumerate(("dx", "dy", "dz")):
        print(f"{name}: signed mean={np.mean(diff[:,i]):.3f} mm   SD={np.std(diff[:,i]):.3f} mm")
    frac_over_100 = float(np.mean(mag > 100.0))
    print(f"fraction of frames with mag > 100 mm: {frac_over_100:.4f}")
    print(f"depth (z) range of labelled points: [{xyz_label_all[:,2].min():.1f}, "
          f"{xyz_label_all[:,2].max():.1f}] mm")

    # ---- summary txt (companion to the CSV/plots, every run) ----
    header_desc = f"labels: {args.labels}\ndetections: {args.detections}"
    write_summary_txt(args.out / "label_vs_detection_summary.txt", header_desc,
                       final_frames, label_common, det_common,
                       n_label0, n_label1, n_det0, n_det1, diff, mag, xyz_label_all)


if __name__ == "__main__":
    main()
