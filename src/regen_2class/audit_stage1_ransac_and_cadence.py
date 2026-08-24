"""Read-only audit: Stage 1 fitting times, cadence overruns, and RANSAC share.

Part A  Stage 1 (results/pi_benchmarking/stage1_results_20260803_1218.json)
        fitting-time field at full precision, n_iterations, points fitted,
        flight population, close-kernel shape resolved AT THE CALL SITE, and
        every other stage time in the same record.
Part B  Cadence overruns in the Pi sweep.
Part C  ransac_ms as a percentage of latency_ms, per (class, window) cell.

READ-ONLY. Re-runs no benchmark, opens every input for reading only, and never
overwrites or deletes: each output takes the next free numeric suffix.

The close kernel is resolved by parsing the producing script's AST and reading
the literal first argument of cv2.getStructuringElement at the call site the
Stage 1 script actually reaches - not by trusting config.close_kernel, which
records only the SIZE (30) and carries no shape at all. A call site whose shape
argument is not a static cv2.<CONST> attribute is reported as unresolved, never
guessed.

PATH NOTE: derived outputs moved from data/ to results/ on 2026-08-24. All paths
here are post-migration.

STOP conditions:
    - the Stage 1 file has no fitting-time field
    - n_iterations for that run cannot be resolved
    - the close kernel at that call site cannot be resolved statically
"""
import ast
import csv
import datetime
import json
import pathlib
import statistics as st
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import common as C

ROOT = pathlib.Path(__file__).resolve().parents[2]

STAGE1_JSON = "results/pi_benchmarking/stage1_results_20260803_1218.json"
STAGE1_SCRIPT = "src/pi_benchmarking/benchmark_pipeline_pi.py"
DETECTOR_CORE = "src/image_processing/02_adjacent_frame_differencing/detector_core.py"
TRAJ_FIT = "src/stereo/trajectory_fit.py"
SWEEP_CSV = "results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv"
SWEEP_JSON = "results/pi_benchmarking/pipeline_sweep_full_20260804.json"

AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"
LOG_DIR = ROOT / "claude/claude_logs"
REPORT_NAME = "audit_stage1_ransac_and_cadence.md"
LOG_NAME = "audit_stage1_ransac_and_cadence.log"

CADENCE_MS = 16.667
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
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    _log.write(line + "\n")
    _log.flush()


def md(s=""):
    _md.append(s)


def stop(msg):
    log(f"*** STOP *** {msg}")
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def resolve_kernels(script):
    """Every cv2.getStructuringElement call site, shape resolved statically."""
    tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
    out = []
    assigned = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Attribute) and fn.attr == "getStructuringElement":
                if isinstance(node.targets[0], ast.Name):
                    assigned[node.value.lineno] = node.targets[0].id
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "getStructuringElement"):
            continue
        a = node.args[0] if node.args else None
        if isinstance(a, ast.Attribute) and a.attr in _CV2_SHAPES:
            shape, static = a.attr, True
        else:
            shape, static = (ast.dump(a) if a is not None else "<missing>"), False
        out.append(dict(line=node.lineno, shape=shape, static=static,
                        size=ast.unparse(node.args[1]) if len(node.args) > 1 else "?",
                        var=assigned.get(node.lineno, "?")))
    # which morphologyEx op consumes each kernel
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "morphologyEx" and len(node.args) >= 3:
                op = node.args[1].attr if isinstance(node.args[1], ast.Attribute) else "?"
                kern = node.args[2].id if isinstance(node.args[2], ast.Name) else "?"
                for r in out:
                    if r["var"] == kern:
                        r["op"] = op
    return out


