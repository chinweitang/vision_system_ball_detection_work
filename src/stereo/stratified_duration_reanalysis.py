# stratified_duration_reanalysis.py
# Further cheap follow-up to the all-flights gravity-vs-drag generalization:
# stratify the existing Phase 2 result by each flight's total observable
# duration (short <1000ms / long >=1000ms, per the bimodal distribution
# found in flight_duration_distribution.py), and switch the primary
# comparison axis from lead time to observation duration (fit_window_duration_ms).
# Pure re-slicing/re-plotting of already-computed data -- no new fitting.
# See claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md.
#
# Usage:
#   python src/stereo/stratified_duration_reanalysis.py

import csv
import sys
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

LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md"
ALL_FLIGHTS_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "all_flights"
PHASE2_CSV = ALL_FLIGHTS_DIR / "phase2" / "prediction_sweep_all_flights.csv"
HEALTH_FLAGS_CSV = ALL_FLIGHTS_DIR / "phase2" / "ransac_health_flags.csv"
DURATIONS_CSV = ALL_FLIGHTS_DIR / "duration_distribution" / "flight_durations.csv"
OUT_DIR = ALL_FLIGHTS_DIR / "stratified_by_duration"

STRATUM_SPLIT_MS = 1000.0
MODEL_COLORS = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green"}
REPRESENTATIVE_PERCENTILES = [25, 50, 75, 90]


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


