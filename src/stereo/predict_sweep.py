# predict_sweep.py
# Gravity-only trajectory-prediction N-sweep on ONE flight: how well does a
# constant-acceleration fit, built from an ever-growing prefix of early
# frames, predict a single withheld LATER labelled point? Run twice per N --
# once fit on labelled points (curve A, the model's best-case floor) and once
# fit on detector points (curve B, what the real pipeline would see) -- both
# aimed at the exact same withheld target, so the vertical gap between the
# two curves is purely the detector's contribution to prediction error.
#
# Camera frame throughout -- NO world registration, NO sync correction.
# Distances (the error metric) are rigid-invariant, so neither is needed for
# this comparison to be meaningful.
#
# TRIANGULATION is imported verbatim from label_vs_detection.py, not re-derived.
#
# Usage:
#   python predict_sweep.py --labels labels_uv.csv --detections detections_uv.csv
#          --calib calibration_outputs --extrinsics calibration_outputs/2026_07_15/stereo_extrinsic.npz
#          --out OUT_DIR

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE      = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))
from src.stereo.label_vs_detection import (
    load_points_csv, load_calib, triangulate, fit_parabola_axis,
)
from src.stereo.world_registration import solve_world_frame, world_transform

DEFAULT_WORLD_IMAGE = (REPO_ROOT / "data" / "2026_07_15_gym" /
                        "world_registration&rebounder_registration" / "cam0" / "img_0030.png")

FRAME_DT = 16.652e-3  # s per frame, as given

# ---- validation-gate expectations ----
ACCEL_GATE_LO, ACCEL_GATE_HI = 8.0, 12.0   # m/s^2, checked on the labelled fit at large N


def gate_stop(msg):
    print(f"\n*** VALIDATION GATE FAILED: {msg}")
    print("*** Stopping.")
    sys.exit(1)


def fit_constant_accel(t, xyz):
    """Fit p(t) = p0 + v0*t + 0.5*a*t^2 per axis (free a, no imposed gravity
    direction -- gravity is not axis-aligned in an arbitrary camera frame).
    Returns (p0, v0, a) each as a 3-vector, reusing fit_parabola_axis verbatim
    per axis (identical model to label_vs_detection.py's own gate)."""
    p0 = np.zeros(3); v0 = np.zeros(3); a = np.zeros(3)
    for ax in range(3):
        p0[ax], v0[ax], a[ax] = fit_parabola_axis(t, xyz[:, ax])
    return p0, v0, a


def predict_at(p0, v0, a, t):
    return p0 + v0 * t + 0.5 * a * t ** 2


