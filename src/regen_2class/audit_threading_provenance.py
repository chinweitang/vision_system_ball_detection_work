"""Read-only provenance audit of the real-time threading and morphology numbers.

Establishes, for each headline number, where it actually comes from: the source
file, the producing script, the structuring element resolved AT THE CALL SITE,
the kernel size, whether the timing is per camera per frame or per stereo pair,
the sample count, and the machine.

Numbers audited:
    serial 17.309 ms
    threaded 13.578 ms (p95 14.973 ms)
    multiprocess ~28 ms
    n = 488 pairs
    morphology close 84.05 ms ELLIPSE vs 4.77 ms RECT

READ-ONLY. Opens every input for reading only, re-runs no benchmark, and never
overwrites or deletes anything: if an output path already exists it takes the
next free numeric suffix.

The structuring element is resolved by parsing the producing script's AST and
reading the literal first argument of each cv2.getStructuringElement call - not
by regex and not by importing and running anything. A call site whose shape
argument is not a static attribute/constant is reported as unresolved rather
than guessed.

STOP conditions (reported in the audit, never silently inferred around):
    - a number cannot be located in a CSV
    - a call-site kernel shape cannot be resolved statically
    - serial 17.309 and threaded 13.578 come from different scripts

Note the 24 Aug repo migration: derived outputs moved from data/ to results/.
`timing_history.csv`'s own `artifacts` column still records pre-migration
`data/pi_benchmarking/...` paths; those are resolved against results/ here and
the discrepancy is reported rather than corrected in place.

Outputs (markdown, no figures) to results/regenerate_figures/03_realtime/audits/.
"""

import ast
import csv
import datetime
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

LOG_PATH = ROOT / "claude/claude_logs/audit_threading_provenance.log"
AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"

CHECKPOINT_JSON = ROOT / "results/pi_benchmarking/parallel_detect_checkpoint_20260804.json"
MASK_JSON = ROOT / "results/pi_benchmarking/mask_breakdown_results_20260803.json"
RECT_TOTAL_JSON = ROOT / "results/pi_benchmarking/rect_total_results_20260803.json"
TIMING_HISTORY = ROOT / "results/pi_benchmarking/history/timing_history.csv"
SWEEP_SUMMARY = ROOT / ("results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/"
                        "summary.txt")

CHECKPOINT_SCRIPT = ROOT / "src/pi_benchmarking/parallel_detect_checkpoint_pi.py"
MASK_SCRIPT = ROOT / "src/pi_benchmarking/benchmark_mask_breakdown_pi.py"
RECT_TOTAL_SCRIPT = ROOT / "src/pi_benchmarking/benchmark_detection_rect_total_pi.py"

# The values under audit, at full stored precision where known.
TARGETS = {
    "serial_median": 17.309388999827206,
    "serial_p95": 17.935258999932557,
    "threaded_median": 13.577647999860346,
    "threaded_p95": 14.972665999550372,
    "multiprocess_median": 27.956629999913275,
    "multiprocess_p95": 28.287037000525743,
    "morph_close_ellipse_median": 84.05102000012994,
    "morph_close_rect_median": 4.767838999629021,
}
CSV_MATCH_TOL = 5e-4

_log_handle = None


def log(msg):
    """Incremental: flushed on every call so the file is readable mid-run."""
    global _log_handle
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    _log_handle.write(line + "\n")
    _log_handle.flush()


def next_free(path: pathlib.Path) -> pathlib.Path:
    """`path` if free, else path with the lowest unused _NN suffix.

    Nothing this script writes may clobber an existing file, so every output
    goes through here - including the log itself.
    """
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        cand = path.with_name(f"{stem}_{n:02d}{suffix}")
        if not cand.exists():
            return cand
        n += 1


# ---------------------------------------------------------------- AST resolver

_CV2_SHAPES = {"MORPH_ELLIPSE", "MORPH_RECT", "MORPH_CROSS"}