def load_durations():
    out = {}
    with open(DURATIONS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight"])] = float(row["total_duration_ms"])
    return out


def load_health_flags():
    flagged = set()
    with open(HEALTH_FLAGS_CSV, newline="") as f:
        for row in csv.DictReader(f):
            flagged.add((row["session"], row["flight"], row["model"], int(row["N"])))
    return flagged


def load_rows(durations):
    rows = []
    with open(PHASE2_CSV, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["session"], row["flight"])
            if key not in durations:
                continue
            if row["error_mm"] == "":
                continue  # NaN (convergence failure), skip
            total_duration = durations[key]
            lead_time_ms = float(row["lead_time_ms"])
            fit_window_duration_ms = total_duration - lead_time_ms
            stratum = "short" if total_duration < STRATUM_SPLIT_MS else "long"
            rows.append(dict(
                session=row["session"], flight=row["flight"], N=int(row["N"]), model=row["model"],
                lead_time_ms=lead_time_ms, fit_window_duration_ms=fit_window_duration_ms,
                error_mm=float(row["error_mm"]), stratum=stratum,
            ))
    return rows


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


def make_plot(stratum_rows, x_key, bin_width, title, out_path, n_flights):
    fig, ax = plt.subplots(figsize=(11, 7))
    for model in ("A", "B", "C"):
        rows_m = [r for r in stratum_rows if r["model"] == model]
        if not rows_m:
            continue
        xs = np.array([r[x_key] for r in rows_m])
        ys = np.array([r["error_mm"] for r in rows_m])
        is_flagged = np.array([r["flagged"] for r in rows_m])

        ax.scatter(xs[~is_flagged], ys[~is_flagged], s=6, alpha=0.15, color=MODEL_COLORS[model],
                   label=f"{model} (points)")
        if is_flagged.any():
            ax.scatter(xs[is_flagged], ys[is_flagged], s=18, alpha=0.8, color=MODEL_COLORS[model],
                       marker="x", label=f"{model} (RANSAC-health-flagged)")

        centers, medians, q1s, q3s = binned_trend(xs, ys, bin_width)
        if centers:
            ax.plot(centers, medians, color=MODEL_COLORS[model], linewidth=2.5, label=f"{model} median trend")
            ax.fill_between(centers, q1s, q3s, color=MODEL_COLORS[model], alpha=0.15)

    ax.set_yscale("log")
    ax.set_xlabel(x_key.replace("_", " "))
    ax.set_ylabel("prediction error at target (mm, log scale)")
    ax.set_title(title + f" (n={n_flights} flights)")
    handles, labels_ = ax.get_legend_handles_labels()
    seen = set()
    uniq = [(h, l) for h, l in zip(handles, labels_) if not (l in seen or seen.add(l))]
    ax.legend([h for h, l in uniq], [l for h, l in uniq], fontsize=7, loc="upper right")
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")
    log_append(f"wrote {out_path}")


def representative_points(rows, x_key, model, pcts):
    xs = np.array([r[x_key] for r in rows if r["model"] == model])
    return {p: float(np.percentile(xs, p)) for p in pcts} if len(xs) else {}


def summary_stats_near(rows, x_key, model, target, tol_frac=0.1):
    xs = np.array([r[x_key] for r in rows if r["model"] == model])
    ys = np.array([r["error_mm"] for r in rows if r["model"] == model])
    tol = max(target * tol_frac, 20.0)
    sel = ys[np.abs(xs - target) <= tol]
    if len(sel) == 0:
        return None
    return len(sel), float(np.median(sel)), float(np.percentile(sel, 90))


def main():
    log_append("=== stratified_duration_reanalysis.py starting ===")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    durations = load_durations()
    flagged_set = load_health_flags()
    all_rows = load_rows(durations)

    flight_strata = {}
    for (session, flight), dur in durations.items():
        flight_strata[(session, flight)] = "short" if dur < STRATUM_SPLIT_MS else "long"
    n_short = sum(1 for v in flight_strata.values() if v == "short")
    n_long = sum(1 for v in flight_strata.values() if v == "long")
    print(f"Flight counts: short (<{STRATUM_SPLIT_MS:.0f}ms) = {n_short}, long (>={STRATUM_SPLIT_MS:.0f}ms) = {n_long}")
    log_append(f"Stratum split at {STRATUM_SPLIT_MS:.0f}ms: short={n_short} flights, long={n_long} flights "
               f"(expected long > short per the bimodal histogram's denser second cluster -- "
               f"{'confirmed' if n_long > n_short else 'NOT confirmed -- unexpected, investigate'})")

    for r in all_rows:
        r["flagged"] = (r["session"], r["flight"], r["model"], r["N"]) in flagged_set

    summary_rows = []
    for stratum in ("short", "long"):
        stratum_rows = [r for r in all_rows if r["stratum"] == stratum]
        n_flights = len({(r["session"], r["flight"]) for r in stratum_rows})
        print(f"\n=== stratum={stratum}: {len(stratum_rows)} rows, {n_flights} flights ===")

        # ---- primary: observation-duration axis ----
        make_plot(stratum_rows, "fit_window_duration_ms", bin_width=50,
                  title=f"Observation-duration axis (PRIMARY), stratum={stratum}",
                  out_path=OUT_DIR / f"prediction_error_vs_obsduration_{stratum}.png",
                  n_flights=n_flights)

        # ---- secondary: lead-time axis, stratified ----
        make_plot(stratum_rows, "lead_time_ms", bin_width=100,
                  title=f"Lead-time axis (secondary), stratum={stratum}",
                  out_path=OUT_DIR / f"prediction_error_vs_leadtime_{stratum}.png",
                  n_flights=n_flights)

        # ---- representative points + summary table ----
        for axis_key, axis_name in (("fit_window_duration_ms", "obs_duration_ms"), ("lead_time_ms", "lead_time_ms")):
            reps = representative_points(stratum_rows, axis_key, "A", REPRESENTATIVE_PERCENTILES)
            # use Model A's own percentile breakdown as the representative point
            # set (all 3 models share the same rows/x-values per (flight,N), so
            # any model's percentiles describe the same achievable range)
            for pct, target in reps.items():
                for model in ("A", "B", "C"):
                    stats = summary_stats_near(stratum_rows, axis_key, model, target)
                    if stats is None:
                        continue
                    n, median, p90 = stats
                    summary_rows.append(dict(
                        stratum=stratum, axis=axis_name, percentile=pct, target_value_ms=round(target, 1),
                        model=model, n_points=n, median_error_mm=round(median, 2), p90_error_mm=round(p90, 2),
                    ))
                print(f"  {axis_name} p{pct}: target={target:.1f}ms")
                log_append(f"stratum={stratum} axis={axis_name} p{pct} representative point = {target:.1f}ms "
                           f"(derived from this stratum's own achievable range)")

    csv_path = OUT_DIR / "stratified_summary_table.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["stratum", "axis", "percentile", "target_value_ms",
                                          "model", "n_points", "median_error_mm", "p90_error_mm"])
        w.writeheader()
        for r in summary_rows:
            w.writerow(r)
    print(f"\n-> {csv_path}")
    log_append(f"wrote {csv_path} ({len(summary_rows)} rows)")

    log_append("=== stratified_duration_reanalysis.py complete ===")


if __name__ == "__main__":
    main()
