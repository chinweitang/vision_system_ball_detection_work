"""Per-stage timing breakdown of the Pi pipeline, by observation window and class.

A READ of frozen results from
    results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv
Nothing is re-run: no detection, no fitting, no Pi job. The input CSV is opened
read-only and never written back.

For each (class, observation window) it reports the median and p95 of the four
timed stages plus the fixed one-frame acquisition lag:

    frame lag           16.667 ms, a CONSTANT, not a measurement
    last_pair_detect_ms detection of the newest stereo pair
    triangulate_ms      stereo triangulation of that pair
    ransac_ms           the fitting block  (see the naming note below)
    predict_ms          crossing solve + state evaluation

NAMING, because two of these columns do not mean what they say:
  - ransac_ms wraps ALL the least-squares fitting, not just the RANSAC call.
  - predict_ms contains NO fitting - only find_own_crossing + eval_pos_vel.
Neither name is changed here; the CSV column names are reproduced verbatim so
this file can be joined back to the raw sweep.

Explicitly NOT done, per the brief: ransac_ms is not compared against any
ransac_fit_ms from the stage-1 benchmark. That stage ran 15 RANSAC iterations
against this sweep's production 3, so the two are not the same quantity and a
side-by-side would be a false comparison. No stage-1 file is read.

STOP conditions, all checked before anything is written:
  - any row's stage times + 16.667 fail to reconcile to latency_ms within 0.5 ms
  - class populations are not SHORT=47 and LONG=60

Outputs (both NEW, nothing existing is overwritten):
    results/regenerate_figures/stage_timing/stage_timing_by_class_window.csv
    results/regenerate_figures/stage_timing/figure_stage_timing_breakdown.png
"""
import csv
import pathlib
import sys

# This folder carries two import conventions: step_1..step_7 use
# "regen_2class.common", step8.. use "common". Both roots are added so this
# script imports cleanly either way, without editing those files.
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import clean_figures as CF
import common as C

OUT_DIR = C.OUT_DIR + "stage_timing/"
OUT_CSV = OUT_DIR + "stage_timing_by_class_window.csv"
OUT_PNG = OUT_DIR + "figure_stage_timing_breakdown.png"

# ONE_FRAME_LAG_MS in prediction_pipeline_sweep_pi.py is CADENCE_MS = 1000/60.
# The brief fixes the value at 16.667, i.e. that quantity rounded to 3 dp; the
# 0.000333 ms difference is the entire reconciliation residual seen below.
FRAME_LAG_MS = 16.667
RECONCILE_TOL_MS = 0.5
EXPECTED_POP = {"SHORT": 47, "LONG": 60}

# Timed stages, in the order they occur in the pipeline. The stack is drawn in
# this order from the bottom up, so vertical position reads as elapsed time.
STAGES = ["last_pair_detect_ms", "triangulate_ms", "ransac_ms", "predict_ms"]
COMPONENTS = ["frame_lag_ms"] + STAGES

STAGE_LABEL = {
    "frame_lag_ms": "frame lag (fixed 16.667 ms)",
    "last_pair_detect_ms": "detect (newest stereo pair)",
    "triangulate_ms": "triangulate",
    "ransac_ms": "ransac_ms  (all LSQ fitting)",
    "predict_ms": "predict_ms  (crossing solve)",
}

# Palette. NOTE: the dataviz bundle's validate_palette.js is not present in this
# environment, so these were NOT machine-checked for CVD separation. They are a
# contiguous run of the documented categorical order already used elsewhere in
# this figure set, kept so the stage colours do not collide with CLASS_COLOR or
# BAND_COLOR. Re-validate before the figure goes to print.
STAGE_COLOR = {
    "frame_lag_ms": "#8a8a84",
    "last_pair_detect_ms": "#2a78d6",
    "triangulate_ms": "#1baf7a",
    "ransac_ms": "#eda100",
    "predict_ms": "#4a3aa7",
}

