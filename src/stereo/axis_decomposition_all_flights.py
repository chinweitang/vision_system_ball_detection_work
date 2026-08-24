# axis_decomposition_all_flights.py
# Further follow-up on the all-flights gravity-vs-drag generalization:
# decompose the flat 3D Euclidean prediction error into world-frame
# X (person->rebounder, STRONG) / Y (width, WEAK -- the actual +-100mm spec
# axis) / Z (up, STRONG) components, per context.md SS4.7/4.8. Reuses the
# EXACT same fit_and_predict_ransac function, RANSAC config, seed, and
# pooled K as trajectory_model_prediction_sweep_all_flights.py (imported
# directly, not reimplemented) -- so error_mm should reproduce identically;
# this is verified explicitly before trusting the new per-axis columns.
# See claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Usage:
#   python src/stereo/axis_decomposition_all_flights.py

import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for, build_corrected_track,
    load_final_point_targets, world_axes_for, find_flight_dir,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.trajectory_model_prediction_sweep_all_flights import (  # noqa: E402
    load_pooled_k, target_time_sec, fit_and_predict_ransac,
)

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
ALL_FLIGHTS_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights"
PHASE2_CSV_ORIGINAL = ALL_FLIGHTS_DIR / "phase2" / "prediction_sweep_all_flights.csv"
OUT_DIR = ALL_FLIGHTS_DIR / "axis_decomposition"
DURATIONS_CSV = ALL_FLIGHTS_DIR / "duration_distribution" / "flight_durations.csv"

STRATUM_SPLIT_MS = 1000.0
MODEL_COLORS = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green"}
AXIS_LABELS = {"x": "X (person->rebounder, STRONG)", "y": "Y (width, WEAK -- +-100mm spec)", "z": "Z (up, STRONG)"}
REPRESENTATIVE_PERCENTILES = [25, 50, 75, 90]


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def process_flight_axis(session: str, flight_id: str, pooled_k: float, targets: dict) -> dict:
    key = (session, flight_id)
    tgt = targets.get(key)
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="missing final-point label (one or both cams)")

    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        g_fixed = g_fixed_for(session, flight_id)
        X_world, Y_world, Z_world = world_axes_for(session, flight_id)
        track = build_corrected_track(session, flight_id, K0, D0, K1, D1, P0, P1)
    except Exception as e:
        return dict(session=session, flight=flight_id, status="error", reason=f"exception: {e!r}")

    if track is None:
        return dict(session=session, flight=flight_id, status="skipped", reason="no corrected detector track")

    frames, t, xyz, t_anchor_ns = track

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]), K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        return dict(session=session, flight=flight_id, status="skipped", reason="target frame not found in timestamps.csv")

    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < 3:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason=f"only {len(keep_idx)} fit points after excluding target frame")
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]

    if t_target <= t[0]:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason="target time is before the fit track starts")

    N_max = len(frames)
    rows = []
    for N in range(3, N_max + 1):
        t_win = t[:N]
        xyz_win = xyz[:N]
        frame_win = frames[:N]
        lead_time_ms = (t_target - t_win[-1]) * 1000.0
        if lead_time_ms <= 0:
            continue
        for model in ("A", "B", "C"):
            try:
                pred, _rejected = fit_and_predict_ransac(model, t_win, xyz_win, frame_win, g_fixed, pooled_k, t_target)
                resid = pred - target_xyz
                err = float(np.linalg.norm(resid))
                err_x = float(resid @ X_world)
                err_y = float(resid @ Y_world)
                err_z = float(resid @ Z_world)
            except RuntimeError:
                err = err_x = err_y = err_z = np.nan
            rows.append(dict(session=session, flight=flight_id, N=N, model=model,
                              lead_time_ms=lead_time_ms, error_mm=err,
                              error_x_mm=err_x, error_y_width_mm=err_y, error_z_mm=err_z))

    return dict(session=session, flight=flight_id, status="ok", rows=rows)


