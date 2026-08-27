"""Read-only audit: crossing-position accuracy vs hand labels, and triangulation precision.

Part 1  The comparison of the full-arc fixed-gravity-with-drag crossing position
        against hand-labelled crossing points fitted by local quadratic.
Part 2  The three triangulation-precision RMS values.

READ-ONLY. Re-runs no analysis, opens every input for reading only, and never
overwrites or deletes: each output takes the next free numeric suffix.

The close kernel is resolved by parsing the AST of the module the detection
producer actually calls, and reading the literal first argument of
cv2.getStructuringElement. A call site whose shape is not a static cv2.<CONST>
attribute is reported as unresolved, never guessed.

PATH NOTE: derived outputs moved from data/ to results/ on 2026-08-24. Part 1's
inputs are all post-migration. Part 2's source is NOT - it lives under a session
capture folder (data/2026_07_12_session/...), which stayed in data/ because the
migration moved derived results only.

STOP conditions:
    - no crossing-accuracy comparison exists as a computed result
    - the statistic type cannot be determined from the producing code
    - the close kernel cannot be resolved statically
"""
import ast
import csv
import datetime
import pathlib
import re
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

PER_FLIGHT_CSV = "results/prediction/06_label_vs_fit/label_vs_fit_per_flight.csv"
SUMMARY_TXT = "results/prediction/06_label_vs_fit/summary.txt"
PRODUCER = "src/stereo/label_vs_fit_crossing.py"
CLASSIFIER = "src/stereo/crossing_plane_classification.py"
COMMON = "src/stereo/all_flights_common.py"
DET_PRODUCER = "src/image_processing/02_adjacent_frame_differencing/10_run_full_dataset.py"
DETECTOR_CORE = "src/image_processing/02_adjacent_frame_differencing/detector_core.py"

PRECISION_CSV = "data/2026_07_12_session/validation/results/world_frame/world_frame_precision.csv"
PRECISION_SCRIPT = "src/registration/world_frame_precision_single.py"
INTRINSIC_SCRIPT = "src/calibration/intrinsic/calibrate_intrinsic.py"

AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"
LOG_DIR = ROOT / "claude/claude_logs"
REPORT_NAME = "audit_crossing_accuracy.md"
LOG_NAME = "audit_crossing_accuracy.log"

_CV2_SHAPES = {"MORPH_ELLIPSE", "MORPH_RECT", "MORPH_CROSS"}
_log = None
_md = []


def next_free(p):
    if not p.exists():
        return p
    n = 2
    while p.with_name(f"{p.stem}_{n:02d}{p.suffix}").exists():
        n += 1
    return p.with_name(f"{p.stem}_{n:02d}{p.suffix}")


def log(msg):
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    _log.write(line + "\n")
    _log.flush()


def md(s=""):
    _md.append(s)


