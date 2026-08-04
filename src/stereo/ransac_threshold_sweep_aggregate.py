# ransac_threshold_sweep_aggregate.py
#
# Builds the 4 required tables from ransac_threshold_sweep.py's raw output.
# Read-only against ransac_threshold_sweep_raw.csv -- no RANSAC execution.
#
# table1: population pooled error (median/IQR) + seed-to-seed spread per threshold.
# table2: same, restricted to the 7-flight structurally-unstable subset.
# table3: per threshold, per unstable-subset flight -- mean pairwise Jaccard
#   overlap of accepted-inlier-sets across the 25 seeds. THE decisive table:
#   states directly whether loosening the threshold stabilizes which points
#   get selected as inliers (rising Jaccard) or leaves it unchanged (flat).
# table4: mean accepted inlier count, population vs subset, per threshold --
#   confirms whether the candidate/inlier pool is actually growing as the
#   threshold loosens (context for tables 1-3).
#
# Usage:
#   python src/stereo/ransac_threshold_sweep_aggregate.py

import csv
import itertools
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "ransac_distance_threshold_sweep"
RAW_CSV = SWEEP_DIR / "ransac_threshold_sweep_raw.csv"

THRESHOLD_VALUES_MM = [50.0, 75.0, 100.0, 125.0, 150.0]
UNSTABLE_FLIGHTS = [
    ("2026_07_21_gym", "flight_121"), ("2026_07_21_gym", "flight_122"),
    ("2026_07_21_gym", "flight_38"), ("2026_07_21_gym", "flight_45"),
    ("2026_07_21_gym", "flight_46"), ("2026_07_21_gym", "flight_22"),
    ("2026_07_21_gym", "flight_125"),
]


def load_raw():
    rows = []
    with open(RAW_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] != "ok":
                continue
            row["threshold_mm"] = float(row["threshold_mm"])
            row["error_mm"] = float(row["error_mm"])
            row["n_inliers"] = int(row["n_inliers"])
            row["seed"] = int(row["seed"])
            row["accepted_frames"] = frozenset(int(x) for x in row["accepted_frames"].split(";") if x)
            rows.append(row)
    return rows


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    if not (a | b):
        return 1.0
    return len(a & b) / len(a | b)


def error_stats(rows_subset, thresh):
    vals = np.array([r["error_mm"] for r in rows_subset if r["threshold_mm"] == thresh])
    if len(vals) == 0:
        return None
    return dict(n_runs=len(vals), median_error_mm=float(np.median(vals)),
                iqr_error_mm=float(np.percentile(vals, 75) - np.percentile(vals, 25)))


def seed_std_summary(rows_subset, thresh, flights):
    stds = []
    for key in flights:
        vals = np.array([r["error_mm"] for r in rows_subset
                          if r["threshold_mm"] == thresh and (r["session"], r["flight"]) == key])
        if len(vals) >= 2:
            stds.append(float(np.std(vals)))
    return float(np.median(stds)) if stds else float("nan")