# Print sizing: built 1:1 at 0.8 of A4 width, so a font point here is a real
# point on the page and nothing is rescaled by the document.
PAGE_W_IN, DPI = 6.6, 300
FS_SUPTITLE, FS_PANEL, FS_AXIS = 11, 9, 9.5
FS_TICK, FS_XTICK, FS_LEGEND, FS_ANNOT, FS_CAP = 8, 6.0, 7.5, 6.5, 5.6


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def load_rows():
    """Raw sweep rows, read-only. fit_failed rows carry blank stage columns and
    blank latency_ms, so they are separated out rather than coerced to zero."""
    with open(C.SWEEP_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ok = [r for r in rows if r["status"] == "ok"]
    failed = [r for r in rows if r["status"] != "ok"]
    return rows, ok, failed


def class_map(rows):
    """{(session, flight): class}, from the FULL flight record.

    Keyed on (session, flight) - 32 flight ids exist in both sessions, so a bare
    id silently merges two different flights. Class is taken from the flight's
    bin, asserted single-valued across all 24 of its window rows, then mapped
    through CLASS_OF_BIN (FLAT/MID -> SHORT, LOB -> LONG), which step_1 asserted
    equivalent to the 45 degree elevation cut.
    """
    bins = {}
    for r in rows:
        bins.setdefault((r["session"], r["flight"]), set()).add(r["bin"])
    mixed = {k: v for k, v in bins.items() if len(v) != 1}
    if mixed:
        stop(f"{len(mixed)} flights carry more than one bin, so the class is not "
             f"a property of the flight record: {list(mixed)[:5]}")
    return {k: C.CLASS_OF_BIN[next(iter(v))] for k, v in bins.items()}


def cross_check_elevation(cls_of):
    """Confirm the bin-derived class against two_class_join.csv, which carries
    elevation_deg. Advisory: if the join is absent the breakdown still stands on
    the sweep CSV alone, so this reports rather than stops."""
    p = pathlib.Path(C.JOIN_CSV)
    if not p.is_file():
        return "two_class_join.csv absent - elevation cross-check skipped"
    join = {}
    elev = {}
    for r in C.read_csv(C.JOIN_CSV):
        join[(r["session"], r["flight"])] = r["cls2"]
        elev[(r["session"], r["flight"])] = float(r["elevation_deg"])
    shared = set(join) & set(cls_of)
    disagree = [k for k in shared if join[k] != cls_of[k]]
    wrong_side = [k for k in shared
                  if (elev[k] >= C.ELEVATION_CUT_DEG) != (cls_of[k] == "LONG")]
    return (f"cross-checked against two_class_join.csv on {len(shared)} flights: "
            f"{len(disagree)} class disagreements, "
            f"{len(wrong_side)} on the wrong side of the {C.ELEVATION_CUT_DEG:.0f} deg cut")


def gate_reconcile(ok):
    """GATE 1. Every ok row's four stage times plus the fixed lag must land on
    latency_ms within RECONCILE_TOL_MS."""
    worst, resid = None, []
    for r in ok:
        s = sum(float(r[c]) for c in STAGES) + FRAME_LAG_MS
        d = abs(s - float(r["latency_ms"]))
        resid.append(d)
        if worst is None or d > worst[0]:
            worst = (d, r)
    over = [d for d in resid if d > RECONCILE_TOL_MS]
    if over:
        d, r = worst
        stop(f"{len(over)} of {len(ok)} rows fail to reconcile within "
             f"{RECONCILE_TOL_MS} ms. Worst: {r['session']}/{r['flight']} "
             f"T={r['T_ms']} residual {d:.4f} ms "
             f"(stages+lag {sum(float(r[c]) for c in STAGES) + FRAME_LAG_MS:.4f} "
             f"vs latency_ms {float(r['latency_ms']):.4f})")
    return max(resid), min(resid), len(ok)


def gate_population(cls_of):
    """GATE 2. Class populations must be exactly SHORT=47, LONG=60."""
    pop = {c: sum(1 for v in cls_of.values() if v == c) for c in C.CLASSES}
    if pop != EXPECTED_POP:
        stop(f"class populations are {pop}, expected {EXPECTED_POP}")
    return pop


def summarise(ok, failed, cls_of, windows):
    """{(class, window): {stat -> value}} plus the per-cell counts.

    Percentiles are taken over the ok rows only; a fit_failed row has no timing
    to contribute. n_ok therefore varies by window (a short window can fail to
    fit on flights that fit fine at a long one), and n_ok is carried into the
    output so a cell built on a partial population is visible rather than
    implied.
    """
    cells = {}
    n_fail = {}
    for c in C.CLASSES:
        for w in windows:
            cells[(c, w)] = []
            n_fail[(c, w)] = 0
    for r in ok:
        cells[(cls_of[(r["session"], r["flight"])], int(r["T_ms"]))].append(r)
    for r in failed:
        n_fail[(cls_of[(r["session"], r["flight"])], int(r["T_ms"]))] += 1

    out = {}
    for key, rr in cells.items():
        if not rr:
            out[key] = None
            continue
        d = {"n_ok": len(rr), "n_fit_failed": n_fail[key]}
        for stat, q in (("median", 0.5), ("p95", 0.95)):
            d[f"frame_lag_ms_{stat}"] = FRAME_LAG_MS
            for s in STAGES:
                d[f"{s}_{stat}"] = C.percentile([float(x[s]) for x in rr], q)
            d[f"stage_sum_{stat}"] = sum(d[f"{k}_{stat}"] for k in COMPONENTS)
            d[f"latency_ms_{stat}"] = C.percentile(
                [float(x["latency_ms"]) for x in rr], q)
            d[f"sum_minus_latency_{stat}"] = (d[f"stage_sum_{stat}"]
                                              - d[f"latency_ms_{stat}"])
        out[key] = d
    return out


def write_csv(summary, windows):
    cols = (["cls2", "T_ms", "n_ok", "n_fit_failed"]
            + [f"{k}_{stat}" for stat in ("median", "p95")
               for k in COMPONENTS + ["stage_sum", "latency_ms", "sum_minus_latency"]])
    pathlib.Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=cols)
        wtr.writeheader()
        for c in C.CLASSES:
            for w in windows:
                d = summary[(c, w)]
                if d is None:
                    continue
                row = {"cls2": c, "T_ms": w,
                       "n_ok": d["n_ok"], "n_fit_failed": d["n_fit_failed"]}
                for k in cols[4:]:
                    row[k] = f"{d[k]:.6f}"
                wtr.writerow(row)
    print(f"wrote {OUT_CSV}")


