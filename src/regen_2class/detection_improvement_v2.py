"""Detection improvement across the tuning stages - single panel, two series.

A READ of results/detector_tuning/history/results_history.csv. Opened read-only
and never written back. Nothing is re-run.

Differs from detection_improvement_figure.py (v1) in three ways:
  - ONE panel, not four. Both series share a y-axis.
  - The rect close-kernel stage is excluded entirely.
  - The differing denominators are stated in the caption rather than being
    expressed structurally as separate panels.

Both series are dimensionless rates in [0, 1], so a shared axis is
dimensionally sound. It is worth being explicit that the two series are
nonetheless measured over different populations, and that those populations
CHANGE PART-WAY ALONG each series - which is exactly what the caption carries.

TERMINOLOGY: the source column for series 2 is named with a word this figure
must not use. It is read by column name in code only. Every user-facing string -
series labels, axis label, title, caption, companion CSV headers - says
"true detection rate". A gate asserts the forbidden word appears in none of
them before anything is written.

STOP conditions, both checked before anything is drawn:
  - excluding the rect row leaves fewer than 5 rows carrying a combined rate
  - any stage label is not unique

Outputs (NEW - v1's files are untouched):
    results/regenerate_figures/detection_improvement_v2/detection_improvement_v2.png
    results/regenerate_figures/detection_improvement_v2/detection_improvement_v2.csv
"""
import csv
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import clean_figures as CF

ROOT = pathlib.Path(__file__).resolve().parents[2]
HIST = "results/detector_tuning/history/results_history.csv"
OUT_DIR = ROOT / "results/regenerate_figures/detection_improvement_v2"
OUT_PNG = OUT_DIR / "detection_improvement_v2.png"
OUT_CSV = OUT_DIR / "detection_improvement_v2.csv"

# The stage excluded by the brief, matched on a substring of `stage`.
EXCLUDE_KEY = "rect close kernel"

MIN_COMBINED_ROWS = 5

S1_NAME = "average combined detection rate"
S2_NAME = "true detection rate"
# Categorical slots 1 and 8. common.py records this pair as validating on all six
# checks (CVD dE 21.6 protan, normal-vision dE 32.3).
S1_COLOR, S2_COLOR = "#2a78d6", "#e34948"
NOVAL_COLOR = "#c9c8c3"

# Short x labels, keyed by a substring that must match exactly one stage string.
# Keyed rather than positional so a new history row cannot shift every label by
# one. The rect row has no entry - it is excluded before labelling.
LABEL_KEYS = [
    ("baseline (defaults)", "baseline\n(defaults)"),
    ("round 1 sweep", "round 1 sweep\nstride/thresh/open_k"),
    ("candidate config (no fixes)", "candidate\n(no fixes)"),
    ("artifact audit (pre-mask-v3", "audit\npre-mask-v3"),
    ("mask v2 + trajectory filter", "+ mask v2\n+ traj filter"),
    ("mask v3 (4 zones)", "+ mask v3\n(4 zones)"),
    ("round 3 sweep", "round 3 sweep\nmin_area/min_circ"),
    ("audit at min_area=30/min_circ=0.30 (pre-mask-v4", "audit\npre-mask-v4"),
    ("post-mask-v4 re-audit", "audit\npost-mask-v4"),
    ("10-FLIGHT SAMPLE", "+ mask v4\n+ area30 (sample)"),
    # "(current)" is load-bearing: the rect row's stage text ALSO ends in
    # "- FULL 163-FLIGHT DATASET". Kept even though rect is excluded here, so the
    # key stays correct if the exclusion is ever lifted.
    ("FULL 163-FLIGHT DATASET (current)", "full dataset\n163 flights"),
]

PAGE_W_IN, DPI = 6.6, 300
FS_TITLE, FS_AXIS, FS_TICK = 11, 9.5, 8
FS_XTICK, FS_LEGEND, FS_ANNOT, FS_CAP = 6.8, 8, 6.8, 6.0

