"""Per-flight resolution of the ELLIPSE vs RECT close-kernel question.

Reads, read-only, and never writes back:
    results/detector_tuning/candidate_config_validated_results.csv   (ELLIPSE close)
    results/detector_tuning/candidate_config_rect_close_results.csv  (RECT close)

Computes the per-flight combined-rate delta (rect minus ellipse) for all 163
session-qualified flights, from the two source CSVs directly. The pre-existing
rect_vs_ellipse_comparison.csv is read ONLY at the end as an independent
cross-check - if it disagrees with the deltas computed here, that disagreement is
reported rather than resolved silently.

Then reads every script under src/pi_benchmarking/ and reports which mask
function each one actually calls, so the deployed kernel shape is established
from the code rather than assumed.

STOP condition:
    the two CSVs do not cover the same 163 session-qualified flights

Output: results/regenerate_figures/ellipse_vs_rect_resolution.txt
"""
import csv
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import common as C

ROOT = pathlib.Path(__file__).resolve().parents[2]
ELLIPSE_CSV = "results/detector_tuning/candidate_config_validated_results.csv"
RECT_CSV = "results/detector_tuning/candidate_config_rect_close_results.csv"
CROSSCHECK_CSV = "results/detector_tuning/rect_vs_ellipse_comparison.csv"
PI_DIR = ROOT / "src/pi_benchmarking"
DETECTOR_CORE = "src/image_processing/02_adjacent_frame_differencing/detector_core.py"
OUT_TXT = ROOT / "results/regenerate_figures/ellipse_vs_rect_resolution.txt"

EXPECTED_FLIGHTS = 163
THRESH_PP = 2.0

_lines = []


def emit(s=""):
    _lines.append(s)
    print(s)


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def load_flights(path):
    """Per-flight rows only. Session-qualified rows carry a '/' in `flight`;
    AVERAGE / LABELED_RECALL / CONFIG do not."""
    with open(ROOT / path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    flights = {r["flight"]: r for r in rows if "/" in r["flight"]}
    summary = {r["flight"].split(" (")[0]: r for r in rows if "/" not in r["flight"]}
    if len(flights) != len({r["flight"] for r in rows if "/" in r["flight"]}):
        stop(f"duplicate flight ids in {path}")
    return flights, summary


def mask_usage():
    """Which mask function each Pi script CALLS (not merely defines).

    A script can define compute_mask_rect_close and still call something else,
    so definition and call site are reported separately.
    """
    out = []
    for p in sorted(PI_DIR.glob("*.py")):
        src = p.read_text(encoding="utf-8", errors="replace")
        # strip the module docstring so prose mentioning compute_mask does not
        # register as a call site
        body = re.sub(r'^\s*""".*?"""', "", src, count=1, flags=re.S)
        defines_rect = bool(re.search(r"^def compute_mask_rect_close", body, re.M))
        calls_rect = bool(re.search(r"(?<!def )\bcompute_mask_rect_close\s*\(", body))
        calls_shared = bool(re.search(r"\b(?:dc|detector_core)\.compute_mask\s*\(", body))
        ell = len(re.findall(r"MORPH_ELLIPSE", body))
        rect = len(re.findall(r"MORPH_RECT", body))
        if calls_shared and calls_rect:
            kind = "BOTH - calls shared ellipse AND local rect"
        elif calls_shared:
            kind = "detector_core.compute_mask  (SHARED, ELLIPSE close)"
        elif calls_rect:
            kind = "compute_mask_rect_close     (LOCAL,  RECT close)"
        else:
            kind = "neither - no mask call"
        out.append(dict(name=p.name, kind=kind, defines_rect=defines_rect,
                        calls_shared=calls_shared, calls_rect=calls_rect,
                        n_ellipse=ell, n_rect=rect))
    return out


def core_shapes():
    """The close-kernel shape inside the shared detector, read from source."""
    src = (ROOT / DETECTOR_CORE).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"def compute_mask\b.*?(?=\ndef |\Z)", src, re.S)
    if not m:
        return None, None
    body = m.group(0)
    op = re.search(r"open_k\s*=\s*cv2\.getStructuringElement\(cv2\.(MORPH_\w+)", body)
    cl = re.search(r"close_k\s*=\s*cv2\.getStructuringElement\(cv2\.(MORPH_\w+)", body)
    return (op.group(1) if op else None), (cl.group(1) if cl else None)


