# ransac_threshold_sweep_figures.py
#
# Three report figures from the RANSAC inlier-distance-threshold sweep.
# Read-only against the 4 tables ransac_threshold_sweep_aggregate.py wrote --
# no CSV regenerated or modified.
#
# Palette: dataviz skill's validated default (references/palette.md), light
# mode, static PNG for thesis inclusion -- same convention as
# ransac_sweep_figures.py. Figure 2 has 7 individual-flight lines + 1 mean
# line: per the skill's own guidance ("past three [validated] slots, fold to
# 'Other' or facet" for all-pairs/small-multiples contexts), 7 distinct
# categorical hues can't be guaranteed pairwise-distinct -- so individual
# flights are drawn as one de-emphasis (muted gray) group, identity carried
# by a single legend entry, with the one line the story is about (the
# subset mean) in the bold red accent. This is the documented alternative
# to over-coloring, not an improvised workaround.
#
# Usage:
#   python src/stereo/ransac_threshold_sweep_figures.py

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
SWEEP_DIR = REPO_ROOT / "data" / "trajectory_fit_comparison" / "ransac_distance_threshold_sweep"
FIG_DIR = SWEEP_DIR / "figures"

RAW_CSV = SWEEP_DIR / "ransac_threshold_sweep_raw.csv"
TABLE1_CSV = SWEEP_DIR / "table1_threshold_error_population.csv"
TABLE2_CSV = SWEEP_DIR / "table2_threshold_error_unstable_subset.csv"
TABLE3_CSV = SWEEP_DIR / "table3_threshold_jaccard_unstable_subset.csv"
TABLE4_CSV = SWEEP_DIR / "table4_threshold_inlier_count.csv"

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
RED = "#e34948"
GRAY_DEEMPHASIS = "#c3c2b7"

THRESHOLD_VALUES_MM = [50.0, 75.0, 100.0, 125.0, 150.0]
UNSTABLE_FLIGHTS = [
    ("2026_07_21_gym", "flight_121"), ("2026_07_21_gym", "flight_122"),
    ("2026_07_21_gym", "flight_38"), ("2026_07_21_gym", "flight_45"),
    ("2026_07_21_gym", "flight_46"), ("2026_07_21_gym", "flight_22"),
    ("2026_07_21_gym", "flight_125"),
]

DPI = 300
FIGSIZE = (8.0, 5.0)


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


def load_csv_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def figure1_error(t1_rows, t2_rows):
    x = np.array([float(r["threshold_mm"]) for r in t1_rows])
    pop_med = np.array([float(r["median_error_mm"]) for r in t1_rows])
    sub_med = np.array([float(r["median_error_mm"]) for r in t2_rows])

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)
    ax.plot(x, pop_med, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="full population (n=150 flights) -- median", zorder=3)
    ax.plot(x, sub_med, color=RED, linewidth=2, linestyle=(0, (5, 3)), marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            label="structurally unstable subset (n=7 flights) -- median", zorder=4)

    ax.set_xlabel("RANSAC inlier distance threshold (mm)")
    ax.set_ylabel("final-point prediction error (mm)")
    ax.set_xticks(THRESHOLD_VALUES_MM)
    ax.axvline(75.0, color=INK_MUTED, linewidth=1, linestyle=(0, (1, 2)), zorder=1)
    y_top = max(pop_med.max(), sub_med.max())
    ax.annotate("production (75mm)", xy=(75, y_top), xytext=(76.5, y_top),
                fontsize=8, color=INK_MUTED, ha="left", va="top")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("RANSAC prediction error vs inlier distance threshold\n(n_iterations=3, fit window 430ms)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure1_threshold_error_population_vs_subset.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure2_jaccard(t3_rows):
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    by_flight = {}
    for r in t3_rows:
        key = (r["session"], r["flight"])
        by_flight.setdefault(key, {})[float(r["threshold_mm"])] = float(r["mean_jaccard"])

    for key in UNSTABLE_FLIGHTS:
        vals = by_flight.get(key, {})
        xs = [t for t in THRESHOLD_VALUES_MM if t in vals]
        ys = [vals[t] for t in xs]
        if xs:
            ax.plot(xs, ys, color=GRAY_DEEMPHASIS, linewidth=1.25, alpha=0.9, zorder=2)

    mean_vals = []
    for t in THRESHOLD_VALUES_MM:
        vs = [by_flight[key][t] for key in UNSTABLE_FLIGHTS if key in by_flight and t in by_flight[key]]
        mean_vals.append(float(np.mean(vs)) if vs else np.nan)
    ax.plot(THRESHOLD_VALUES_MM, mean_vals, color=RED, linewidth=2.5, marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", zorder=4)

    # legend proxies (one for the gray group, one for the mean)
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], color=GRAY_DEEMPHASIS, linewidth=1.25, label="individual flights (n=7)"),
        Line2D([0], [0], color=RED, linewidth=2.5, marker="o", markersize=8,
               markerfacecolor=RED, markeredgecolor=SURFACE, label="subset mean"),
    ]
    ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2,
              frameon=False, fontsize=8.5, labelcolor=INK_SECONDARY)

    ax.set_xlabel("RANSAC inlier distance threshold (mm)")
    ax.set_ylabel("mean pairwise Jaccard overlap\n(accepted-inlier sets across 25 seeds)")
    ax.set_xticks(THRESHOLD_VALUES_MM)
    ax.set_ylim(0, 1)
    ax.set_title("Structurally unstable subset: inlier-set stability vs threshold\n"
                 "(rising = threshold was the bottleneck; flat = candidate-pool mechanism, decision 66)",
                 fontsize=11.5, color=INK_PRIMARY, loc="left", pad=12)
    fig.tight_layout()
    out = FIG_DIR / "figure2_threshold_jaccard_unstable_subset.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure3_inlier_count(t4_rows):
    x = np.array([float(r["threshold_mm"]) for r in t4_rows])
    pop = np.array([float(r["population_mean_inliers"]) for r in t4_rows])
    sub = np.array([float(r["unstable_subset_mean_inliers"]) for r in t4_rows])

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)
    ax.plot(x, pop, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="full population -- mean inlier count", zorder=3)
    ax.plot(x, sub, color=RED, linewidth=2, linestyle=(0, (5, 3)), marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            label="structurally unstable subset -- mean inlier count", zorder=4)

    ax.set_xlabel("RANSAC inlier distance threshold (mm)")
    ax.set_ylabel("mean accepted inlier count")
    ax.set_xticks(THRESHOLD_VALUES_MM)
    ax.set_title("Mean accepted-inlier count vs threshold: population vs unstable subset",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure3_threshold_inlier_count.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    t1_rows = load_csv_rows(TABLE1_CSV)
    t2_rows = load_csv_rows(TABLE2_CSV)
    t3_rows = load_csv_rows(TABLE3_CSV)
    t4_rows = load_csv_rows(TABLE4_CSV)

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    p1 = figure1_error(t1_rows, t2_rows)
    print(f"Figure 1 -> {p1}")
    p2 = figure2_jaccard(t3_rows)
    print(f"Figure 2 -> {p2}")
    p3 = figure3_inlier_count(t4_rows)
    print(f"Figure 3 -> {p3}")

    for p in (p1, p2, p3):
        img = plt.imread(p)
        h, w = img.shape[0], img.shape[1]
        print(f"  {p.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")


if __name__ == "__main__":
    main()