def main():
    ap = argparse.ArgumentParser(description="Gravity-only trajectory prediction N-sweep, labelled vs detected.")
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--detections", type=Path, required=True)
    ap.add_argument("--calib", type=Path, required=True)
    ap.add_argument("--extrinsics", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--world-image", type=Path, default=DEFAULT_WORLD_IMAGE,
                     help="cam0 image of the checkerboard used for world-frame registration "
                          "(display-only, additional plots -- does not affect fitting/error).")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    K0, D0, K1, D1, R, T = load_calib(args.calib, args.extrinsics)
    P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P1 = np.hstack([R, T.reshape(3, 1)])

    labels = load_points_csv(args.labels)
    dets   = load_points_csv(args.detections)

    label_common = sorted(set(labels[0]) & set(labels[1]))
    det_common   = sorted(set(dets[0]) & set(dets[1]))
    print(f"label_common: {len(label_common)} frames [{label_common[0]}..{label_common[-1]}]")
    print(f"det_common:   {len(det_common)} frames [{det_common[0]}..{det_common[-1]}]")

    # ---- target: always the LAST labelled frame, always a labelled point ----
    target_frame = label_common[-1]
    target_uv0 = np.array([labels[0][target_frame]])
    target_uv1 = np.array([labels[1][target_frame]])
    target_xyz = triangulate(target_uv0, target_uv1, K0, D0, K1, D1, P0, P1)[0]
    print(f"target_frame: {target_frame}  target_xyz: {target_xyz}")

    # ---- fit frames: frames usable by BOTH curves, so N means the same
    # thing (same frame_numbers, same time base) for curve A and curve B --
    # the only difference is which point (label vs detection) sits at each
    # frame. target_frame is explicitly excluded -- it must never be fit on.
    fit_frames = sorted((set(label_common) & set(det_common)) - {target_frame})
    dropped_label_only = sorted(set(label_common) - set(det_common) - {target_frame})
    dropped_det_only   = sorted(set(det_common) - set(label_common))
    print(f"fit_frames (label & det, target excluded): {len(fit_frames)} "
          f"[{fit_frames[0]}..{fit_frames[-1]}]")
    print(f"  dropped (labelled-only, no matching detection): {dropped_label_only}")
    print(f"  dropped (detected-only, no matching label):     {dropped_det_only}")
    assert target_frame not in fit_frames, "target_frame leaked into fit_frames -- must never happen"

    if len(fit_frames) < 3:
        gate_stop(f"Only {len(fit_frames)} usable fit frames -- need at least 3 (N=2 excluded, "
                  "under-determined for a 9-parameter constant-acceleration fit).")

    # ---- triangulate every fit-frame point once for both curves ----
    fit_uv0_label = np.array([labels[0][f] for f in fit_frames])
    fit_uv1_label = np.array([labels[1][f] for f in fit_frames])
    xyz_label_pts = triangulate(fit_uv0_label, fit_uv1_label, K0, D0, K1, D1, P0, P1)

    fit_uv0_det = np.array([dets[0][f] for f in fit_frames])
    fit_uv1_det = np.array([dets[1][f] for f in fit_frames])
    xyz_det_pts = triangulate(fit_uv0_det, fit_uv1_det, K0, D0, K1, D1, P0, P1)

    # also triangulate the FULL labelled track (not just fit_frames) for
    # plotting the true ground-truth arc later
    full_uv0 = np.array([labels[0][f] for f in label_common])
    full_uv1 = np.array([labels[1][f] for f in label_common])
    xyz_label_full = triangulate(full_uv0, full_uv1, K0, D0, K1, D1, P0, P1)

    # t=0 at the first fit frame -- since "first N frames" windows are
    # nested (window(N) is a prefix of window(N+1)), this anchor is the same
    # frame, fit_frames[0], for every N. Gap-safe: uses actual frame_number,
    # not array position.
    t0_frame = fit_frames[0]
    t_full = np.array([(f - t0_frame) * FRAME_DT for f in fit_frames])

    N_max = len(fit_frames)
    N_values = list(range(3, N_max + 1))   # N=2 excluded: under-determined for 9 free params

    rows = []
    fits_by_N = {}   # N -> (label p0,v0,a ; det p0,v0,a) for the trajectory plots later
    for N in N_values:
        window_frames = fit_frames[:N]
        assert target_frame not in window_frames, "target_frame leaked into a fit window"
        t_win = t_full[:N]
        last_fit_frame = window_frames[-1]
        t_extrap_ms = (target_frame - last_fit_frame) * FRAME_DT * 1000.0
        t_target = (target_frame - t0_frame) * FRAME_DT

        p0_l, v0_l, a_l = fit_constant_accel(t_win, xyz_label_pts[:N])
        p0_d, v0_d, a_d = fit_constant_accel(t_win, xyz_det_pts[:N])

        pred_label = predict_at(p0_l, v0_l, a_l, t_target)
        pred_det   = predict_at(p0_d, v0_d, a_d, t_target)

        err_label = float(np.linalg.norm(pred_label - target_xyz))
        err_det   = float(np.linalg.norm(pred_det   - target_xyz))
        norm_a_label = float(np.linalg.norm(a_l)) / 1000.0   # mm/s^2 -> m/s^2
        norm_a_det   = float(np.linalg.norm(a_d)) / 1000.0

        rows.append(dict(N=N, last_fit_frame=last_fit_frame, t_extrap_ms=t_extrap_ms,
                          err_label_mm=err_label, err_det_mm=err_det,
                          norm_a_label=norm_a_label, norm_a_det=norm_a_det))
        fits_by_N[N] = dict(p0_l=p0_l, v0_l=v0_l, a_l=a_l, p0_d=p0_d, v0_d=v0_d, a_d=a_d,
                             window_frames=window_frames, t_win=t_win, t_target=t_target,
                             pred_label=pred_label, pred_det=pred_det)

    # ---- VALIDATION GATE ----
    accel_at_max_N = rows[-1]["norm_a_label"]
    print(f"\n--- VALIDATION GATE ---")
    print(f"labelled |a| at largest N ({N_values[-1]}): {accel_at_max_N:.3f} m/s^2  "
          f"(expect {ACCEL_GATE_LO}-{ACCEL_GATE_HI})")
    if not (ACCEL_GATE_LO <= accel_at_max_N <= ACCEL_GATE_HI):
        gate_stop(f"Labelled |a| at large N = {accel_at_max_N:.3f} m/s^2, outside "
                  f"{ACCEL_GATE_LO}-{ACCEL_GATE_HI} -- fit or triangulation is broken.")

    err_label_arr = np.array([r["err_label_mm"] for r in rows])
    slope, _ = np.polyfit(N_values, err_label_arr, 1)
    print(f"err_label trend: linear slope = {slope:+.3f} mm/N over N={N_values[0]}..{N_values[-1]} "
          f"(expect non-positive -- error should decrease then flatten as N grows)")
    if slope > 0:
        gate_stop(f"err_label (curve A, the model floor) has a POSITIVE trend (slope={slope:+.3f} "
                  "mm/N) -- it should generally decrease then flatten as N grows. Something is "
                  "wrong before detection even enters the picture.")
    print("--- END VALIDATION GATE ---\n")

    # ---- write CSV ----
    csv_path = args.out / "predict_sweep.csv"
    fieldnames = ["N", "last_fit_frame", "t_extrap_ms", "err_label_mm", "err_det_mm",
                  "norm_a_label", "norm_a_det"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"-> {csv_path}")

    # ---- stdout table ----
    header = f"{'N':>3} {'last_fit':>9} {'t_extrap_ms':>12} {'err_label':>10} {'err_det':>9} {'|a|_label':>10} {'|a|_det':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['N']:>3} {r['last_fit_frame']:>9} {r['t_extrap_ms']:>12.1f} "
              f"{r['err_label_mm']:>10.1f} {r['err_det_mm']:>9.1f} "
              f"{r['norm_a_label']:>10.3f} {r['norm_a_det']:>9.3f}")

    best_label = min(rows, key=lambda r: r["err_label_mm"])
    best_det   = min(rows, key=lambda r: r["err_det_mm"])
    print(f"\nmin err_label: N={best_label['N']}  err={best_label['err_label_mm']:.1f} mm  "
          f"t_extrap={best_label['t_extrap_ms']:.1f} ms")
    print(f"min err_det:   N={best_det['N']}  err={best_det['err_det_mm']:.1f} mm  "
          f"t_extrap={best_det['t_extrap_ms']:.1f} ms")
    print("\nNOTE: this is ONE flight. The result is the SHAPE of the two curves "
          "(how error falls off with N/lead-time, and the gap between them), "
          "not a single 'best N' to conclude from.")

    # ---- sweep_error_vs_N.png ----
    Ns = [r["N"] for r in rows]
    t_extrap_arr = np.array([r["t_extrap_ms"] for r in rows])
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(Ns, [r["err_label_mm"] for r in rows], marker="o", label="curve A: fit on labelled points (model floor)")
    ax.plot(Ns, [r["err_det_mm"] for r in rows], marker="s", label="curve B: fit on detected points (end-to-end)")
    ax.set_xlabel("N (frames in fit window)")
    ax.set_ylabel("prediction error at target (mm, log scale)")
    # Log scale: err spans ~3 orders of magnitude (huge at low N, small once
    # it flattens), and the flattened region for larger N -- where the A/B
    # gap actually lives -- is the point of this plot, not the low-N spike.
    ax.set_yscale("log")
    ax.set_title(f"Prediction error vs N -- target frame {target_frame}")
    ax.legend()
    ax.grid(True, alpha=0.3, which="both")

    # secondary top axis: t_extrap_ms for each N (via interpolation over the
    # actual N -> t_extrap_ms table, not assumed-linear, so it stays correct
    # even if fit_frames has small internal gaps)
    N_sorted = np.array(Ns, dtype=float)
    t_sorted = t_extrap_arr.astype(float)
    def n_to_t(n):
        return np.interp(n, N_sorted, t_sorted)
    def t_to_n(t):
        return np.interp(t, t_sorted[::-1], N_sorted[::-1])
    secax = ax.secondary_xaxis("top", functions=(n_to_t, t_to_n))
    secax.set_xlabel("t_extrap (ms)")

    fig.tight_layout()
    fig.savefig(args.out / "sweep_error_vs_N.png", dpi=150)
    plt.close(fig)
    print(f"-> {args.out / 'sweep_error_vs_N.png'}")

    # ---- representative N values for the trajectory plots ----
    N_small = N_values[0]
    N_large = N_values[-1]
    N_mid   = N_values[len(N_values) // 2]
    rep_Ns = sorted(set([N_small, N_mid, N_large]))

    # ---- gravity-aligned DISPLAY frame (plots only). Fitting/error above is
    # untouched and stays in the raw camera frame -- distances are
    # rotation-invariant, so err_label_mm/err_det_mm are unaffected by this.
    # Built from the LARGEST-N labelled fit only (most physical; small-N fits
    # are unphysical -- e.g. |a|~440 m/s^2 at N=3 in the table above).
    a_ref  = fits_by_N[N_large]["a_l"]
    v0_ref = fits_by_N[N_large]["v0_l"]
    down    = a_ref / np.linalg.norm(a_ref)                   # gravity points down by definition
    fwd_raw = v0_ref - np.dot(v0_ref, down) * down            # Gram-Schmidt: v0 with 'down' removed
    forward = fwd_raw / np.linalg.norm(fwd_raw)
    lateral = np.cross(down, forward)
    up      = -down
    R_gravity = np.vstack([forward, lateral, up])             # rows = new basis, expressed in camera frame

    def rotate(pts):
        """Rotation only (no translation/rescale) into the gravity-aligned display frame."""
        pts = np.atleast_2d(pts)
        return pts @ R_gravity.T

    # sanity check: the labelled arc's vertical ('up') coordinate should rise
    # then fall (downward-opening parabola). Checked against the FULL labelled
    # arc's own shape, independent of any one fit, so it's a real check on the
    # forward/down construction, not just a restatement of a_ref.
    gt_rot_check = rotate(xyz_label_full)
    up_coord = gt_rot_check[:, 2]
    t_gt = np.array([(f - t0_frame) * FRAME_DT for f in label_common])
    quad_coef = np.polyfit(t_gt, up_coord, 2)
    peak_idx = int(np.argmax(up_coord))
    interior_peak = 0 < peak_idx < len(up_coord) - 1
    print(f"\ngravity-aligned frame sanity check:")
    print(f"  labelled arc 'up' vs t: quadratic leading coeff = {quad_coef[0]:.4f} mm/s^2 "
          f"(expect negative)")
    print(f"  peak 'up' at labelled-track index {peak_idx}/{len(up_coord) - 1} "
          f"({'interior -- rises then falls' if interior_peak else 'AT AN ENDPOINT -- does not rise then fall'})")
    if quad_coef[0] >= 0 or not interior_peak:
        gate_stop("Gravity-aligned 'up' axis does not rise then fall over the labelled arc -- "
                  "the forward/down construction is wrong.")

    # ---- world-frame registration (checkerboard, cam0). Display-only,
    # additional plots -- does not touch fitting/error above. ----
    print(f"\nworld-frame registration from: {args.world_image}")
    R_wc, T_wc = solve_world_frame(args.world_image, K0, D0)

    def to_world(pts):
        return world_transform(pts, R_wc, T_wc)

    # cross-check: world "up" (bottom-to-up, i.e. -y_solve) vs the INDEPENDENT
    # gravity "up" direction already established above from the trajectory's
    # own fit (up = -down = -a_ref/|a_ref|). These come from two unrelated
    # sources (a static checkerboard photo vs. the ball's dynamics), so close
    # agreement is a strong check that the row-flip determination above
    # (which end of the board is physically "up") was correct.
    world_up_in_cam = -R_wc[:, 1]   # object's local +y (top-to-bottom) column of R_wc, negated
    cos_angle = np.clip(np.dot(world_up_in_cam, up) / (np.linalg.norm(world_up_in_cam) * np.linalg.norm(up)), -1, 1)
    angle_deg = float(np.degrees(np.arccos(cos_angle)))
    print(f"world-frame 'up' vs gravity-derived 'up': angle = {angle_deg:.1f} deg "
          f"(expect small -- independent cross-check of the checkerboard row-flip)")
    if angle_deg > 45.0:
        print(f"  WARNING: {angle_deg:.1f} deg is a large disagreement -- the checkerboard "
              f"row-direction determination in world_registration.py may be wrong.")

    # least-varying axis of the full labelled trajectory (raw camera frame) ->
    # dropped for the camera-frame side view.
    spread = xyz_label_full.max(axis=0) - xyz_label_full.min(axis=0)
    drop_axis = int(np.argmin(spread))
    keep_axes = [ax_i for ax_i in range(3) if ax_i != drop_axis]
    cam_axis_names = ["x", "y", "z"]
    print(f"\ncamera-frame side view drops axis '{cam_axis_names[drop_axis]}' "
          f"(least variation: {spread[drop_axis]:.1f} mm vs "
          f"{spread[keep_axes[0]]:.1f}/{spread[keep_axes[1]]:.1f} mm)")

    def plot_trajectory(proj, is_3d, xlabel, ylabel, zlabel, out_name, title):
        fig = plt.figure(figsize=(6 * len(rep_Ns), 6))
        for i, N in enumerate(rep_Ns):
            fitN = fits_by_N[N]
            if is_3d:
                ax = fig.add_subplot(1, len(rep_Ns), i + 1, projection="3d")
            else:
                ax = fig.add_subplot(1, len(rep_Ns), i + 1)

            # ground-truth arc: all labelled points
            gt = proj(xyz_label_full)
            if is_3d:
                ax.plot(gt[:, 0], gt[:, 1], gt[:, 2], "k.", markersize=3, alpha=0.5, label="labelled arc (ground truth)")
            else:
                ax.plot(gt[:, 0], gt[:, 1], "k.", markersize=3, alpha=0.5, label="labelled arc (ground truth)")

            # fitted+extrapolated curve B (detected fit), from t=0 to t_target
            t_line = np.linspace(0, fitN["t_target"], 50)
            line_pts = np.array([predict_at(fitN["p0_d"], fitN["v0_d"], fitN["a_d"], tt) for tt in t_line])
            line_p = proj(line_pts)
            if is_3d:
                ax.plot(line_p[:, 0], line_p[:, 1], line_p[:, 2], "b-", linewidth=2, label="curve B fit+extrapolation")
            else:
                ax.plot(line_p[:, 0], line_p[:, 1], "b-", linewidth=2, label="curve B fit+extrapolation")

            # fit-window points actually used (detected), ringed
            win_idx = [fit_frames.index(f) for f in fitN["window_frames"]]
            win_pts = proj(xyz_det_pts[win_idx])
            if is_3d:
                ax.plot(win_pts[:, 0], win_pts[:, 1], win_pts[:, 2], "o", markerfacecolor="none",
                        markeredgecolor="b", markersize=10, markeredgewidth=1.5, label=f"fit window (N={N})")
            else:
                ax.plot(win_pts[:, 0], win_pts[:, 1], "o", markerfacecolor="none",
                        markeredgecolor="b", markersize=10, markeredgewidth=1.5, label=f"fit window (N={N})")

            # target and predicted points
            tgt = proj(target_xyz)
            pred = proj(fitN["pred_det"])
            if is_3d:
                ax.scatter(*tgt[0], c="green", s=80, marker="*", label="target (labelled)")
                ax.scatter(*pred[0], c="red", s=80, marker="X", label="predicted (from det fit)")
            else:
                ax.scatter(*tgt[0], c="green", s=120, marker="*", label="target (labelled)", zorder=5)
                ax.scatter(*pred[0], c="red", s=120, marker="X", label="predicted (from det fit)", zorder=5)

            ax.set_title(f"N={N}  err_det={next(r['err_det_mm'] for r in rows if r['N']==N):.0f} mm")
            if i == 0:
                ax.legend(fontsize=8, loc="upper left")
            if is_3d:
                ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.set_zlabel(zlabel)
            else:
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)

        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(args.out / out_name, dpi=150)
        plt.close(fig)
        print(f"-> {args.out / out_name}")

    def proj_cam_3d(pts):
        return np.atleast_2d(pts)

    def proj_cam_side(pts):
        return np.atleast_2d(pts)[:, keep_axes]

    def proj_grav_3d(pts):
        return rotate(pts)

    def proj_grav_side(pts):
        return rotate(pts)[:, [0, 2]]   # forward (x) vs up (vertical)

    # gravity-aligned (fixes the unreadable tilted-camera-frame parabola)
    plot_trajectory(proj_grav_3d, True, "forward (mm)", "lateral (mm)", "up (mm)",
                     "trajectory_3d.png",
                     f"Prediction at representative N (3D, gravity-aligned) -- target frame {target_frame}")
    plot_trajectory(proj_grav_side, False, "forward (mm)", "up (mm)", None,
                     "trajectory_side.png",
                     f"Prediction at representative N (side view: forward vs up, gravity-aligned) "
                     f"-- target frame {target_frame}")

    # original raw camera frame, kept alongside the gravity-aligned versions
    plot_trajectory(proj_cam_3d, True, "x (mm)", "y (mm)", "z (mm)",
                     "trajectory_3d_camera_frame.png",
                     f"Prediction at representative N (3D, raw camera frame) -- target frame {target_frame}")
    plot_trajectory(proj_cam_side, False, f"{cam_axis_names[keep_axes[0]]} (mm)",
                     f"{cam_axis_names[keep_axes[1]]} (mm)", None,
                     "trajectory_side_camera_frame.png",
                     f"Prediction at representative N (side view, '{cam_axis_names[drop_axis]}' dropped, "
                     f"raw camera frame) -- target frame {target_frame}")

    # world frame (checkerboard-registered): x=left-to-right, y=bottom-to-up,
    # z=into-the-checkerboard. Side view is world (x, y) per request.
    def proj_world_3d(pts):
        return to_world(pts)

    def proj_world_side(pts):
        return to_world(pts)[:, [0, 1]]

    plot_trajectory(proj_world_3d, True, "world x (mm)", "world y (mm)", "world z (mm)",
                     "world_frame_registered_3d.png",
                     f"Prediction at representative N (3D, world-frame registered) -- target frame {target_frame}")
    plot_trajectory(proj_world_side, False, "world x (mm)", "world y (mm)", None,
                     "world_frame_registered_side.png",
                     f"Prediction at representative N (side view: world x vs y, registered) "
                     f"-- target frame {target_frame}")

    # same world-frame data, but with world y (bottom-to-up) on the plot's
    # vertical (3D "z") axis instead of world z (into-the-board) -- matplotlib
    # 3D always renders its 3rd coordinate vertically, so swap columns 1/2.
    # Separate file, does not replace world_frame_registered_3d.png.
    def proj_world_3d_yup(pts):
        w = to_world(pts)
        return w[:, [0, 2, 1]]   # (world x, world z, world y) -> plotted (x, y, z)

    plot_trajectory(proj_world_3d_yup, True, "world x (mm)", "world z (mm)", "world y (mm)",
                     "world_frame_registered_3d_2.png",
                     f"Prediction at representative N (3D, world-frame registered, y up) "
                     f"-- target frame {target_frame}")


if __name__ == "__main__":
    main()
