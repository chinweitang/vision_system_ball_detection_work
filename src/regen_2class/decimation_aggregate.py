"""Aggregate the frame-rate decimation arms and emit the reporting artefacts.

Reads the two arm CSVs produced by framerate_decimation_sweep.py (60 fps run
alone for the regression gate, then 30/20 fps) plus the SHORT/LONG class join,
and writes the combined raw file, the per (class, rate, window) summary, and the
figure.

TERMINOLOGY. The reference is the full-arc fixed-gravity-with-drag fit, so every
error here is CONVERGENCE toward that reference, not accuracy against ground
truth.

TIMINGS ARE VOID. This reads position and point-count columns only. No timing
column from the decimation run is read, aggregated or written.

Nothing is overwritten: any output path that already exists takes the next free
numeric suffix.
"""
import csv
import math
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results/regenerate_figures/05_framerate_decimation"
# One CSV per arm-group invocation. Globbed rather than listed so the run can be
# split per arm (--phases) without editing this file. Sorted for determinism.
ARM_CSVS = sorted(OUT_DIR.glob("decimation_*fps*.csv"))
JOIN_CSV = ROOT / "results/regenerate_figures/two_class_join.csv"

WINDOW = {"SHORT": 400, "LONG": 850}
CLASSES = ["SHORT", "LONG"]
RATES = [60, 30, 20]
EXPECTED_PHASES = {60: 1, 30: 2, 20: 3}
EXPECTED_N = {"SHORT": 47, "LONG": 60}

RATE_COLOUR = {60: "#2a78d6", 30: "#eda100", 20: "#e34948"}


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def next_free(p):
    if not p.exists():
        return p
    n = 2
    while p.with_name(f"{p.stem}_{n:02d}{p.suffix}").exists():
        n += 1
    return p.with_name(f"{p.stem}_{n:02d}{p.suffix}")


