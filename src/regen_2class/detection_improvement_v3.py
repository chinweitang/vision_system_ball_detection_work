"""Detection improvement across the tuning stages - v3, data-bearing stages only.

A READ of results/detector_tuning/history/results_history.csv. Opened read-only
and never written back. Nothing is re-run.

Differs from detection_improvement_v2.py in five ways:
  - Stages carrying NO rate in either series are excluded, so every x position
    holds at least one marker. v2's grey "no value recorded" dashes are therefore
    gone - after this exclusion no such stage survives.
  - x tick labels are integer row numbers from ROW_NUMBERS below, not prose.
  - A vertical dashed divider sits immediately before the final stage, annotated
    with the population change it marks.
  - The caption is two lines, denominators only.
  - The x-axis label points at the report's Table 3.

v2's exclusion of the rect close-kernel stage CARRIES FORWARD - the brief lists
it among neither the changes nor the reversals. The divider requirement confirms
it independently: "immediately before the final stage" marks a population change
to 163 flights, which is only true if the final stage is the 163-flight row. The
rect row is also a 163-flight row, so including it would put the divider between
two 163-flight stages.

TERMINOLOGY: the source column for series 2 is named with a word this figure must
not use. It is read by column name in code only. Every user-facing string - series
labels, axis labels, title, caption, annotation, companion CSV headers - says
"true detection rate". A gate asserts the forbidden word appears in none of them
before anything is written.

STOP conditions, all checked before anything is drawn:
  - excluding no-rate rows leaves fewer than 5 stages
  - ROW_NUMBERS is empty, or any of its keys matches no surviving stage
  - a surviving stage matches no ROW_NUMBERS key, or matches more than one
  - the assigned row numbers are not unique

Outputs (NEW - v1's and v2's files are untouched):
    results/regenerate_figures/detection_improvement_v3/detection_improvement_v3.png
    results/regenerate_figures/detection_improvement_v3/detection_improvement_v3.csv
"""
import csv
import os
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
# Overridable so the layout can be proof-rendered to a scratch directory without
# writing into results/. Unset in normal use.
OUT_DIR = pathlib.Path(os.environ.get(
    "DETECTION_IMPROVEMENT_V3_OUT",
    ROOT / "results/regenerate_figures/detection_improvement_v3"))
OUT_PNG = OUT_DIR / "detection_improvement_v3.png"
OUT_CSV = OUT_DIR / "detection_improvement_v3.csv"

EXCLUDE_KEY = "rect close kernel"      # carried forward from v2
MIN_STAGES = 5

# ---------------------------------------------------------------------------
# SUPPLIED MAPPING: stage -> integer row number as printed in Table 3.
# Keyed by a substring that must match exactly one surviving stage string, not
# by position, so a new history row cannot silently shift every number by one.
# Every key must be used: an unused key means the mapping refers to a stage this
# figure does not plot, which is a STOP.
# ---------------------------------------------------------------------------
ROW_NUMBERS = [
    ("baseline (defaults)", 4),
    ("candidate config (no fixes)", 5),
    ("mask v2", 6),
    ("mask v3 (4 zones)", 7),
    ("10-FLIGHT SAMPLE", 8),
    ("FULL 163-FLIGHT DATASET", 9),
]
# Table 3 rows 1-3 are the library dataset and have no counterpart here.

S1_NAME = "average combined detection rate"
S2_NAME = "true detection rate"
# Unchanged from v2. Categorical slots 1 and 8; common.py records this pair as
# validating on all six checks (CVD dE 21.6 protan, normal-vision dE 32.3).
S1_COLOR, S2_COLOR = "#2a78d6", "#e34948"

DIVIDER_NOTE = "population changes to 163 flights"

PAGE_W_IN, DPI = 6.6, 300
FS_TITLE, FS_AXIS, FS_TICK = 11, 9.5, 8
FS_XTICK, FS_LEGEND, FS_ANNOT, FS_CAP = 9, 8, 6.8, 6.0
FS_DIVIDER = 6.6

