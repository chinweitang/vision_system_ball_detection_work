# crossing_plane_candidate_reselection.py
#
# v1 (crossing_plane_plots_and_ranking.py's ranked_candidates.csv) sorted by
# edge_dist ascending -- wrong for the actual goal (validating Model-C
# crossing-state prediction across trajectory regimes), since it filled the
# list with near-edge lobs and excluded flat drives entirely, which are a
# physically distinct regime (fast, shallow, crossing early in descent) from
# lobs (steep, near/past apex).
#
# This script re-selects 20 candidates from the SAME crossing_classification.csv,
# stratified by launch elevation (FLAT/MID/LOB), selecting for spread across
# the aperture box within each stratum (not edge proximity), with 2 reserved
# probe picks (a decision-boundary flight, a few flagged-flat drives).
#
# Pure post-processing of crossing_classification.csv -- no re-fit, no
# frozen-code changes, does not touch 01_crossing_plane_setup/.

import csv
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

IN_DIR = REPO_ROOT / "data" / "prediction" / "01_crossing_plane_setup"
OUT_DIR = REPO_ROOT / "data" / "prediction" / "02_candidate_reselection"
LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-04_1347_crossing_plane_setup_worklog.md"

APERTURE_SIZE_MM = 2000.0
BOX_CENTER = (1000.0, 1000.0)

FLAT_MAX = 15.0
MID_MAX = 45.0

N_TOTAL = 20
N_FLAGGED_FLAT_PROBES = 3
BIN_TARGETS = {"FLAT": 7, "MID": 7, "LOB": 6}  # sums to 20; reserved picks count toward these
REG_DIVERSITY_PENALTY_MM = 300.0  # soft per-repeat-registration penalty in the FPS score

RESERVED_FLIGHT = dict(session="2026_07_21_gym", flight_id="flight_109", reason="boundary probe")


def log_append(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"{msg}\n")


def to_float(v):
    return float(v) if v not in (None, "") else None


