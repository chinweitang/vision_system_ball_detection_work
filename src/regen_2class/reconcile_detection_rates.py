"""Reconcile the reported detection rates for the final production config.

Read-only against every input. Reports, for ONE config only:
  (a) avg_combined_rate across all 163 flights
  (b) labelled recall and the point count it is computed over
  (c) which flights the recall is actually computed on
  (d) the exact config dict the numbers correspond to

Sources - NO sweep-grid CSV is used:
  results/detector_tuning/candidate_config_validated_results.csv   (per-flight rates)
  results/detector_tuning/history/results_history.csv              (provenance row)
  the per-flight *_labels.csv files                             (recall point count)

STOP conditions, all checked before anything is written:
  - fewer than 163 unique session-qualified flight rows
  - recall point count != 240
  - avg_combined_rate differs from 0.9667, or labelled recall from 0.9250,
    by more than 0.001

Output: results/regenerate_figures/detection_rates_reconciled.txt
"""
import csv
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATED_CSV = ROOT / "results/detector_tuning/candidate_config_validated_results.csv"
HISTORY_CSV = ROOT / "results/detector_tuning/history/results_history.csv"
CONFIG_JSON = ROOT / "results/detector_tuning/candidate_config.json"
OUT_TXT = ROOT / "results/regenerate_figures/detection_rates_reconciled.txt"

EXPECTED_COMBINED = 0.9667
EXPECTED_RECALL = 0.9250
TOLERANCE = 0.001
EXPECTED_POINTS = 240
EXPECTED_FLIGHTS = 163

# Replicated verbatim from 10_run_full_dataset.py so the recall population is
# resolved the same way the number was produced, not guessed at.
SESSIONS = ["2026_07_15_gym", "2026_07_21_gym"]
LABELED_FLIGHT_SUBPATHS = [
    "2 ball contacts ground before plane/flight_01",
    "flight_22",
]
CAMS = ["cam0", "cam1"]

_lines = []


