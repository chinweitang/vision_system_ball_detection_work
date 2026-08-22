"""Step 11 - R4 pass rate versus panel size.

The R4 position threshold scales with panel width. A delta-wide dead band around the
perimeter retains 81 per cent of usable area, which fixes

    R4 threshold = aperture / 20

    2000 -> 100    2250 -> 112.5    2500 -> 125    2750 -> 137.5    3000 -> 150 mm

Two things are reported at each aperture, both at the class operating windows
(SHORT 300 ms, LONG 700 ms) with A = 72 ms:

  1. R4 alone: the fraction of flights whose position_error_mm is below that
     aperture's threshold.
  2. The full six-band verdict from the existing chaos sweep, re-run with only the
     position threshold changed, so the movement in OVERALL success rate is visible
     rather than just the movement in R4.

DELIBERATELY NOT DONE: the hit/miss classification is NOT recomputed at other
apertures. `wrong_class` keeps the frozen 2000 mm classification carried in
`hit_miss_match`. Where a ball happened to cross in this dataset is a property of
these throws, not of a venue, so re-thresholding it would produce a number that does
not generalise. APERTURE_SIZE_MM is not touched anywhere.

Verdict machinery is imported from step10 rather than re-implemented, so the bands
are identical by construction. Reads existing outputs only; nothing is re-run.

Output: data/regenerate_figures/panel_size_sensitivity.csv. No figure.
"""
import csv

import common as C
from step10_chaos_outcome_sweep import (
    A_VALUES, BAND_ORDER, evaluate, load_per_axis,
)

OUT_CSV = C.OUT_DIR + "panel_size_sensitivity.csv"

