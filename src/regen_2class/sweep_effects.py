"""Readout of the two detector parameter sweeps for the report.

Reads (read-only, never writes back):
  results/detector_tuning/sweep_results.csv            - stride x diff_threshold x open_kernel
  results/detector_tuning/sweep_results_min_area_circ.csv - min_area x min_circ

Both were requested as `data/detector_tuning/...`; the 2026-08-24_0215 migration
moved everything under `data/detector_tuning/` except `contact_sheets/` into
`results/`. Same files.

Every emitted number carries its source path and 1-based file line number (the
line numbering `cat -n` produces, header included), so each figure in the report
can be traced back to an exact row.

The stored `meets_recall_gate` column is NOT trusted: decision_log.md #15 records
that this CSV once carried gate/baseline columns its generating script did not
actually compute. The gate is recomputed here as
`labeled_recall >= baseline labeled_recall` and cross-checked against the stored
column; any disagreement is reported rather than silently resolved.

Writes results/regenerate_figures/sweep_effects.txt.
"""

from pathlib import Path
import csv
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

SWEEP_A = REPO_ROOT / "results" / "detector_tuning" / "sweep_results.csv"
SWEEP_B = REPO_ROOT / "results" / "detector_tuning" / "sweep_results_min_area_circ.csv"
OUT_PATH = REPO_ROOT / "results" / "regenerate_figures" / "sweep_effects.txt"

REL = lambda p: p.relative_to(REPO_ROOT).as_posix()  # noqa: E731


