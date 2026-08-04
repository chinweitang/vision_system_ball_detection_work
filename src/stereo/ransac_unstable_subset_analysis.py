# ransac_unstable_subset_analysis.py
#
# Re-aggregates the EXISTING RANSAC sweep results (no new RANSAC runs),
# restricted to the 7 flights that stayed flagged as seed-to-seed-spread
# outliers even at n_iterations=25 (the "structurally unstable subset" from
# figure2_ransac_error_vs_niterations.png / decision log #68): 2026_07_21_gym/
# flight_121, flight_122, flight_38, flight_45, flight_46, flight_22, flight_125.
#
# Answers the question Figure 2 raised but didn't settle on its own: does
# cutting n_iterations cost THIS subset more than it costs the population,
# i.e. is n_iterations=3 actually safe for these flights specifically, not
# just on average.
#
# Read-only against data/trajectory_fit_comparison/ransac_iterations_sweep/
# ransac_sweep_raw.csv and seed_spread_outlier_flights.csv -- no RANSAC
# execution, no modification of either file.
#
# Usage:
#   python src/stereo/ransac_unstable_subset_analysis.py

import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "ransac_iterations_sweep"
RAW_CSV = SWEEP_DIR / "ransac_sweep_raw.csv"
OUT_TABLE = SWEEP_DIR / "table3_unstable_subset_error_by_niterations.csv"
OUT_FIG = SWEEP_DIR / "figures" / "figure3_unstable_subset_error_vs_niterations.png"

N_ITERATIONS_VALUES = [3, 5, 7, 10, 15, 25]
UNSTABLE_FLIGHTS = [
    ("2026_07_21_gym", "flight_121"), ("2026_07_21_gym", "flight_122"),
    ("2026_07_21_gym", "flight_38"), ("2026_07_21_gym", "flight_45"),
    ("2026_07_21_gym", "flight_46"), ("2026_07_21_gym", "flight_22"),
    ("2026_07_21_gym", "flight_125"),
]

# palette (references/palette.md, light mode) -- matches ransac_sweep_figures.py
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
RED = "#e34948"