FORBIDDEN = "recall"


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_history():
    with open(ROOT / HIST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def point_count(text):
    m = re.search(r"\((\d+) points\)", text)
    return int(m.group(1)) if m else None


def has_rate(row):
    """True if the row carries a value in EITHER series."""
    return bool(row["avg_combined_rate"].strip()) or bool(row["labeled_recall"].strip())


def flight_word(text):
    """'one flight' / 'two flights' from the stage's own annotation, so the
    caption does not hardcode a count the source file could contradict."""
    n = text.count("flight_")
    return {1: "one flight", 2: "two flights"}.get(n, f"{n} flights")


def stage_range(recs, pred, what):
    """Render the row numbers of the stages satisfying `pred` as 'stages N-M'.

    Derived rather than hardcoded so the caption cannot drift from ROW_NUMBERS.
    A non-contiguous set STOPs: 'stages 4-8' would silently misdescribe it.
    """
    nums = sorted(r["rownum"] for r in recs if pred(r))
    if not nums:
        stop(f"no stage matches {what}, so the caption cannot name a range for it")
    if nums != list(range(nums[0], nums[-1] + 1)):
        stop(f"the stages matching {what} carry non-contiguous row numbers {nums};\n"
             f"a 'stages {nums[0]}-{nums[-1]}' caption would misdescribe them")
    return f"stage {nums[0]}" if len(nums) == 1 else f"stages {nums[0]}-{nums[-1]}"


def assign_row_numbers(recs):
    """Attach ROW_NUMBERS to surviving stages, enforcing the mapping STOPs."""
    if not ROW_NUMBERS:
        stop("ROW_NUMBERS is empty. This figure labels its x axis with row numbers\n"
             "supplied by hand; there is nothing to substitute for them. Fill in\n"
             "ROW_NUMBERS with one (stage_substring, integer) pair per surviving\n"
             "stage, in any order. The surviving stages are:\n"
             + "\n".join(f"  - {r['stage'][:100]}" for r in recs))

    used = {i: [] for i in range(len(ROW_NUMBERS))}
    for r in recs:
        hits = [(i, num) for i, (key, num) in enumerate(ROW_NUMBERS)
                if key.lower() in r["stage"].lower()]
        if len(hits) != 1:
            stop(f"stage matched {len(hits)} ROW_NUMBERS key(s), expected exactly 1:\n"
                 f"  {r['stage'][:110]}\n"
                 + ("  no key matches it - add one.\n" if not hits else
                    "  matched keys: "
                    + ", ".join(repr(ROW_NUMBERS[i][0]) for i, _ in hits) + "\n"))
        i, num = hits[0]
        used[i].append(r["stage"])
        r["rownum"] = num

    unused = [ROW_NUMBERS[i] for i, stages in used.items() if not stages]
    if unused:
        stop(f"{len(unused)} supplied row number(s) went unused - each refers to a "
             f"stage this figure does not plot:\n"
             + "\n".join(f"  - {key!r} -> {num}" for key, num in unused))

    nums = [r["rownum"] for r in recs]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    if dupes:
        stop(f"assigned row numbers are not unique - repeated: {dupes}")

    return recs


def main():
    rows_all = read_history()
    print(f"read {HIST}: {len(rows_all)} rows")

    # ---- exclusion 1: rect close kernel (carried forward from v2) ----------
    after_rect = [r for r in rows_all if EXCLUDE_KEY.lower() not in r["stage"].lower()]
    dropped_rect = [r for r in rows_all if EXCLUDE_KEY.lower() in r["stage"].lower()]
    print(f"excluded {len(dropped_rect)} row(s) matching {EXCLUDE_KEY!r} (v2 rule):")
    for r in dropped_rect:
        print(f"    {r['date']}  {r['stage'][:76]}")

    # ---- exclusion 2: no rate in either series ----------------------------
    kept = [r for r in after_rect if has_rate(r)]
    dropped_norate = [r for r in after_rect if not has_rate(r)]
    print(f"excluded {len(dropped_norate)} row(s) carrying no rate in either series:")
    for r in dropped_norate:
        print(f"    {r['date']}  {r['stage'][:76]}")
    print(f"remaining: {len(kept)} stages")

    # ---- GATE 1: enough stages survive ------------------------------------
    if len(kept) < MIN_STAGES:
        stop(f"excluding no-rate rows leaves only {len(kept)} stage(s), "
             f"need at least {MIN_STAGES}")
    print(f"GATE 1 PASS: {len(kept)} stages survive (minimum {MIN_STAGES})")

    # ---- assemble ---------------------------------------------------------
    recs = []
    for i, r in enumerate(kept):
        s2 = r["labeled_recall"].strip()          # column name only; never printed
        recs.append(dict(
            idx=i, date=r["date"], stage=r["stage"],
            n_flights=r["n_flights"].strip(),
            s1=float(r["avg_combined_rate"]) if r["avg_combined_rate"].strip() else None,
            s2=float(s2) if s2 else None,
            pts=point_count(r["labeled_recall_flights"]),
            pop_text=r["labeled_recall_flights"],
        ))

    # ---- GATE 2: the supplied mapping -------------------------------------
    recs = assign_row_numbers(recs)
    print(f"GATE 2 PASS: {len(ROW_NUMBERS)} supplied row number(s), all used, "
          f"all unique: {[r['rownum'] for r in recs]}")

    # ---- divider position, derived not hardcoded --------------------------
    # Immediately before the final stage, i.e. midway between the last two x slots.
    divider_x = recs[-1]["idx"] - 0.5
    pre_n, post_n = recs[-2]["n_flights"], recs[-1]["n_flights"]
    print(f"divider at x={divider_x}: population {pre_n} -> {post_n} flights")
    if post_n != "163":
        stop(f"the final stage is a {post_n}-flight row, but the divider annotation "
             f"states a change to 163 flights")

    # ---- caption: two lines max -------------------------------------------
    # Only the changing denominators. The markers-only rationale and the source
    # line are deliberately NOT here - the LaTeX caption carries the same
    # information, and repeating it puts it on the page twice. The source stays
    # recorded in this module's docstring and in the worklog.
    pre_pts, post_pts = recs[0]["pts"], recs[-1]["pts"]
    sample_stages = stage_range(recs, lambda r: r["n_flights"] != post_n,
                                f"the {pre_n}-flight validation sample")
    full_stages = stage_range(recs, lambda r: r["n_flights"] == post_n,
                              f"the full {post_n}-flight population")
    early_stages = stage_range(recs, lambda r: r["pts"] == pre_pts,
                               f"the {pre_pts}-point population")
    late_stages = stage_range(recs, lambda r: r["pts"] == post_pts,
                              f"the {post_pts}-point population")
    pre_word = flight_word(next(r["pop_text"] for r in recs if r["pts"] == pre_pts))
    post_word = flight_word(next(r["pop_text"] for r in recs if r["pts"] == post_pts))

    caption = [
        f"combined rate is measured on the validation sample at {sample_stages} "
        f"and on all {post_n} flights at {full_stages}.",
        f"{S2_NAME} is {pre_pts} labelled points on {pre_word} at {early_stages} "
        f"and {post_pts} points on {post_word} at {late_stages}.",
    ]
    if len(caption) > 2:
        stop(f"caption is {len(caption)} lines, the brief allows at most 2")

    # ---- GATE 3: terminology ----------------------------------------------
    surfaced = ([S1_NAME, S2_NAME, "rate", DIVIDER_NOTE,
                 "iteration stage, numbered as in Table 3",
                 "Detection performance across the tuning iteration stages"]
                + caption + [str(r["rownum"]) for r in recs])
    hits = [s for s in surfaced if FORBIDDEN in s.lower()]
    if hits:
        stop(f"the word {FORBIDDEN!r} appears in {len(hits)} user-facing string(s), "
             f"which this figure must not use:\n"
             + "\n".join(f"  - {h[:90]}" for h in hits))
    print(f"GATE 3 PASS: {FORBIDDEN!r} appears in none of the "
          f"{len(surfaced)} user-facing strings")

    # ---- draw -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, 4.4))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax, grid_axis="y")
    xs = [r["idx"] for r in recs]

    for key, name, colour, marker in (("s1", S1_NAME, S1_COLOR, "o"),
                                      ("s2", S2_NAME, S2_COLOR, "D")):
        pts = [(r["idx"], r[key]) for r in recs if r[key] is not None]
        ax.plot([i for i, _ in pts], [v for _, v in pts], linestyle="none",
                marker=marker, ms=6.0, color=colour, label=name, zorder=4)

    # Value labels placed by RANK at each x, not by series - a fixed
    # above-for-s1 / below-for-s2 rule collides wherever s2 > s1.
    for r in recs:
        present = [(k, r[k], c) for k, c in (("s1", S1_COLOR), ("s2", S2_COLOR))
                   if r[k] is not None]
        present.sort(key=lambda t: t[1])                      # low -> high
        for rank, (k, v, colour) in enumerate(present):
            dy = 9 if (len(present) == 1 or rank == len(present) - 1) else -15
            ax.annotate(f"{v:.4f}", xy=(r["idx"], v), xytext=(0, dy),
                        textcoords="offset points", ha="center",
                        color=colour, fontsize=FS_ANNOT, zorder=5)

    vals = [r[k] for r in recs for k in ("s1", "s2") if r[k] is not None]
    lo, hi = min(vals), max(vals)
    span = hi - lo
    ax.set_ylim(lo - span * 0.16, hi + span * 0.16)

    # ---- divider ----------------------------------------------------------
    y0, y1 = ax.get_ylim()
    ax.axvline(divider_x, linestyle="--", linewidth=1.0, color=C.MUTED, zorder=2)
    ax.annotate(DIVIDER_NOTE, xy=(divider_x, y1), xytext=(-4, -4),
                textcoords="offset points", rotation=90, ha="right", va="top",
                color=C.INK2, fontsize=FS_DIVIDER, zorder=5)

    ax.set_xticks(xs)
    ax.set_xticklabels([str(r["rownum"]) for r in recs], fontsize=FS_XTICK)
    ax.set_xlim(-0.6, len(recs) - 0.4)
    ax.set_ylabel("rate", color=C.INK, fontsize=FS_AXIS)
    ax.set_xlabel("iteration stage, numbered as in Table 3",
                  color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    # Centre-left, not lower-right: the divider spans the full plot height at the
    # right-hand end, and a lower-right legend sits on top of it.
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
              loc="center left")
    ax.set_title("Detection performance across the tuning iteration stages",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)

    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
        plt.close(fig)
    else:
        gap, floor_y = 0.0225, 0.010
        start_y = floor_y + (len(caption) - 1) * gap
        cap_texts = [fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
                     for i, line in enumerate(caption)]

        fig.tight_layout(rect=[0, start_y + 0.024, 1, 1])

        # Measure the caption as rendered rather than guessing a character budget -
        # a line that runs past the page edge is silently clipped in the PNG, which
        # is how the first draft lost the end of its second line.
        fig.canvas.draw()
        fig_w_px = fig.get_size_inches()[0] * fig.dpi
        over = [(i, t.get_window_extent().x1 / fig_w_px)
                for i, t in enumerate(cap_texts)
                if t.get_window_extent().x1 / fig_w_px > 1.0]
        if over:
            stop("caption line(s) run past the right page edge and would be clipped:\n"
                 + "\n".join(f"  line {i + 1} ends at {frac:.3f} of page width:\n"
                             f"    {caption[i]}" for i, frac in over))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=DPI, facecolor=C.SURF)
        plt.close(fig)
        print(f"\nwrote {OUT_PNG}")

    # ---- companion CSV ----------------------------------------------------
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["table3_row", "date", "flights_in_combined_rate",
                    "average_combined_detection_rate",
                    "true_detection_rate", "true_detection_rate_points", "stage"])
        for r in recs:
            w.writerow([r["rownum"], r["date"], r["n_flights"],
                        "" if r["s1"] is None else f"{r['s1']:.4f}",
                        "" if r["s2"] is None else f"{r['s2']:.4f}",
                        "" if r["pts"] is None else r["pts"], r["stage"]])
    print(f"wrote {OUT_CSV}")
    print("v1 and v2 outputs untouched; source CSV not modified")


if __name__ == "__main__":
    main()