def draw_panel(ax, summary, windows, cls, stat, first):
    xs = list(range(len(windows)))
    bottom = [0.0] * len(windows)
    C.style_axes(ax, grid_axis="y")
    for comp in COMPONENTS:
        vals = [summary[(cls, w)][f"{comp}_{stat}"] if summary[(cls, w)] else 0.0
                for w in windows]
        ax.bar(xs, vals, bottom=bottom, color=STAGE_COLOR[comp], width=0.82,
               linewidth=0, zorder=3, label=STAGE_LABEL[comp] if first else None)
        bottom = [a + b for a, b in zip(bottom, vals)]

    # The measured latency at the same statistic. For the median this sits close
    # to the stack; for p95 it does NOT, and that gap is the point - percentiles
    # are not additive, so a stack of per-stage p95s is not the p95 of the total.
    lat = [summary[(cls, w)][f"latency_ms_{stat}"] if summary[(cls, w)] else 0.0
           for w in windows]
    # Labelled generically: this line is the panel's own statistic, so on the
    # p95 row it is the p95 of latency_ms, not the median.
    ax.plot(xs, lat, color=C.INK, lw=1.0, ls="--", marker="o", ms=2.0, zorder=5,
            label="measured latency_ms (panel's own statistic)" if first else None)

    n = EXPECTED_POP[cls]
    ax.set_title(f"{cls}  (n={n} flights)   {stat}", color=C.INK,
                 fontsize=FS_PANEL, loc="left", pad=4)
    ax.set_ylabel("time (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.set_xticks(xs)
    ax.set_xticklabels([str(w) if i % 2 == 0 else "" for i, w in enumerate(windows)],
                       rotation=90, fontsize=FS_XTICK)
    ax.set_xlim(-0.7, len(windows) - 0.3)


def caption_block(fig, lines, gap=0.0142, floor_y=0.009):
    """Anchor the LAST line at a fixed height and grow upward, so a longer
    caption cannot run off the bottom edge. Returns the rect bottom to use."""
    start_y = floor_y + (len(lines) - 1) * gap
    for i, line in enumerate(lines):
        fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
    return start_y + 0.016


def caption_facts(summary):
    """Every number quoted in the caption, measured rather than asserted.

    Written after the first draft of this caption claimed the median stack and
    the measured median coincide. They do not: a median is no more additive than
    a p95, and the gap takes both signs. The figures below are computed so the
    caption cannot drift from the data again.
    """
    cells = [v for v in summary.values() if v]
    f = {}
    f["tri_share"] = max(100 * v["triangulate_ms_median"] / v["latency_ms_median"]
                         for v in cells)
    f["rs_lo"] = min(100 * v["ransac_ms_median"] / v["latency_ms_median"] for v in cells)
    f["rs_hi"] = max(100 * v["ransac_ms_median"] / v["latency_ms_median"] for v in cells)
    for stat, tag in (("median", "med"), ("p95", "p95")):
        d = [v[f"sum_minus_latency_{stat}"] for v in cells]
        pct = [100 * abs(x) / v[f"latency_ms_{stat}"] for x, v in zip(d, cells)]
        f[f"{tag}_max"] = max(abs(x) for x in d)
        f[f"{tag}_min"] = abs(min(d))
        f[f"{tag}_pct"] = max(pct)
        f[f"{tag}_neg"] = sum(1 for x in d if x < 0)
        f[f"{tag}_pos"] = sum(1 for x in d if x >= 0)
    f["n_lo"] = min(v["n_ok"] for v in cells)
    f["n_hi"] = max(v["n_ok"] for v in cells)
    f["n_part"] = sum(1 for (c, _), v in summary.items()
                      if v and v["n_ok"] < EXPECTED_POP[c])
    return f


def make_figure(summary, windows, f):
    tri_share, rs_lo, rs_hi = f["tri_share"], f["rs_lo"], f["rs_hi"]
    med_max, med_pct, med_neg = f["med_max"], f["med_pct"], f["med_neg"]
    p95_max, p95_min, p95_pct = f["p95_max"], f["p95_min"], f["p95_pct"]
    p95_pos, p95_neg = f["p95_pos"], f["p95_neg"]
    n_lo, n_hi, n_part = f["n_lo"], f["n_hi"], f["n_part"]

    fig, axg = plt.subplots(2, 2, figsize=(PAGE_W_IN, 7.4), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    for row_i, stat in enumerate(("median", "p95")):
        for col_i, cls in enumerate(C.CLASSES):
            draw_panel(axg[row_i][col_i], summary, windows, cls, stat,
                       first=(row_i == 0 and col_i == 0))
    for col_i in range(2):
        axg[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)

    handles, labels = axg[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center",
               bbox_to_anchor=(0.5, 0.965), ncol=3)
    fig.suptitle("Pi pipeline latency by stage, observation window and class",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.006, ha="left", y=0.995)

    # Lines are held to ~150 characters. At FS_CAP on a PAGE_W_IN canvas, longer
    # lines run past the right edge and are silently clipped.
    caption = [
        "Stack order is pipeline order, bottom to top. Frame lag is a FIXED 16.667 ms constant (one frame at 60 Hz), not a measurement. PNG decode is untimed.",
        f"Two column names from the raw CSV mislead: ransac_ms wraps ALL the least-squares fitting, not just the RANSAC call, and is {rs_lo:.0f}-{rs_hi:.0f}% of median latency.",
        f"predict_ms contains NO fitting - only the crossing solve and state evaluation. triangulate_ms is real but invisible: at worst {tri_share:.2f}% of median latency.",
        "The per-ROW identity stage sum + 16.667 = latency_ms is exact (residual 0.0003 ms on all 2481 ok rows), but neither the median nor the p95 of a sum",
        "equals the sum of the medians or p95s, so the stack and the dashed measured line need not meet, and do not.",
        f"MEDIAN panels: stack minus measured stays within {med_max:.1f} ms ({med_pct:.1f}% of latency) and takes BOTH signs - {med_neg} of 48 cells low, {48 - med_neg} high.",
        f"P95 panels: the stack runs HIGH in {p95_pos} of 48 cells, by up to {p95_max:.1f} ms ({p95_pct:.1f}%), because the stages do not hit their p95 on the same flight.",
        f"It is not a strict upper bound either - {p95_neg} cells sit below the measured p95, by at most {p95_min:.1f} ms. Read the dashed line, not the stack top.",
        f"Percentiles are over status=='ok' rows only; fit_failed rows carry no timing. n_ok ranges {n_lo}-{n_hi} and {n_part} of 48 cells rest on a partial population,",
        "because a short window can fail to fit on flights that fit at a long one. Per-cell n_ok and n_fit_failed are in the companion CSV.",
        "Class is from the full flight record, 45 deg elevation cut. ransac_ms is NOT compared here against stage 1's ransac_fit_ms: that benchmark ran 15",
        "RANSAC iterations against this sweep's production 3, so the two are different quantities.",
    ]
    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
        plt.close(fig)
    else:
        rect_bottom = caption_block(fig, caption)
        fig.tight_layout(rect=[0, rect_bottom, 1, 0.945])
        pathlib.Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=DPI, facecolor=C.SURF)
        plt.close(fig)
        print(f"wrote {OUT_PNG}")


def main():
    rows, ok, failed = load_rows()
    windows = sorted({int(r["T_ms"]) for r in rows})
    cls_of = class_map(rows)

    print(f"read {C.SWEEP_CSV}")
    print(f"  {len(rows)} rows = {len(ok)} ok + {len(failed)} fit_failed, "
          f"{len(cls_of)} flights, {len(windows)} windows")

    max_r, min_r, n = gate_reconcile(ok)
    print(f"GATE 1 reconciliation PASS: stage sum + {FRAME_LAG_MS} == latency_ms "
          f"for all {n} ok rows, residual {min_r:.6f}..{max_r:.6f} ms "
          f"(tolerance {RECONCILE_TOL_MS})")
    pop = gate_population(cls_of)
    print(f"GATE 2 population PASS: {pop}")
    print(f"  {cross_check_elevation(cls_of)}")

    summary = summarise(ok, failed, cls_of, windows)
    empty = [k for k, v in summary.items() if v is None]
    if empty:
        print(f"  note: {len(empty)} (class, window) cells have no ok rows: {empty}")

    facts = caption_facts(summary)
    write_csv(summary, windows)
    make_figure(summary, windows, facts)

    print(f"\nstack vs measured latency (neither median nor p95 is additive):")
    print(f"  median: |stack - measured| <= {facts['med_max']:.2f} ms "
          f"({facts['med_pct']:.2f}% of latency), {facts['med_neg']} of 48 cells low, "
          f"{facts['med_pos']} high")
    print(f"  p95   : stack high in {facts['p95_pos']} of 48 cells by up to "
          f"{facts['p95_max']:.2f} ms ({facts['p95_pct']:.2f}%), low in "
          f"{facts['p95_neg']} by at most {facts['p95_min']:.2f} ms")
    print(f"  ransac_ms is {facts['rs_lo']:.1f}-{facts['rs_hi']:.1f}% of median latency; "
          f"triangulate_ms at most {facts['tri_share']:.3f}%")

    # ---- console summary, the numbers worth quoting -------------------------
    print("\nmedian latency composition at the two min-anchored deadlines:")
    for cls, w in (("SHORT", 490), ("LONG", 1040)):
        w_use = w if w in windows else max(x for x in windows if x <= w)
        d = summary[(cls, w_use)]
        tag = "" if w_use == w else f" (nearest grid window to {w})"
        print(f"  {cls} @ {w_use} ms{tag}: "
              + "  ".join(f"{k.replace('_ms','')} {d[k + '_median']:.2f}"
                          for k in COMPONENTS)
              + f"  -> latency median {d['latency_ms_median']:.2f}, "
                f"p95 {d['latency_ms_p95']:.2f}")
    print("\ninput CSV not modified; no stage-1 file read")


if __name__ == "__main__":
    main()