def load_raw():
    rows = []
    with open(RAW_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] != "ok":
                continue
            rows.append(row)
    return rows


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(BASELINE)
        ax.spines[spine].set_linewidth(1)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def main():
    raw = load_raw()
    subset_rows = [r for r in raw if (r["session"], r["flight"]) in UNSTABLE_FLIGHTS]
    print(f"Subset rows in ransac_sweep_raw.csv: {len(subset_rows)} "
          f"(expected up to {len(UNSTABLE_FLIGHTS)} flights x {len(N_ITERATIONS_VALUES)} n_iterations x 25 seeds "
          f"= {len(UNSTABLE_FLIGHTS)*len(N_ITERATIONS_VALUES)*25})")

    # also compute the POPULATION's per-n_iterations median-of-per-flight-seed-std,
    # for a fair, freshly-computed comparison baseline (not relying on memory of
    # the original sweep's console output)
    all_flights = sorted(set((r["session"], r["flight"]) for r in raw))

    results = []
    for n_iter in N_ITERATIONS_VALUES:
        # -- subset pooled error --
        sub_errs = np.array([float(r["error_mm"]) for r in subset_rows if int(r["n_iterations"]) == n_iter])
        sub_median = float(np.median(sub_errs))
        sub_iqr = float(np.percentile(sub_errs, 75) - np.percentile(sub_errs, 25))

        # -- subset per-flight seed-to-seed spread (std AND IQR), summarised (median) across the 7 flights --
        sub_stds, sub_iqrs = [], []
        for key in UNSTABLE_FLIGHTS:
            vals = np.array([float(r["error_mm"]) for r in subset_rows
                              if int(r["n_iterations"]) == n_iter and (r["session"], r["flight"]) == key])
            if len(vals) >= 2:
                sub_stds.append(float(np.std(vals)))
                sub_iqrs.append(float(np.percentile(vals, 75) - np.percentile(vals, 25)))
        sub_spread_std_median = float(np.median(sub_stds)) if sub_stds else float("nan")
        sub_spread_iqr_median = float(np.median(sub_iqrs)) if sub_iqrs else float("nan")

        # -- population per-flight seed-to-seed spread, summarised (median), freshly computed --
        pop_stds = []
        for key in all_flights:
            vals = np.array([float(r["error_mm"]) for r in raw
                              if int(r["n_iterations"]) == n_iter and (r["session"], r["flight"]) == key])
            if len(vals) >= 2:
                pop_stds.append(float(np.std(vals)))
        pop_spread_std_median = float(np.median(pop_stds)) if pop_stds else float("nan")

        results.append(dict(n_iterations=n_iter, n_runs=len(sub_errs),
                             median_error_mm=sub_median, iqr_error_mm=sub_iqr,
                             subset_seed_std_median_mm=sub_spread_std_median,
                             subset_seed_iqr_median_mm=sub_spread_iqr_median,
                             population_seed_std_median_mm=pop_spread_std_median,
                             ratio_subset_over_population=sub_spread_std_median / pop_spread_std_median
                             if pop_spread_std_median else float("nan")))

    print(f"\n{'n_iter':>7s} {'n_runs':>7s} {'med_err':>9s} {'IQR_err':>9s} "
          f"{'subset_std':>11s} {'pop_std':>9s} {'ratio':>7s}")
    for r in results:
        print(f"{r['n_iterations']:7d} {r['n_runs']:7d} {r['median_error_mm']:9.1f} {r['iqr_error_mm']:9.1f} "
              f"{r['subset_seed_std_median_mm']:11.1f} {r['population_seed_std_median_mm']:9.1f} "
              f"{r['ratio_subset_over_population']:7.2f}x")

    with open(OUT_TABLE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        for r in results:
            row = dict(r)
            for k in ("median_error_mm", "iqr_error_mm", "subset_seed_std_median_mm",
                      "subset_seed_iqr_median_mm", "population_seed_std_median_mm",
                      "ratio_subset_over_population"):
                row[k] = f"{row[k]:.2f}"
            w.writerow(row)
    print(f"\n-> {OUT_TABLE}")

    # -- widening check: does subset spread grow faster (relatively) than population's as n drops --
    subset_std_n3 = results[0]["subset_seed_std_median_mm"]
    subset_std_n25 = results[-1]["subset_seed_std_median_mm"]
    pop_std_n3 = results[0]["population_seed_std_median_mm"]
    pop_std_n25 = results[-1]["population_seed_std_median_mm"]
    subset_widen_ratio = subset_std_n3 / subset_std_n25
    pop_widen_ratio = pop_std_n3 / pop_std_n25
    print(f"\nSubset spread widening n=25->n=3: {subset_std_n25:.1f}mm -> {subset_std_n3:.1f}mm "
          f"({subset_widen_ratio:.2f}x)")
    print(f"Population spread widening n=25->n=3: {pop_std_n25:.1f}mm -> {pop_std_n3:.1f}mm "
          f"({pop_widen_ratio:.2f}x)")

    # -- figure --
    n_arr = np.array([r["n_iterations"] for r in results], dtype=float)
    med_arr = np.array([r["median_error_mm"] for r in results])
    q25, q75 = [], []
    for n_iter in N_ITERATIONS_VALUES:
        vals = np.array([float(r["error_mm"]) for r in subset_rows if int(r["n_iterations"]) == n_iter])
        q25.append(np.percentile(vals, 25))
        q75.append(np.percentile(vals, 75))
    q25, q75 = np.array(q25), np.array(q75)

    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=300)
    style_axes(ax)
    ax.fill_between(n_arr, q25, q75, color=RED, alpha=0.12, zorder=1, linewidth=0)
    ax.plot(n_arr, med_arr, color=RED, linewidth=2, marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="structurally unstable subset (n=7 flights) -- median, IQR band",
            zorder=3)
    ax.set_xlabel("n_iterations")
    ax.set_ylabel("final-point prediction error (mm)")
    ax.set_xticks(N_ITERATIONS_VALUES)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Structurally unstable subset: prediction error vs iteration count",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=300, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print(f"-> {OUT_FIG}")


if __name__ == "__main__":
    main()
