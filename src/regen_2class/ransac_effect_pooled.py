"""Pooled effect of the RANSAC robustifier on Model C prediction error.

Joins, both strictly read-only:
  results/regenerate_figures/plain_drag_sweep/plain_drag_sweep.csv   ("without RANSAC")
  results/trajectory_fit_comparison/all_flights/phase2/
      prediction_sweep_all_flights.csv, model == "C" rows            ("with RANSAC")

on (session, flight, N). The two runs are identical in population, window grid,
pooled K, held-out target and leakage exclusion, so a matched join is meaningful
and the ONLY thing that differs between the series is the robustifier.

X AXIS - the observation window in ms is not a column in either CSV. It is NOT
approximated from a nominal frame rate: it is recomputed exactly as
(t[N-1] - t[0]) * 1000 from each flight's own corrected track, by calling
plain_drag_sweep.prepare_flight (which does calibration + track building only, no
fitting - about a second for all 158 flights). Windows are then pooled into
BIN_MS-wide bins because each flight's own timing grid differs.

PAIRED CELLS - the RANSAC series has windows where the fit never converged and
no error was recorded. Those keys still exist, so the key-set gate passes, but
they cannot enter a paired comparison. They are excluded from the paired
statistics ONLY, and counted per bin in the companion CSV as n_ransac_missing.

STOP conditions:
  - the two series do not share an identical set of (session, flight, N) keys
  - any plotted window has fewer than 100 contributing cells in either series
  - the bins meeting that threshold are not contiguous (a gap would make a
    joined median line assert a continuity the data does not have)

Windows that fail the >=100 threshold at the ends of the range are reported
explicitly, in the summary and on stdout - never silently trimmed.

Outputs: results/regenerate_figures/ransac_effect_pooled/
"""

import csv
import pathlib
import sys

import numpy as np

_HERE = pathlib.Path(__file__).resolve().parent
ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import clean_figures as CF  # noqa: E402
import common as C  # noqa: E402
from src.regen_2class.plain_drag_sweep import prepare_flight  # noqa: E402
from src.stereo.all_flights_common import load_final_point_targets  # noqa: E402
from src.stereo.trajectory_fit import RANSAC_MIN_SAMPLES  # noqa: E402

PLAIN_CSV = ROOT / "results/regenerate_figures/plain_drag_sweep/plain_drag_sweep.csv"
RANSAC_CSV = ROOT / ("results/trajectory_fit_comparison/all_flights/phase2/"
                     "prediction_sweep_all_flights.csv")
OUT_DIR = ROOT / "results/regenerate_figures/ransac_effect_pooled"
OUT_PNG = OUT_DIR / "ransac_effect_pooled.png"
OUT_CSV = OUT_DIR / "ransac_effect_pooled.csv"
OUT_SUMMARY = OUT_DIR / "ransac_effect_pooled_summary.txt"

MODEL = "C"
BIN_MS = 100.0
# Below this window size the original never ran RANSAC at all - it falls back to
# the plain fit - so those cells are identical to the plain series BY
# CONSTRUCTION, not because RANSAC lost. Tracked so the win/loss fractions can
# separate real ties from that artefact.
MIN_SAMPLES_C = RANSAC_MIN_SAMPLES[MODEL]
TIE_TOL_MM = 1e-9
MIN_CELLS = 100

S_PLAIN, S_RANSAC = "without RANSAC", "with RANSAC"
# Categorical slots 1 and 8, as used by the other figures in this set; common.py
# records the pair as validating on all six checks.
COLOR = {S_PLAIN: "#2a78d6", S_RANSAC: "#e34948"}