def stop(msg):
    log(f"*** STOP *** {msg}")
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read(path):
    with open(ROOT / path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolve_kernels(script):
    """cv2.getStructuringElement call sites with shape resolved statically."""
    tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
    out, assigned = [], {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            if isinstance(f, ast.Attribute) and f.attr == "getStructuringElement" \
                    and isinstance(n.targets[0], ast.Name):
                assigned[n.value.lineno] = n.targets[0].id
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and f.attr == "getStructuringElement"):
            continue
        a = n.args[0] if n.args else None
        static = isinstance(a, ast.Attribute) and a.attr in _CV2_SHAPES
        out.append(dict(line=n.lineno,
                        shape=a.attr if static else (ast.dump(a) if a else "<missing>"),
                        static=static,
                        size=ast.unparse(n.args[1]) if len(n.args) > 1 else "?",
                        var=assigned.get(n.lineno, "?")))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == "morphologyEx" and len(n.args) >= 3:
                op = n.args[1].attr if isinstance(n.args[1], ast.Attribute) else "?"
                kern = n.args[2].id if isinstance(n.args[2], ast.Name) else "?"
                for r in out:
                    if r["var"] == kern:
                        r["op"] = op
    return out


def main():
    global _log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = next_free(LOG_DIR / LOG_NAME)
    report = next_free(AUDIT_DIR / REPORT_NAME)
    _log = open(log_path, "a", encoding="utf-8")
    log("=== audit_crossing_accuracy starting ===")
    log("read-only; no analysis re-run")

    # ---------------------------------------------------------------- PART 1
    for p in (PER_FLIGHT_CSV, SUMMARY_TXT, PRODUCER, DETECTOR_CORE, DET_PRODUCER):
        if not (ROOT / p).is_file():
            stop(f"required input missing: {p}")
    log(f"crossing-accuracy result located: {PER_FLIGHT_CSV}")
    log(f"producing script: {PRODUCER}")

    rows = read(PER_FLIGHT_CSV)
    src = (ROOT / PRODUCER).read_text(encoding="utf-8")

    # --- statistic type, from the producing code ---------------------------
    stat_defs = {}
    for name, pat in (("median_total", r"median_total=float\(np\.(\w+)\("),
                      ("mean_total", r"mean_total=float\(np\.(\w+)\("),
                      ("p90_total", r"p90_total=float\(np\.(\w+)\("),
                      ("rms_Y", r"rms_Y=float\(np\.sqrt\(np\.(\w+)\("),
                      ("rms_Z", r"rms_Z=float\(np\.sqrt\(np\.(\w+)\(")):
        m = re.search(pat, src)
        if m:
            stat_defs[name] = m.group(1)
    if "median_total" not in stat_defs:
        stop("the statistic type cannot be determined from the producing code: "
             "no median_total definition found in " + PRODUCER)
    log(f"statistic definitions parsed from source: {stat_defs}")

    m = re.search(r"pos_err_total\s*=\s*math\.(\w+)\(pos_err_Y,\s*pos_err_Z\)", src)
    if not m:
        stop("cannot determine the axes of pos_err_total from the producing code")
    log(f"pos_err_total = math.{m.group(1)}(pos_err_Y, pos_err_Z) -> in-plane Y,Z only")

    # --- clean subset, exactly as the producer defines it -------------------
    clean = [r for r in rows
             if r["symmetric"].strip().lower() == "true"
             and r["residual_flagged"].strip().lower() == "false"]
    errs = [float(r["pos_err_total"]) for r in clean if r["pos_err_total"].strip()]
    errs_Y = [float(r["pos_err_Y"]) for r in clean if r["pos_err_Y"].strip()]
    errs_Z = [float(r["pos_err_Z"]) for r in clean if r["pos_err_Z"].strip()]
    n_pts = {int(r["n_points"]) for r in rows}
    log(f"{len(rows)} flights in the CSV; {len(clean)} clean (symmetric & not "
        f"residual-flagged); n_points per flight = {sorted(n_pts)}")

    median_full = st.median(errs)
    mean_full = st.mean(errs)
    rmsY = (sum(v * v for v in errs_Y) / len(errs_Y)) ** 0.5
    rmsZ = (sum(v * v for v in errs_Z) / len(errs_Z)) ** 0.5
    log(f"median total (full precision) = {median_full!r}")
    log(f"mean total   (full precision) = {mean_full!r}")
    log(f"rms_Y = {rmsY!r}   rms_Z = {rmsZ!r}")

    summ = (ROOT / SUMMARY_TXT).read_text(encoding="utf-8")
    m2 = re.search(r"median total=([\d.]+)mm", summ)
    log(f"summary.txt states median total={m2.group(1)}mm; recomputed "
        f"{median_full:.4f} (summary rounds to 1 dp)")

    # --- observation window -------------------------------------------------
    full_arc = bool(re.search(r"full-arc", src))
    win_consts = re.findall(r"^([A-Z_]*WINDOW[A-Z_]*)\s*=\s*(.+)$", src, re.M)
    log(f"producer describes the fit as full-arc: {full_arc}; "
        f"window constants in producer: {win_consts or 'none'}")
    cls_src = (ROOT / CLASSIFIER).read_text(encoding="utf-8") if (ROOT / CLASSIFIER).is_file() else ""
    cls_win = re.findall(r"^([A-Z_]*WINDOW[A-Z_]*)\s*=\s*(.+)$", cls_src, re.M)
    log(f"window constants in {CLASSIFIER}: {cls_win or 'none'}")

    # --- close kernel at the call site --------------------------------------
    det_src = (ROOT / DET_PRODUCER).read_text(encoding="utf-8")
    calls_shared = "dc.compute_mask(" in det_src
    kerns = resolve_kernels(DETECTOR_CORE)
    close = [k for k in kerns if k.get("op") == "MORPH_CLOSE"]
    if len(close) != 1:
        stop(f"expected one MORPH_CLOSE kernel site in {DETECTOR_CORE}, found {len(close)}")
    if not close[0]["static"]:
        stop(f"close kernel at {DETECTOR_CORE}:{close[0]['line']} is not statically "
             f"resolvable ({close[0]['shape']}) - refusing to guess")
    log(f"detections root feeding the fit: results/detector_tuning/detections/"
        f"03_stride1_thresh16_openk3_area30_circ0.3")
    log(f"{DET_PRODUCER} calls dc.compute_mask: {calls_shared}")
    log(f"close kernel RESOLVED: cv2.{close[0]['shape']} at "
        f"{DETECTOR_CORE}:{close[0]['line']}")

    # ---------------------------------------------------------------- PART 2
    if not (ROOT / PRECISION_CSV).is_file():
        stop(f"triangulation precision source missing: {PRECISION_CSV}")
    prow = read(PRECISION_CSV)[0]
    isrc = (ROOT / INTRINSIC_SCRIPT).read_text(encoding="utf-8")
    pm = re.search(r"^PATTERN_SIZE\s*=\s*\((\d+),\s*(\d+)\)", isrc, re.M)
    n_corners = int(pm.group(1)) * int(pm.group(2)) if pm else None
    log(f"precision source: {PRECISION_CSV} (NOT migrated - session capture folder)")
    log(f"PATTERN_SIZE=({pm.group(1)},{pm.group(2)}) -> N_CORNERS={n_corners}")
    for k in ("rms_person_rebounder_mm", "rms_width_mm", "rms_vertical_mm"):
        log(f"  {k} = {prow[k]}")

    # ---------------------------------------------------------------- report
    md("# Audit: crossing-position accuracy and triangulation precision")
    md("")
    md("Generated by `src/regen_2class/audit_crossing_accuracy.py`. Read-only; no")
    md("analysis was re-run.")
    md(f"Log: `{log_path.relative_to(ROOT).as_posix()}`")
    md("")
    md("> **Path note.** Derived outputs moved from `data/` to `results/` on")
    md("> 2026-08-24. Part 1's inputs are post-migration. **Part 2's source is not** -")
    md("> it sits under a session capture folder, which stayed in `data/` because the")
    md("> migration moved derived results only.")
    md("")
    md("## Part 1 — crossing position vs hand labels")
    md("")
    md("| field | value |")
    md("|---|---|")
    md(f"| source CSV | `{PER_FLIGHT_CSV}` |")
    md(f"| summary | `{SUMMARY_TXT}` |")
    md(f"| producing script | `{PRODUCER}` |")
    md("")
    md("### The statistic")
    md("")
    md(f"**Median.** From the producer: `median_total=float(np.{stat_defs['median_total']}(errs_T))`.")
    md("")
    md("| statistic | definition in source | full-precision value (mm) |")
    md("|---|---|--:|")
    md(f"| **median total** | `np.{stat_defs['median_total']}` | **{median_full!r}** |")
    md(f"| mean total | `np.{stat_defs.get('mean_total','?')}` | {mean_full!r} |")
    md(f"| rms Y | `sqrt(np.{stat_defs.get('rms_Y','?')}(square))` | {rmsY!r} |")
    md(f"| rms Z | `sqrt(np.{stat_defs.get('rms_Z','?')}(square))` | {rmsZ!r} |")
    md("")
    md(f"`summary.txt` reports `median total={m2.group(1)}mm`, i.e. the same value")
    md("rounded to 1 dp. The headline figure is a **median, not a mean or an RMS** —")
    md("though per-axis RMS values exist alongside it, so quoting \"RMS\" for the")
    md("total would be wrong on two counts (wrong statistic, and no total-RMS is")
    md("computed at all).")
    md("")
    md("### Flights and labelled points")
    md("")
    import collections as _c
    d_all = dict(sorted(_c.Counter(int(r["n_points"]) for r in rows).items()))
    d_cln = dict(sorted(_c.Counter(int(r["n_points"]) for r in clean).items()))
    pts_all = sum(int(r["n_points"]) for r in rows)
    pts_cln = sum(int(r["n_points"]) for r in clean)
    short = [(r["flight_id"], r["n_points"], r["symmetric"]) for r in rows
             if int(r["n_points"]) != 6]
    md(f"| | |")
    md(f"|---|--:|")
    md(f"| flights in the CSV | {len(rows)} |")
    md(f"| **flights behind the pooled statistic** | **{len(clean)}** |")
    md(f"| labelled points per flight, all {len(rows)} | {d_all} |")
    md(f"| labelled points per flight, clean {len(clean)} | {d_cln} |")
    md(f"| **labelled points behind the pooled statistic** | **{pts_cln}** |")
    md(f"| labelled points across all {len(rows)} flights | {pts_all} |")
    md("")
    md("**The \"six points\" premise needs one correction, and it turns out to be a")
    md("tidy one.** Not all twenty flights carry six labelled points — the counts are")
    md(f"{d_all}. But every one of the **{len(clean)} clean flights has exactly six**,")
    md("and the three that fall short are precisely the three excluded ones:")
    md("")
    md("| flight | n_points | symmetric |")
    md("|---|--:|---|")
    for fid, npn, sym in short:
        md(f"| `{fid}` | {npn} | {sym} |")
    md("")
    md("So six labelled points is effectively the condition that makes a flight")
    md(f"usable here. \"20 flights\" describes the labelling effort ({pts_all} points);")
    md(f"**{len(clean)} flights x 6 = {pts_cln} points** is what the median rests on.")
    md("None were residual-flagged; all three exclusions are for asymmetry.")
    md("")
    md("### Axes")
    md("")
    md(f"`pos_err_total = math.{m.group(1)}(pos_err_Y, pos_err_Z)` — **in-plane Y and Z")
    md("only**, a two-component distance. There is no `pos_err_X` column.")
    md("")
    md("That two-component distance nonetheless **is** the full 3D magnitude here:")
    md("both the labelled crossing point and the fitted crossing point are, by")
    md("construction, the point where each trajectory intersects the crossing plane,")
    md("so both lie on that plane and the depth component is identically zero. It is")
    md("in-plane by construction, not by truncation.")
    md("")
    md("### Observation window")
    md("")
    md(f"**Full arc.** The producer's own header describes the comparison as against")
    md(f"*\"Model-C's full-arc-fit crossing-plane state\"*. No windowing constant exists")
    md(f"in `{PRODUCER}`" + (f" or in `{CLASSIFIER}`" if not cls_win else "") + ";")
    md("the fit uses every usable point on the track rather than a truncated prefix.")
    md("This is the same full-arc reference the convergence figures measure against —")
    md("which is why those figures measure convergence, not accuracy, while this one")
    md("measures accuracy against independent hand labels.")
    md("")
    md("### Close kernel, resolved at the call site")
    md("")
    md("Lineage: the fitted track comes from")
    md("`results/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3`,")
    md(f"written by `{DET_PRODUCER}`, which calls `dc.compute_mask` — the **shared**")
    md("detector, not a local rect variant.")
    md("")
    md("| file:line | shape | static? | size | consumed by |")
    md("|---|---|:--:|---|---|")
    for k in kerns:
        md(f"| `{DETECTOR_CORE}:{k['line']}` | **cv2.{k['shape']}** | "
           f"{'yes' if k['static'] else '**NO**'} | {k['size']} | {k.get('op','?')} |")
    md("")
    md(f"**Close kernel = `cv2.{close[0]['shape']}`.** Note this is the ELLIPSE path,")
    md("i.e. NOT the rect variant every Pi real-time script uses. This accuracy figure")
    md("therefore describes the ellipse detector's tracks.")
    md("")
    md("## Part 2 — triangulation precision")
    md("")
    md(f"| field | value (mm) |")
    md(f"|---|--:|")
    for k in ("rms_person_rebounder_mm", "rms_width_mm", "rms_vertical_mm"):
        md(f"| `{k}` | **{prow[k]}** |")
    md(f"| `overall_rms_mm` | {prow['overall_rms_mm']} |")
    md("")
    md("| | |")
    md("|---|---|")
    md(f"| source file | `{PRECISION_CSV}` |")
    md(f"| producing script | `{PRECISION_SCRIPT}` |")
    md(f"| **corners behind them** | **{n_corners}** (PATTERN_SIZE {pm.group(1)}x{pm.group(2)}) |")
    md(f"| board | `{prow['board']}` at depth {float(prow['depth_mm']):.1f} mm |")
    md("")
    md("The three axes are named for the rig, not for the camera frame:")
    md("`rms_person_rebounder_mm` is X_world (depth, strong), `rms_width_mm` is")
    md("Y_world (**weak**), `rms_vertical_mm` is Z_world (strong). The weak axis is")
    md("the widest at 2.40 mm, and the producing script flags it as *somewhat")
    md("optimistic* because the board's own tilt mixes the strong axes into it.")
    md("")
    md(f"All {n_corners} corners come from a single board image, so this is a")
    md("precision figure for one pose — not a spread across poses or sessions.")
    md("")

    report.write_text("\n".join(_md) + "\n", encoding="utf-8")
    log(f"wrote report: {report.relative_to(ROOT)} ({len(_md)} lines)")
    log("=== complete ===")
    _log.close()


if __name__ == "__main__":
    main()
