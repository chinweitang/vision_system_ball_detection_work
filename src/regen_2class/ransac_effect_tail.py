"""Tail behaviour of Model C prediction error, with and without the RANSAC robustifier.

The pooled median/IQR figure (`ransac_effect_pooled.py`) shows the two series are
close in the middle of the distribution. A robustifier's job is not the middle -
it is the tail. This re-cuts the SAME matched cells on tail statistics: the
fraction of cells whose prediction error exceeds 500 mm (plotted), plus p90, p95,
max and a 200 mm fraction (tabulated).

Inputs, all read-only:
  results/regenerate_figures/plain_drag_sweep/plain_drag_sweep.csv       ("without RANSAC")
  results/trajectory_fit_comparison/.../prediction_sweep_all_flights.csv ("with RANSAC", model C)
  results/regenerate_figures/ransac_effect_pooled/ransac_effect_pooled.csv (cross-check only)

EXACT PAIRING - the RANSAC series has 331 windows with no recorded value. Those
cells are dropped from BOTH series, not just from the one missing them, so every
statistic on both sides is computed over the identical cell set and the two
series remain comparable cell for cell. Per-bin surviving counts are reported.

The binning, cell reading, window-duration recomputation, minimum-cell threshold
and series colours are all IMPORTED from ransac_effect_pooled rather than
restated, so the two figures cannot drift onto different grids.

STOP conditions:
  - the two series do not share an identical key set after the exclusion
  - any plotted bin has fewer than 100 cells
  - the bins meeting that threshold are not contiguous
  - the surviving cell count disagrees with the pooled run's own n_paired totals

Nothing is smoothed. Where a tail statistic favours the plain fit, it is plotted
as measured and named in the summary.

Outputs: results/regenerate_figures/ransac_effect_tail/
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

import common as C  # noqa: E402
import clean_figures as CF  # noqa: E402
from src.regen_2class.ransac_effect_pooled import (  # noqa: E402
    read_series, window_ms_lookup, BIN_MS, MIN_CELLS, MIN_SAMPLES_C,
    S_PLAIN, S_RANSAC, COLOR, TIE_TOL_MM,
)

POOLED_CSV = ROOT / "results/regenerate_figures/ransac_effect_pooled/ransac_effect_pooled.csv"
OUT_DIR = ROOT / "results/regenerate_figures/ransac_effect_tail"
OUT_PNG = OUT_DIR / "ransac_effect_tail.png"
OUT_PNG_P95 = OUT_DIR / "ransac_effect_p95.png"
OUT_CSV = OUT_DIR / "ransac_effect_tail.csv"
OUT_SUMMARY = OUT_DIR / "ransac_effect_tail_summary.txt"

TAIL_MM = 500.0        # the plotted statistic
SECOND_MM = 200.0      # tabulated alongside it

PAGE_W_IN, PAGE_H_IN, DPI = 6.6, 4.4, 300
FS_TITLE, FS_AXIS, FS_TICK, FS_LEGEND, FS_CAP = 11, 9.5, 8, 8, 6.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def pooled_paired_totals():
    """The pooled run's own per-bin n_paired, used purely as a cross-check that
    this script's exclusion reproduces the same surviving cell set."""
    out = {}
    with open(POOLED_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[int(float(r["window_lo_ms"]) // BIN_MS)] = int(r["n_paired"])
    return out


def stats(values):
    """Every per-series statistic the companion CSV carries."""
    a = np.asarray(values, dtype=float)
    return dict(
        n=int(a.size),
        median=float(np.median(a)),
        p90=float(np.percentile(a, 90)),
        p95=float(np.percentile(a, 95)),
        max=float(a.max()),
        frac_over_tail=float((a > TAIL_MM).mean()),
        frac_over_second=float((a > SECOND_MM).mean()),
    )


def main():
    plain, ransac = read_series()

    # ---- the exclusion, applied to BOTH series -----------------------------
    kp_all, kr_all = set(plain), set(ransac)
    if kp_all != kr_all:
        stop(f"the two series do not share an identical key set even BEFORE the "
             f"exclusion: {len(kp_all)} vs {len(kr_all)}.")
    dropped = sorted(k for k in kp_all
                     if plain[k] is None or ransac[k] is None)
    keys = sorted(kp_all - set(dropped))
    dropped_for_ransac = [k for k in dropped if ransac[k] is None]
    dropped_for_plain = [k for k in dropped if plain[k] is None]
    print(f"matched keys before exclusion: {len(kp_all)}")
    print(f"excluded {len(dropped)} cell(s) from BOTH series "
          f"({len(dropped_for_ransac)} missing in the RANSAC series, "
          f"{len(dropped_for_plain)} in the plain series)")
    print(f"surviving paired cells: {len(keys)}")

    # ---- STOP: identical key set AFTER the exclusion ------------------------
    # Built independently per series rather than asserting the obvious, so the
    # gate can actually fail if the exclusion is ever applied one-sidedly.
    kp = {k for k in keys if plain.get(k) is not None}
    kr = {k for k in keys if ransac.get(k) is not None}
    if kp != kr:
        only_p, only_r = sorted(kp - kr), sorted(kr - kp)
        stop(f"after the exclusion the two series still do not share an identical "
             f"key set - the pairing is not exact.\n"
             f"  without RANSAC: {len(kp)}\n  with RANSAC   : {len(kr)}\n"
             f"  only without ({len(only_p)}): {only_p[:10]}\n"
             f"  only with    ({len(only_r)}): {only_r[:10]}")
    print(f"KEY GATE PASS: both series carry the identical {len(kp)} keys after exclusion")

    wms = window_ms_lookup(keys)

    # ---- bin ---------------------------------------------------------------
    bins = {}
    for k in keys:
        bins.setdefault(int(wms[k] // BIN_MS), []).append(k)

    pooled_n = pooled_paired_totals()
    mismatch = [(b, len(ks), pooled_n.get(b)) for b, ks in sorted(bins.items())
                if pooled_n.get(b) != len(ks)]
    if mismatch:
        stop("this script's surviving cell counts disagree with the pooled run's "
             "own n_paired, so the two figures would not be over the same cells:\n"
             + "\n".join(f"    bin {b * BIN_MS:.0f} ms: here {here}, pooled {there}"
                         for b, here, there in mismatch))
    print(f"CROSS-CHECK PASS: per-bin surviving counts match the pooled run's n_paired")

    rows = []
    for b in sorted(bins):
        ks = bins[b]
        sp = stats([plain[k] for k in ks])
        sr = stats([ransac[k] for k in ks])
        rows.append(dict(
            bin=b, lo=b * BIN_MS, hi=(b + 1) * BIN_MS, centre=(b + 0.5) * BIN_MS,
            n=len(ks), plain=sp, ransac=sr,
            n_identical=sum(1 for k in ks
                            if abs(plain[k] - ransac[k]) <= TIE_TOL_MM),
            n_below_min_samples=sum(1 for k in ks if k[2] < MIN_SAMPLES_C),
        ))

    # ---- plotted range ------------------------------------------------------
    ok = [r["bin"] for r in rows if r["n"] >= MIN_CELLS]
    if not ok:
        stop(f"no {BIN_MS:.0f} ms bin reaches {MIN_CELLS} surviving cells.")
    lo_b, hi_b = min(ok), max(ok)
    if ok != list(range(lo_b, hi_b + 1)):
        gaps = [b for b in range(lo_b, hi_b + 1) if b not in ok]
        stop(f"the bins meeting the >= {MIN_CELLS}-cell threshold are not "
             f"contiguous - bins {gaps} fall below it with passing bins either "
             f"side. A joined line across that gap would assert continuity the "
             f"data does not have.")
    plotted = [r for r in rows if lo_b <= r["bin"] <= hi_b]
    excluded = [r for r in rows if not (lo_b <= r["bin"] <= hi_b)]
    for r in plotted:
        if r["n"] < MIN_CELLS:
            stop(f"plotted bin {r['lo']:.0f}-{r['hi']:.0f} ms has {r['n']} cells, "
                 f"below the {MIN_CELLS} minimum.")
    print(f"PLOTTED RANGE: {plotted[0]['lo']:.0f}-{plotted[-1]['hi']:.0f} ms "
          f"({len(plotted)} bins), all >= {MIN_CELLS} cells")
    for r in excluded:
        print(f"  EXCLUDED {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  n={r['n']} "
              f"(below {MIN_CELLS}; reported, not hidden)")

    # ---- where the plain fit is at least as good ---------------------------
    tail_favours_plain = [r for r in plotted
                          if r["plain"]["frac_over_tail"] < r["ransac"]["frac_over_tail"]]
    tail_equal = [r for r in plotted
                  if r["plain"]["frac_over_tail"] == r["ransac"]["frac_over_tail"]]
    p95_favours_plain = [r for r in plotted
                         if r["plain"]["p95"] < r["ransac"]["p95"]]

    # ---- figure: the plotted tail statistic --------------------------------
    def draw(key, ylabel, title, path, as_pct):
        fig, ax = plt.subplots(figsize=(PAGE_W_IN, PAGE_H_IN))
        fig.patch.set_facecolor(C.SURF)
        C.style_axes(ax, grid_axis="y")
        x = [r["centre"] for r in plotted]
        for name, side in ((S_PLAIN, "plain"), (S_RANSAC, "ransac")):
            y = [r[side][key] * (100.0 if as_pct else 1.0) for r in plotted]
            ax.plot(x, y, color=COLOR[name], linewidth=1.9, marker="o", ms=3.4,
                    label=name, zorder=4)
        ax.set_xlabel("observation window (ms)", color=C.INK, fontsize=FS_AXIS)
        ax.set_ylabel(ylabel, color=C.INK, fontsize=FS_AXIS)
        ax.tick_params(labelsize=FS_TICK)
        ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2, loc="upper right")
        ax.set_title(title, color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)
        cap = [
            f"Model C, {len({(s, f) for s, f, _ in keys})} flights, {len(keys)} exactly paired "
            f"(flight, window) cells in {BIN_MS:.0f} ms bins. Not smoothed.",
            f"{len(dropped)} cells where the RANSAC fit recorded no value are dropped from BOTH "
            f"series so the pairing stays exact. Bins under {MIN_CELLS} cells are not plotted.",
        ]
        if CF.clean():
            CF.write_clean(fig, cap, path)
        else:
            gap, floor_y = 0.0235, 0.010
            start_y = floor_y + (len(cap) - 1) * gap
            for i, line in enumerate(cap):
                fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
            fig.tight_layout(rect=[0, start_y + 0.026, 1, 1])
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=DPI, facecolor=C.SURF)
        plt.close(fig)

    draw("frac_over_tail", f"fraction of cells with error > {TAIL_MM:.0f} mm",
         f"Tail rate: share of predictions worse than {TAIL_MM:.0f} mm",
         OUT_PNG, as_pct=False)
    # Second statistic, on its own axes: the brief asks to SEE p95 alongside the
    # tail rate before choosing between them, and they do not share a y unit.
    draw("p95", "95th percentile of prediction error (mm)",
         "95th-percentile prediction error", OUT_PNG_P95, as_pct=False)

    # ---- companion CSV ------------------------------------------------------
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["window_lo_ms", "window_hi_ms", "window_centre_ms", "plotted",
                    "series", "n_cells", "median_mm", "p90_mm", "p95_mm", "max_mm",
                    f"frac_over_{TAIL_MM:.0f}mm", f"frac_over_{SECOND_MM:.0f}mm",
                    "n_cells_identical_to_other_series", "n_cells_below_min_samples"])
        for r in rows:
            for name, side in ((S_PLAIN, "plain"), (S_RANSAC, "ransac")):
                s = r[side]
                w.writerow([f"{r['lo']:.0f}", f"{r['hi']:.0f}", f"{r['centre']:.0f}",
                            "yes" if lo_b <= r["bin"] <= hi_b else "no", name,
                            s["n"], f"{s['median']:.4f}", f"{s['p90']:.4f}",
                            f"{s['p95']:.4f}", f"{s['max']:.4f}",
                            f"{s['frac_over_tail']:.4f}", f"{s['frac_over_second']:.4f}",
                            r["n_identical"], r["n_below_min_samples"]])

    # ---- summary ------------------------------------------------------------
    L = []
    L += ["RANSAC EFFECT - TAIL STATISTICS, MODEL C", "=" * 78, "",
          f"Matched keys before exclusion : {len(kp_all)}",
          f"Excluded from BOTH series     : {len(dropped)} "
          f"({len(dropped_for_ransac)} missing in the RANSAC series, "
          f"{len(dropped_for_plain)} in the plain series)",
          f"Exactly paired cells          : {len(keys)} over "
          f"{len({(s, f) for s, f, _ in keys})} flights",
          "Key gate after exclusion      : PASS (identical key sets)",
          "Cross-check vs pooled n_paired: PASS (same cells per bin)",
          f"Plotted range                 : {plotted[0]['lo']:.0f}-{plotted[-1]['hi']:.0f} ms, "
          f"{len(plotted)} bins of {BIN_MS:.0f} ms, all >= {MIN_CELLS} cells", ""]
    if excluded:
        L.append(f"Bins excluded for falling below {MIN_CELLS} cells (reported, not trimmed silently):")
        for r in excluded:
            L.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  n={r['n']}")
        L.append("")

    # Per-bin dropped counts, computed over the SAME binning as the survivors so
    # the two columns add up to the pooled run's n_cells.
    wms_dropped = window_ms_lookup(dropped) if dropped else {}
    drop_count = {}
    for k in dropped:
        b = int(wms_dropped[k] // BIN_MS)
        drop_count[b] = drop_count.get(b, 0) + 1

    L += [f"SURVIVING CELLS PER BIN (after dropping the {len(dropped)} unpaired)", "",
          f"  {'window (ms)':<14}{'n paired':>9}{'dropped':>9}{'n total':>9}"]
    for r in rows:
        label = "{:.0f}-{:.0f}".format(r["lo"], r["hi"])
        d = drop_count.get(r["bin"], 0)
        L.append(f"  {label:<14}{r['n']:>9}{d:>9}{r['n'] + d:>9}")
    L.append("")

    L += [f"PLOTTED STATISTIC - fraction of cells with error > {TAIL_MM:.0f} mm", "",
          f"  {'window (ms)':<14}{'without':>10}{'with':>10}{'diff':>10}{'n':>7}"]
    for r in plotted:
        label = "{:.0f}-{:.0f}".format(r["lo"], r["hi"])
        a, b = r["plain"]["frac_over_tail"], r["ransac"]["frac_over_tail"]
        L.append(f"  {label:<14}{a:>10.4f}{b:>10.4f}{b - a:>+10.4f}{r['n']:>7}")
    L.append("")

    L += ["SECOND STATISTIC - 95th percentile of prediction error (mm)", "",
          f"  {'window (ms)':<14}{'without':>10}{'with':>10}{'diff':>10}{'n':>7}"]
    for r in plotted:
        label = "{:.0f}-{:.0f}".format(r["lo"], r["hi"])
        a, b = r["plain"]["p95"], r["ransac"]["p95"]
        L.append(f"  {label:<14}{a:>10.1f}{b:>10.1f}{b - a:>+10.1f}{r['n']:>7}")
    L.append("")

    L.append(f"WHERE THE PLAIN FIT WINS ON THE TAIL STATISTIC (> {TAIL_MM:.0f} mm)")
    if tail_favours_plain:
        L.append(f"  The plain fit has a SMALLER tail fraction at {len(tail_favours_plain)} "
                 f"of {len(plotted)} plotted windows. Plotted as measured:")
        for r in tail_favours_plain:
            L.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  without={r['plain']['frac_over_tail']:.4f}"
                     f"  with={r['ransac']['frac_over_tail']:.4f}"
                     f"  (with is {r['ransac']['frac_over_tail'] - r['plain']['frac_over_tail']:+.4f})")
    else:
        L.append(f"  None: the RANSAC tail fraction is at or below the plain fit's at "
                 f"all {len(plotted)} plotted windows.")
    if tail_equal:
        L.append(f"  Exactly equal at {len(tail_equal)} window(s): "
                 + ", ".join(f"{r['lo']:.0f}-{r['hi']:.0f} ms" for r in tail_equal))
    L.append("")
    L.append("WHERE THE PLAIN FIT WINS ON p95")
    if p95_favours_plain:
        L.append(f"  The plain fit has a LOWER p95 at {len(p95_favours_plain)} of "
                 f"{len(plotted)} plotted windows:")
        for r in p95_favours_plain:
            L.append(f"  {r['lo']:>6.0f}-{r['hi']:<6.0f} ms  without={r['plain']['p95']:>9.1f} mm"
                     f"  with={r['ransac']['p95']:>9.1f} mm")
    else:
        L.append(f"  None: the RANSAC p95 is at or below the plain fit's at all "
                 f"{len(plotted)} plotted windows.")
    L += ["", f"Figure (tail rate): {OUT_PNG.relative_to(ROOT).as_posix()}",
          f"Figure (p95)      : {OUT_PNG_P95.relative_to(ROOT).as_posix()}",
          f"Table             : {OUT_CSV.relative_to(ROOT).as_posix()}",
          "All inputs read-only; none modified."]

    OUT_SUMMARY.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n" + "\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