FORBIDDEN = "recall"


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_history():
    with open(ROOT / HIST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def short_label(stage):
    hits = [lab for key, lab in LABEL_KEYS if key.lower() in stage.lower()]
    if len(hits) != 1:
        stop(f"stage string matched {len(hits)} label keys, expected exactly 1:\n"
             f"  {stage[:110]}\nLABEL_KEYS is out of date with the history file.")
    return hits[0]


def point_count(text):
    m = re.search(r"\((\d+) points\)", text)
    return int(m.group(1)) if m else None


def flight_word(text):
    """'one flight' / 'two flights' from the stage's own annotation, so the
    caption does not hardcode a count the file could contradict."""
    n = text.count("flight_")
    return {1: "one flight", 2: "two flights"}.get(n, f"{n} flights")


def main():
    rows_all = read_history()

    # ---- exclusion -------------------------------------------------------
    kept = [r for r in rows_all if EXCLUDE_KEY.lower() not in r["stage"].lower()]
    dropped = [r for r in rows_all if EXCLUDE_KEY.lower() in r["stage"].lower()]
    print(f"read {HIST}: {len(rows_all)} rows")
    print(f"excluded {len(dropped)} row(s) matching {EXCLUDE_KEY!r}:")
    for r in dropped:
        print(f"    {r['date']}  {r['stage'][:78]}")
    print(f"remaining: {len(kept)} rows")

    # ---- GATE 1: enough combined-rate rows after exclusion ----------------
    with_comb = [r for r in kept if r["avg_combined_rate"].strip()]
    if len(with_comb) < MIN_COMBINED_ROWS:
        stop(f"excluding the rect row leaves only {len(with_comb)} row(s) carrying a "
             f"combined rate, need at least {MIN_COMBINED_ROWS}")
    print(f"GATE 1 PASS: {len(with_comb)} rows carry a combined rate "
          f"(minimum {MIN_COMBINED_ROWS})")

    # ---- GATE 2: stage labels unique --------------------------------------
    labels = [short_label(r["stage"]) for r in kept]
    dupes = {l for l in labels if labels.count(l) > 1}
    if dupes:
        stop(f"stage labels are not unique - {len(dupes)} repeated: "
             + ", ".join(sorted(d.replace(chr(10), ' ') for d in dupes)))
    raw_dupes = {r["stage"] for r in kept if [x["stage"] for x in kept].count(r["stage"]) > 1}
    if raw_dupes:
        stop(f"raw stage strings are not unique: {sorted(raw_dupes)[:3]}")
    print(f"GATE 2 PASS: {len(labels)} stage labels, all unique")

    # ---- assemble ---------------------------------------------------------
    recs = []
    for i, r in enumerate(kept):
        s2 = r["labeled_recall"].strip()          # column name only; never printed
        recs.append(dict(
            idx=i, n=i + 1, date=r["date"], stage=r["stage"],
            label=short_label(r["stage"]),
            n_flights=r["n_flights"].strip(),
            s1=float(r["avg_combined_rate"]) if r["avg_combined_rate"].strip() else None,
            s2=float(s2) if s2 else None,
            pts=point_count(r["labeled_recall_flights"]),
            pop_text=r["labeled_recall_flights"],
        ))

    # denominator transitions, derived not hardcoded
    full_idx = next(i for i, x in enumerate(recs) if x["n_flights"] == "163"
                    and x["s1"] is not None)
    r3_idx = next(i for i, x in enumerate(recs) if "round 3" in x["stage"].lower())
    pre_pts = next(x["pts"] for x in recs[:r3_idx] if x["pts"])
    post_pts = next(x["pts"] for x in recs[r3_idx:] if x["pts"])
    pre_flight_word = flight_word(next(x["pop_text"] for x in recs[:r3_idx] if x["pts"]))
    post_flight_word = flight_word(next(x["pop_text"] for x in recs[r3_idx:] if x["pts"]))
    pre_n = next(x["n_flights"] for x in recs if x["s1"] is not None)
    post_n = recs[full_idx]["n_flights"]
    print(f"  combined rate: {pre_n}-flight sample up to index {full_idx}, "
          f"{post_n} flights from '{recs[full_idx]['label'][:20]}' onward")
    print(f"  {S2_NAME}: {pre_pts} points on {pre_flight_word} before round 3, "
          f"{post_pts} points on {post_flight_word} after")

    # ---- caption, built before drawing so the gate can check it -----------
    caption = [
        f"Markers only - NO lines. The stages are discrete configuration changes, so the x positions are ordinal, not a time axis, and a",
        f"line between two of them would assert a path through configurations that were never run. Stages with no marker recorded no rate.",
        f"DENOMINATORS CHANGE PART-WAY ALONG BOTH SERIES, so neither series is a like-for-like comparison end to end:",
        f"  {S1_NAME} is measured on a {pre_n}-flight validation sample up to and including "
        f"'{recs[full_idx-1]['label'].replace(chr(10), ' ')}',",
        f"  and on all {post_n} flights from '{recs[full_idx]['label'].replace(chr(10), ' ')}' onward. The step between those two is a change of",
        f"  population, not a change in performance.",
        f"  {S2_NAME} is measured over {pre_pts} labelled points on {pre_flight_word} before the round 3 sweep, and {post_pts} labelled",
        f"  points on {post_flight_word} after it.",
        f"The rect close-kernel stage is excluded from this figure.",
        f"Source: {HIST}, read-only, plotted in the file's own row order.",
    ]

    # ---- TERMINOLOGY GATE -------------------------------------------------
    surfaced = ([S1_NAME, S2_NAME, "detection rate", "iteration stage",
                 "Detection performance across the tuning iteration stages"]
                + caption + [r["label"] for r in recs])
    hits = [s for s in surfaced if FORBIDDEN in s.lower()]
    if hits:
        stop(f"the word {FORBIDDEN!r} appears in {len(hits)} user-facing string(s), "
             f"which this figure must not use:\n"
             + "\n".join(f"  - {h[:90]}" for h in hits))
    print(f"GATE 3 PASS: {FORBIDDEN!r} appears in none of the "
          f"{len(surfaced)} user-facing strings")

    # ---- draw -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, 5.6))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax, grid_axis="y")
    xs = [r["idx"] for r in recs]

    for key, name, colour, marker in (("s1", S1_NAME, S1_COLOR, "o"),
                                      ("s2", S2_NAME, S2_COLOR, "D")):
        pts = [(r["idx"], r[key]) for r in recs if r[key] is not None]
        ax.plot([i for i, _ in pts], [v for _, v in pts], linestyle="none",
                marker=marker, ms=6.0, color=colour, label=name, zorder=4)

    # Value labels placed by RANK at each x, not by series. A fixed
    # above-for-s1 / below-for-s2 rule collides wherever s2 > s1 - the label for
    # the lower series lands on top of the higher series' marker, which happens
    # at 4 of the 6 stages carrying both.
    for r in recs:
        present = [(k, r[k], c) for k, c in (("s1", S1_COLOR), ("s2", S2_COLOR))
                   if r[k] is not None]
        if not present:
            continue
        present.sort(key=lambda t: t[1])                      # low -> high
        for rank, (k, v, colour) in enumerate(present):
            # single value: above. two values: lower goes below, higher above.
            dy = 9 if (len(present) == 1 or rank == len(present) - 1) else -15
            ax.annotate(f"{v:.4f}", xy=(r["idx"], v), xytext=(0, dy),
                        textcoords="offset points", ha="center",
                        color=colour, fontsize=FS_ANNOT, zorder=5)

    vals = [r[k] for r in recs for k in ("s1", "s2") if r[k] is not None]
    lo, hi = min(vals), max(vals)
    span = hi - lo
    ax.set_ylim(lo - span * 0.18, hi + span * 0.15)

    # stages carrying neither series - marked so an empty slot reads as
    # "not measured here" rather than "measured as zero"
    y0, y1 = ax.get_ylim()
    empties = [r["idx"] for r in recs if r["s1"] is None and r["s2"] is None]
    for i in empties:
        ax.plot([i], [y0 + (y1 - y0) * 0.035], linestyle="none", marker="_",
                ms=6, color=NOVAL_COLOR, zorder=3)

    ax.set_xticks(xs)
    ax.set_xticklabels([r["label"] for r in recs], rotation=90, fontsize=FS_XTICK)
    ax.set_xlim(-0.6, len(recs) - 0.4)
    ax.set_ylabel("rate", color=C.INK, fontsize=FS_AXIS)
    ax.set_xlabel("iteration stage, chronological (not to time scale)",
                  color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
              loc="lower right")
    ax.set_title("Detection performance across the tuning iteration stages",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)

    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
    else:
        gap, floor_y = 0.0163, 0.008
        start_y = floor_y + (len(caption) - 1) * gap
        for i, line in enumerate(caption):
            fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)

        fig.tight_layout(rect=[0, start_y + 0.018, 1, 1])
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=DPI, facecolor=C.SURF)
        print(f"\nwrote {OUT_PNG.relative_to(ROOT)}")
    plt.close(fig)

    # ---- companion CSV ----------------------------------------------------
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "date", "stage_label", "flights_in_combined_rate",
                    "average_combined_detection_rate",
                    "true_detection_rate", "true_detection_rate_points", "stage"])
        for r in recs:
            w.writerow([r["n"], r["date"], r["label"].replace("\n", " "),
                        r["n_flights"],
                        "" if r["s1"] is None else f"{r['s1']:.4f}",
                        "" if r["s2"] is None else f"{r['s2']:.4f}",
                        "" if r["pts"] is None else r["pts"], r["stage"]])
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print("v1 outputs untouched; source CSV not modified")


if __name__ == "__main__":
    main()