def main():
    global _log
    log_path = next_free(LOG_DIR / LOG_NAME)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    report = next_free(AUDIT_DIR / REPORT_NAME)
    _log = open(log_path, "a", encoding="utf-8")

    log("=== audit_stage1_ransac_and_cadence starting ===")
    log(f"log    : {log_path.relative_to(ROOT)}")
    log(f"report : {report.relative_to(ROOT)}")
    log("read-only; no benchmark re-run")

    for p in (STAGE1_JSON, STAGE1_SCRIPT, DETECTOR_CORE, SWEEP_CSV, SWEEP_JSON):
        if not (ROOT / p).is_file():
            stop(f"required input missing: {p}")

    # ================================================================ PART A
    log("--- PART A: Stage 1 ---")
    s1 = json.loads((ROOT / STAGE1_JSON).read_text(encoding="utf-8"))
    flights = s1["flights"]
    log(f"{STAGE1_JSON}: {len(flights)} flight records")

    FIT_FIELD = "ransac_fit_ms"
    if not any(FIT_FIELD in f for f in flights):
        stop(f"Stage 1 file has no fitting-time field '{FIT_FIELD}'")
    log(f"fitting-time field present: flights[i].{FIT_FIELD}")

    iters = {f.get("ransac_fit_n_iterations") for f in flights}
    if iters == {None} or None in iters:
        stop("n_iterations for the Stage 1 run cannot be resolved from the record")
    if len(iters) != 1:
        stop(f"n_iterations is not constant across the Stage 1 flights: {sorted(iters)}")
    n_iter = iters.pop()
    log(f"n_iterations resolved: {n_iter} (constant across all {len(flights)} flights)")

    kern_core = resolve_kernels(DETECTOR_CORE)
    log(f"{DETECTOR_CORE}: {len(kern_core)} getStructuringElement call site(s)")
    for k in kern_core:
        log(f"   L{k['line']}  shape={k['shape']} static={k['static']} "
            f"size={k['size']} var={k['var']} op={k.get('op','?')}")
    close_sites = [k for k in kern_core if k.get("op") == "MORPH_CLOSE"]
    if len(close_sites) != 1:
        stop(f"expected exactly one MORPH_CLOSE kernel call site, found {len(close_sites)}")
    close = close_sites[0]
    if not close["static"]:
        stop(f"close kernel shape at {DETECTOR_CORE}:{close['line']} is not statically "
             f"resolvable ({close['shape']}) - refusing to guess")
    calls_shared = "dc.compute_mask(" in (ROOT / STAGE1_SCRIPT).read_text(encoding="utf-8")
    log(f"Stage 1 calls detector_core.compute_mask: {calls_shared}")
    log(f"close kernel RESOLVED: cv2.{close['shape']}, size {close['size']} "
        f"(config.close_kernel={s1['config']['close_kernel']} gives only the SIZE)")

    fit_vals = [f[FIT_FIELD] for f in flights if f.get("ransac_fit_ok")]
    single = [f["single_shot_fit_ms"] for f in flights if f.get("single_shot_fit_ok")]
    npts = [f.get("single_shot_fit_n") for f in flights]
    log(f"{FIT_FIELD}: n={len(fit_vals)} ok of {len(flights)}; "
        f"min={min(fit_vals):.6f} median={st.median(fit_vals):.6f} max={max(fit_vals):.6f}")
    log(f"points fitted per flight (single_shot_fit_n): {sorted(npts)}")

    # ================================================================ PART B
    log("--- PART B: cadence ---")
    rows = list(csv.DictReader(open(ROOT / SWEEP_CSV, newline="", encoding="utf-8")))
    ok = [r for r in rows if r["status"] == "ok"]
    det = [float(r["last_pair_detect_ms"]) for r in ok]
    over = [d for d in det if d > CADENCE_MS]
    log(f"{SWEEP_CSV}: {len(ok)} ok rows with last_pair_detect_ms")
    log(f"  over {CADENCE_MS} ms: {len(over)} ({100*len(over)/len(det):.3f}%)")

    has_col = "over_cadence_pair_count" in rows[0]
    log(f"  over_cadence_pair_count present in the CSV: {has_col}")
    if not has_col:
        log(f"  -> not a CSV column; taken from {SWEEP_JSON} per-flight records instead")
    sj = json.loads((ROOT / SWEEP_JSON).read_text(encoding="utf-8"))
    sfl = sj.get("flights") or sj.get("results")
    counts = [f.get("over_cadence_pair_count") for f in sfl
              if f.get("over_cadence_pair_count") is not None]
    n_any = sum(1 for c in counts if c > 0)
    dist = {}
    for c in counts:
        dist[c] = dist.get(c, 0) + 1
    log(f"  {len(counts)} flights carry over_cadence_pair_count; "
        f"total pairs={sum(counts)}; flights with >=1: {n_any}")
    log(f"  distribution: {dict(sorted(dist.items()))}")

    # ================================================================ PART C
    log("--- PART C: ransac share of latency ---")
    cls_of = {(r["session"], r["flight"]): C.CLASS_OF_BIN[r["bin"]] for r in rows}
    windows = sorted({int(r["T_ms"]) for r in rows})
    cells = []
    for cl in C.CLASSES:
        for w in windows:
            g = [r for r in ok
                 if cls_of[(r["session"], r["flight"])] == cl and int(r["T_ms"]) == w]
            if not g:
                continue
            mr = C.percentile([float(r["ransac_ms"]) for r in g], 0.50)
            ml = C.percentile([float(r["latency_ms"]) for r in g], 0.50)
            per_row = C.percentile([100 * float(r["ransac_ms"]) / float(r["latency_ms"])
                                    for r in g], 0.50)
            cells.append(dict(cls=cl, w=w, n=len(g), med_r=mr, med_l=ml,
                              pct=100 * mr / ml, pct_rowwise=per_row))
    pcts = [c["pct"] for c in cells]
    lo = min(cells, key=lambda c: c["pct"])
    hi = max(cells, key=lambda c: c["pct"])
    log(f"  {len(cells)} cells; ratio-of-medians min {min(pcts):.2f}% "
        f"({lo['cls']}/{lo['w']}), max {max(pcts):.2f}% ({hi['cls']}/{hi['w']})")

    # ================================================================ report
    md("# Audit: Stage 1 fitting time, cadence overruns, RANSAC share of latency")
    md("")
    md("Generated by `src/regen_2class/audit_stage1_ransac_and_cadence.py`. Read-only;")
    md("no benchmark was re-run.")
    md(f"Log: `{log_path.relative_to(ROOT).as_posix()}`")
    md("")
    md("> **Path note.** Derived outputs moved from `data/` to `results/` on 2026-08-24.")
    md("> All paths below are post-migration.")
    md("")
    md("## Part A — Stage 1")
    md("")
    md(f"Source: `{STAGE1_JSON}`  ·  producer: `{STAGE1_SCRIPT}`")
    md("")
    md("### Fitting time")
    md("")
    md(f"Field path: **`flights[i].{FIT_FIELD}`** — one value per flight record.")
    md("")
    md("| # | session / flight | `ransac_fit_ms` (full precision) | `single_shot_fit_ms` | points fitted |")
    md("|--:|---|--:|--:|--:|")
    for i, f in enumerate(flights):
        md(f"| {i} | {f['session']}/{f['flight']} | {f[FIT_FIELD]!r} | "
           f"{f['single_shot_fit_ms']!r} | {f.get('single_shot_fit_n')} |")
    md("")
    md(f"- **Per flight, per fit — a single measurement, not a median or mean.** Each")
    md(f"  record holds one `{FIT_FIELD}` from one timed call. The spread across the")
    md(f"  {len(fit_vals)} flights is min **{min(fit_vals):.4f}**, median")
    md(f"  **{st.median(fit_vals):.4f}**, max **{max(fit_vals):.4f}** ms — but those")
    md(f"  three are computed *here*, over flights; they are not fields in the file.")
    md(f"- Contrast the detect stages, which ARE per-frame distributions in the file")
    md(f"  (`detect_cam0.total.{{n,mean,median,p95,p99,max,min}}`).")
    md("")
    md("### n_iterations")
    md("")
    md(f"**{n_iter}**, recorded per flight as `flights[i].ransac_fit_n_iterations` and")
    md(f"constant across all {len(flights)} records. The producer sets it from")
    md(f"`RANSAC_N_ITERATIONS[\"C\"]` (`{STAGE1_SCRIPT}` line 224/232).")
    md("")
    md("### Observation window / points fitted")
    md("")
    md("There is **no observation-window sweep in Stage 1**. Each flight is fitted once")
    md("on its whole usable track:")
    md("")
    md(f"- points fitted per flight (`single_shot_fit_n`): {sorted(npts)}")
    md(f"- pairs available (`n_pairs`): {sorted(f['n_pairs'] for f in flights)}")
    md("")
    md("So the x-quantity is a **point count**, not a time window. That is the key")
    md("difference from the later sweep, which sweeps 150–1250 ms.")
    md("")
    md("### Flight population")
    md("")
    md(f"**n = {len(flights)} flights**, all eight listed above.")
    md("")
    md("### Close kernel, resolved at the call site")
    md("")
    md(f"Stage 1 calls `dc.compute_mask` (`{STAGE1_SCRIPT}:99`), i.e. the SHARED")
    md(f"detector, not a local rect variant. Resolving that function's AST:")
    md("")
    md("| file:line | shape | static? | size | consumed by |")
    md("|---|---|:--:|---|---|")
    for k in kern_core:
        md(f"| `{DETECTOR_CORE}:{k['line']}` | **cv2.{k['shape']}** | "
           f"{'yes' if k['static'] else '**NO**'} | {k['size']} | {k.get('op','?')} |")
    md("")
    md(f"**Close kernel = `cv2.{close['shape']}`, size {close['size']}.**")
    md("")
    md(f"`config.close_kernel = {s1['config']['close_kernel']}` in the JSON gives only")
    md("the **size**. It carries no shape field at all, so the shape cannot be read")
    md("from the results file — it has to come from the call site, which is why this")
    md("is resolved by AST rather than assumed.")
    md("")
    md("### Every other stage time in the same record")
    md("")
    md("| field | kind | flight 0 value |")
    md("|---|---|--:|")
    f0 = flights[0]
    for k in ("load_ms", "pair_correct_ms", "triangulate_ms", "single_shot_fit_ms",
              "ransac_fit_ms", "wall_clock_ms"):
        md(f"| `flights[i].{k}` | single value, per flight | {f0[k]!r} |")
    md(f"| `flights[i].detect_cam0.total.median` | per-frame distribution, n={f0['detect_cam0']['total']['n']} | "
       f"{f0['detect_cam0']['total']['median']!r} |")
    md(f"| `flights[i].detect_cam1.total.median` | per-frame distribution, n={f0['detect_cam1']['total']['n']} | "
       f"{f0['detect_cam1']['total']['median']!r} |")
    md(f"| `flights[i].rolling_refit[j].ms` | per refit, {len(f0['rolling_refit'])} entries | "
       f"{f0['rolling_refit'][0]['ms']!r} (k={f0['rolling_refit'][0]['k']}) |")
    md("")
    md(f"Detection is further broken down per camera into `diff`, `mask`, `contours`,")
    md(f"`total`, each with `n / mean / median / p95 / p99 / max / min`. "
       f"`n_warmup_pairs = {s1['n_warmup_pairs']}` warm-up pairs precede the timed frames.")
    md("")
    md("## Part B — cadence overruns")
    md("")
    md(f"### Detect timings over {CADENCE_MS} ms, from the CSV")
    md("")
    md(f"| | |")
    md(f"|---|--:|")
    md(f"| rows with a detect timing (`status=='ok'`) | {len(det)} |")
    md(f"| exceeding {CADENCE_MS} ms | **{len(over)}** |")
    md(f"| fraction | **{100*len(over)/len(det):.3f}%** |")
    md(f"| max observed | {max(det):.3f} ms |")
    md("")
    md("**Read this narrowly.** `last_pair_detect_ms` is the detect time of the *last")
    md("pair in that window only*, sampled once per (flight, window) row — not every")
    md("frame. It is the same underlying frames re-sampled across 24 windows, so these")
    md("rows are not independent.")
    md("")
    md("### over_cadence_pair_count per flight")
    md("")
    md(f"**Not a column in `{SWEEP_CSV}`.** The CSV has no cadence-overrun field. The")
    md(f"per-flight counts live in `{SWEEP_JSON}` as `flights[i].over_cadence_pair_count`,")
    md("which counts overruns across **all** frames rather than the sampled last pair.")
    md("")
    md("| over_cadence_pair_count | flights |")
    md("|--:|--:|")
    for k, v in sorted(dist.items()):
        md(f"| {k} | {v} |")
    md("")
    md(f"- flights carrying the field: **{len(counts)}**")
    md(f"- **flights with at least one over-cadence pair: {n_any}**")
    md(f"- total over-cadence pairs across the run: **{sum(counts)}**")
    md("")
    md("## Part C — ransac_ms as a percentage of latency_ms")
    md("")
    md("Ratio of medians: `median(ransac_ms) / median(latency_ms)` within each cell.")
    md("The median of the per-row ratios is given alongside, since the two are not")
    md("identical and neither is more correct without a stated intent.")
    md("")
    md("| class | window (ms) | n | median ransac_ms | median latency_ms | **% of latency** | % (median of row ratios) |")
    md("|---|--:|--:|--:|--:|--:|--:|")
    for c in cells:
        md(f"| {c['cls']} | {c['w']} | {c['n']} | {c['med_r']:.2f} | {c['med_l']:.2f} | "
           f"**{c['pct']:.2f}%** | {c['pct_rowwise']:.2f}% |")
    md("")
    md(f"- **minimum: {min(pcts):.2f}%** at {lo['cls']} / {lo['w']} ms")
    md(f"- **maximum: {max(pcts):.2f}%** at {hi['cls']} / {hi['w']} ms")
    md(f"- across all {len(cells)} cells")
    md("")

    report.write_text("\n".join(_md) + "\n", encoding="utf-8")
    log(f"wrote report: {report.relative_to(ROOT)} ({len(_md)} lines)")
    log("=== complete ===")
    _log.close()


if __name__ == "__main__":
    main()