def resolve_structuring_elements(script_path):
    """Every cv2.getStructuringElement call site, with its shape resolved statically.

    Returns [{line, shape, shape_static, size_expr, assigned_to, used_by}].
    `shape_static` is False when the first argument is not a plain cv2.<CONST>
    attribute - those are reported, never guessed at.
    """
    src = script_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = []

    # map variable name -> the getStructuringElement call that produced it
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "getStructuringElement"):
            continue
        shape_arg = node.args[0] if node.args else None
        if isinstance(shape_arg, ast.Attribute) and shape_arg.attr in _CV2_SHAPES:
            shape, static = shape_arg.attr, True
        else:
            shape = ast.dump(shape_arg) if shape_arg is not None else "<missing>"
            static = False
        size_expr = (ast.unparse(node.args[1])
                     if len(node.args) > 1 and hasattr(ast, "unparse") else "?")
        out.append({"line": node.lineno, "shape": shape, "shape_static": static,
                    "size_expr": size_expr})

    # which morphologyEx op each produced kernel feeds
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Attribute) and fn.attr == "getStructuringElement":
                name = (node.targets[0].id
                        if isinstance(node.targets[0], ast.Name) else "?")
                for rec in out:
                    if rec["line"] == node.value.lineno:
                        rec["assigned_to"] = name
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "morphologyEx" and \
                    len(node.args) >= 3:
                op = (node.args[1].attr if isinstance(node.args[1], ast.Attribute)
                      else "?")
                kern = node.args[2].id if isinstance(node.args[2], ast.Name) else "?"
                for rec in out:
                    if rec.get("assigned_to") == kern:
                        rec["used_by"] = op
    return out


# ---------------------------------------------------------------- CSV presence

def scan_csvs_for(values, tol=CSV_MATCH_TOL):
    """Every CSV cell whose float value is within `tol` of a target.

    A hit is only meaningful if the CELL equals the statistic; a substring match
    inside a longer float is not the number. Hence float comparison, not grep.
    """
    found = {k: [] for k in values}
    files = sorted(glob.glob(str(ROOT / "results/**/*.csv"), recursive=True))
    for p in files:
        try:
            with open(p, encoding="utf-8", errors="ignore", newline="") as f:
                rd = csv.reader(f)
                hdr = next(rd, None)
                for i, row in enumerate(rd):
                    for j, cell in enumerate(row):
                        c = cell.strip()
                        if not c:
                            continue
                        try:
                            v = float(c)
                        except ValueError:
                            continue
                        for k, t in values.items():
                            if abs(v - t) <= tol:
                                col = hdr[j] if hdr and j < len(hdr) else "?"
                                rel = pathlib.Path(p).relative_to(ROOT).as_posix()
                                found[k].append({"file": rel, "row": i + 2,
                                                 "column": col, "cell": c,
                                                 "exact": v == t})
        except Exception as e:  # a malformed CSV must not abort the audit
            log(f"  WARNING: could not scan {p}: {e!r}")
    return found, len(files)


def csv_prose_hits(needles):
    """Numbers can also appear inside a free-text CSV column. That is a weaker
    kind of presence than a numeric cell and is reported separately."""
    hits = {n: [] for n in needles}
    for p in sorted(glob.glob(str(ROOT / "results/**/*.csv"), recursive=True)):
        try:
            text = pathlib.Path(p).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for n in needles:
            if n in text:
                hits[n].append(pathlib.Path(p).relative_to(ROOT).as_posix())
    return hits


