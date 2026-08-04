# ellipse_rect_pipeline_divergence_diagnostic.py
#
# For flight_51 and flight_125 (2026_07_21_gym, the two biggest Model-C
# prediction-error regressions found in decision 65: +865.7mm and +426.0mm),
# traces where in the pipeline the ellipse-kernel and rect-kernel runs first
# diverge meaningfully: 2D detection -> trajectory-filtering/pairing ->
# triangulation -> RANSAC inlier selection -> final fit. Reports each stage's
# divergence explicitly rather than just re-confirming the final error gap
# already known from decision 65.
#
# Reuses build_corrected_track_from_dir/target_time_sec/ELLIPSE_DETECTIONS_ROOT/
# RECT_DETECTIONS_ROOT/FIT_WINDOW_S/load_pooled_k directly from
# rect_vs_ellipse_prediction_comparison.py (import, not duplicate -- that
# module's own main() is __main__-guarded so importing it is safe).
#
# Does NOT modify detector_core.py or any existing production module.
#
# Usage:
#   python src/stereo/ellipse_rect_pipeline_divergence_diagnostic.py

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.rect_vs_ellipse_prediction_comparison import (  # noqa: E402
    build_corrected_track_from_dir, target_time_sec, load_pooled_k,
    ELLIPSE_DETECTIONS_ROOT, RECT_DETECTIONS_ROOT, FIT_WINDOW_S,
)
from src.stereo.all_flights_common import load_session_calib, g_fixed_for, load_final_point_targets  # noqa: E402
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.trajectory_fit import (  # noqa: E402
    build_model_fit_predict, ransac_fit,
    RANSAC_INLIER_THRESHOLD_MM, RANSAC_MIN_SAMPLES, RANSAC_N_ITERATIONS, RANSAC_SEED,
)

OUT_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "rect_vs_ellipse_kernel"
FLIGHTS = [("2026_07_21_gym", "flight_51"), ("2026_07_21_gym", "flight_125")]


def load_raw_detections_csv(path: Path) -> dict:
    d = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            d[int(row["frame_number"])] = (float(row["u"]), float(row["v"]))
    return d


def stage1_2d_comparison(session, flight_id):
    """Raw 2D centroid detections, ellipse vs rect, per camera, at full
    sub-pixel precision -- not the contact-sheet-thumbnail resolution."""
    out = {}
    for cam in ("cam0", "cam1"):
        e_path = ELLIPSE_DETECTIONS_ROOT / session / f"{flight_id}_{cam}_detections.csv"
        r_path = RECT_DETECTIONS_ROOT / session / f"{flight_id}_{cam}_detections.csv"
        e = load_raw_detections_csv(e_path)
        r = load_raw_detections_csv(r_path)
        common = sorted(set(e) & set(r))
        per_frame = {fr: float(np.hypot(e[fr][0] - r[fr][0], e[fr][1] - r[fr][1])) for fr in common}
        deltas = list(per_frame.values())
        out[cam] = dict(
            n_ellipse=len(e), n_rect=len(r), n_common=len(common),
            only_ellipse=sorted(set(e) - set(r)), only_rect=sorted(set(r) - set(e)),
            delta_px=dict(mean=float(np.mean(deltas)) if deltas else 0.0,
                          median=float(np.median(deltas)) if deltas else 0.0,
                          max=float(np.max(deltas)) if deltas else 0.0),
            per_frame_deltas_px=per_frame,
        )
    return out