def load(path):
    """Rows as dicts with a `_line` field = 1-based line number in the file
    (header is line 1, so the first data row is line 2)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["_line"] = i + 2
    return rows


def as_float(rows, *fields):
    for r in rows:
        for fld in fields:
            r[fld] = float(r[fld])
    return rows


def as_bool(v):
    return str(v).strip().lower() == "true"


def find_baseline(rows, path):
    hits = [r for r in rows if as_bool(r["is_baseline"])]
    if len(hits) != 1:
        raise SystemExit("{}: expected exactly 1 is_baseline row, found {} (lines {})"
                         .format(REL(path), len(hits), [r["_line"] for r in hits]))
    return hits[0]


def check_gate_column(rows, baseline_recall, path, out):
    """Recompute the gate and compare with the stored column."""
    disagree = [r for r in rows
                if (r["labeled_recall"] >= baseline_recall) != as_bool(r["meets_recall_gate"])]
    if disagree:
        out.append("  !! stored meets_recall_gate disagrees with recomputed gate on "
                   "{} row(s): lines {}".format(len(disagree), [r["_line"] for r in disagree]))
        out.append("     Using the RECOMPUTED gate (labeled_recall >= baseline recall).")
    else:
        out.append("  Gate integrity check: stored meets_recall_gate matches the recomputed"
                   " gate on all {} rows.".format(len(rows)))


def cfg_a(r):
    return "stride={} diff_threshold={} open_kernel={}".format(
        r["stride"], r["diff_threshold"], r["open_kernel"])


def cfg_b(r):
    return "min_area={} min_circ={}".format(r["min_area"], r["min_circ"])


def loc(r, path):
    return "[{}:{}]".format(REL(path), r["_line"])


def main():
    out = []
    add = out.append

    for p in (SWEEP_A, SWEEP_B):
        if not p.is_file():
            raise SystemExit("NOT_FOUND: {} does not exist".format(REL(p)))

    add("SWEEP EFFECTS - detector parameter sweeps")
    add("=" * 78)
    add("")
    add("Sources (read-only):")
    add("  (a) {}".format(REL(SWEEP_A)))
    add("  (b) {}".format(REL(SWEEP_B)))
    add("Row locators are 1-based file line numbers; line 1 is the header.")
    add("")

    # ---------------------------------------------------------------- gate check
    for path in (SWEEP_A, SWEEP_B):
        with open(path, newline="") as f:
            header = f.readline().strip()
        if "labeled_recall" not in header.split(","):
            add("NOT_FOUND: {} has no labelled-recall column. Header: {}".format(
                REL(path), header))
            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUT_PATH.write_text("\n".join(out) + "\n")
            print("\n".join(out))
            return 1

    add("Labelled-recall column present in both CSVs (`labeled_recall`) - "
        "NOT_FOUND condition does not apply.")
    add("")

    # ================================================================ (a)
    rows_a = as_float(load(SWEEP_A), "avg_combined_rate", "labeled_recall")
    base_a = find_baseline(rows_a, SWEEP_A)
    base_recall_a = base_a["labeled_recall"]

    add("-" * 78)
    add("(a) STRIDE x DIFF_THRESHOLD x OPEN_KERNEL SWEEP")
    add("    {}".format(REL(SWEEP_A)))
    add("-" * 78)
    add("")
    add("Total configs evaluated: {}  (data rows, lines {}-{})".format(
        len(rows_a), rows_a[0]["_line"], rows_a[-1]["_line"]))
    add("")
    add("Baseline (is_baseline=True) {}".format(loc(base_a, SWEEP_A)))
    add("  config             : {}".format(cfg_a(base_a)))
    add("  avg_combined_rate  : {:.4f}".format(base_a["avg_combined_rate"]))
    add("  labeled_recall     : {:.4f}   <- the recall gate threshold".format(base_recall_a))
    add("")
    check_gate_column(rows_a, base_recall_a, SWEEP_A, out)
    add("")

    top_raw_a = max(rows_a, key=lambda r: r["avg_combined_rate"])
    passing_a = [r for r in rows_a if r["labeled_recall"] >= base_recall_a]
    winner_a = max(passing_a, key=lambda r: r["avg_combined_rate"])

    add("TOP CONFIG BY RAW avg_combined_rate (gate ignored) {}".format(loc(top_raw_a, SWEEP_A)))
    add("  config             : {}".format(cfg_a(top_raw_a)))
    add("  avg_combined_rate  : {:.4f}".format(top_raw_a["avg_combined_rate"]))
    add("  labeled_recall     : {:.4f}".format(top_raw_a["labeled_recall"]))
    add("  passes recall gate : {}".format(
        "YES" if top_raw_a["labeled_recall"] >= base_recall_a else "NO"))
    if top_raw_a["labeled_recall"] < base_recall_a:
        add("  -> recall is {:.4f} BELOW the {:.4f} baseline gate. Ranking on "
            "combined rate".format(base_recall_a - top_raw_a["labeled_recall"], base_recall_a))
        add("     alone is gameable: a config that fires on nearly every frame scores a")
        add("     high combined rate while its recall against labelled ground truth collapses.")
    add("")

    add("CONFIGS PASSING THE RECALL GATE (labeled_recall >= {:.4f})".format(base_recall_a))
    add("  {} of {} configs pass.".format(len(passing_a), len(rows_a)))
    add("  Passing rows: {}".format(", ".join(
        "{} ({})".format(r["_line"], cfg_a(r)) for r in sorted(passing_a, key=lambda r: r["_line"]))))
    add("")

    add("GATE-PASSING WINNER (highest avg_combined_rate among passing) {}".format(
        loc(winner_a, SWEEP_A)))
    add("  config             : {}".format(cfg_a(winner_a)))
    add("  avg_combined_rate  : {:.4f}".format(winner_a["avg_combined_rate"]))
    add("  labeled_recall     : {:.4f}".format(winner_a["labeled_recall"]))
    add("  vs baseline        : combined rate {:.4f} -> {:.4f} ({:.2f}x); "
        "recall {:.4f} -> {:.4f}".format(
            base_a["avg_combined_rate"], winner_a["avg_combined_rate"],
            winner_a["avg_combined_rate"] / base_a["avg_combined_rate"],
            base_recall_a, winner_a["labeled_recall"]))
    add("")

    # ================================================================ (b)
    rows_b = as_float(load(SWEEP_B), "avg_combined_rate", "labeled_recall")
    base_b = find_baseline(rows_b, SWEEP_B)
    base_recall_b = base_b["labeled_recall"]

    add("-" * 78)
    add("(b) MIN_AREA x MIN_CIRC SWEEP")
    add("    {}".format(REL(SWEEP_B)))
    add("-" * 78)
    add("")
    add("Total grid combinations: {}  (data rows, lines {}-{})".format(
        len(rows_b), rows_b[0]["_line"], rows_b[-1]["_line"]))
    add("")
    check_gate_column(rows_b, base_recall_b, SWEEP_B, out)
    add("")

    add("BASELINE (is_baseline=True) {}".format(loc(base_b, SWEEP_B)))
    add("  config             : {}".format(cfg_b(base_b)))
    add("  avg_combined_rate  : {:.4f}".format(base_b["avg_combined_rate"]))
    add("  labeled_recall     : {:.4f}   <- the recall gate threshold".format(base_recall_b))
    add("")

    # The adopted config is the one that became candidate_config.json: min_area=30,
    # min_circ=0.30 (decision_log.md, "prioritising recall over a small combined-rate
    # gap"). Located by value rather than by rank so the row is unambiguous.
    winner_b = next((r for r in rows_b
                     if r["min_area"] == "30" and r["min_circ"] == "0.3"), None)
    if winner_b is None:
        raise SystemExit("{}: no min_area=30, min_circ=0.3 row found".format(REL(SWEEP_B)))

    add("WINNING / ADOPTED CONFIG {}".format(loc(winner_b, SWEEP_B)))
    add("  config             : {}".format(cfg_b(winner_b)))
    add("  avg_combined_rate  : {:.4f}".format(winner_b["avg_combined_rate"]))
    add("  labeled_recall     : {:.4f}".format(winner_b["labeled_recall"]))
    add("  vs baseline        : combined rate {:.4f} -> {:.4f} ({:+.4f}); "
        "recall {:.4f} -> {:.4f} ({:+.4f})".format(
            base_b["avg_combined_rate"], winner_b["avg_combined_rate"],
            winner_b["avg_combined_rate"] - base_b["avg_combined_rate"],
            base_recall_b, winner_b["labeled_recall"],
            winner_b["labeled_recall"] - base_recall_b))
    add("")

    add("MIN_CIRC HELD CONSTANT ACROSS THE COMPARED PAIR")
    add("  baseline min_circ  : {}  {}".format(base_b["min_circ"], loc(base_b, SWEEP_B)))
    add("  winner   min_circ  : {}  {}".format(winner_b["min_circ"], loc(winner_b, SWEEP_B)))
    same = float(base_b["min_circ"]) == float(winner_b["min_circ"]) == 0.30
    add("  CONFIRMED: min_circ = 0.30 in both rows; the pair differs only in min_area "
        "({} -> {}).".format(base_b["min_area"], winner_b["min_area"])
        if same else
        "  NOT CONFIRMED: min_circ differs between the two rows or is not 0.30.")
    add("")

    failing_b = [r for r in rows_b if r["labeled_recall"] < base_recall_b]
    add("GRID COMBINATIONS FAILING THE RECALL GATE (labeled_recall < {:.4f})".format(
        base_recall_b))
    add("  {} of {} combinations fail.".format(len(failing_b), len(rows_b)))
    for r in sorted(failing_b, key=lambda r: r["_line"]):
        add("    {}  {}  avg_combined_rate={:.4f}  labeled_recall={:.4f}".format(
            loc(r, SWEEP_B), cfg_b(r), r["avg_combined_rate"], r["labeled_recall"]))
    add("")

    # Reported because the adopted config is NOT the grid's recall maximum, and the
    # decision log describes it as "the highest recall in the grid" - a report
    # quoting that wording would be wrong.
    max_recall_b = max(r["labeled_recall"] for r in rows_b)
    best_recall_rows = [r for r in rows_b if r["labeled_recall"] == max_recall_b]
    add("NOTE - highest labelled recall anywhere in the grid: {:.4f}".format(max_recall_b))
    for r in best_recall_rows:
        add("    {}  {}  avg_combined_rate={:.4f}".format(
            loc(r, SWEEP_B), cfg_b(r), r["avg_combined_rate"]))
    if max_recall_b > winner_b["labeled_recall"]:
        add("  The adopted config's recall ({:.4f}) is NOT the grid maximum ({:.4f}); "
            "the".format(winner_b["labeled_recall"], max_recall_b))
        add("  higher-recall rows sit at min_circ=0.35. The adopted row is the recall")
        add("  maximum only among min_circ<=0.30 rows.")
    add("")

    add("=" * 78)
    add("END")

    text = "\n".join(out) + "\n"
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text)
    print(text)
    print("Wrote {}".format(REL(OUT_PATH)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
