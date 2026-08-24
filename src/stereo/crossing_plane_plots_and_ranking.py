# crossing_plane_plots_and_ranking.py
#
# Reads results/prediction/01_crossing_plane_setup/crossing_classification.csv
# (produced by crossing_plane_classification.py) and produces:
#   - pooled + per-registration Y-Z scatter plots (aperture box drawn,
#     points colored by class) -- dataviz-skill conventions, static PNG,
#     light mode
#   - a ranked ~20-candidate table for manual crossing-bracket labelling
#
# Does not re-fit anything -- pure post-processing of the classification CSV.

import csv
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "results" / "prediction" / "01_crossing_plane_setup"
CSV_PATH = OUT_DIR / "crossing_classification.csv"

APERTURE_SIZE_MM = 2000.0
DURATION_FILTER_MS = 1200.0
N_CANDIDATES = 20
N_ELEVATION_BINS = 4

# dataviz skill: status palette (light mode) + chart chrome, from references/palette.md
COLOR_SURFACE = "#fcfcfb"
COLOR_PRIMARY_INK = "#0b0b0b"
COLOR_SECONDARY_INK = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRIDLINE = "#e1e0d9"
COLOR_BASELINE = "#c3c2b7"
COLOR_HIT = "#0ca30c"          # status: good
COLOR_MISS_HIGH_WIDE = "#fab219"  # status: warning


def load_rows() -> list:
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def to_float(v):
    return float(v) if v not in (None, "") else None


# ---- plotting -----------------------------------------------------------------

def style_axes(ax):
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(COLOR_BASELINE)
    ax.tick_params(colors=COLOR_MUTED, labelsize=9)
    ax.grid(True, color=COLOR_GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def plot_scatter(rows: list, title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 7), facecolor=COLOR_SURFACE)
    style_axes(ax)

    # aperture box, hairline border, no fill
    box = plt.Rectangle((0, 0), APERTURE_SIZE_MM, APERTURE_SIZE_MM,
                         fill=False, edgecolor=COLOR_BASELINE, linewidth=1.5, zorder=1)
    ax.add_patch(box)

    hits = [(to_float(r["crossing_Y"]), to_float(r["crossing_Z"])) for r in rows if r["cls"] == "HIT"]
    misses = [(to_float(r["crossing_Y"]), to_float(r["crossing_Z"])) for r in rows if r["cls"] == "MISS_HIGH_WIDE"]

    if hits:
        hx, hy = zip(*hits)
        ax.scatter(hx, hy, s=36, marker="o", facecolor=COLOR_HIT, edgecolor=COLOR_SURFACE,
                   linewidth=0.6, label=f"HIT (n={len(hits)})", zorder=3)
    if misses:
        mx, my = zip(*misses)
        ax.scatter(mx, my, s=42, marker="^", facecolor=COLOR_MISS_HIGH_WIDE, edgecolor=COLOR_SURFACE,
                   linewidth=0.6, label=f"MISS_HIGH_WIDE (n={len(misses)})", zorder=3)

    ax.set_xlabel("Y  (mm, along tape from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_ylabel("Z  (mm, up from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_title(title, color=COLOR_PRIMARY_INK, fontsize=12, loc="left")

    all_y = [p[0] for p in hits + misses]
    all_z = [p[1] for p in hits + misses]
    if all_y:
        pad = 400.0
        ax.set_xlim(min(0, min(all_y)) - pad, max(APERTURE_SIZE_MM, max(all_y)) + pad)
        ax.set_ylim(min(0, min(all_z)) - pad, max(APERTURE_SIZE_MM, max(all_z)) + pad)

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=COLOR_SECONDARY_INK)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=COLOR_SURFACE)
    plt.close(fig)


# ---- ranking --------------------------------------------------------------