def _worker(task):
    session, flight_id, pooled_k, targets = task
    return process_flight_axis(session, flight_id, pooled_k, targets)


def load_original_errors():
    """{(session,flight,N,model): error_mm} from the existing Phase 2 CSV,
    for the reproduction check."""
    out = {}
    with open(PHASE2_CSV_ORIGINAL, newline="") as f:
        for row in csv.DictReader(f):
            if row["error_mm"] == "":
                continue
            out[(row["session"], row["flight"], int(row["N"]), row["model"])] = float(row["error_mm"])
    return out


def load_durations():
    out = {}
    with open(DURATIONS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight"])] = float(row["total_duration_ms"])
    return out


def binned_trend(xs, ys, bin_width):
    bin_edges = np.arange(0, xs.max() + bin_width, bin_width) if len(xs) else np.array([0, bin_width])
    bin_idx = np.digitize(xs, bin_edges)
    centers, medians, q1s, q3s = [], [], [], []
    for b in range(1, len(bin_edges)):
        sel = ys[bin_idx == b]
        if len(sel) >= 3:
            centers.append((bin_edges[b - 1] + bin_edges[b]) / 2)
            medians.append(np.median(sel))
            q1s.append(np.percentile(sel, 25))
            q3s.append(np.percentile(sel, 75))
    return centers, medians, q1s, q3s


def make_axis_panel_plot(stratum_rows, stratum, out_path, n_flights):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharex=True)
    for ax, axis_key, axis_col in zip(axes, ("x", "y", "z"), ("error_x_mm", "error_y_width_mm", "error_z_mm")):
        for model in ("A", "B", "C"):
            rows_m = [r for r in stratum_rows if r["model"] == model and not np.isnan(r[axis_col])]
            if not rows_m:
                continue
            xs = np.array([r["fit_window_duration_ms"] for r in rows_m])
            ys = np.array([abs(r[axis_col]) for r in rows_m])  # magnitude of the signed axis error
            ax.scatter(xs, ys, s=5, alpha=0.12, color=MODEL_COLORS[model])
            centers, medians, q1s, q3s = binned_trend(xs, ys, bin_width=50)
            if centers:
                ax.plot(centers, medians, color=MODEL_COLORS[model], linewidth=2.5, label=f"{model} median trend")
                ax.fill_between(centers, q1s, q3s, color=MODEL_COLORS[model], alpha=0.15)
        if axis_key == "y":
            ax.axhline(100, color="red", linestyle="--", linewidth=1.5, label="+-100mm spec")
        ax.set_yscale("log")
        ax.set_xlabel("fit window duration (ms)")
        ax.set_title(AXIS_LABELS[axis_key])
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
    axes[0].set_ylabel("|axis error| (mm, log scale)")
    fig.suptitle(f"Axis-decomposed prediction error, stratum={stratum} (n={n_flights} flights)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")
    log_append(f"wrote {out_path}")


def representative_points(rows, pcts):
    xs = np.array([r["fit_window_duration_ms"] for r in rows if r["model"] == "A"])
    return {p: float(np.percentile(xs, p)) for p in pcts} if len(xs) else {}


def axis_stats_near(rows, model, target, tol_frac=0.1):
    rows_m = [r for r in rows if r["model"] == model]
    xs = np.array([r["fit_window_duration_ms"] for r in rows_m])
    tol = max(target * tol_frac, 20.0)
    mask = np.abs(xs - target) <= tol
    sel_rows = [r for r, m in zip(rows_m, mask) if m]
    if not sel_rows:
        return None
    out = dict(n=len(sel_rows))
    for axis_col, name in (("error_x_mm", "x"), ("error_y_width_mm", "y_width"), ("error_z_mm", "z")):
        vals = np.abs([r[axis_col] for r in sel_rows if not np.isnan(r[axis_col])])
        if len(vals):
            out[f"median_abs_{name}_mm"] = float(np.median(vals))
            out[f"p90_abs_{name}_mm"] = float(np.percentile(vals, 90))
    return out