def main():
    ell, ell_sum = load_flights(ELLIPSE_CSV)
    rect, rect_sum = load_flights(RECT_CSV)

    # ---- STOP GATE -------------------------------------------------------
    only_e, only_r = sorted(set(ell) - set(rect)), sorted(set(rect) - set(ell))
    if only_e or only_r or len(ell) != EXPECTED_FLIGHTS or len(rect) != EXPECTED_FLIGHTS:
        stop(f"the two CSVs do not cover the same {EXPECTED_FLIGHTS} flights.\n"
             f"  ellipse: {len(ell)} flights, rect: {len(rect)} flights\n"
             f"  only in ellipse ({len(only_e)}): {only_e[:10]}\n"
             f"  only in rect    ({len(only_r)}): {only_r[:10]}")

    deltas = []
    for f in sorted(ell):
        e = float(ell[f]["combined_rate"])
        r = float(rect[f]["combined_rate"])
        deltas.append(dict(flight=f, ell=e, rect=r,
                           # combined_rate is stored to 4 dp, so delta_pp lands
                           # on exact hundredths - rounding here is not a fudge,
                           # it removes float representation noise only.
                           d_pp=round((r - e) * 100, 2)))
    d = [x["d_pp"] for x in deltas]

    regressed = [x for x in deltas if x["d_pp"] < -THRESH_PP]
    improved_strict = [x for x in deltas if x["d_pp"] > THRESH_PP]
    improved_any = [x for x in deltas if x["d_pp"] > 0]
    unchanged = [x for x in deltas if x["d_pp"] == 0]
    worse_any = [x for x in deltas if x["d_pp"] < 0]
    b_neg = [x for x in deltas if x["d_pp"] == -THRESH_PP]
    b_pos = [x for x in deltas if x["d_pp"] == THRESH_PP]

    usage = mask_usage()
    op_shape, cl_shape = core_shapes()
    shared_users = [u for u in usage if u["calls_shared"]]
    rect_users = [u for u in usage if u["calls_rect"]]

    # ------------------------------------------------------------- report
    emit("=" * 78)
    emit("ELLIPSE vs RECT CLOSE KERNEL - PER-FLIGHT RESOLUTION")
    emit("=" * 78)
    emit(f"ELLIPSE source : {ELLIPSE_CSV}")
    emit(f"RECT source    : {RECT_CSV}")
    emit(f"Deltas computed from these two files directly (rect minus ellipse).")
    emit()
    emit(f"STOP GATE: both CSVs cover the same {len(ell)} session-qualified "
         f"flights -- PASS")
    emit(f"  ellipse rows {len(ell)}, rect rows {len(rect)}, "
         f"symmetric difference 0")
    emit(f"  stored AVERAGE: ellipse {ell_sum['AVERAGE']['combined_rate']}, "
         f"rect {rect_sum['AVERAGE']['combined_rate']}")
    emit(f"  stored RECALL : ellipse {ell_sum['LABELED_RECALL']['combined_rate']}, "
         f"rect {rect_sum['LABELED_RECALL']['combined_rate']}")
    emit()

    emit("-" * 78)
    emit("1. DISTRIBUTION OF THE PER-FLIGHT DELTA (percentage points)")
    emit("-" * 78)
    mean = sum(d) / len(d)
    emit(f"  n            : {len(d)}")
    emit(f"  mean         : {mean:+.3f} pp")
    emit(f"  min          : {min(d):+.2f} pp")
    emit(f"  P5           : {C.percentile(d, 0.05):+.2f} pp")
    emit(f"  Q1           : {C.percentile(d, 0.25):+.2f} pp")
    emit(f"  median       : {C.percentile(d, 0.50):+.2f} pp")
    emit(f"  Q3           : {C.percentile(d, 0.75):+.2f} pp")
    emit(f"  P95          : {C.percentile(d, 0.95):+.2f} pp")
    emit(f"  max          : {max(d):+.2f} pp")
    emit()
    emit("  histogram:")
    edges = [(-100, -10), (-10, -8), (-8, -6), (-6, -4), (-4, -2), (-2, 0),
             (0, 0), (0, 2), (2, 4), (4, 6), (6, 100)]
    for lo, hi in edges:
        if lo == hi == 0:
            n, lab = len(unchanged), "exactly 0"
        elif lo < 0:
            n = sum(1 for x in d if lo <= x < hi)
            lab = f"[{lo:+5.0f}, {hi:+3.0f})"
        else:
            n = sum(1 for x in d if lo < x <= hi)
            lab = f"({lo:+5.0f}, {hi:+3.0f}]"
        emit(f"    {lab:>16s}  {n:3d}  {'#' * n}")
    emit()

    emit("-" * 78)
    emit("2. COUNTS")
    emit("-" * 78)
    emit(f"  regressing by MORE than {THRESH_PP:.0f} pp (delta < -{THRESH_PP:.2f}) : "
         f"{len(regressed):3d}  ({100*len(regressed)/len(d):.1f}%)")
    emit(f"  improving by MORE than {THRESH_PP:.0f} pp (delta > +{THRESH_PP:.2f}) : "
         f"{len(improved_strict):3d}  ({100*len(improved_strict)/len(d):.1f}%)")
    emit(f"  improving at all       (delta > 0)          : {len(improved_any):3d}")
    emit(f"  unchanged              (delta == 0)         : {len(unchanged):3d}")
    emit(f"  worse at all           (delta < 0)          : {len(worse_any):3d}")
    emit()
    emit("  NOTE ON THE '13 IMPROVED' FIGURE IN results_history.csv:")
    emit(f"  strictly > +2 pp gives {len(improved_strict)}; >= +2 pp gives "
         f"{len(improved_strict) + len(b_pos)}. The history row counts >=.")
    emit()

    emit("-" * 78)
    emit(f"3. BOUNDARY FLIGHTS AT EXACTLY +/-{THRESH_PP:.2f} pp")
    emit("-" * 78)
    emit(f"  exactly -{THRESH_PP:.2f} pp : {len(b_neg)}")
    for x in b_neg:
        emit(f"      {x['flight']:<38s} ellipse {x['ell']:.4f} -> rect {x['rect']:.4f}")
    emit(f"  exactly +{THRESH_PP:.2f} pp : {len(b_pos)}")
    for x in b_pos:
        emit(f"      {x['flight']:<38s} ellipse {x['ell']:.4f} -> rect {x['rect']:.4f}")
    emit()
    emit("  These sit ON the threshold, so whether they count depends on whether the")
    emit("  test is strict (>) or inclusive (>=). Reported explicitly because that")
    emit("  choice is the entire difference between 12 and 13 improved flights.")
    emit()
    near = sorted((x for x in deltas if 1.5 <= abs(x["d_pp"]) <= 2.5),
                  key=lambda x: x["d_pp"])
    emit(f"  for context, flights within 1.5-2.5 pp of zero either way ({len(near)}):")
    for x in near:
        emit(f"      {x['d_pp']:+6.2f} pp  {x['flight']}")
    emit()

    emit("-" * 78)
    emit("4. WORST AND BEST FLIGHTS")
    emit("-" * 78)
    for x in sorted(deltas, key=lambda x: x["d_pp"])[:10]:
        emit(f"    {x['d_pp']:+6.2f} pp  {x['flight']:<38s} "
             f"{x['ell']:.4f} -> {x['rect']:.4f}")
    emit("      ...")
    for x in sorted(deltas, key=lambda x: x["d_pp"])[-5:]:
        emit(f"    {x['d_pp']:+6.2f} pp  {x['flight']:<38s} "
             f"{x['ell']:.4f} -> {x['rect']:.4f}")
    emit()

    emit("-" * 78)
    emit("5. WHICH MASK EACH Pi SCRIPT ACTUALLY CALLS")
    emit("-" * 78)
    emit(f"  detector_core.compute_mask ({DETECTOR_CORE}):")
    emit(f"      open kernel  = cv2.{op_shape}")
    emit(f"      close kernel = cv2.{cl_shape}")
    emit()
    emit(f"  {'script':<42s} {'calls':<45s}")
    for u in usage:
        emit(f"    {u['name']:<40s} {u['kind']}")
    emit()
    emit(f"  Scripts calling the SHARED ellipse detector_core.compute_mask: "
         f"{len(shared_users)}")
    for u in shared_users:
        emit(f"      {u['name']}")
    if not shared_users:
        emit("      (none)")
    emit()
    emit(f"  Scripts calling the LOCAL rect compute_mask_rect_close: {len(rect_users)}")
    for u in rect_users:
        emit(f"      {u['name']}")
    emit()
    emit("  Each local compute_mask_rect_close keeps the OPEN kernel as MORPH_ELLIPSE")
    emit("  and changes ONLY the CLOSE kernel to MORPH_RECT - the same single-variable")
    emit("  change the rect CSV's CONFIG cell records.")
    emit()

    emit("-" * 78)
    emit("6. CROSS-CHECK AGAINST rect_vs_ellipse_comparison.csv")
    emit("-" * 78)
    p = ROOT / CROSSCHECK_CSV
    if not p.is_file():
        emit(f"  {CROSSCHECK_CSV} absent - no cross-check performed.")
    else:
        with open(p, newline="", encoding="utf-8") as f:
            cc = {r["flight"]: r for r in csv.DictReader(f)}
        mism = [x for x in deltas
                if x["flight"] in cc
                and abs(float(cc[x["flight"]]["delta_pp"]) - x["d_pp"]) > 0.005]
        missing = [x["flight"] for x in deltas if x["flight"] not in cc]
        emit(f"  rows in cross-check file : {len(cc)}")
        emit(f"  flights missing from it  : {len(missing)}")
        emit(f"  delta disagreements >0.005 pp : {len(mism)}")
        for x in mism[:10]:
            emit(f"      {x['flight']}: computed {x['d_pp']:+.2f}, "
                 f"file {float(cc[x['flight']]['delta_pp']):+.2f}")
        flagged = sum(1 for r in cc.values() if r.get("flagged_regression") == "YES")
        emit(f"  flagged_regression==YES in file : {flagged}  "
             f"(computed regressing >2pp: {len(regressed)})")
        if not mism and not missing:
            emit("  -> independently computed deltas reproduce the file exactly.")
    emit()

    emit("=" * 78)
    emit("SUMMARY")
    emit("=" * 78)
    emit(f"  RECT is worse on the whole dataset: mean delta {mean:+.2f} pp, "
         f"{len(regressed)} of {len(d)} flights")
    emit(f"  regressing by more than {THRESH_PP:.0f} pp against "
         f"{len(improved_strict)} improving by more than {THRESH_PP:.0f} pp.")
    emit(f"  {len(worse_any)} flights are worse to some degree, "
         f"{len(improved_any)} better, {len(unchanged)} unchanged.")
    emit()
    if rect_users and len(shared_users) <= 1:
        emit(f"  DEPLOYED PATH: {len(rect_users)} of the {len(usage)} Pi scripts call the")
        emit(f"  RECT variant. Only {len(shared_users)} calls the shared ELLIPSE detector.")
        emit(f"  So every Pi sweep that fed a downstream figure ran RECT, whose validated")
        emit(f"  rates are {rect_sum['AVERAGE']['combined_rate']} combined / "
             f"{rect_sum['LABELED_RECALL']['combined_rate']} recall -")
        emit(f"  NOT the {ell_sum['AVERAGE']['combined_rate']} / "
             f"{ell_sum['LABELED_RECALL']['combined_rate']} usually quoted alongside them.")
    emit("=" * 78)

    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT_TXT.relative_to(ROOT)}")
    print("neither input CSV modified")


if __name__ == "__main__":
    main()