def rank_candidates(rows: list) -> list:
    crossers = [r for r in rows if r["cls"] in ("HIT", "MISS_HIGH_WIDE")]
    crossers = [r for r in crossers if to_float(r["duration_ms"]) is not None
                and to_float(r["duration_ms"]) > DURATION_FILTER_MS]
    for r in crossers:
        r["_edge_dist"] = to_float(r["edge_dist"])
        r["_elevation"] = to_float(r["elevation_deg"])
        r["_flagged"] = bool(r["flag_reason"])

    crossers = [r for r in crossers if r["_edge_dist"] is not None and r["_elevation"] is not None]
    if not crossers:
        return []

    elevations = [r["_elevation"] for r in crossers]
    lo, hi = min(elevations), max(elevations)
    bin_width = (hi - lo) / N_ELEVATION_BINS if hi > lo else 1.0
    for r in crossers:
        idx = int((r["_elevation"] - lo) / bin_width) if bin_width else 0
        r["_bin"] = min(idx, N_ELEVATION_BINS - 1)

    # sort key: unflagged first, then smallest edge distance (closest to the
    # aperture boundary = most informative for bracket-labelling); flagged
    # entries are deprioritized, not excluded, so a few can still surface.
    def sort_key(r):
        return (r["_flagged"], r["_edge_dist"])

    bins = {i: sorted([r for r in crossers if r["_bin"] == i], key=sort_key)
            for i in range(N_ELEVATION_BINS)}

    ranked = []
    seen = set()
    round_idx = 0
    while len(ranked) < N_CANDIDATES:
        progressed = False
        for i in range(N_ELEVATION_BINS):
            pool = bins[i]
            if round_idx < len(pool):
                r = pool[round_idx]
                key = (r["session"], r["flight_id"])
                if key not in seen:
                    seen.add(key)
                    ranked.append(r)
                    progressed = True
                    if len(ranked) >= N_CANDIDATES:
                        break
        if not progressed:
            break
        round_idx += 1

    return ranked


def write_ranked_table(ranked: list, out_path: Path) -> None:
    fieldnames = ["rank", "registration", "session", "flight_id", "cls", "crossing_Y",
                  "crossing_Z", "edge_dist", "duration_ms", "elevation_deg", "speed_m_s",
                  "flagged", "flag_reason"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, r in enumerate(ranked, 1):
            w.writerow(dict(
                rank=i, registration=r["registration"], session=r["session"],
                flight_id=r["flight_id"], cls=r["cls"], crossing_Y=r["crossing_Y"],
                crossing_Z=r["crossing_Z"], edge_dist=r["_edge_dist"],
                duration_ms=r["duration_ms"], elevation_deg=r["_elevation"],
                speed_m_s=r["speed_m_s"], flagged=r["_flagged"], flag_reason=r["flag_reason"],
            ))


def main():
    rows = load_rows()

    plot_scatter(rows, "Crossing-plane classification -- pooled (all registrations)",
                 OUT_DIR / "crossing_scatter_pooled.png")
    for reg_key in ("REG_15", "REG_21_1", "REG_21_2"):
        reg_rows = [r for r in rows if r["registration"] == reg_key]
        plot_scatter(reg_rows, f"Crossing-plane classification -- {reg_key}",
                     OUT_DIR / f"crossing_scatter_{reg_key}.png")

    miss_short = [r for r in rows if r["cls"] == "MISS_SHORT"]
    with open(OUT_DIR / "miss_short_flights.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["registration", "session", "flight_id", "duration_ms", "elevation_deg", "flag_reason"])
        for r in miss_short:
            w.writerow([r["registration"], r["session"], r["flight_id"], r["duration_ms"],
                        r["elevation_deg"], r["flag_reason"]])

    ranked = rank_candidates(rows)
    write_ranked_table(ranked, OUT_DIR / "ranked_candidates.csv")

    print(f"Plots written: crossing_scatter_pooled.png + 3 per-registration PNGs, in {OUT_DIR}")
    print(f"MISS_SHORT flights: {len(miss_short)} -> miss_short_flights.csv")
    print(f"Ranked candidates: {len(ranked)} -> ranked_candidates.csv")
    print()
    print(f"{'rank':<5}{'flight':<28}{'cls':<16}{'Y':>8}{'Z':>8}{'edge_dist':>10}{'elev':>8}{'flagged':>9}")
    for i, r in enumerate(ranked, 1):
        print(f"{i:<5}{r['session']+'/'+r['flight_id']:<28}{r['cls']:<16}"
              f"{to_float(r['crossing_Y']):>8.0f}{to_float(r['crossing_Z']):>8.0f}{r['_edge_dist']:>10.0f}"
              f"{r['_elevation']:>8.1f}{str(r['_flagged']):>9}")


if __name__ == "__main__":
    main()