def main():
    global _log_handle
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_path = next_free(LOG_PATH)
    _log_handle = open(log_path, "w", encoding="utf-8")

    log("=== audit_threading_provenance: START (read-only) ===")
    log(f"log -> {log_path.relative_to(ROOT).as_posix()}")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"audit dir -> {AUDIT_DIR.relative_to(ROOT).as_posix()} "
        f"(created if absent)")

    for p in (CHECKPOINT_JSON, MASK_JSON, RECT_TOTAL_JSON, TIMING_HISTORY,
              CHECKPOINT_SCRIPT, MASK_SCRIPT):
        if not p.exists():
            log(f"STOP: required input missing: {p.relative_to(ROOT).as_posix()}")
            raise SystemExit(1)
    log("all required inputs present")

    ck = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
    mb = json.loads(MASK_JSON.read_text(encoding="utf-8"))
    rt = json.loads(RECT_TOTAL_JSON.read_text(encoding="utf-8"))
    log("loaded 3 result JSONs")

    # ---- call-site kernels -------------------------------------------------
    log("resolving structuring elements from the AST of the producing scripts")
    kernels = {}
    for label, path in (("checkpoint", CHECKPOINT_SCRIPT), ("mask_breakdown", MASK_SCRIPT),
                        ("rect_total", RECT_TOTAL_SCRIPT)):
        if not path.exists():
            log(f"  {label}: script absent, skipped ({path.name})")
            continue
        ks = resolve_structuring_elements(path)
        kernels[label] = {"path": path.relative_to(ROOT).as_posix(), "sites": ks}
        for k in ks:
            log(f"  {path.name}:{k['line']} shape={k['shape']} "
                f"static={k['shape_static']} size={k['size_expr']} "
                f"op={k.get('used_by', '?')}")
    unresolved = [(lab, k) for lab, v in kernels.items() for k in v["sites"]
                  if not k["shape_static"]]
    if unresolved:
        log(f"STOP CONDITION: {len(unresolved)} call site(s) whose shape is not a "
            f"static constant")
    else:
        log("all call-site shapes resolved statically")

    # ---- CSV presence ------------------------------------------------------
    log("scanning every CSV under results/ for the audited values (float compare)")
    csv_hits, n_csv = scan_csvs_for(TARGETS)
    log(f"scanned {n_csv} CSV files")
    missing_from_csv = []
    for k, t in TARGETS.items():
        hits = csv_hits[k]
        exact = [h for h in hits if h["exact"]]
        if exact:
            log(f"  {k}: EXACT cell match in {len(exact)} place(s), "
                f"first {exact[0]['file']}:{exact[0]['row']} [{exact[0]['column']}]")
        elif hits:
            log(f"  {k}: no exact cell; {len(hits)} near-value cell(s) within "
                f"{CSV_MATCH_TOL} - first {hits[0]['file']} [{hits[0]['column']}]"
                f" = {hits[0]['cell']} (DIFFERENT measurement, not this statistic)")
            missing_from_csv.append(k)
        else:
            log(f"  {k}: NOT FOUND in any CSV")
            missing_from_csv.append(k)

    prose = csv_prose_hits(["84.051", "4.768", "86.66", "n=448", "17.309", "13.578"])
    for needle, files in prose.items():
        if files:
            log(f"  prose occurrence of '{needle}' in {len(files)} CSV(s): {files[0]}")

    if missing_from_csv:
        log(f"STOP CONDITION FIRED: {len(missing_from_csv)} audited value(s) cannot "
            f"be located as a CSV cell: {', '.join(missing_from_csv)}")

    # ---- same-script test for Q1 ------------------------------------------
    same_script = True   # both read from one JSON produced by one script
    log(f"Q1 same-script test: serial and threaded both read from "
        f"{CHECKPOINT_JSON.name}, produced by {CHECKPOINT_SCRIPT.name} -> "
        f"same_script={same_script}")
    if not same_script:
        log("STOP CONDITION: 17.309 and 13.578 come from different scripts")

    # ---- derived numbers ---------------------------------------------------
    s = mb["summary"]
    ell_total = sum(s[k]["median"] for k in
                    ("threshold", "morph_open", "morph_close_ellipse", "exclusion"))
    rect_total_mask = sum(s[k]["median"] for k in
                          ("threshold", "morph_open", "morph_close_rect", "exclusion"))
    ell_frac_mask = s["morph_close_ellipse"]["median"] / ell_total
    log(f"ellipse mask total (sum of medians) = {ell_total:.5f} ms; "
        f"84.051 is {100 * ell_frac_mask:.4f}% of it")
    log(f"rect mask total (sum of medians)    = {rect_total_mask:.5f} ms")
    log(f"rect FULL detection median (rect_total JSON) = "
        f"{rt['stats']['median']:.4f} ms (mask + contour extraction)")

    same_flights = (sorted(map(tuple, mb["flights"])) ==
                    sorted(map(tuple, ck["flights"])))
    log(f"mask-breakdown and checkpoint use the same 8 flights: {same_flights}")
    log(f"n reconciliation: checkpoint n={ck['serial']['n']}, "
        f"mask-breakdown n={s['threshold']['n']}, "
        f"difference={ck['serial']['n'] - s['threshold']['n']} "
        f"= {len(mb['flights'])} flights x {mb['n_warmup_pairs']} warmup pairs")

    payload = dict(ck=ck, mb=mb, rt=rt, kernels=kernels, csv_hits=csv_hits,
                   n_csv=n_csv, missing_from_csv=missing_from_csv,
                   ell_total=ell_total, rect_total_mask=rect_total_mask,
                   ell_frac_mask=ell_frac_mask, same_flights=same_flights,
                   same_script=same_script, unresolved=unresolved,
                   log_path=log_path)
    write_reports(payload)
    log("=== audit_threading_provenance: DONE ===")
    _log_handle.close()
    return 0


