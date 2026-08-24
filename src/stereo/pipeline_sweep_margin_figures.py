# pipeline_sweep_margin_figures.py
#
# claude/prompts/2026-08-05_1233_pi_pipeline_sweep_new_graphs.md
#
# Figures 1-3 of the corrected feasibility analysis (Figure 4, velocity by
# axis, is BLOCKED -- per-component velocity error was never persisted, see
# worklog). Read-only against margin_analysis.csv (pipeline_sweep_
# margin_analysis.py's output) -- no CSV regenerated, no Pi re-run.
#
# Dataviz skill conventions, light mode, static PNG. Categorical colours
# fixed across all figures tonight: FLAT=blue, MID=amber, LOB=red.
#
# Accuracy is a CONVERGENCE result (early-cutoff vs full-arc reference,
# decision 76) -- NOT ground truth. Labelled explicitly in Figure 3.

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "results" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection"
FIG_DIR = SWEEP_DIR / "figures2"
MARGIN_CSV = FIG_DIR / "margin_analysis.csv"

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
COLORS = {"FLAT": "#2a78d6", "MID": "#e39a1f", "LOB": "#e34948"}
INFEASIBLE_FILL = "#e34948"
BIN_ORDER = ["FLAT", "MID", "LOB"]
DEADLINE_MS = {"FLAT": 490.0, "MID": 710.0, "LOB": 1080.0}
POSITION_ERROR_THRESHOLD_MM = 100.0
DPI = 300


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


