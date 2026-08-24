"""Pooled trajectory-model comparison: prediction error vs observation window.

A READ of
    results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv
opened read-only and never written back. Nothing is re-fitted or re-run.

Pooled across ALL flights. No duration stratum, no elevation class, no binning
of any kind beyond the observation window itself.

THE X-AXIS IS DERIVED, NOT READ
There is no observation-window column. The sweep variable is `N`, the number of
points in the fit window, and the generating script warns that N is not
comparable across flights because frame densities differ. That warning is
checked here rather than accepted or ignored: each flight's frame period is
derived from its own consecutive-N lead-time steps, and all 158 flights come out
at an identical period (spread 0.0000 ms). With no spread there is no
incomparability, so

    observation window (ms) = (N - 1) * frame_period

is exact. The period is measured at runtime and asserted flat; it is NOT
hardcoded, and it is NOT assumed to be 1000/60 (it measures 16.65, not 16.667).
N-1 intervals because the window spans first point to last.

Do not confuse this axis with `lead_time_ms`, which is the file's own aggregation
axis and a different quantity running the opposite way: lead time is the gap from
the window's END to the target, so a longer observation window means a SHORTER
lead time.

STOP conditions:
  - pooled flight count is not 158
  - contributing n at a plotted window falls below 40 -> the x-range is
    truncated there rather than plotting thin data, and the cut is reported

Outputs:
    results/regenerate_figures/model_comparison_pooled/model_comparison_pooled.png
    results/regenerate_figures/model_comparison_pooled/model_comparison_pooled.csv
"""
import csv
import pathlib
import statistics as st
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import clean_figures as CF
import common as C

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = "results/trajectory_fit_comparison/all_flights/phase2/prediction_sweep_all_flights.csv"
OUT_DIR = ROOT / "results/regenerate_figures/model_comparison_pooled"
OUT_PNG = OUT_DIR / "model_comparison_pooled.png"
OUT_CSV = OUT_DIR / "model_comparison_pooled.csv"

EXPECTED_FLIGHTS = 158
MIN_N = 40

# The model codes are read from the file by key. They are never surfaced: a gate
# below asserts the rendered forms appear in no user-facing string.
SERIES = [
    ("A", "free gravity", "#2a78d6", "o"),
    ("B", "fixed gravity", "#eda100", "s"),
    ("C", "fixed gravity + drag", "#1baf7a", "D"),
]
FORBIDDEN = ["model a", "model b", "model c"]

