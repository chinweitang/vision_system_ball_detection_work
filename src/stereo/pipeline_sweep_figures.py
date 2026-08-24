# pipeline_sweep_figures.py
#
# Three report figures from the Pi prediction-pipeline sweep. Read-only
# against pipeline_sweep_summary_by_bin_T.csv / pipeline_sweep_raw.csv --
# no CSV regenerated or modified.
#
# Palette: dataviz skill's validated default (references/palette.md), light
# mode, static PNG -- same convention as every other figure tonight.
# Categorical hues in fixed order: FLAT=blue, MID=amber, LOB=red (matches
# budget_by_elevation_bin.py's figure, same session, same meaning).
#
# ACCURACY IS A CONVERGENCE RESULT (early-cutoff vs full-arc reference),
# NOT ground truth -- every figure title/caption says so explicitly.

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "results" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection"
FIG_DIR = SWEEP_DIR / "figures"

SUMMARY_CSV = SWEEP_DIR / "pipeline_sweep_summary_by_bin_T.csv"

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
COLORS = {"FLAT": "#2a78d6", "MID": "#e39a1f", "LOB": "#e34948"}
BIN_ORDER = ["FLAT", "MID", "LOB"]
HEADLINE_T = 490.0
CADENCE_MS = 1000.0 / 60.0
POSITION_ERROR_THRESHOLD_MM = 100.0

DPI = 300
FIGSIZE = (9.0, 5.5)


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


def by_bin(rows):
    out = {b: sorted([r for r in rows if r["bin"] == b], key=lambda r: float(r["T_ms"])) for b in BIN_ORDER}
    return out


def figure1_accuracy(rows):
    binned = by_bin(rows)
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    for b in BIN_ORDER:
        rs = binned[b]
        x = np.array([float(r["T_ms"]) for r in rs])
        y = np.array([float(r["hit_miss_accuracy"]) * 100.0 for r in rs])
        h490 = next(r for r in rs if float(r["T_ms"]) == HEADLINE_T)
        label = f"{b} (n={h490['n_fit_ok']}/{h490['n_airborne']} @490ms)"
        ax.plot(x, y, color=COLORS[b], linewidth=2, marker="o", markersize=6,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.2,
                solid_capstyle="round", label=label, zorder=3)

    ax.axvline(HEADLINE_T, color=INK_MUTED, linewidth=1.25, linestyle=(0, (1, 2)), zorder=1)
    ax.annotate("t=490ms (v1 deadline)", xy=(HEADLINE_T, 45), xytext=(HEADLINE_T + 25, 45),
                fontsize=8.5, color=INK_MUTED, ha="left", va="center")

    ax.set_xlabel("prediction cutoff time t (ms)")
    ax.set_ylabel("HIT/MISS accuracy vs full-arc reference (%)")
    ax.set_ylim(0, 105)
    ax.set_xlim(100, 1400)
    ax.set_title("HIT/MISS convergence accuracy vs cutoff time, by elevation regime\n"
                 "(CONVERGENCE vs full-arc fit -- placeholder, NOT ground truth)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure1_accuracy_vs_t.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure2_position_error(rows):
    binned = by_bin(rows)
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    for b in BIN_ORDER:
        rs = binned[b]
        x = np.array([float(r["T_ms"]) for r in rs])
        med = np.array([float(r["position_error_median_mm"]) for r in rs])
        ax.plot(x, med, color=COLORS[b], linewidth=2, marker="o", markersize=6,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.2,
                solid_capstyle="round", label=f"{b}", zorder=3)

    ax.axhline(POSITION_ERROR_THRESHOLD_MM, color=INK_MUTED, linewidth=1.25,
               linestyle=(0, (1, 2)), zorder=1)
    ax.annotate("100mm threshold (provisional)", xy=(1260, POSITION_ERROR_THRESHOLD_MM),
                xytext=(1260, POSITION_ERROR_THRESHOLD_MM + 30), fontsize=8, color=INK_MUTED,
                ha="right", va="bottom")
    ax.axvline(HEADLINE_T, color=INK_MUTED, linewidth=1.25, linestyle=(0, (1, 2)), zorder=1)

    ax.set_xlabel("prediction cutoff time t (ms)")
    ax.set_ylabel("crossing-point position error, median (mm)")
    ax.set_xlim(100, 1400)
    ax.set_title("Position-error convergence vs cutoff time, by elevation regime\n"
                 "(CONVERGENCE vs full-arc fit -- placeholder, NOT ground truth)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure2_position_error_vs_t.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure3_latency(rows, detect_median_ms):
    binned = by_bin(rows)
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    for b in BIN_ORDER:
        rs = binned[b]
        x = np.array([float(r["T_ms"]) for r in rs])
        y = np.array([float(r["latency_median_ms"]) for r in rs])
        ax.plot(x, y, color=COLORS[b], linewidth=2, marker="o", markersize=6,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.2,
                solid_capstyle="round", label=f"{b} latency(t)", zorder=3)

    ax.axhline(HEADLINE_T, color=INK_MUTED, linewidth=1.5, linestyle=(0, (4, 2)), zorder=2)
    ax.annotate("490ms v1 deadline", xy=(1260, HEADLINE_T), xytext=(1260, HEADLINE_T + 15),
                fontsize=8.5, color=INK_MUTED, ha="right", va="bottom")

    legend_text = (f"threaded detect (median) = {detect_median_ms:.1f}ms\n"
                   f"60fps cadence = {CADENCE_MS:.1f}ms\n"
                   f"(capture-bound: detect < cadence)")
    ax.text(0.02, 0.96, legend_text, transform=ax.transAxes, fontsize=8.5,
            color=INK_SECONDARY, ha="left", va="top", linespacing=1.6,
            family="monospace", bbox=dict(facecolor=SURFACE, edgecolor=BASELINE,
                                           boxstyle="round,pad=0.4", linewidth=1))

    ax.set_xlabel("prediction cutoff time t (ms)")
    ax.set_ylabel("pipeline latency, median (ms)\n(last-pair detect + triangulate + RANSAC + predict + 1-frame lag)")
    ax.set_xlim(100, 1400)
    ax.set_title("Pipeline latency vs cutoff time, by elevation regime\n"
                 "(concurrent-with-capture model -- latency never binds at any regime/t)",
                 fontsize=11.5, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="center right", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure3_latency_vs_t.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    rows = load_csv_rows(SUMMARY_CSV)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # pull the pooled detect median from the raw CSV for figure 3's annotation
    raw_rows = load_csv_rows(SWEEP_DIR / "pipeline_sweep_raw.csv")
    detect_vals = [float(r["last_pair_detect_ms"]) for r in raw_rows if r["status"] == "ok"]
    detect_median_ms = float(np.median(detect_vals))

    p1 = figure1_accuracy(rows)
    print(f"Figure 1 -> {p1}")
    p2 = figure2_position_error(rows)
    print(f"Figure 2 -> {p2}")
    p3 = figure3_latency(rows, detect_median_ms)
    print(f"Figure 3 -> {p3}")

    for p in (p1, p2, p3):
        img = plt.imread(p)
        h, w = img.shape[0], img.shape[1]
        print(f"  {p.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")


if __name__ == "__main__":
    main()