def main():
    raw = load_raw()
    all_flights = sorted(set((r["session"], r["flight"]) for r in raw))
    subset_rows = [r for r in raw if (r["session"], r["flight"]) in UNSTABLE_FLIGHTS]

    print(f"Raw rows: {len(raw)}. Population flights: {len(all_flights)}. "
          f"Unstable-subset rows: {len(subset_rows)} (expected up to {len(UNSTABLE_FLIGHTS)*5*25})")

    # ---- table1: population pooled error + seed-spread per threshold ----
    t1_rows = []
    for thresh in THRESHOLD_VALUES_MM:
        stats = error_stats(raw, thresh)
        std_summary = seed_std_summary(raw, thresh, all_flights)
        t1_rows.append(dict(threshold_mm=thresh, n_runs=stats["n_runs"],
                             median_error_mm=stats["median_error_mm"], iqr_error_mm=stats["iqr_error_mm"],
                             seed_std_median_mm=std_summary))
    with open(SWEEP_DIR / "table1_threshold_error_population.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(t1_rows[0].keys()))
        w.writeheader()
        for r in t1_rows:
            row = dict(r)
            for k in ("median_error_mm", "iqr_error_mm", "seed_std_median_mm"):
                row[k] = f"{row[k]:.2f}"
            w.writerow(row)
    print(f"-> table1_threshold_error_population.csv")

    # ---- table2: unstable-subset pooled error + seed-spread per threshold ----
    t2_rows = []
    for thresh in THRESHOLD_VALUES_MM:
        stats = error_stats(subset_rows, thresh)
        std_summary = seed_std_summary(subset_rows, thresh, UNSTABLE_FLIGHTS)
        t2_rows.append(dict(threshold_mm=thresh, n_runs=stats["n_runs"],
                             median_error_mm=stats["median_error_mm"], iqr_error_mm=stats["iqr_error_mm"],
                             seed_std_median_mm=std_summary))
    with open(SWEEP_DIR / "table2_threshold_error_unstable_subset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(t2_rows[0].keys()))
        w.writeheader()
        for r in t2_rows:
            row = dict(r)
            for k in ("median_error_mm", "iqr_error_mm", "seed_std_median_mm"):
                row[k] = f"{row[k]:.2f}"
            w.writerow(row)
    print(f"-> table2_threshold_error_unstable_subset.csv")

    # ---- table3: mean pairwise Jaccard overlap across 25 seeds, per (threshold, flight) ----
    t3_rows = []
    jaccard_by_flight_thresh = {}
    for thresh in THRESHOLD_VALUES_MM:
        for key in UNSTABLE_FLIGHTS:
            session, flight = key
            sets = [r["accepted_frames"] for r in subset_rows
                    if r["threshold_mm"] == thresh and (r["session"], r["flight"]) == key]
            if len(sets) < 2:
                continue
            pairwise = [jaccard(a, b) for a, b in itertools.combinations(sets, 2)]
            mean_jaccard = float(np.mean(pairwise))
            t3_rows.append(dict(threshold_mm=thresh, session=session, flight=flight,
                                 n_seeds=len(sets), n_pairs=len(pairwise), mean_jaccard=mean_jaccard))
            jaccard_by_flight_thresh[(key, thresh)] = mean_jaccard

    with open(SWEEP_DIR / "table3_threshold_jaccard_unstable_subset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["threshold_mm", "session", "flight", "n_seeds", "n_pairs", "mean_jaccard"])
        w.writeheader()
        for r in t3_rows:
            row = dict(r)
            row["mean_jaccard"] = f"{row['mean_jaccard']:.4f}"
            w.writerow(row)
    print(f"-> table3_threshold_jaccard_unstable_subset.csv ({len(t3_rows)} rows)")

    # ---- table4: mean inlier count, population vs subset, per threshold ----
    t4_rows = []
    for thresh in THRESHOLD_VALUES_MM:
        pop_inliers = np.array([r["n_inliers"] for r in raw if r["threshold_mm"] == thresh])
        sub_inliers = np.array([r["n_inliers"] for r in subset_rows if r["threshold_mm"] == thresh])
        t4_rows.append(dict(threshold_mm=thresh,
                             population_mean_inliers=float(np.mean(pop_inliers)) if len(pop_inliers) else float("nan"),
                             unstable_subset_mean_inliers=float(np.mean(sub_inliers)) if len(sub_inliers) else float("nan")))
    with open(SWEEP_DIR / "table4_threshold_inlier_count.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["threshold_mm", "population_mean_inliers", "unstable_subset_mean_inliers"])
        w.writeheader()
        for r in t4_rows:
            row = dict(r)
            row["population_mean_inliers"] = f"{row['population_mean_inliers']:.2f}"
            row["unstable_subset_mean_inliers"] = f"{row['unstable_subset_mean_inliers']:.2f}"
            w.writerow(row)
    print(f"-> table4_threshold_inlier_count.csv")

    # ---- console summary + explicit text conclusion ----
    print(f"\n=== TABLE 1: population error vs threshold ===")
    for r in t1_rows:
        print(f"  threshold={r['threshold_mm']:.0f}mm  n={r['n_runs']:5d}  "
              f"median_err={r['median_error_mm']:7.1f}mm  IQR={r['iqr_error_mm']:7.1f}mm  "
              f"seed_std={r['seed_std_median_mm']:6.1f}mm")

    print(f"\n=== TABLE 2: unstable-subset error vs threshold ===")
    for r in t2_rows:
        print(f"  threshold={r['threshold_mm']:.0f}mm  n={r['n_runs']:5d}  "
              f"median_err={r['median_error_mm']:7.1f}mm  IQR={r['iqr_error_mm']:7.1f}mm  "
              f"seed_std={r['seed_std_median_mm']:6.1f}mm")

    print(f"\n=== TABLE 4: mean inlier count vs threshold ===")
    for r in t4_rows:
        print(f"  threshold={r['threshold_mm']:.0f}mm  population={r['population_mean_inliers']:.1f}  "
              f"unstable_subset={r['unstable_subset_mean_inliers']:.1f}")

    print(f"\n=== TABLE 3 summary: mean Jaccard overlap by flight, across thresholds ===")
    for key in UNSTABLE_FLIGHTS:
        vals = [jaccard_by_flight_thresh.get((key, t)) for t in THRESHOLD_VALUES_MM]
        vals_str = "  ".join(f"{v:.3f}" if v is not None else "n/a" for v in vals)
        print(f"  {key[0]}/{key[1]:12s}: {vals_str}")
    mean_across_subset = [float(np.mean([jaccard_by_flight_thresh[(k, t)] for k in UNSTABLE_FLIGHTS
                                          if (k, t) in jaccard_by_flight_thresh])) for t in THRESHOLD_VALUES_MM]
    print(f"  {'MEAN OF SUBSET':24s}: " + "  ".join(f"{v:.3f}" for v in mean_across_subset))

    jaccard_50 = mean_across_subset[0]
    jaccard_150 = mean_across_subset[-1]
    jaccard_rise = jaccard_150 - jaccard_50
    err_50 = t2_rows[0]["median_error_mm"]
    err_150 = t2_rows[-1]["median_error_mm"]
    err_change = err_150 - err_50

    print(f"\n=== EXPLICIT CONCLUSION ===")
    print(f"Mean Jaccard overlap (unstable subset), threshold 50mm -> 150mm: "
          f"{jaccard_50:.3f} -> {jaccard_150:.3f} (change: {jaccard_rise:+.3f})")
    print(f"Unstable-subset median error, threshold 50mm -> 150mm: "
          f"{err_50:.1f}mm -> {err_150:.1f}mm (change: {err_change:+.1f}mm)")
    if jaccard_rise > 0.10:
        verdict = ("Jaccard overlap RISES MEANINGFULLY as threshold loosens -- threshold WAS a real "
                    "contributor to this subset's instability (candidate pool too tight at 75mm).")
    else:
        verdict = ("Jaccard overlap stays FLAT (change <=0.10) across the threshold range -- threshold is "
                    "NOT the bottleneck for this subset. Confirms decision 66's candidate-pool mechanism: "
                    "the instability is about which points are AVAILABLE/geometrically consistent, not "
                    "how loosely 'close enough' is defined.")
    print(verdict)
    if abs(err_change) < 20 and jaccard_rise <= 0.10:
        print("Error does NOT meaningfully track the (flat) Jaccard trend either -- consistent with "
              "threshold not being the fix for these 7 flights.")
    elif jaccard_rise > 0.10 and err_change < -20:
        print("Error improvement COINCIDES with rising Jaccard overlap -- threshold loosening is a "
              "real, usable lever for this subset.")
    else:
        print("Jaccard and error trends do not move cleanly together -- worth inspecting table3 "
              "per-flight, not just the subset mean.")


if __name__ == "__main__":
    main()