def stage2_3_track_comparison(session, flight_id, K0, D0, K1, D1, P0, P1):
    """Trajectory-filtering/pairing survival + resulting 3D triangulated
    positions, ellipse vs rect."""
    e_track = build_corrected_track_from_dir(session, flight_id, ELLIPSE_DETECTIONS_ROOT / session,
                                              K0, D0, K1, D1, P0, P1)
    r_track = build_corrected_track_from_dir(session, flight_id, RECT_DETECTIONS_ROOT / session,
                                              K0, D0, K1, D1, P0, P1)
    if e_track is None or r_track is None:
        return None, e_track, r_track

    e_frames, e_t, e_xyz, e_anchor = e_track
    r_frames, r_t, r_xyz, r_anchor = r_track
    e_set, r_set = set(e_frames), set(r_frames)
    common_frames = sorted(e_set & r_set)
    e_map = {fr: e_xyz[i] for i, fr in enumerate(e_frames)}
    r_map = {fr: r_xyz[i] for i, fr in enumerate(r_frames)}
    per_frame = {fr: float(np.linalg.norm(e_map[fr] - r_map[fr])) for fr in common_frames}
    deltas = list(per_frame.values())

    summary = dict(
        n_ellipse_frames=len(e_frames), n_rect_frames=len(r_frames), n_common_frames=len(common_frames),
        only_ellipse_frames=sorted(e_set - r_set), only_rect_frames=sorted(r_set - e_set),
        t_anchor_delta_ms=(r_anchor - e_anchor) / 1e6,
        xyz_delta_mm=dict(mean=float(np.mean(deltas)) if deltas else 0.0,
                          median=float(np.median(deltas)) if deltas else 0.0,
                          max=float(np.max(deltas)) if deltas else 0.0),
        per_frame_xyz_deltas_mm=per_frame,
    )
    return summary, e_track, r_track