def main():
    log_append("=== axis_decomposition_all_flights.py starting ===")
    pooled_k = load_pooled_k()
    targets = load_final_point_targets()
    durations = load_durations()
    flights = enumerate_eligible_flights()
    log_append(f"pooled_k={pooled_k:.6e}, {len(flights)} eligible flights, "
               f"{len(durations)} flights with known total duration")

    t0 = time.time()
    all_results = {}
    tasks = [(s, f, pooled_k, targets) for s, f in flights]
    with ProcessPoolExecutor() as ex:
        futures = {ex.submit(_worker, t): t for t in tasks}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            all_results[(r["session"], r["flight"])] = r
            done += 1
            if done % 20 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} flights processed")
                log_append(f"progress: {done}/{len(tasks)} flights processed")
    elapsed = time.time() - t0
    print(f"Batch done in {elapsed:.1f}s")
    log_append(f"batch complete: {len(tasks)} flights in {elapsed:.1f}s (parallel=True)")

    n_ok = sum(1 for r in all_results.values() if r["status"] == "ok")
    log_append(f"{n_ok} flights ok (expect 158, matching the original Phase 2 run)")

    all_rows = []
    for r in all_results.values():
        if r["status"] == "ok":
            all_rows.extend(r["rows"])

    # ---- REPRODUCTION CHECK (must pass before trusting anything else) ----
    original = load_original_errors()
    mismatches = []
    n_compared = 0
    max_diff = 0.0
    for r in all_rows:
        key = (r["session"], r["flight"], r["N"], r["model"])
        if key not in original:
            continue
        if np.isnan(r["error_mm"]):
            continue
        n_compared += 1
        diff = abs(r["error_mm"] - original[key])
        max_diff = max(max_diff, diff)
        if diff > 1e-3:
            mismatches.append((key, r["error_mm"], original[key], diff))

    print(f"\n=== REPRODUCTION CHECK ===")
    print(f"Compared {n_compared} rows against the existing prediction_sweep_all_flights.csv")
    print(f"Max abs diff: {max_diff:.6f} mm, {len(mismatches)} mismatches (tol=1e-3mm)")
    log_append(f"REPRODUCTION CHECK: compared {n_compared} rows, max_diff={max_diff:.6f}mm, "
               f"{len(mismatches)} mismatches (tol=1e-3mm)")
    if mismatches:
        print("*** MISMATCHES FOUND -- STOPPING, do not trust axis decomposition ***")
        for key, new, old, diff in mismatches[:10]:
            print(f"  {key}: new={new:.4f} old={old:.4f} diff={diff:.4f}")
        log_append(f"*** REPRODUCTION CHECK FAILED: {len(mismatches)} mismatches -- "
                   f"STOPPING before trusting axis decomposition ***")
        sys.exit(1)
    else:
        print("Reproduction VERIFIED: error_mm matches the existing CSV within float precision.")
        log_append("Reproduction VERIFIED -- error_mm matches the existing CSV within float "
                   "precision (max diff <1e-3mm) -- trusting the new axis-decomposed data")

    # ---- axis-reconciliation check ----
    recon_diffs = []
    for r in all_rows:
        if np.isnan(r["error_mm"]):
            continue
        recon = np.sqrt(r["error_x_mm"] ** 2 + r["error_y_width_mm"] ** 2 + r["error_z_mm"] ** 2)
        recon_diffs.append(abs(recon - r["error_mm"]))
    recon_diffs = np.array(recon_diffs)
    print(f"\nAxis-reconciliation check: max diff = {recon_diffs.max():.6f}mm "
          f"(sqrt(x^2+y^2+z^2) vs error_mm), n={len(recon_diffs)}")
    log_append(f"Axis-reconciliation check: max diff = {recon_diffs.max():.6f}mm across "
               f"{len(recon_diffs)} rows -- {'PASS' if recon_diffs.max() < 1e-3 else 'FAIL'}")

    # ---- write prediction_sweep_axis_decomposed.csv ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "prediction_sweep_axis_decomposed.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "N", "model", "lead_time_ms", "error_mm",
                    "error_x_mm", "error_y_width_mm", "error_z_mm"])
        for r in all_rows:
            w.writerow([r["session"], r["flight"], r["N"], r["model"], f"{r['lead_time_ms']:.2f}",
                        f"{r['error_mm']:.4f}" if not np.isnan(r["error_mm"]) else "",
                        f"{r['error_x_mm']:.4f}" if not np.isnan(r["error_x_mm"]) else "",
                        f"{r['error_y_width_mm']:.4f}" if not np.isnan(r["error_y_width_mm"]) else "",
                        f"{r['error_z_mm']:.4f}" if not np.isnan(r["error_z_mm"]) else ""])
    print(f"-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(all_rows)} rows)")

    # ---- assign fit_window_duration_ms + stratum, per the established relationship ----
    for r in all_rows:
        key = (r["session"], r["flight"])
        total_duration = durations.get(key)
        r["fit_window_duration_ms"] = (total_duration - r["lead_time_ms"]) if total_duration is not None else None
        r["stratum"] = ("short" if total_duration < STRATUM_SPLIT_MS else "long") if total_duration is not None else None

    summary_rows = []
    for stratum in ("short", "long"):
        stratum_rows = [r for r in all_rows if r["stratum"] == stratum and not np.isnan(r["error_mm"])]
        n_flights = len({(r["session"], r["flight"]) for r in stratum_rows})
        make_axis_panel_plot(stratum_rows, stratum, OUT_DIR / f"axis_error_{stratum}.png", n_flights)

        reps = representative_points(stratum_rows, REPRESENTATIVE_PERCENTILES)
        for pct, target in reps.items():
            for model in ("A", "B", "C"):
                stats = axis_stats_near(stratum_rows, model, target)
                if stats is None:
                    continue
                row = dict(stratum=stratum, percentile=pct, target_obs_duration_ms=round(target, 1),
                           model=model, n_points=stats["n"])
                for k, v in stats.items():
                    if k != "n":
                        row[k] = round(v, 2)
                summary_rows.append(row)

    fieldnames = ["stratum", "percentile", "target_obs_duration_ms", "model", "n_points",
                  "median_abs_x_mm", "p90_abs_x_mm", "median_abs_y_width_mm", "p90_abs_y_width_mm",
                  "median_abs_z_mm", "p90_abs_z_mm"]
    csv_path2 = OUT_DIR / "axis_summary_table.csv"
    with open(csv_path2, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in summary_rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    print(f"-> {csv_path2}")
    log_append(f"wrote {csv_path2} ({len(summary_rows)} rows)")

    print("\n=== Model C width-axis (Y) error at representative points ===")
    for r in summary_rows:
        if r["model"] == "C":
            y_med = r.get("median_abs_y_width_mm")
            verdict = "INSIDE +-100mm" if y_med is not None and y_med <= 100 else "OUTSIDE +-100mm"
            print(f"  stratum={r['stratum']} p{r['percentile']} (obs_dur={r['target_obs_duration_ms']:.0f}ms): "
                  f"median|Y|={y_med}mm p90|Y|={r.get('p90_abs_y_width_mm')}mm -> {verdict}")
            log_append(f"Model C width(Y)-axis at stratum={r['stratum']} p{r['percentile']} "
                       f"(obs_dur={r['target_obs_duration_ms']:.0f}ms): median|Y|={y_med}mm, "
                       f"p90|Y|={r.get('p90_abs_y_width_mm')}mm -> {verdict}")

    log_append("=== axis_decomposition_all_flights.py complete ===")


if __name__ == "__main__":
    main()