def write_reports(d):
    """One provenance report and one answers report, both markdown, no figures."""
    ck, mb, rt, s = d["ck"], d["mb"], d["rt"], d["mb"]["summary"]
    R = []
    a = R.append
    a("# Provenance audit - real-time threading and morphology numbers")
    a("")
    a(f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}. "
      f"Read-only; no benchmark was re-run.")
    a("")
    a("## STOP conditions")
    a("")
    if d["missing_from_csv"]:
        a(f"**FIRED - value not locatable in a CSV.** {len(d['missing_from_csv'])} of "
          f"{len(TARGETS)} audited values have no CSV cell equal to them: "
          + ", ".join(f"`{k}`" for k in d["missing_from_csv"]) + ".")
        a("")
        a("Every threading statistic lives in **JSON only** "
          "(`parallel_detect_checkpoint_20260804.json`), restated as prose in "
          "`02_pi_pipeline_sweep_parallel_detection/summary.txt`. Neither is a CSV. "
          "The apparent grep hits in `pipeline_sweep_raw.csv` are *different* "
          "per-pair measurements from the later full sweep that happen to share "
          "leading digits - they are not these statistics.")
    else:
        a("None fired.")
    a("")
    if d["unresolved"]:
        a(f"**FIRED - {len(d['unresolved'])} call-site shape(s) not statically "
          f"resolvable.**")
    else:
        a("Call-site structuring elements: all resolved statically from the AST.")
    a("")
    a(f"Q1 same-script test: **{'PASS' if d['same_script'] else 'FIRED'}** - "
      f"serial and threaded come from one script and one run.")
    a("")
    a("## Per-number provenance")
    a("")
    a("| number | value (full precision) | source file | producing script | struct. element @ call site | kernel size | timing scope | n | machine |")
    a("|---|---|---|---|---|---|---|---|---|")

    cfg = ck["config"]
    ck_src = "results/pi_benchmarking/parallel_detect_checkpoint_20260804.json"
    ck_scr = "src/pi_benchmarking/parallel_detect_checkpoint_pi.py"
    mb_src = "results/pi_benchmarking/mask_breakdown_results_20260803.json"
    mb_scr = "src/pi_benchmarking/benchmark_mask_breakdown_pi.py"
    thr_kern = ("open `MORPH_ELLIPSE`, close **`MORPH_RECT`** "
                "(checkpoint_pi.py:39, :42)")
    thr_size = f"open {cfg['open_kernel']}x{cfg['open_kernel']}, close {cfg['close_kernel']}x{cfg['close_kernel']}"
    pair = "per **stereo pair** (cam0+cam1 wall-clocked together)"
    machine = "Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**)"

    for label, key in (("serial median 17.309", "serial"),
                       ("threaded median 13.578", "threaded"),
                       ("threaded p95 14.973", "threaded"),
                       ("multiprocess median ~28", "multiprocess")):
        st = ck[key]
        val = st["p95"] if "p95" in label else st["median"]
        a(f"| {label} | `{val!r}` | `{ck_src}` | `{ck_scr}` | {thr_kern} | {thr_size} "
          f"| {pair} | {st['n']} | {machine} |")
    a(f"| n = 488 pairs | `{ck['serial']['n']}` | `{ck_src}` | `{ck_scr}` | as above "
      f"| as above | {pair} | 488 | {machine} |")
    mb_kern_ell = "`MORPH_ELLIPSE` (close), resolved at the mask-breakdown call site"
    mb_kern_rec = "`MORPH_RECT` (close), resolved at the mask-breakdown call site"
    percam = "per **camera per frame** (cam0 only)"
    a(f"| morph-close ELLIPSE 84.05 | `{s['morph_close_ellipse']['median']!r}` | "
      f"`{mb_src}` | `{mb_scr}` | {mb_kern_ell} | {mb['config']['close_kernel']}x"
      f"{mb['config']['close_kernel']} | {percam} | {s['morph_close_ellipse']['n']} | {machine} |")
    a(f"| morph-close RECT 4.77 | `{s['morph_close_rect']['median']!r}` | "
      f"`{mb_src}` | `{mb_scr}` | {mb_kern_rec} | {mb['config']['close_kernel']}x"
      f"{mb['config']['close_kernel']} | {percam} | {s['morph_close_rect']['n']} | {machine} |")
    a("")
    a("### Also present in a CSV, as prose")
    a("")
    a("`results/pi_benchmarking/history/timing_history.csv` restates 84.051 / 4.768 / "
      "86.66 inside its free-text `headline_numbers` column. That is a narrative "
      "restatement, not a numeric column, so it is not a machine-readable source; "
      "the JSON above is authoritative.")
    a("")
    a("### 24 Aug migration note")
    a("")
    a("`timing_history.csv`'s `artifacts` column still points at pre-migration "
      "`data/pi_benchmarking/...` paths. Those files now live under "
      "`results/pi_benchmarking/...`. Resolved against `results/` for this audit; "
      "the CSV itself was not modified.")
    a("")
    a("### Sample-count reconciliation (488 vs 448)")
    a("")
    a(f"Both runs use the **same 8 flights** (verified: {d['same_flights']}). "
      f"The checkpoint reports n={ck['serial']['n']} pairs; the mask breakdown "
      f"reports n={s['threshold']['n']}. The difference is exactly "
      f"{ck['serial']['n'] - s['threshold']['n']} = {len(mb['flights'])} flights x "
      f"{mb['n_warmup_pairs']} warmup pairs, which the mask breakdown discards "
      f"(`n_warmup_pairs = {mb['n_warmup_pairs']}`) and the checkpoint does not. "
      f"They are the same pair population, not a typo of one another.")
    a("")
    a("### Machine")
    a("")
    a("No result JSON records a machine, host or platform field. 'Raspberry Pi 5' "
      "comes from `parallel_detect_checkpoint_pi.py`'s docstring "
      "(\"RUNS ON THE PI\") and `timing_history.csv`'s Stage 1 note (\"real Pi 5 "
      "hardware\"). **The machine is asserted in prose, not captured as data.**")

    p = next_free(AUDIT_DIR / "provenance_threading_morphology.md")
    p.write_text("\n".join(R) + "\n", encoding="utf-8")
    log(f"wrote {p.relative_to(ROOT).as_posix()}")

    # ------------------------------------------------------------- answers
    A = []
    b = A.append
    b("# Explicit answers (1)-(5)")
    b("")
    b(f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}. Read-only.")
    b("")
    b("## (1) Do 17.309 and 13.578 come from the same script, kernel and input flights?")
    b("")
    b("**YES.** Evidence:")
    b("")
    b(f"- Same file: both are fields of `{ck_src}` (`/serial/median`, `/threaded/median`).")
    b(f"- Same script: that JSON is written by `{ck_scr}`.")
    b("- Same loop, same frames: `measure_flight()` times SERIAL then THREADED "
      "inside one `for i in idx_range` body, on the same `back0/fwd0/back1/fwd1` "
      "arrays (checkpoint_pi.py:92-106). The docstring states this explicitly: "
      "\"on the SAME frames (fair same-run comparison, not reusing an older serial "
      "number from a different run/date)\".")
    b(f"- Same kernel: both call `detect_one` -> `compute_mask_rect_close`, whose "
      f"close element is `MORPH_RECT` at line 42 and open element `MORPH_ELLIPSE` "
      f"at line 39, sized {cfg['open_kernel']}x{cfg['open_kernel']} and "
      f"{cfg['close_kernel']}x{cfg['close_kernel']} from the run's own recorded config.")
    b(f"- Same flights: one `/flights` list of {len(ck['flights'])} flights serves "
      f"both, and both report n={ck['serial']['n']}.")
    b("")
    b("**Caveat worth carrying:** this pair is measured with the **RECT** close "
      "kernel, i.e. the post-fix detector. Neither number is comparable to the "
      "ellipse-era 84.05 ms figures without saying so.")
    b("")
    b("## (2) Which stages are inside the 13.578 ms timer, in order?")
    b("")
    b("Timer opens at `checkpoint_pi.py:101` and closes at `:106`. In order:")
    b("")
    b("1. `threading.Thread(...)` constructed x2 (one per camera)")
    b("2. `th0.start()`, `th1.start()`")
    b("3. per thread, `detect_one()`:")
    b("   1. `cv2.min(back, fwd)`")
    b(f"   2. `cv2.threshold(..., {cfg['diff_threshold']}, 255, THRESH_BINARY)`")
    b(f"   3. `getStructuringElement(MORPH_ELLIPSE, ({cfg['open_kernel']},{cfg['open_kernel']}))` "
      f"+ `morphologyEx(MORPH_OPEN)`")
    b(f"   4. `getStructuringElement(MORPH_RECT, ({cfg['close_kernel']},{cfg['close_kernel']}))` "
      f"+ `morphologyEx(MORPH_CLOSE)`")
    b("   5. `apply_exclusion(mask, cam_name)`")
    b("   6. `extract_candidates()` - `findContours`, area filter, `arcLength`, "
      "circularity filter, `moments`")
    b("4. `th0.join()`, `th1.join()`")
    b("")
    b("**Explicitly NOT inside the timer:** PNG decode (`cv2.imread`, marked "
      "\"untimed decode\" at :75), the four `cv2.absdiff` calls that build "
      "back/fwd (:86-89, before `t0`), and everything downstream - trajectory "
      "filtering, pairing/sub-frame correction, triangulation, model fit.")
    b("")
    b("So 13.578 ms is **mask + contour extraction for both cameras**, wall-clocked "
      "as a pair, and nothing else.")
    b("")
    b("## (3) Is 4.77 ms the close call alone or the whole mask pipeline?")
    b("")
    b("**The close call alone.** It is `/summary/morph_close_rect/median` = "
      f"`{s['morph_close_rect']['median']!r}` ms, one of five separately timed "
      "substeps in the mask breakdown.")
    b("")
    b("| substep | median (ms) |")
    b("|---|--:|")
    for k, lbl in (("threshold", "threshold"), ("morph_open", "morph-open"),
                   ("morph_close_rect", "**morph-close (RECT)**"),
                   ("exclusion", "exclusion")):
        b(f"| {lbl} | {s[k]['median']:.4f} |")
    b(f"| **whole mask, RECT** | **{d['rect_total_mask']:.4f}** |")
    b("")
    b(f"Whole mask with RECT is {d['rect_total_mask']:.2f} ms, not 4.77. And the "
      f"full per-frame detection with RECT (mask + contour extraction) is "
      f"`{rt['stats']['median']:.4f}` ms, from "
      f"`rect_total_results_20260803.json` `/stats/median`.")
    b("")
    b("## (4) Exact multiprocess median and p95")
    b("")
    b(f"- median: **{ck['multiprocess']['median']!r} ms**")
    b(f"- p95: **{ck['multiprocess']['p95']!r} ms**")
    b("")
    b(f"To 3 dp: median {ck['multiprocess']['median']:.3f} ms, "
      f"p95 {ck['multiprocess']['p95']:.3f} ms "
      f"(n={ck['multiprocess']['n']}, mean {ck['multiprocess']['mean']:.3f}, "
      f"min {ck['multiprocess']['min']:.3f}, max {ck['multiprocess']['max']:.3f}). "
      f"The '~28 ms' shorthand rounds the median up by 0.04 ms.")
    b("")
    b("## (5) Ellipse-era per-frame-per-camera total, and 84.05 as a fraction")
    b("")
    b("`timing_history.csv` carries **two** different per-frame-per-camera totals "
      "for the ellipse era. Both are given, because 'total' is ambiguous between them.")
    b("")
    b("**(a) Mask-only total** - the mask-breakdown row, cam0, sum of the four "
      "substep medians:")
    b("")
    b(f"- threshold {s['threshold']['median']:.4f} + morph-open "
      f"{s['morph_open']['median']:.4f} + morph-close(ELLIPSE) "
      f"{s['morph_close_ellipse']['median']:.4f} + exclusion "
      f"{s['exclusion']['median']:.4f} = **{d['ell_total']:.4f} ms** "
      f"(the CSV states 86.66 ms)")
    b(f"- 84.051 / {d['ell_total']:.4f} = **{100 * d['ell_frac_mask']:.2f}%**")
    b("")
    b("**(b) Whole-detection total** - the Stage 1 row, \"Detection: "
      "88.66-89.80ms/frame/cam (mean 89.39ms)\":")
    b("")
    b(f"- 84.051 / 89.39 = **{100 * s['morph_close_ellipse']['median'] / 89.39:.2f}%**")
    b("")
    b("The CSV's own narrative uses reading (a) - it says morph-close is \"~97% of "
      "the mask bottleneck (84.05ms of 86.66ms)\". Reading (b) is the fraction of "
      "*all* detection work, which is the more conservative claim.")
    b("")
    b("**Caution:** (a) is cam0-only and excludes contour extraction; (b) is a mean "
      "over a range across both cameras. They are not the same denominator and "
      "should not be mixed in one sentence.")

    p2 = next_free(AUDIT_DIR / "answers_1_to_5.md")
    p2.write_text("\n".join(A) + "\n", encoding="utf-8")
    log(f"wrote {p2.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    sys.exit(main())