APERTURES_MM = [2000.0, 2250.0, 2500.0, 2750.0, 3000.0]
DEAD_BAND_DIVISOR = 20.0          # threshold = aperture / 20, from the 81% area rule
OPERATING_WINDOW = {"SHORT": 300, "LONG": 700}
A_MS = 72.0


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()
    assert A_MS in A_VALUES, "A_MS must be one of the swept A values"

    n_class = {c: len(v) for c, v in C.class_durations(rows).items()}
    print(f"classes: SHORT={n_class['SHORT']}, LONG={n_class['LONG']}, "
          f"pooled={sum(n_class.values())}")
    print(f"operating windows: {OPERATING_WINDOW}, A = {A_MS:.0f} ms")
    print("hit/miss classification NOT recomputed - wrong_class keeps the frozen "
          "2000 mm result")
    print()

    # position errors at each class's operating window, ok rows only
    pos_at_window, n_ok = {}, {}
    for cls, w in OPERATING_WINDOW.items():
        sub = [r for r in rows if r["cls2"] == cls and int(r["T_ms"]) == w]
        pos_at_window[cls] = [float(r["position_error_mm"]) for r in sub
                              if r["status"] == "ok"]
        n_ok[cls] = len(pos_at_window[cls])
        print(f"  {cls} at {w} ms: {n_ok[cls]} fitted of {n_class[cls]} "
              f"({n_class[cls] - n_ok[cls]} fit_failed)")
    print()

    out_rows = []
    for aperture in APERTURES_MM:
        thresh = aperture / DEAD_BAND_DIVISOR
        # six-band verdict with ONLY the position threshold changed
        _, _, counts, rate, _ = evaluate(rows, per_axis, windows, A_MS, thresh)

        pooled_pass = pooled_total = 0
        pooled_bands = {b: 0 for b in BAND_ORDER}
        for cls in ("SHORT", "LONG"):
            w = OPERATING_WINDOW[cls]
            i = windows.index(w)
            npass = sum(1 for p in pos_at_window[cls] if p < thresh)
            band = {b: counts[cls][b][i] for b in BAND_ORDER}
            out_rows.append(dict(
                aperture_mm=aperture, r4_threshold_mm=thresh, scope=cls, window_ms=w,
                n_total=n_class[cls], n_ok=n_ok[cls], r4_pass=npass,
                r4_pass_rate=100.0 * npass / n_class[cls],
                success_rate=rate[cls][i], **band))
            pooled_pass += npass
            pooled_total += n_class[cls]
            for b in BAND_ORDER:
                pooled_bands[b] += band[b]
        out_rows.append(dict(
            aperture_mm=aperture, r4_threshold_mm=thresh, scope="POOLED",
            window_ms="300/700", n_total=pooled_total,
            n_ok=n_ok["SHORT"] + n_ok["LONG"], r4_pass=pooled_pass,
            r4_pass_rate=100.0 * pooled_pass / pooled_total,
            success_rate=100.0 * pooled_bands["success"] / pooled_total,
            **pooled_bands))

    cols = (["aperture_mm", "r4_threshold_mm", "scope", "window_ms", "n_total",
             "n_ok", "r4_pass", "r4_pass_rate", "success_rate"] + BAND_ORDER)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in out_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in r.items()})
    print(f"wrote {OUT_CSV}")
    print()

    print("=== R4 ALONE: fraction below aperture/20, at the class operating windows ===")
    hdr = (f"{'aperture':>9} {'R4 thr':>8} | " +
           " | ".join(f"{s:>16}" for s in ("SHORT (300ms)", "LONG (700ms)", "POOLED")))
    print(hdr)
    print("-" * len(hdr))
    for aperture in APERTURES_MM:
        cells = []
        for scope in ("SHORT", "LONG", "POOLED"):
            r = next(x for x in out_rows
                     if x["aperture_mm"] == aperture and x["scope"] == scope)
            cells.append(f"{r['r4_pass']:>3d}/{r['n_total']:<3d} {r['r4_pass_rate']:>5.1f}%")
        print(f"{aperture:>8.0f}m {aperture/DEAD_BAND_DIVISOR:>7.1f} | " +
              " | ".join(f"{c:>16}" for c in cells))

    print()
    print("=== FULL SIX-BAND VERDICT at each aperture (A = 72 ms, only the position "
          "threshold changes) ===")
    hdr2 = (f"{'aperture':>9} {'R4 thr':>8} {'scope':>7} {'n':>4} | "
            f"{'success':>8} {'w_vel':>6} {'w_pos':>6} {'w_cls':>6} {'late':>6} "
            f"{'no_resp':>8} | {'success rate':>13}")
    print(hdr2)
    print("-" * len(hdr2))
    for aperture in APERTURES_MM:
        for scope in ("SHORT", "LONG", "POOLED"):
            r = next(x for x in out_rows
                     if x["aperture_mm"] == aperture and x["scope"] == scope)
            print(f"{aperture:>8.0f}m {r['r4_threshold_mm']:>7.1f} {scope:>7} "
                  f"{r['n_total']:>4d} | {r['success']:>8d} {r['wrong_velocity']:>6d} "
                  f"{r['wrong_position']:>6d} {r['wrong_class']:>6d} {r['late']:>6d} "
                  f"{r['no_response']:>8d} | {r['success_rate']:>12.1f}%")
        print()

    base = next(x for x in out_rows
                if x["aperture_mm"] == APERTURES_MM[0] and x["scope"] == "POOLED")
    top = next(x for x in out_rows
               if x["aperture_mm"] == APERTURES_MM[-1] and x["scope"] == "POOLED")
    print(f"POOLED movement {APERTURES_MM[0]:.0f} -> {APERTURES_MM[-1]:.0f} mm: "
          f"R4 {base['r4_pass_rate']:.1f}% -> {top['r4_pass_rate']:.1f}% "
          f"({top['r4_pass_rate'] - base['r4_pass_rate']:+.1f} pp), "
          f"overall success {base['success_rate']:.1f}% -> {top['success_rate']:.1f}% "
          f"({top['success_rate'] - base['success_rate']:+.1f} pp)")


if __name__ == "__main__":
    main()