PAGE_W_IN, DPI = 6.6, 4.9
FS_TITLE, FS_AXIS, FS_TICK, FS_LEGEND, FS_CAP = 11, 9.5, 8, 8, 6.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_rows():
    with open(ROOT / SRC, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def frame_period(rows):
    """Each flight's frame period, from its own consecutive-N lead-time steps.

    lead_time = t_target - t_window_end, and adding one point advances the window
    end by exactly one frame, so the step between consecutive N IS the period.
    Returns (period, spread) and stops if the spread is large enough that a
    single shared period would misrepresent some flights.
    """
    per = {}
    for r in rows:
        if r["model"] != "C":
            continue
        per.setdefault((r["session"], r["flight"]), {})[int(r["N"])] = \
            float(r["lead_time_ms"])
    dts = []
    for d in per.values():
        ns = sorted(d)
        steps = [d[a] - d[b] for a, b in zip(ns, ns[1:])]
        if steps:
            dts.append(st.median(steps))
    if not dts:
        stop("could not derive a frame period from lead_time_ms")
    spread = max(dts) - min(dts)
    if spread > 0.5:
        stop(f"frame period varies by {spread:.3f} ms across flights "
             f"({min(dts):.3f}..{max(dts):.3f}). N is then NOT comparable across "
             f"flights and (N-1)*period is not a sound observation-window axis - "
             f"which is exactly what the generating script warns about.")
    return st.median(dts), spread, len(dts)


def main():
    rows = read_rows()
    flights = {(r["session"], r["flight"]) for r in rows}
    print(f"read {SRC}")
    print(f"  {len(rows)} rows, {len(flights)} flights, "
          f"{len({r['flight'] for r in rows})} distinct bare flight ids")

    # ---- GATE 1: flight count -------------------------------------------
    if len(flights) != EXPECTED_FLIGHTS:
        stop(f"pooled flight count is {len(flights)}, expected {EXPECTED_FLIGHTS}")
    print(f"GATE 1 PASS: pooled flight count is {len(flights)}")

    period, spread, n_fl = frame_period(rows)
    print(f"  frame period derived from {n_fl} flights: {period:.4f} ms, "
          f"spread {spread:.4f} ms (1000/60 would be {1000/60:.4f})")

    # ---- exclusions -------------------------------------------------------
    excluded = {k: 0 for k, _, _, _ in SERIES}
    kept = []
    for r in rows:
        if not r["error_mm"].strip():
            excluded[r["model"]] = excluded.get(r["model"], 0) + 1
            continue
        kept.append(r)
    print("\nrows excluded for blank error_mm:")
    for key, label, _, _ in SERIES:
        print(f"  {label:<24} {excluded.get(key, 0):>4}")
    print(f"  {'total':<24} {sum(excluded.values()):>4} of {len(rows)}")

    # ---- aggregate --------------------------------------------------------
    by = {}
    for r in kept:
        by.setdefault((r["model"], int(r["N"])), []).append(float(r["error_mm"]))
    all_n = sorted({int(r["N"]) for r in rows})

    # ---- GATE 2: contributing n, truncate rather than plot thin ----------
    def min_n(n):
        return min(len(by.get((k, n), [])) for k, _, _, _ in SERIES)

    keep_ns = []
    for n in all_n:
        if min_n(n) < MIN_N:
            break
        keep_ns.append(n)
    dropped = [n for n in all_n if n not in keep_ns]
    interior = [n for n in dropped if n < max(keep_ns)]
    if interior:
        stop(f"contributing n falls below {MIN_N} at interior windows "
             f"{[round((n-1)*period,1) for n in interior]} ms - truncation cannot "
             f"fix an interior gap, so nothing is plotted")
    cut_ms = (max(keep_ns) - 1) * period
    print(f"\nGATE 2: contributing n >= {MIN_N} for N={min(keep_ns)}..{max(keep_ns)}"
          f"  ->  x truncated at {cut_ms:.1f} ms")
    if dropped:
        print(f"  dropped N={min(dropped)}..{max(dropped)} "
              f"({(min(dropped)-1)*period:.1f}..{(max(dropped)-1)*period:.1f} ms), "
              f"lowest n there = {min(min_n(n) for n in dropped)}")
    thin = sorted(keep_ns, key=min_n)[:2]
    for n in thin:
        counts = ", ".join(f"{lab} {len(by.get((k, n), []))}"
                           for k, lab, _, _ in SERIES)
        print(f"  thinnest kept window {(n-1)*period:7.1f} ms: {counts}")

    # ---- series -----------------------------------------------------------
    stats = {}
    for key, label, _, _ in SERIES:
        xs, med, q1, q3, ns = [], [], [], [], []
        for n in keep_ns:
            v = by.get((key, n), [])
            if not v:
                continue
            xs.append((n - 1) * period)
            med.append(C.percentile(v, 0.50))
            q1.append(C.percentile(v, 0.25))
            q3.append(C.percentile(v, 0.75))
            ns.append(len(v))
        stats[key] = dict(x=xs, med=med, q1=q1, q3=q3, n=ns)

    # ---- TERMINOLOGY GATE, before anything is written --------------------
    caption = [
        f"Pooled across all {len(flights)} flights. NO duration stratum and NO elevation class applied - every flight contributes to every",
        f"window it has data for. Bands are the interquartile range, lines the median. Log y: the three series span several orders of",
        f"magnitude at short windows, and a linear axis would render the two lower series flat against zero.",
        f"x is DERIVED, not a column: the file's sweep variable is the number of points in the fit window, converted here as",
        f"(points - 1) x {period:.2f} ms. That frame period is measured from the data - all {n_fl} flights share it with spread {spread:.4f} ms - so the",
        f"conversion is exact rather than approximate. It is not the same quantity as the file's own lead-time axis, which runs the other way.",
        f"Rows with a blank error were excluded: " + ", ".join(
            f"{lab} {excluded.get(k, 0)}" for k, lab, _, _ in SERIES)
        + f" ({sum(excluded.values())} of {len(rows)}).",
        f"x truncated at {cut_ms:.0f} ms, where the contributing count falls below {MIN_N} on all three series.",
        f"Contributing count is NOT constant across windows, so series are not always compared on the same subset of flights - at",
        f"{(thin[0]-1)*period:.0f} ms and {(thin[1]-1)*period:.0f} ms in particular. Per-window counts are in the companion CSV.",
        f"Error is measured against each flight's held-out final-point label.",
        f"Source: {SRC}",
    ]
    surfaced = ([lab for _, lab, _, _ in SERIES] + caption
                + ["observation window (ms)", "prediction error at target (mm)",
                   "Prediction error vs observation window, pooled across all flights"])
    hits = [s for s in surfaced if any(f in s.lower() for f in FORBIDDEN)]
    if hits:
        stop("a forbidden model-code string appears in "
             f"{len(hits)} user-facing string(s):\n"
             + "\n".join(f"  - {h[:90]}" for h in hits))
    print(f"\nGATE 3 PASS: none of {FORBIDDEN} appear in the "
          f"{len(surfaced)} user-facing strings")

    # ---- draw -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, DPI))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)
    ax.set_yscale("log")
    for key, label, colour, marker in SERIES:
        s = stats[key]
        ax.fill_between(s["x"], s["q1"], s["q3"], color=colour, alpha=0.16,
                        linewidth=0, zorder=2)
        ax.plot(s["x"], s["med"], color=colour, lw=1.6, zorder=4, label=label)
    ax.set_xlabel("observation window (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("prediction error at target (mm)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.set_xlim(min(stats["C"]["x"]) - 10, cut_ms + 10)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
              loc="upper right", title=None)
    ax.set_title("Prediction error vs observation window, pooled across all flights",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)

    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
    else:
        gap, floor_y = 0.0185, 0.008
        start_y = floor_y + (len(caption) - 1) * gap
        for i, line in enumerate(caption):
            fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
        fig.tight_layout(rect=[0, start_y + 0.020, 1, 1])
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=300, facecolor=C.SURF)
        print(f"\nwrote {OUT_PNG.relative_to(ROOT)}")
    plt.close(fig)

    # ---- companion CSV ----------------------------------------------------
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["series", "observation_window_ms", "n_contributing",
                    "median_error_mm", "q1_error_mm", "q3_error_mm", "iqr_error_mm"])
        for key, label, _, _ in SERIES:
            s = stats[key]
            for i, x in enumerate(s["x"]):
                w.writerow([label, f"{x:.1f}", s["n"][i], f"{s['med'][i]:.4f}",
                            f"{s['q1'][i]:.4f}", f"{s['q3'][i]:.4f}",
                            f"{s['q3'][i] - s['q1'][i]:.4f}"])
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")

    print("\nmedian error at a few windows:")
    for target in (100, 300, 500, 1000):
        i = min(range(len(stats["C"]["x"])),
                key=lambda j: abs(stats["C"]["x"][j] - target))
        w_ms = stats["C"]["x"][i]
        vals = "  ".join(f"{lab} {stats[k]['med'][i]:9.1f}"
                         for k, lab, _, _ in SERIES)
        print(f"  {w_ms:7.1f} ms   {vals}")
    print("\nsource CSV not modified")


if __name__ == "__main__":
    main()