PAGE_W_IN, DPI = 6.6, 4.6,
FS_TITLE, FS_AXIS, FS_TICK, FS_LEGEND, FS_CAP = 11, 9.5, 8, 8, 6.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_series():
    plain, ransac = {}, {}
    with open(PLAIN_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["session"], r["flight"], int(r["N"]))
            plain[key] = float(r["error_mm"]) if r["error_mm"].strip() else None
    with open(RANSAC_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["model"] != MODEL:
                continue
            key = (r["session"], r["flight"], int(r["N"]))
            ransac[key] = float(r["error_mm"]) if r["error_mm"].strip() else None
    return plain, ransac


def check_keys(plain, ransac):
    kp, kr = set(plain), set(ransac)
    if kp != kr:
        only_p, only_r = sorted(kp - kr), sorted(kr - kp)
        stop(f"the two series do not share an identical key set - refusing to plot "
             f"an unmatched comparison.\n"
             f"  without RANSAC: {len(kp)} keys\n"
             f"  with RANSAC   : {len(kr)} keys\n"
             f"  only without ({len(only_p)}): {only_p[:10]}\n"
             f"  only with    ({len(only_r)}): {only_r[:10]}")
    print(f"KEY GATE PASS: both series carry the identical {len(kp)} "
          f"(session, flight, N) keys")


def window_ms_lookup(keys):
    """Exact observation-window duration per key, from each flight's own track."""
    targets = load_final_point_targets()
    flights = sorted({(s, f) for s, f, _ in keys})
    out, missing = {}, []
    for s, f in flights:
        prep = prepare_flight(s, f, targets)
        if prep["status"] != "ok":
            missing.append((s, f, prep.get("reason", "?")))
            continue
        t = prep["t"]
        for N in {n for ss, ff, n in keys if (ss, ff) == (s, f)}:
            out[(s, f, N)] = float((t[N - 1] - t[0]) * 1000.0)
    if missing:
        stop(f"could not rebuild the track for {len(missing)} flight(s) that the "
             f"joined CSVs contain, so their observation windows are unknown:\n"
             + "\n".join(f"    {s}/{f}: {why}" for s, f, why in missing[:10]))
    absent = [k for k in keys if k not in out]
    if absent:
        stop(f"{len(absent)} key(s) have no observation window - N exceeds the "
             f"rebuilt track length. First: {absent[:5]}")
    print(f"window durations recomputed for {len(out)} keys across {len(flights)} flights")
    return out


def main():
    for p in (PLAIN_CSV, RANSAC_CSV):
        if not p.is_file():
            stop(f"missing input: {p.relative_to(ROOT).as_posix()}")

    plain, ransac = read_series()
    check_keys(plain, ransac)
    keys = sorted(plain)
    wms = window_ms_lookup(keys)

    # ---- bin ---------------------------------------------------------------
    bins = {}
    for k in keys:
        b = int(wms[k] // BIN_MS)
        bins.setdefault(b, []).append(k)

    rows = []
    for b in sorted(bins):
        ks = bins[b]
        pv = [plain[k] for k in ks if plain[k] is not None]
        rv = [ransac[k] for k in ks if ransac[k] is not None]
        paired = [(plain[k], ransac[k]) for k in ks
                  if plain[k] is not None and ransac[k] is not None]
        rows.append(dict(
            bin=b, lo=b * BIN_MS, hi=(b + 1) * BIN_MS, centre=(b + 0.5) * BIN_MS,
            n_cells=len(ks), n_plain=len(pv), n_ransac=len(rv),
            n_ransac_missing=len(ks) - len(rv), n_paired=len(paired),
            p_med=float(np.median(pv)) if pv else None,
            p_q1=float(np.percentile(pv, 25)) if pv else None,
            p_q3=float(np.percentile(pv, 75)) if pv else None,
            r_med=float(np.median(rv)) if rv else None,
            r_q1=float(np.percentile(rv, 25)) if rv else None,
            r_q3=float(np.percentile(rv, 75)) if rv else None,
            # Two different "median difference" statistics, both reported: the
            # difference of the two pooled medians, and the median of the
            # per-cell paired differences. They are not the same number and the
            # paired one is the one that answers "does RANSAC help on a given
            # window", so both are emitted rather than picking one silently.
            med_diff_of_medians=(float(np.median(pv) - np.median(rv))
                                 if pv and rv else None),
            med_paired_diff=(float(np.median([p - r for p, r in paired]))
                             if paired else None),
            frac_ransac_better=(sum(1 for p, r in paired if r < p - TIE_TOL_MM) / len(paired)
                                if paired else None),
            frac_ransac_worse=(sum(1 for p, r in paired if r > p + TIE_TOL_MM) / len(paired)
                               if paired else None),
            frac_identical=(sum(1 for p, r in paired if abs(p - r) <= TIE_TOL_MM) / len(paired)
                            if paired else None),
            n_identical=sum(1 for p, r in paired if abs(p - r) <= TIE_TOL_MM),
            n_below_min_samples=sum(1 for k in ks if k[2] < MIN_SAMPLES_C),
        ))

    # ---- plotted range: contiguous bins meeting MIN_CELLS in BOTH series ----
    ok_bins = [r["bin"] for r in rows
               if r["n_plain"] >= MIN_CELLS and r["n_ransac"] >= MIN_CELLS]
    if not ok_bins:
        stop(f"no {BIN_MS:.0f} ms window has >= {MIN_CELLS} contributing cells in "
             f"both series; nothing can be plotted at this threshold.")
    lo_b, hi_b = min(ok_bins), max(ok_bins)
    if ok_bins != list(range(lo_b, hi_b + 1)):
        gaps = [b for b in range(lo_b, hi_b + 1) if b not in ok_bins]
        stop(f"the windows meeting the >= {MIN_CELLS}-cell threshold are NOT "
             f"contiguous - bins {gaps} fall below it while bins on both sides "
             f"pass. A joined median line across that gap would assert a "
             f"continuity the data does not have.")

    plotted = [r for r in rows if lo_b <= r["bin"] <= hi_b]
    below = [r for r in rows if r["bin"] < lo_b or r["bin"] > hi_b]
    for r in plotted:  # interior violation is a STOP, not a trim
        if r["n_plain"] < MIN_CELLS or r["n_ransac"] < MIN_CELLS:
            stop(f"window {r['lo']:.0f}-{r['hi']:.0f} ms is inside the plotted range "
                 f"but has n_plain={r['n_plain']}, n_ransac={r['n_ransac']}, "
                 f"below the {MIN_CELLS} minimum.")

    print(f"PLOTTED RANGE: {plotted[0]['lo']:.0f}-{plotted[-1]['hi']:.0f} ms "
          f"({len(plotted)} bins), all >= {MIN_CELLS} cells in both series")
    if below:
        print(f"EXCLUDED (below the {MIN_CELLS}-cell threshold, reported not hidden):")
        for r in below:
            print(f"    {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  n_cells={r['n_cells']:>4}  "
                  f"n_plain={r['n_plain']:>4}  n_ransac={r['n_ransac']:>4}")

    # ---- the finding the brief asks to be flagged --------------------------
    worse = [r for r in plotted if r["r_med"] > r["p_med"]]
    # Compare wins against LOSSES, not against "not-wins": a bin can have a low
    # win fraction purely because most cells are exact ties, which is the case at
    # short windows where RANSAC never ran. Both framings are reported.
    worse_paired = [r for r in plotted
                    if r["frac_ransac_worse"] > r["frac_ransac_better"]]
    tie_heavy = [r for r in plotted if r["frac_identical"] >= 0.5]

    # ---- figure ------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, DPI))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax, grid_axis="y")
    x = [r["centre"] for r in plotted]
    for name, med_k, q1_k, q3_k in ((S_PLAIN, "p_med", "p_q1", "p_q3"),
                                    (S_RANSAC, "r_med", "r_q1", "r_q3")):
        med = [r[med_k] for r in plotted]
        ax.fill_between(x, [r[q1_k] for r in plotted], [r[q3_k] for r in plotted],
                        color=COLOR[name], alpha=0.16, linewidth=0, zorder=2)
        ax.plot(x, med, color=COLOR[name], linewidth=1.9, label=name, zorder=4)

    ax.set_yscale("log")
    ax.set_xlabel("observation window (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("prediction error at target (mm)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2, loc="upper right")
    ax.set_title("Effect of the RANSAC robustifier on drag-model prediction error",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)

    caption = [
        f"Model C (fixed gravity + quadratic drag), {len({(s, f) for s, f, _ in keys})} flights, "
        f"{len(keys)} matched (flight, window) cells. Median line, shaded IQR, {BIN_MS:.0f} ms bins.",
        f"Both series share an identical key set; the only difference is the robustifier. "
        f"Bins outside {plotted[0]['lo']:.0f}-{plotted[-1]['hi']:.0f} ms fall below "
        f"{MIN_CELLS} cells and are not plotted.",
    ]
    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
    else:
        gap, floor_y = 0.0235, 0.010
        start_y = floor_y + (len(caption) - 1) * gap
        for i, line in enumerate(caption):
            fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
        fig.tight_layout(rect=[0, start_y + 0.026, 1, 1])
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=300, facecolor=C.SURF)
    plt.close(fig)

    # ---- companion CSV -----------------------------------------------------
    def fmt(v, nd=4):
        return "" if v is None else f"{v:.{nd}f}"

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["window_lo_ms", "window_hi_ms", "window_centre_ms", "plotted",
                    "n_cells", "n_paired", "n_ransac_missing",
                    "n_without_ransac", "median_without_ransac_mm",
                    "q1_without_ransac_mm", "q3_without_ransac_mm",
                    "n_with_ransac", "median_with_ransac_mm",
                    "q1_with_ransac_mm", "q3_with_ransac_mm",
                    "median_difference_of_medians_mm", "median_paired_difference_mm",
                    "frac_cells_ransac_better", "frac_cells_ransac_worse",
                    "frac_cells_identical", "n_cells_identical",
                    "n_cells_below_min_samples"])
        for r in rows:
            w.writerow([f"{r['lo']:.0f}", f"{r['hi']:.0f}", f"{r['centre']:.0f}",
                        "yes" if lo_b <= r["bin"] <= hi_b else "no",
                        r["n_cells"], r["n_paired"], r["n_ransac_missing"],
                        r["n_plain"], fmt(r["p_med"]), fmt(r["p_q1"]), fmt(r["p_q3"]),
                        r["n_ransac"], fmt(r["r_med"]), fmt(r["r_q1"]), fmt(r["r_q3"]),
                        fmt(r["med_diff_of_medians"]), fmt(r["med_paired_diff"]),
                        fmt(r["frac_ransac_better"], 4), fmt(r["frac_ransac_worse"], 4),
                        fmt(r["frac_identical"], 4), r["n_identical"],
                        r["n_below_min_samples"]])

    # ---- summary -----------------------------------------------------------
    total_missing = sum(r["n_ransac_missing"] for r in rows)
    lines = [
        "RANSAC EFFECT, POOLED - MODEL C",
        "=" * 74, "",
        f"Matched cells: {len(keys)} over {len({(s, f) for s, f, _ in keys})} flights.",
        "Key-set gate: PASS (identical (session, flight, N) sets).",
        f"RANSAC windows with no recorded error: {total_missing} "
        f"(excluded from paired stats only; the plain series has 0).",
        f"Plotted range: {plotted[0]['lo']:.0f}-{plotted[-1]['hi']:.0f} ms, "
        f"{len(plotted)} bins of {BIN_MS:.0f} ms, all >= {MIN_CELLS} cells per series.",
        "",
    ]
    if below:
        lines.append(f"Bins excluded for falling below {MIN_CELLS} cells "
                     f"(reported, not silently trimmed):")
        for r in below:
            lines.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  n_cells={r['n_cells']:>4}  "
                         f"n_without={r['n_plain']:>4}  n_with={r['n_ransac']:>4}")
        lines.append("")

    lines.append("WHERE RANSAC IS WORSE")
    if worse:
        lines.append(f"  On the pooled median, RANSAC is WORSE at {len(worse)} of "
                     f"{len(plotted)} plotted windows:")
        for r in worse:
            lines.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  "
                         f"without={r['p_med']:>9.1f} mm  with={r['r_med']:>9.1f} mm  "
                         f"(with is {r['r_med'] - r['p_med']:+.1f} mm)")
        lines.append("  Not smoothed and not dropped.")
    else:
        lines.append(f"  None: the RANSAC median is at or below the plain median at "
                     f"all {len(plotted)} plotted windows.")
    lines.append("")
    if worse_paired:
        lines.append(f"  By paired cell count, RANSAC LOSES more cells than it wins at "
                     f"{len(worse_paired)} plotted window(s):")
        for r in worse_paired:
            lines.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  "
                         f"better={r['frac_ransac_better']:.3f}  "
                         f"worse={r['frac_ransac_worse']:.3f}  "
                         f"tied={r['frac_identical']:.3f}  (n_paired={r['n_paired']})")
    else:
        lines.append("  RANSAC wins at least as many paired cells as it loses at "
                     "every plotted window.")
    lines.append("")
    lines.append("TIES - cells where the two series are numerically identical")
    lines.append("  Two causes, both real 'no difference', neither a RANSAC loss:")
    lines.append(f"    (1) N < {MIN_SAMPLES_C}: the original never runs RANSAC, it falls "
                 f"back to the plain fit, so the cells are identical by construction.")
    lines.append("    (2) N large enough, but RANSAC rejected nothing, so its refit on "
                 "the full set IS the plain fit.")
    for r in plotted:
        if r["n_identical"]:
            lines.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  identical={r['n_identical']:>4}"
                         f"/{r['n_paired']:<4} ({r['frac_identical']:.3f})  "
                         f"of which N<{MIN_SAMPLES_C}: {r['n_below_min_samples']}")
    lines += ["", f"Figure : {OUT_PNG.relative_to(ROOT).as_posix()}",
              f"Table  : {OUT_CSV.relative_to(ROOT).as_posix()}",
              "Both source CSVs read-only; neither modified."]
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nwrote {OUT_PNG.relative_to(ROOT).as_posix()}")
    print(f"wrote {OUT_CSV.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