def load_crossers() -> list:
    with open(IN_DIR / "crossing_classification.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    crossers = [r for r in rows if r["cls"] in ("HIT", "MISS_HIGH_WIDE")]
    for r in crossers:
        r["_Y"] = to_float(r["crossing_Y"])
        r["_Z"] = to_float(r["crossing_Z"])
        r["_elev"] = to_float(r["elevation_deg"])
        r["_edge_dist"] = to_float(r["edge_dist"])
        r["_flagged"] = bool(r["flag_reason"])
        r["_key"] = (r["session"], r["flight_id"])
    return crossers


def elevation_bin(elev: float) -> str:
    if elev < FLAT_MAX:
        return "FLAT"
    if elev < MID_MAX:
        return "MID"
    return "LOB"


def dist(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def farthest_point_select(pool: list, k: int, seed_points: list, reg_counts: dict) -> list:
    """Greedy max-min-distance spread selection over (Y,Z), seeded by
    already-reserved points in this bin so new picks spread away from them
    too. Soft per-registration diversity penalty, not a hard constraint."""
    selected = []
    seed_positions = list(seed_points)
    remaining = list(pool)

    while len(selected) < k and remaining:
        best, best_score = None, -1.0
        for r in remaining:
            p = (r["_Y"], r["_Z"])
            all_ref = seed_positions + [(s["_Y"], s["_Z"]) for s in selected]
            min_d = min((dist(p, q) for q in all_ref), default=1e9)
            penalty = REG_DIVERSITY_PENALTY_MM * reg_counts.get(r["registration"], 0)
            score = min_d - penalty
            if best is None or score > best_score:
                best, best_score = r, score
        selected.append(best)
        remaining.remove(best)
        reg_counts[best["registration"]] = reg_counts.get(best["registration"], 0) + 1

    return selected


def select_bin_spread(bin_pool: list, k: int, already_reserved_in_bin: list, reg_counts: dict) -> list:
    """Unflagged-first spread selection, falling back to flagged only if the
    unflagged pool in this bin is exhausted before reaching k."""
    reserved_keys = {r["_key"] for r in already_reserved_in_bin}
    pool = [r for r in bin_pool if r["_key"] not in reserved_keys]
    unflagged = [r for r in pool if not r["_flagged"]]
    flagged = [r for r in pool if r["_flagged"]]

    seed_points = [(r["_Y"], r["_Z"]) for r in already_reserved_in_bin]
    picked = farthest_point_select(unflagged, k, seed_points, reg_counts)
    if len(picked) < k:
        need = k - len(picked)
        more = farthest_point_select(flagged, need, seed_points + [(p["_Y"], p["_Z"]) for p in picked], reg_counts)
        picked += more
    return picked


def main():
    log_append("")
    crossers = load_crossers()
    log_append(f"- [14:16] Loaded {len(crossers)} crossers (HIT+MISS_HIGH_WIDE) from crossing_classification.csv.")

    for r in crossers:
        r["elevation_bin"] = elevation_bin(r["_elev"])

    bins = {"FLAT": [], "MID": [], "LOB": []}
    for r in crossers:
        bins[r["elevation_bin"]].append(r)

    for name in ("FLAT", "MID", "LOB"):
        pool = bins[name]
        n_hit = sum(1 for r in pool if r["cls"] == "HIT")
        n_miss = sum(1 for r in pool if r["cls"] == "MISS_HIGH_WIDE")
        n_flag = sum(1 for r in pool if r["_flagged"])
        n_unflag = len(pool) - n_flag
        log_append(f"- [14:16] {name} bin: {len(pool)} crossers "
                   f"(HIT={n_hit}, MISS_HIGH_WIDE={n_miss}; unflagged={n_unflag}, flagged={n_flag})")

    # ---- reserved picks ------------------------------------------------
    selection_reason = {}
    reserved = []

    boundary = next((r for r in crossers if r["_key"] == (RESERVED_FLIGHT["session"], RESERVED_FLIGHT["flight_id"])), None)
    if boundary is None:
        log_append(f"- [14:17] *** {RESERVED_FLIGHT['flight_id']} not found among crossers -- skipping this reserved pick. ***")
    else:
        reserved.append(boundary)
        selection_reason[boundary["_key"]] = "boundary probe (edge_dist~11mm)"
        log_append(f"- [14:17] Reserved: {boundary['session']}/{boundary['flight_id']} "
                   f"(bin={boundary['elevation_bin']}, edge_dist={boundary['_edge_dist']:.0f}mm) - boundary probe.")

    flat_flagged = [r for r in bins["FLAT"] if r["_flagged"] and r["_key"] not in {b["_key"] for b in reserved}]
    flat_flagged_sorted = sorted(flat_flagged, key=lambda r: dist((r["_Y"], r["_Z"]), BOX_CENTER))
    flat_probes = flat_flagged_sorted[:N_FLAGGED_FLAT_PROBES]
    if len(flat_probes) < N_FLAGGED_FLAT_PROBES:
        log_append(f"- [14:17] Only {len(flat_probes)}/{N_FLAGGED_FLAT_PROBES} flagged-FLAT crossers available "
                   f"(pool has {len(flat_flagged)}) -- taking all of them, not padding from elsewhere.")
    for r in flat_probes:
        selection_reason[r["_key"]] = "flagged-flat probe (nearest mid-box)"
        log_append(f"- [14:17] Reserved: {r['session']}/{r['flight_id']} (flagged-FLAT, "
                   f"dist-to-center={dist((r['_Y'], r['_Z']), BOX_CENTER):.0f}mm) - flat-regime + flag-validity probe.")
    reserved += flat_probes

    reserved_by_bin = {"FLAT": [], "MID": [], "LOB": []}
    for r in reserved:
        reserved_by_bin[r["elevation_bin"]].append(r)

    # ---- fill remaining slots per bin, spread selection -----------------
    reg_counts = {}  # registration -> count picked so far (soft diversity across all bins)
    final_selection = list(reserved)

    for name in ("FLAT", "MID", "LOB"):
        target = BIN_TARGETS[name]
        already = len(reserved_by_bin[name])
        need = target - already
        available = len(bins[name]) - already
        if need > available:
            log_append(f"- [14:18] {name} bin: target {target}, {already} reserved, only {available} more "
                       f"available (pool={len(bins[name])}) -- taking all {available}, NOT padding from another bin.")
            need = available
        picked = select_bin_spread(bins[name], need, reserved_by_bin[name], reg_counts)
        for r in picked:
            selection_reason[r["_key"]] = f"{name} stratum, box-position spread"
        final_selection += picked
        log_append(f"- [14:18] {name} bin: filled {len(picked)} more (target {target}, {already} reserved) "
                   f"via box-spread selection.")

    if len(final_selection) < N_TOTAL:
        log_append(f"- [14:18] *** Only {len(final_selection)}/{N_TOTAL} candidates found total "
                   f"(bins ran short) -- reporting fewer than 20 rather than padding. ***")

    log_append(f"- [14:19] Final selection: {len(final_selection)} candidates, per bin:")
    for name in ("FLAT", "MID", "LOB"):
        n = sum(1 for r in final_selection if r["elevation_bin"] == name)
        log_append(f"    {name}: {n}")

    # ---- outputs --------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    v2_fields = ["registration", "session", "flight_id", "cls", "elevation_bin", "elevation_deg",
                 "speed_m_s", "crossing_Y", "crossing_Z", "crossing_speed", "crossing_vel_xyz",
                 "edge_dist", "flagged", "flag_reason", "selection_reason"]
    with open(OUT_DIR / "ranked_candidates_v2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=v2_fields)
        w.writeheader()
        for r in final_selection:
            w.writerow(dict(
                registration=r["registration"], session=r["session"], flight_id=r["flight_id"],
                cls=r["cls"], elevation_bin=r["elevation_bin"], elevation_deg=r["_elev"],
                speed_m_s=r["speed_m_s"], crossing_Y=r["_Y"], crossing_Z=r["_Z"],
                crossing_speed=r["crossing_speed"], crossing_vel_xyz=r["crossing_vel_xyz"],
                edge_dist=r["_edge_dist"], flagged=r["_flagged"], flag_reason=r["flag_reason"],
                selection_reason=selection_reason.get(r["_key"], ""),
            ))
    log_append(f"- [14:19] Wrote ranked_candidates_v2.csv ({len(final_selection)} rows).")

    all_fields = ["registration", "session", "flight_id", "cls", "elevation_bin", "elevation_deg",
                  "speed_m_s", "crossing_Y", "crossing_Z", "crossing_speed", "crossing_vel_xyz",
                  "edge_dist", "flagged", "flag_reason"]
    with open(OUT_DIR / "all_crossers_stratified.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_fields)
        w.writeheader()
        for r in sorted(crossers, key=lambda r: (r["elevation_bin"], r["_elev"])):
            w.writerow(dict(
                registration=r["registration"], session=r["session"], flight_id=r["flight_id"],
                cls=r["cls"], elevation_bin=r["elevation_bin"], elevation_deg=r["_elev"],
                speed_m_s=r["speed_m_s"], crossing_Y=r["_Y"], crossing_Z=r["_Z"],
                crossing_speed=r["crossing_speed"], crossing_vel_xyz=r["crossing_vel_xyz"],
                edge_dist=r["_edge_dist"], flagged=r["_flagged"], flag_reason=r["flag_reason"],
            ))
    log_append(f"- [14:19] Wrote all_crossers_stratified.csv ({len(crossers)} rows).")

    plot_candidates(final_selection, reserved, OUT_DIR / "candidates_scatter.png")
    log_append(f"- [14:20] Wrote candidates_scatter.png.")

    return final_selection


# ---- plotting (dataviz skill conventions, light mode, status+categorical) --

COLOR_SURFACE = "#fcfcfb"
COLOR_PRIMARY_INK = "#0b0b0b"
COLOR_SECONDARY_INK = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRIDLINE = "#e1e0d9"
COLOR_BASELINE = "#c3c2b7"
# categorical slots 1/2/3 (blue/orange/aqua) for FLAT/MID/LOB -- all-pairs
# validated for exactly 3 series per references/palette.md
COLOR_FLAT = "#2a78d6"
COLOR_MID = "#eb6834"
COLOR_LOB = "#1baf7a"
BIN_COLOR = {"FLAT": COLOR_FLAT, "MID": COLOR_MID, "LOB": COLOR_LOB}


def style_axes(ax):
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(COLOR_BASELINE)
    ax.tick_params(colors=COLOR_MUTED, labelsize=9)
    ax.grid(True, color=COLOR_GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def plot_candidates(selection: list, reserved: list, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 7.5), facecolor=COLOR_SURFACE)
    style_axes(ax)

    box = plt.Rectangle((0, 0), APERTURE_SIZE_MM, APERTURE_SIZE_MM,
                         fill=False, edgecolor=COLOR_BASELINE, linewidth=1.5, zorder=1)
    ax.add_patch(box)

    reserved_keys = {r["_key"] for r in reserved}
    seen_bins = set()
    for r in selection:
        marker = "o" if r["cls"] == "HIT" else "^"
        color = BIN_COLOR[r["elevation_bin"]]
        label = r["elevation_bin"] if r["elevation_bin"] not in seen_bins else None
        seen_bins.add(r["elevation_bin"])
        ax.scatter(r["_Y"], r["_Z"], s=70, marker=marker, facecolor=color,
                   edgecolor=COLOR_SURFACE, linewidth=0.8, zorder=3, label=label)
        if r["_key"] in reserved_keys:
            ax.annotate(r["flight_id"], (r["_Y"], r["_Z"]), textcoords="offset points",
                       xytext=(6, 6), fontsize=7.5, color=COLOR_PRIMARY_INK, zorder=4)

    ax.set_xlabel("Y  (mm, along tape from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_ylabel("Z  (mm, up from P_far)", color=COLOR_SECONDARY_INK, fontsize=10)
    ax.set_title("Candidate reselection (v2) -- stratified by elevation, spread by box position",
                color=COLOR_PRIMARY_INK, fontsize=11, loc="left")

    all_y = [r["_Y"] for r in selection]
    all_z = [r["_Z"] for r in selection]
    pad = 400.0
    ax.set_xlim(min(0, min(all_y)) - pad, max(APERTURE_SIZE_MM, max(all_y)) + pad)
    ax.set_ylim(min(0, min(all_z)) - pad, max(APERTURE_SIZE_MM, max(all_z)) + pad)

    from matplotlib.lines import Line2D
    bin_handles = [Line2D([0], [0], marker="s", color="none", markerfacecolor=BIN_COLOR[b],
                          markersize=8, label=b) for b in ("FLAT", "MID", "LOB")]
    shape_handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=COLOR_MUTED,
                            markersize=8, label="HIT"),
                      Line2D([0], [0], marker="^", color="none", markerfacecolor=COLOR_MUTED,
                            markersize=8, label="MISS_HIGH_WIDE")]
    legend = ax.legend(handles=bin_handles + shape_handles, loc="upper left", frameon=False,
                       fontsize=9, labelcolor=COLOR_SECONDARY_INK, ncol=1)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=COLOR_SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