def emit(s=""):
    _lines.append(s)
    print(s)


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_validated():
    with open(VALIDATED_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    flights = [r for r in rows if "/" in r["flight"]]
    summary = {r["flight"].split(" (")[0]: r for r in rows if "/" not in r["flight"]}
    return rows, flights, summary


def count_label_points():
    """Which flights the recall actually runs on, and how many points each gives.
    A directory whose relative path matches but which has no *_labels.csv
    contributes zero and is reported as such."""
    found = []
    for sess in SESSIONS:
        base = ROOT / "data" / sess / "ball_flights"
        for rel in LABELED_FLIGHT_SUBPATHS:
            fd = base / rel
            if not fd.is_dir():
                continue
            per_cam, n = {}, 0
            for cam in CAMS:
                p = fd / f"{fd.name}_{cam}_labels.csv"
                if p.is_file():
                    with open(p, newline="", encoding="utf-8") as f:
                        k = sum(1 for _ in csv.DictReader(f))
                    per_cam[cam] = k
                    n += k
                else:
                    per_cam[cam] = None
            found.append(dict(session=sess, rel=rel, points=n, per_cam=per_cam))
    return found


def parse_config(cfg_str):
    """key=value pairs -> dict; everything else kept verbatim as annotations."""
    d = {}
    for k, v in re.findall(r"(\w+)=([\w.]+)", cfg_str):
        d[k] = v
    annotations = [a.strip() for a in re.findall(r"\+\s*([^+\-]+)", cfg_str)]
    return d, annotations


def main():
    rows, flights, summary = read_validated()

    # ---- GATE 1: flight-row count -------------------------------------------
    unique = {r["flight"] for r in flights}
    if len(unique) < EXPECTED_FLIGHTS:
        stop(f"only {len(unique)} unique session-qualified flight rows in "
             f"{VALIDATED_CSV.name}, need >= {EXPECTED_FLIGHTS}")
    if len(unique) != len(flights):
        stop(f"{len(flights)} flight rows but only {len(unique)} unique - duplicates present")

    # ---- GATE 2: recall point count -----------------------------------------
    label_dirs = count_label_points()
    total_points = sum(d["points"] for d in label_dirs)
    if total_points != EXPECTED_POINTS:
        stop(f"recall point count is {total_points}, expected {EXPECTED_POINTS}")

    # ---- GATE 3: values ------------------------------------------------------
    stored_avg = float(summary["AVERAGE"]["combined_rate"])
    stored_recall = float(summary["LABELED_RECALL"]["combined_rate"])
    recomputed_avg = st.mean(float(r["combined_rate"]) for r in flights)
    for name, got, want in (("avg_combined_rate (stored)", stored_avg, EXPECTED_COMBINED),
                            ("avg_combined_rate (recomputed)", recomputed_avg, EXPECTED_COMBINED),
                            ("labelled recall (stored)", stored_recall, EXPECTED_RECALL)):
        if abs(got - want) > TOLERANCE:
            stop(f"{name} = {got:.6f}, expected {want} +/- {TOLERANCE} "
                 f"(difference {abs(got-want):.6f}) - reporting, not reconciling")

    cfg_str = summary["CONFIG"]["combined_rate"]
    cfg, annotations = parse_config(cfg_str)
    hist = list(csv.DictReader(open(HISTORY_CSV, newline="", encoding="utf-8")))
    prod = [h for h in hist if h["artifacts"].startswith(
        "results/detector_tuning/candidate_config_validated_results.csv")
        and h["n_flights"] == str(EXPECTED_FLIGHTS)]

    # ---------------------------------------------------------------- report
    emit("=" * 78)
    emit("DETECTION RATES, RECONCILED - FINAL PRODUCTION CONFIG")
    emit("=" * 78)
    emit(f"Source (per-flight rates) : {VALIDATED_CSV.relative_to(ROOT)}")
    emit(f"Source (provenance)       : {HISTORY_CSV.relative_to(ROOT)}")
    emit(f"Source (recall points)    : per-flight *_labels.csv on disk")
    emit("No sweep-grid CSV was read.")
    emit()
    emit("GATES: flight rows >= 163 PASS | recall points == 240 PASS | "
         "values within +/-0.001 PASS")
    emit()

    emit("-" * 78)
    emit("(a) avg_combined_rate across all 163 flights")
    emit("-" * 78)
    emit(f"  stored in CSV        : {stored_avg:.4f}")
    emit(f"  recomputed from rows : {recomputed_avg:.6f}   "
         f"(difference {abs(recomputed_avg - stored_avg):.2e})")
    emit(f"  flights contributing : {len(flights)}")
    by_sess = {}
    for r in flights:
        by_sess[r["flight"].split("/")[0]] = by_sess.get(r["flight"].split("/")[0], 0) + 1
    emit(f"  per session          : " + ", ".join(f"{k} {v}" for k, v in sorted(by_sess.items())))
    emit("  definition           : per-flight co-detected / co-processable frames,")
    emit("                         then an UNWEIGHTED mean across flights (each flight")
    emit("                         counts equally regardless of frame count).")
    emit()

    emit("-" * 78)
    emit("(b) labelled recall and its point count")
    emit("-" * 78)
    emit(f"  stored in CSV        : {stored_recall:.4f}")
    emit(f"  point count          : {total_points}  (counted from the label CSVs on disk)")
    if prod:
        emit(f"  history states       : {prod[-1]['labeled_recall']} on "
             f"\"{prod[-1]['labeled_recall_flights']}\"")
    emit("  definition           : a labelled point counts as a hit if the kept detection")
    emit("                         for that (cam, frame) lies within the label's own")
    emit("                         tolerance (diameter_px / 2, else 20 px fallback).")
    emit()

    emit("-" * 78)
    emit("(c) which flights the recall is computed on")
    emit("-" * 78)
    emit("  Resolved by replicating 10_run_full_dataset.py's matching rule: each entry")
    emit("  of LABELED_FLIGHT_SUBPATHS is matched against BOTH sessions.")
    emit()
    for d in label_dirs:
        cams = ", ".join(f"{c}={'MISSING' if v is None else v}" for c, v in d["per_cam"].items())
        tag = "" if d["points"] else "   <- matches the pattern but has NO label files"
        emit(f"    {d['session']}/{d['rel']}")
        emit(f"        points={d['points']:<5d} ({cams}){tag}")
    emit()
    contributing = [d for d in label_dirs if d["points"]]
    emit(f"  contributing flights : {len(contributing)}")
    for d in contributing:
        emit(f"      {d['session']}/{d['rel']}  ({d['points']} points)")
    emit()
    emit("  NOTE: the CSV row is labelled \"LABELED_RECALL (flight_01 + flight_22)\",")
    emit("  which is NOT session-qualified. flight_22 exists under BOTH sessions and the")
    emit("  matching rule tries both, so the label alone does not identify the population.")
    emit("  Both contributing flights are in 2026_07_15_gym.")
    emit()

    emit("-" * 78)
    emit("(d) the exact config these numbers correspond to")
    emit("-" * 78)
    emit("  parsed config dict:")
    for k, v in cfg.items():
        emit(f"      {k:<12s} = {v}")
    emit("  annotations:")
    for a in annotations:
        emit(f"      {a}")
    emit()
    emit(f"  verbatim CONFIG cell:")
    emit(f"      {cfg_str}")
    if prod:
        emit()
        emit(f"  history row  : {prod[-1]['date']}  |  {prod[-1]['stage']}")
    emit()

    emit("=" * 78)
    emit("DISCREPANCY - REPORTED, NOT RECONCILED")
    emit("=" * 78)
    rect = [h for h in hist if "rect close kernel" in h["stage"].lower()]
    if rect:
        r = rect[-1]
        emit(f"  A LATER full-dataset run exists: {r['date']}")
        emit(f"      {r['stage']}")
        emit(f"      avg_combined_rate {r['avg_combined_rate']}   "
             f"labelled recall {r['labeled_recall']}   n_flights {r['n_flights']}")
        emit(f"      artifact: results/detector_tuning/candidate_config_rect_close_results.csv")
        emit()
        emit("  It differs ONLY in the close-kernel SHAPE (MORPH_ELLIPSE -> MORPH_RECT).")
        emit("  candidate_config.json records close_k=30 but carries no shape field, so the")
        emit("  two configs are indistinguishable from that file alone.")
        emit()
        emit("  This matters because every Pi real-time script "
             "(prediction_pipeline_sweep_pi.py,")
        emit("  two_axis_fit_window_sweep_pi.py, parallel_detect_checkpoint_pi.py,")
        emit("  benchmark_detection_rect_total_pi.py) calls a local compute_mask_rect_close")
        emit("  using MORPH_RECT - i.e. the RECT variant, whose validated rates are")
        emit(f"  {r['avg_combined_rate']} / {r['labeled_recall']}, not "
             f"{EXPECTED_COMBINED} / {EXPECTED_RECALL}.")
        emit()
        emit("  Which of the two is 'the final production config' is not resolvable from")
        emit("  these files: the 2026-07-25 ellipse row is annotated \"(current)\" but the")
        emit("  2026-08-03 rect row is later. Reported for a human decision.")
    emit()
    emit("  Second, smaller: 2026_07_21_gym/flight_22 matches the recall subpath but has")
    emit("  no label CSVs, so it silently contributes 0 points. If labels were ever added")
    emit("  there, the recall population would change without the CSV label text changing.")
    emit("=" * 78)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_TXT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