def load_rows():
    with open(MARGIN_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in r:
            if k != "bin" and k != "feasible_p95":
                r[k] = float(r[k])
        r["feasible_p95"] = r["feasible_p95"] == "True"
    return rows


def by_bin(rows):
    return {b: sorted([r for r in rows if r["bin"] == b], key=lambda r: r["T_ms"]) for b in BIN_ORDER}


def max_usable_t(rows_b):
    feasible = [r["T_ms"] for r in rows_b if r["feasible_p95"]]
    return max(feasible) if feasible else None


def figure1_margin(rows):
    binned = by_bin(rows)
    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=DPI)
    style_axes(ax)

    y_min = min(min(r["margin_p95_ms"] for r in binned[b]) for b in BIN_ORDER)
    y_max = max(max(r["margin_median_ms"] for r in binned[b]) for b in BIN_ORDER)
    ax.axhspan(y_min - 50, 0, color=INFEASIBLE_FILL, alpha=0.07, zorder=0)
    ax.axhline(0, color=INK_MUTED, linewidth=1.5, linestyle=(0, (1, 2)), zorder=2)
    ax.annotate("margin = 0 (feasibility boundary)", xy=(1260, 0), xytext=(1260, 25),
                fontsize=8.5, color=INK_MUTED, ha="right", va="bottom")

    for b in BIN_ORDER:
        rs = binned[b]
        x = np.array([r["T_ms"] for r in rs])
        m_p95 = np.array([r["margin_p95_ms"] for r in rs])
        m_med = np.array([r["margin_median_ms"] for r in rs])
        mt = max_usable_t(rs)

        ax.plot(x, m_med, color=COLORS[b], linewidth=1.25, linestyle=(0, (4, 2)), alpha=0.55, zorder=2)
        ax.plot(x, m_p95, color=COLORS[b], linewidth=2.25, marker="o", markersize=5,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.0,
                solid_capstyle="round", label=f"{b} margin_p95 (deadline={DEADLINE_MS[b]:.0f}ms)", zorder=3)
        if mt is not None:
            ax.axvline(mt, color=COLORS[b], linewidth=1.25, linestyle=(0, (1, 1)), alpha=0.6, zorder=1)
            ax.annotate(f"max-usable-t={mt:.0f}ms", xy=(mt, y_max * 0.9 - (BIN_ORDER.index(b) * y_max * 0.12)),
                        fontsize=7.5, color=COLORS[b], ha="left", va="center", rotation=0)

    ax.set_xlabel("prediction cutoff time t (ms)")
    ax.set_ylabel("margin_p95(t) = deadline - t - latency_p95(t)  (ms)")
    ax.set_xlim(100, 1400)
    ax.set_title("Feasibility margin vs cutoff time (worst-case, p95 latency)\n"
                 "solid=p95 guarantee, dashed=median (reference only) -- shaded region = infeasible",
                 fontsize=11.5, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure1_margin.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure2_feasibility_panels(rows):
    binned = by_bin(rows)
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 5.5), dpi=DPI, sharey=False)

    for ax, b in zip(axes, BIN_ORDER):
        style_axes(ax)
        rs = binned[b]
        x = np.array([r["T_ms"] for r in rs])
        t_ready_med = np.array([r["T_ready_median_ms"] for r in rs])
        t_ready_p95 = np.array([r["T_ready_p95_ms"] for r in rs])
        deadline = DEADLINE_MS[b]
        mt = max_usable_t(rs)

        y_top = max(t_ready_p95.max(), deadline) * 1.05
        ax.axhspan(deadline, y_top, color=INFEASIBLE_FILL, alpha=0.08, zorder=0)
        ax.axhline(deadline, color=INK_MUTED, linewidth=1.5, linestyle=(0, (1, 2)), zorder=2)

        ax.plot(x, t_ready_med, color=COLORS[b], linewidth=1.5, linestyle=(0, (4, 2)),
                alpha=0.6, label="T_ready median", zorder=2)
        ax.plot(x, t_ready_p95, color=COLORS[b], linewidth=2.25, marker="o", markersize=5,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.0,
                solid_capstyle="round", label="T_ready p95", zorder=3)
        if mt is not None:
            ax.axvline(mt, color=INK_SECONDARY, linewidth=1.25, linestyle=(0, (1, 1)), zorder=1)

        ax.set_xlabel("cutoff t (ms)")
        if b == "FLAT":
            ax.set_ylabel("T_ready(t) = t + latency(t)  (ms)")
        ax.set_title(f"{b}  (deadline={deadline:.0f}ms" + (f", max-usable-t={mt:.0f}ms)" if mt else ", INFEASIBLE at all t)"),
                     fontsize=10.5, color=INK_PRIMARY, loc="left")
        ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK_SECONDARY)

    fig.suptitle("Pipeline-ready time vs cutoff time, per regime (shaded = infeasible, above deadline)",
                 fontsize=12.5, color=INK_PRIMARY, x=0.02, ha="left", y=1.02)
    fig.tight_layout()
    out = FIG_DIR / "figure2_feasibility_panels.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure3_position_error(rows):
    binned = by_bin(rows)
    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=DPI)
    style_axes(ax)

    for b in BIN_ORDER:
        rs = binned[b]
        x = np.array([r["T_ms"] for r in rs])
        med = np.array([r["position_error_median_mm"] for r in rs])
        iqr = np.array([r["position_error_iqr_mm"] for r in rs])
        mt = max_usable_t(rs)

        ax.fill_between(x, med - iqr / 2, med + iqr / 2, color=COLORS[b], alpha=0.10, zorder=1)
        ax.plot(x, med, color=COLORS[b], linewidth=2, marker="o", markersize=5,
                markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=1.0,
                solid_capstyle="round", label=f"{b}", zorder=3)
        if mt is not None:
            ax.axvline(mt, color=COLORS[b], linewidth=1.5, linestyle=(0, (1, 1)), zorder=2)

    ax.axhline(POSITION_ERROR_THRESHOLD_MM, color=INK_MUTED, linewidth=1.25,
               linestyle=(0, (1, 2)), zorder=1)
    ax.annotate("100mm threshold (provisional)", xy=(1260, POSITION_ERROR_THRESHOLD_MM),
                xytext=(1260, POSITION_ERROR_THRESHOLD_MM + 25), fontsize=8, color=INK_MUTED,
                ha="right", va="bottom")

    ax.set_xlabel("prediction cutoff time t (ms) -- vertical lines = each regime's max-usable-t")
    ax.set_ylabel("crossing-point position error, median (mm, shaded=IQR)")
    ax.set_xlim(100, 1400)
    ax.set_title("Position-error convergence at the FEASIBLE operating point\n"
                 "(CONVERGENCE vs full-arc fit -- placeholder, NOT ground truth; "
                 "~106mm label-vs-fit reference floor, decision 77)",
                 fontsize=11, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure3_position_error_at_operating_point.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    rows = load_rows()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    p1 = figure1_margin(rows)
    print(f"Figure 1 -> {p1}")
    p2 = figure2_feasibility_panels(rows)
    print(f"Figure 2 -> {p2}")
    p3 = figure3_position_error(rows)
    print(f"Figure 3 -> {p3}")

    for p in (p1, p2, p3):
        img = plt.imread(p)
        h, w = img.shape[0], img.shape[1]
        print(f"  {p.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")

    print("\nFigure 4 (velocity error by axis) BLOCKED -- per-component velocity "
          "error not available in existing outputs. See worklog.")


if __name__ == "__main__":
    main()