def read(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def percentile(v, q):
    v = sorted(v)
    if not v:
        return float("nan")
    k = (len(v) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def main():
    print("=" * 78)
    print("FRAME-RATE DECIMATION — AGGREGATE")
    print("=" * 78)
    print("Reference = full-arc fixed-gravity-with-drag fit. CONVERGENCE, not")
    print("accuracy against ground truth. All timings from these runs are VOID.")
    print()

    if not ARM_CSVS:
        stop(f"no arm CSVs matched {OUT_DIR.relative_to(ROOT)}/decimation_*fps*.csv")
    rows = []
    seen_arm = {}
    for p in ARM_CSVS:
        r = read(p)
        print(f"read {p.relative_to(ROOT)}  ({len(r)} rows)")
        for a in {(int(x["fps"]), int(x["phase"])) for x in r}:
            if a in seen_arm:
                stop(f"arm {a[0]}fps/phase{a[1]} appears in both "
                     f"{seen_arm[a].name} and {p.name} — would double-count")
            seen_arm[a] = p
        rows += r

    # The join file is one row per (flight, window), so collapsing it to one class
    # per flight is only safe if cls2 never varies within a flight. Check, do not
    # assume: a flight that changed class between windows would silently take
    # whichever row happened to come last.
    join = read(JOIN_CSV)
    cls_of = {}
    for x in join:
        k = (x["session"], x["flight"])
        if k in cls_of and cls_of[k] != x["cls2"]:
            stop(f"flight {k} has two classes in the join file: "
                 f"{cls_of[k]} and {x['cls2']}")
        cls_of[k] = x["cls2"]

    counts = {c: sum(1 for v in cls_of.values() if v == c) for c in CLASSES}
    print(f"class join: {counts['SHORT']} SHORT + {counts['LONG']} LONG "
          f"= {len(cls_of)} flights")
    if counts != EXPECTED_N:
        stop(f"class populations are {counts}, expected {EXPECTED_N}")

    unjoined = {(r["session"], r["flight"]) for r in rows
                if (r["session"], r["flight"]) not in cls_of}
    if unjoined:
        stop(f"{len(unjoined)} flight(s) failed to join to a class: "
             f"{sorted(unjoined)[:5]}")

    # ---- arm shape checks --------------------------------------------------
    arms = sorted({(int(r["fps"]), int(r["phase"])) for r in rows})
    print(f"\narms present: {arms}")
    for rate, n_ph in EXPECTED_PHASES.items():
        got = sorted({p for f, p in arms if f == rate})
        if len(got) != n_ph:
            stop(f"{rate} fps has phases {got}, expected {n_ph}")
    windows = sorted({int(r["T_ms"]) for r in rows})
    for (rate, ph) in arms:
        sub = [r for r in rows if int(r["fps"]) == rate and int(r["phase"]) == ph]
        fl = {(r["session"], r["flight"]) for r in sub}
        w = {int(r["T_ms"]) for r in sub}
        if len(fl) != 107 or len(w) != len(windows):
            stop(f"arm {rate}fps/phase{ph}: {len(fl)} flights, {len(w)} windows; "
                 f"expected 107 and {len(windows)} — arms are not comparable")
    print(f"all {len(arms)} arms carry 107 flights x {len(windows)} windows")

    # decimation must not change which flights are included
    per_rate_flights = {rate: {(r["session"], r["flight"]) for r in rows
                               if int(r["fps"]) == rate} for rate in RATES}
    base = per_rate_flights[60]
    for rate in RATES:
        if per_rate_flights[rate] != base:
            d = base ^ per_rate_flights[rate]
            stop(f"{rate} fps covers a different flight set than 60 fps: {sorted(d)[:5]}")
    print("decimation did not alter the flight set (identical across all rates)")

    # ---- combined raw ------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_cols = ["session", "flight", "cls", "fps", "phase", "T_ms", "status",
                "n_points_used", "position_error_mm",
                "cy_own", "cz_own", "cy_ref", "cz_ref"]
    raw_out = []
    for r in rows:
        rec = {c: r.get(c) for c in raw_cols if c != "cls"}
        rec["cls"] = cls_of[(r["session"], r["flight"])]
        raw_out.append(rec)
    p = next_free(OUT_DIR / "decimation_raw.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=raw_cols)
        w.writeheader()
        w.writerows(raw_out)
    print(f"\nwrote {p.relative_to(ROOT)}  ({len(raw_out)} rows)")

    # ---- summary per (class, rate, window), averaged across phases ---------
    summary = []
    for cls in CLASSES:
        for rate in RATES:
            for T in windows:
                sub = [r for r in rows
                       if cls_of[(r["session"], r["flight"])] == cls
                       and int(r["fps"]) == rate and int(r["T_ms"]) == T]
                n_cells = len(sub)
                errs = [float(r["position_error_mm"]) for r in sub
                        if r["position_error_mm"].strip()]
                npts = [int(r["n_points_used"]) for r in sub
                        if str(r.get("n_points_used", "")).strip()]
                n_fail = n_cells - len(errs)
                summary.append(dict(
                    cls=cls, fps=rate, T_ms=T,
                    n_phases=EXPECTED_PHASES[rate],
                    n_cells=n_cells, n_fit_ok=len(errs), n_fit_fail=n_fail,
                    fit_fail_fraction=f"{(n_fail / n_cells) if n_cells else 0:.6f}",
                    median_position_error_mm=f"{percentile(errs, 0.50):.4f}" if errs else "",
                    p95_position_error_mm=f"{percentile(errs, 0.95):.4f}" if errs else "",
                    median_n_points_used=f"{percentile(npts, 0.50):.1f}" if npts else "",
                ))
    p = next_free(OUT_DIR / "decimation_summary.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print(f"wrote {p.relative_to(ROOT)}  ({len(summary)} rows)")

    # ---- HEADLINE: operating points, error AND point count -----------------
    print("\n" + "=" * 78)
    print("HEADLINE — at the operating points")
    print("=" * 78)
    print(f"  {'class':<7}{'window':>8}{'rate':>7}{'median err (mm)':>18}"
          f"{'p95 err (mm)':>15}{'median n_points':>17}{'fit fails':>11}")
    for cls in CLASSES:
        T = WINDOW[cls]
        for rate in RATES:
            s = next(x for x in summary
                     if x["cls"] == cls and x["fps"] == rate and x["T_ms"] == T)
            print(f"  {cls:<7}{T:>6} ms{rate:>6}f{s['median_position_error_mm']:>18}"
                  f"{s['p95_position_error_mm']:>15}{s['median_n_points_used']:>17}"
                  f"{s['n_fit_fail']:>7}/{s['n_cells']:<3}")

    # ---- fit-failure count per (rate, window), full shape ------------------
    print("\n" + "=" * 78)
    print("FIT FAILURES per (rate, window) — counts over all cells, both classes")
    print("=" * 78)
    print(f"  {'window':>7}", end="")
    for rate in RATES:
        print(f"{str(rate) + ' fps':>22}", end="")
    print()
    print(f"  {'':>7}", end="")
    for _ in RATES:
        print(f"{'fail/cells':>13}{'frac':>9}", end="")
    print()
    for T in windows:
        print(f"  {T:>5} ms", end="")
        for rate in RATES:
            ss = [x for x in summary if x["fps"] == rate and x["T_ms"] == T]
            nf = sum(x["n_fit_fail"] for x in ss)
            nc = sum(x["n_cells"] for x in ss)
            print(f"{str(nf) + '/' + str(nc):>13}{nf / nc if nc else 0:>9.3f}", end="")
        print()

    print("\n  shortest window with a fit for >90% of cells, per rate:")
    for rate in RATES:
        ok = None
        for T in windows:
            ss = [x for x in summary if x["fps"] == rate and x["T_ms"] == T]
            nf = sum(x["n_fit_fail"] for x in ss)
            nc = sum(x["n_cells"] for x in ss)
            if nc and (nc - nf) / nc > 0.90:
                ok = T
                break
        print(f"    {rate} fps: {str(ok) + ' ms' if ok else 'NONE of the tested windows'}")

    # ---- figure ------------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, cls in zip(axes, CLASSES):
        ax.set_facecolor("white")
        ax.grid(True, color="#dddddd", lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for rate in RATES:
            ss = sorted((x for x in summary if x["cls"] == cls and x["fps"] == rate),
                        key=lambda x: x["T_ms"])
            xs = [x["T_ms"] for x in ss if x["median_position_error_mm"]]
            ys = [float(x["median_position_error_mm"]) for x in ss
                  if x["median_position_error_mm"]]
            ax.plot(xs, ys, marker="o", ms=4, lw=1.7, color=RATE_COLOUR[rate],
                    zorder=3, label=f"{rate} fps")
        ax.axvline(WINDOW[cls], color="#444444", ls="--", lw=1.2, zorder=2)
        ax.set_yscale("log")
        ax.set_xlabel("observation window (ms)", fontsize=10)
        ax.set_title(f"{cls}  (operating point {WINDOW[cls]} ms)", fontsize=11,
                     loc="left")
        ax.tick_params(labelsize=9)
    axes[0].set_ylabel("median crossing-position error (mm)", fontsize=10)
    axes[0].legend(frameon=False, fontsize=9.5, loc="upper right")
    fig.tight_layout()
    p = next_free(OUT_DIR / "figure_framerate_decimation.png")
    fig.savefig(p, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote {p.relative_to(ROOT)}")
    print("  (no caption burned into the image; caption text lives in the log)")
    print("\n  No timing column was read or written.")


if __name__ == "__main__":
    main()