def stage4_5_ransac_fit(session, flight_id, track, targets, pooled_k, K0, D0, K1, D1, P0, P1, g_fixed):
    """RANSAC inlier selection + final fit, for ONE variant's track."""
    frames, t, xyz, t_anchor_ns = track
    tgt = targets[(session, flight_id)]
    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)

    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    frames2 = [frames[i] for i in keep_idx]
    t2 = t[np.array(keep_idx)]
    xyz2 = xyz[np.array(keep_idx)]
    N = int(np.searchsorted(t2, FIT_WINDOW_S, side="right"))
    t_win, xyz_win, frame_win = t2[:N], xyz2[:N], frames2[:N]

    fit_fn, predict_fn = build_model_fit_predict("C", g_fixed, k_fixed=pooled_k)
    res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=RANSAC_MIN_SAMPLES["C"],
                      inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM, n_iterations=RANSAC_N_ITERATIONS["C"],
                      random_seed=RANSAC_SEED, frame_numbers=frame_win)
    pred = predict_fn(res["params"], np.array([t_target]))[0]
    err = float(np.linalg.norm(pred - target_xyz))

    return dict(N=N, fit_window_duration_ms=float(t_win[-1] * 1000.0),
                n_inliers=res["n_inliers"], accepted_frames=sorted(int(x) for x in res["accepted_frames"]),
                rejected_frames=sorted(int(x) for x in res["rejected_frames"]),
                residual_rms_mm=res["residual_rms_mm"], error_mm=err, lead_time_ms=(t_target - t_win[-1]) * 1000.0)


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def run_flight(session, flight_id, pooled_k, targets):
    print(f"\n{'='*70}\n{session}/{flight_id}\n{'='*70}")
    K0, D0, K1, D1, P0, P1 = load_session_calib(session)
    g_fixed = g_fixed_for(session, flight_id)

    # -- Stage 1: 2D detections --
    s1 = stage1_2d_comparison(session, flight_id)
    print(f"\n--- Stage 1: 2D detections ---")
    for cam, d in s1.items():
        print(f"  {cam}: ellipse n={d['n_ellipse']}, rect n={d['n_rect']}, common={d['n_common']}, "
              f"only_ellipse={d['only_ellipse']}, only_rect={d['only_rect']}")
        print(f"    delta_px: mean={d['delta_px']['mean']:.3f} median={d['delta_px']['median']:.3f} "
              f"max={d['delta_px']['max']:.3f}")

    # -- Stage 2/3: trajectory-filtering/pairing + triangulation --
    s23, e_track, r_track = stage2_3_track_comparison(session, flight_id, K0, D0, K1, D1, P0, P1)
    if s23 is None:
        print("  Could not build one or both tracks -- stopping here.")
        return dict(session=session, flight=flight_id, stage1=s1, stage23=None, stage45=None)

    print(f"\n--- Stage 2/3: trajectory-filtering/pairing + triangulation ---")
    print(f"  n_frames survived: ellipse={s23['n_ellipse_frames']} rect={s23['n_rect_frames']} "
          f"common={s23['n_common_frames']}")
    print(f"  only_ellipse_frames={s23['only_ellipse_frames']}  only_rect_frames={s23['only_rect_frames']}")
    print(f"  t_anchor delta (rect vs ellipse first-pair time): {s23['t_anchor_delta_ms']:.2f}ms")
    print(f"  xyz_delta_mm (common frames): mean={s23['xyz_delta_mm']['mean']:.2f} "
          f"median={s23['xyz_delta_mm']['median']:.2f} max={s23['xyz_delta_mm']['max']:.2f}")

    # -- Stage 4/5: RANSAC inlier selection + fit --
    e_res = stage4_5_ransac_fit(session, flight_id, e_track, targets, pooled_k, K0, D0, K1, D1, P0, P1, g_fixed)
    r_res = stage4_5_ransac_fit(session, flight_id, r_track, targets, pooled_k, K0, D0, K1, D1, P0, P1, g_fixed)

    print(f"\n--- Stage 4/5: RANSAC inlier selection + fit ---")
    print(f"  ellipse: N={e_res['N']} window_dur={e_res['fit_window_duration_ms']:.1f}ms "
          f"n_inliers={e_res['n_inliers']} residual_rms={e_res['residual_rms_mm']:.2f}mm "
          f"error={e_res['error_mm']:.1f}mm")
    print(f"  rect:    N={r_res['N']} window_dur={r_res['fit_window_duration_ms']:.1f}ms "
          f"n_inliers={r_res['n_inliers']} residual_rms={r_res['residual_rms_mm']:.2f}mm "
          f"error={r_res['error_mm']:.1f}mm")
    accepted_jaccard = jaccard(e_res["accepted_frames"], r_res["accepted_frames"])
    print(f"  accepted_frames Jaccard overlap: {accepted_jaccard:.3f}")
    print(f"  ellipse accepted: {e_res['accepted_frames']}")
    print(f"  rect    accepted: {r_res['accepted_frames']}")
    print(f"  ellipse rejected: {e_res['rejected_frames']}")
    print(f"  rect    rejected: {r_res['rejected_frames']}")

    # -- Synthesis: where does divergence FIRST become meaningful? --
    max_2d_delta = max(d["delta_px"]["max"] for d in s1.values())
    mean_2d_delta = float(np.mean([d["delta_px"]["mean"] for d in s1.values()]))
    frame_survival_diverges = bool(s23["only_ellipse_frames"] or s23["only_rect_frames"])
    max_3d_delta = s23["xyz_delta_mm"]["max"]

    print(f"\n--- SYNTHESIS ---")
    print(f"  Stage 1 (2D detection): mean_delta={mean_2d_delta:.3f}px, max_delta={max_2d_delta:.3f}px")
    print(f"  Stage 2 (frame survival through filtering/pairing): "
          f"{'DIVERGES (' + str(len(s23['only_ellipse_frames'])+len(s23['only_rect_frames'])) + ' frame(s) differ)' if frame_survival_diverges else 'IDENTICAL frame sets'}")
    print(f"  Stage 3 (triangulated 3D, common frames): max_delta={max_3d_delta:.2f}mm")
    print(f"  Stage 4 (RANSAC accepted-frame sets): Jaccard={accepted_jaccard:.3f} "
          f"({'IDENTICAL' if accepted_jaccard==1.0 else 'DIVERGES'})")
    print(f"  Stage 5 (final error): ellipse={e_res['error_mm']:.1f}mm rect={r_res['error_mm']:.1f}mm "
          f"delta={r_res['error_mm']-e_res['error_mm']:+.1f}mm")

    return dict(session=session, flight=flight_id, stage1=s1, stage23=s23,
                stage4_ellipse=e_res, stage4_rect=r_res, accepted_jaccard=accepted_jaccard)


def main():
    pooled_k = load_pooled_k()
    targets = load_final_point_targets()

    all_results = []
    for session, flight_id in FLIGHTS:
        r = run_flight(session, flight_id, pooled_k, targets)
        all_results.append(r)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "pipeline_divergence_diagnostic.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\nWrote {out_path}")


if __name__ == "__main__":
    main()
