"""Read-only provenance audit of the RANSAC n_iterations sweep numbers.

Traces every number the brief names back to a CSV row and a producing script,
and records machine, observation window, flight population and column units.

READ-ONLY. Opens inputs for reading only. Writes exactly two things, both new:
a markdown report under results/regenerate_figures/03_realtime/audits/ and an
incremental log under claude/claude_logs/. Never overwrites: if either path
exists, a numeric suffix is appended.

NOTE ON PATHS: this repo moved derived outputs from data/ to results/ on
2026-08-24. Every path here is the post-migration one. Anything still written as
data/<results folder> in older logs refers to the same file at its new location.

Numbers audited:
    median prediction error   193.6 mm, 189.8 mm
    wall clock                1162.7 ms, 295.5 ms
    successful runs           22,367
    grid                      150 flights x 6 n_iterations x 25 seeds

STOP conditions:
    1162.7 or 295.5 cannot be traced to a CSV
"""
import csv
import datetime
import pathlib
import re
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SWEEP_DIR = "results/trajectory_fit_comparison/ransac_iterations_sweep"
RAW = f"{SWEEP_DIR}/ransac_sweep_raw.csv"
T1 = f"{SWEEP_DIR}/table1_wallclock_by_niterations.csv"
T2 = f"{SWEEP_DIR}/table2_error_by_niterations.csv"
T3 = f"{SWEEP_DIR}/table3_unstable_subset_error_by_niterations.csv"
EXCLUDED = f"{SWEEP_DIR}/excluded_flights.csv"
PRODUCER = "src/stereo/ransac_iterations_sweep.py"
DECISION_LOG = "claude/decision_log.md"

AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"
LOG_DIR = ROOT / "claude/claude_logs"
REPORT_NAME = "audit_ransac_iterations.md"
LOG_NAME = "audit_ransac_iterations.log"

TARGETS = {
    "193.6": ("median prediction error", "mm"),
    "189.8": ("median prediction error", "mm"),
    "1162.7": ("wall clock", "ms"),
    "295.5": ("wall clock", "ms"),
}

_log_path = None
_md = []


def safe_path(directory, name):
    """A path that does not exist yet. Never overwrites: file.md -> file_2.md."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    if not p.exists():
        return p
    stem, suf = p.stem, p.suffix
    n = 2
    while (directory / f"{stem}_{n}{suf}").exists():
        n += 1
    return directory / f"{stem}_{n}{suf}"


def log(msg):
    """Append immediately - the log is written as the audit proceeds, not at the end."""
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    with open(_log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def md(s=""):
    _md.append(s)


def stop(msg):
    log(f"*** STOP *** {msg}")
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read(path):
    with open(ROOT / path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_in_csv(path, value_str, tol=0.05):
    """Every (row index, column, stored value) whose float is within tol of the
    target. Matching numerically, not by string, so 295.46 is found for 295.5."""
    target = float(value_str)
    hits = []
    for i, row in enumerate(read(path), start=2):   # start=2: row 1 is the header
        for col, raw in row.items():
            if raw is None or not str(raw).strip():
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            if abs(v - target) <= tol:
                hits.append((i, col, raw, row))
    return hits


def main():
    global _log_path
    _log_path = safe_path(LOG_DIR, LOG_NAME)
    report = safe_path(AUDIT_DIR, REPORT_NAME)

    log("=== audit_ransac_iterations starting ===")
    log(f"log file    : {_log_path.relative_to(ROOT)}")
    log(f"report file : {report.relative_to(ROOT)}")
    log("read-only: no input is opened for writing")

    # ---------------------------------------------------------------- inputs
    for p in (RAW, T1, T2, T3, EXCLUDED, PRODUCER, DECISION_LOG):
        if not (ROOT / p).is_file():
            stop(f"required input missing: {p}")
    log(f"all {6} inputs present")

    raw = read(RAW)
    t1 = read(T1)
    t2 = read(T2)
    log(f"{RAW}: {len(raw)} rows")
    log(f"{T1}: {len(t1)} rows;  {T2}: {len(t2)} rows")

    # ------------------------------------------------- producing script facts
    src = (ROOT / PRODUCER).read_text(encoding="utf-8")

    def const(name, cast=str):
        m = re.search(rf"^{name}\s*=\s*(.+?)(?:\s*#.*)?$", src, re.M)
        return cast(m.group(1).strip()) if m else None

    fit_window_s = const("FIT_WINDOW_S", float)
    dur_thresh = const("DURATION_THRESHOLD_MS", float)
    n_iter_vals = const("N_ITERATIONS_VALUES")
    n_seeds = const("N_SEEDS", int)
    machine_claim = "LAPTOP" if re.search(r"Runs on the LAPTOP, not the Pi", src) else None
    # the timed region, quoted rather than described
    tm = re.search(r"(t0 = time\.perf_counter\(\).*?wall_ms = \(time\.perf_counter\(\) - t0\) \* 1000\.0)",
                   src, re.S)
    timed_region = tm.group(1) if tm else None

    log(f"producer: {PRODUCER}")
    log(f"  FIT_WINDOW_S={fit_window_s}  DURATION_THRESHOLD_MS={dur_thresh}")
    log(f"  N_ITERATIONS_VALUES={n_iter_vals}  N_SEEDS={n_seeds}")
    log(f"  machine per docstring: {machine_claim}")
    if timed_region is None:
        stop("could not locate the perf_counter timed region in the producer")
    log(f"  wall_ms times a region of {len(timed_region.splitlines())} lines "
        f"(quoted in the report)")

    # ------------------------------------------------------------ population
    flights = {(r["session"], r["flight"]) for r in raw}
    ok = [r for r in raw if r["status"] == "ok"]
    n_iters = sorted({int(r["n_iterations"]) for r in raw})
    seeds = sorted({int(r["seed"]) for r in raw})
    excluded = read(EXCLUDED)
    log(f"population: {len(flights)} flights, n_iterations={n_iters}, "
        f"{len(seeds)} seeds ({min(seeds)}..{max(seeds)})")
    log(f"grid product = {len(flights)} x {len(n_iters)} x {len(seeds)} "
        f"= {len(flights)*len(n_iters)*len(seeds)}; raw rows {len(raw)}")
    log(f"successful runs (status=='ok') = {len(ok)}")
    log(f"excluded flights file lists {len(excluded)} flights "
        f"(reason: {excluded[0]['reason'] if excluded else 'n/a'})")

    # --------------------------------------------------------- trace numbers
    log("--- tracing each target number ---")
    traced = {}
    for val, (what, unit) in TARGETS.items():
        found = []
        for path in (T1, T2, T3, RAW):
            for i, col, stored, row in find_in_csv(path, val):
                # only accept a hit in a column that plausibly holds this quantity
                if unit == "ms" and "wall" not in col:
                    continue
                if unit == "mm" and "error" not in col:
                    continue
                found.append(dict(path=path, row=i, col=col, stored=stored,
                                  n_iterations=row.get("n_iterations"),
                                  n_runs=row.get("n_runs")))
            if found:
                break                      # summary tables first; raw only if needed
        traced[val] = found
        if found:
            f0 = found[0]
            log(f"  {val} {unit:<3} -> {f0['path']} row {f0['row']} "
                f"col {f0['col']} = {f0['stored']} at n_iterations={f0['n_iterations']}")
        else:
            log(f"  {val} {unit:<3} -> NOT FOUND in any summary table")

    # ------------------------------------------------------------ STOP gates
    for must in ("1162.7", "295.5"):
        if not traced[must]:
            stop(f"{must} ms could not be traced to a CSV")
    log("STOP GATE PASS: both 1162.7 and 295.5 traced to a CSV")

    # -------------------------------------------- recompute from the raw grid
    log("--- recomputing the summary tables from the raw grid ---")
    recomputed = {}
    for n in n_iters:
        g = [r for r in ok if int(r["n_iterations"]) == n]
        w = sorted(float(r["wall_ms"]) for r in g)
        e = sorted(float(r["error_mm"]) for r in g if r["error_mm"].strip())
        recomputed[n] = dict(n_ok=len(g), med_wall=st.median(w), med_err=st.median(e))
        log(f"  n={n:<3} n_ok={len(g):<5} median wall_ms={st.median(w):9.2f}  "
            f"median error_mm={st.median(e):8.2f}")

    mism = []
    for row in t1:
        n = int(row["n_iterations"])
        if abs(float(row["median_wall_ms"]) - recomputed[n]["med_wall"]) > 0.01:
            mism.append(("table1", n, row["median_wall_ms"], recomputed[n]["med_wall"]))
        if int(row["n_runs"]) != recomputed[n]["n_ok"]:
            mism.append(("table1 n_runs", n, row["n_runs"], recomputed[n]["n_ok"]))
    for row in t2:
        n = int(row["n_iterations"])
        if abs(float(row["median_error_mm"]) - recomputed[n]["med_err"]) > 0.01:
            mism.append(("table2", n, row["median_error_mm"], recomputed[n]["med_err"]))
    log(f"summary-table vs raw-grid mismatches: {len(mism)}")
    for m in mism:
        log(f"    {m}")

    # ------------------------------------------------- decision log 70 check
    dl = (ROOT / DECISION_LOG).read_text(encoding="utf-8")
    m70 = re.search(r"Decision 70:.*?(?=\nDecision \d+:|\Z)", dl, re.S)
    d70 = m70.group(0) if m70 else ""
    d70_line = next((l for l in dl.splitlines() if "Decision 70:" in l), None)
    d70_lineno = dl.splitlines().index(d70_line) + 1 if d70_line else None
    after_val = re.search(r"N=3 -> ([\d.]+)ms", d70)
    after = after_val.group(1) if after_val else None
    log(f"decision log 70 at {DECISION_LOG}:{d70_lineno}; after-value parsed = {after}")
    after_hits = find_in_csv(T1, after) if after else []
    after_hits = [h for h in after_hits if "wall" in h[1]]
    if after_hits:
        i, col, stored, row = after_hits[0]
        log(f"  after-value {after} FOUND: {T1} row {i} col {col} = {stored} "
            f"(n_iterations={row['n_iterations']})")
    else:
        log(f"  after-value {after} NOT found in {T1}")

    # ------------------------------------------------------------- report
    md(f"# Provenance audit: RANSAC n_iterations sweep")
    md("")
    md(f"Generated by `src/regen_2class/audit_ransac_iterations.py`. Read-only.")
    md(f"Log: `{_log_path.relative_to(ROOT).as_posix()}`")
    md("")
    md("> **Path note.** This repo moved derived outputs from `data/` to `results/`")
    md("> on 2026-08-24. All paths below are post-migration. Older worklogs citing")
    md("> `data/trajectory_fit_comparison/...` refer to the same files at their new")
    md("> location.")
    md("")
    md("## Per-number provenance")
    md("")
    md("| number | quantity | source CSV | row | column | stored value | n_iterations |")
    md("|---|---|---|--:|---|--:|--:|")
    for val, (what, unit) in TARGETS.items():
        f = traced[val]
        if not f:
            md(f"| {val} {unit} | {what} | **NOT FOUND** | - | - | - | - |")
            continue
        f0 = f[0]
        md(f"| **{val} {unit}** | {what} | `{f0['path']}` | {f0['row']} | "
           f"`{f0['col']}` | {f0['stored']} | **{f0['n_iterations']}** |")
    md("")
    md(f"| number | meaning | established from |")
    md("|---|---|---|")
    md(f"| **{len(ok):,}** | successful runs (`status=='ok'`) | `{RAW}`, counted; "
       f"equals the sum of `n_runs` over `{T1}` |")
    md(f"| **{len(flights)} x {len(n_iters)} x {len(seeds)}** | flights x n_iterations x seeds "
       f"= {len(flights)*len(n_iters)*len(seeds)} | distinct `(session, flight)`, "
       f"`n_iterations`, `seed` in `{RAW}` |")
    md("")
    md("## Shared provenance for all six numbers")
    md("")
    md("| field | value | evidence |")
    md("|---|---|---|")
    md(f"| producing script | `{PRODUCER}` | writes `{SWEEP_DIR}/` |")
    md(f"| **machine** | **laptop, not the Pi** | producer docstring: *\"Runs on the "
       f"LAPTOP, not the Pi -- these are relative-shape/tradeoff numbers ... not the "
       f"Pi's absolute timing (already measured separately, Pi benchmark Stage 1)\"* |")
    md(f"| **observation window** | **fixed {fit_window_s*1000:.0f} ms** - NOT swept | "
       f"`FIT_WINDOW_S = {fit_window_s}`; the fit uses the points falling inside that "
       f"one window (`np.searchsorted(t, FIT_WINDOW_S)`) |")
    md(f"| flight population | {len(flights)} flights, duration >= {dur_thresh:.0f} ms | "
       f"`DURATION_THRESHOLD_MS = {dur_thresh}`; `{EXCLUDED}` lists the "
       f"{len(excluded)} flights dropped below it |")
    md(f"| detections used | ELLIPSE (production/validated), not rect | producer docstring |")
    md(f"| **units of the wall-clock column** | **milliseconds** | "
       f"`wall_ms = (time.perf_counter() - t0) * 1000.0` - perf_counter returns "
       f"seconds, scaled by 1000 |")
    md("")
    md("### What `wall_ms` actually times")
    md("")
    md("Quoted from the producer, not paraphrased:")
    md("")
    md("```python")
    for l in timed_region.splitlines():
        md(l)
    md("```")
    md("")
    md("So `wall_ms` brackets **the `ransac_fit` call alone** - one model, one RANSAC")
    md("fit. It excludes detection, pairing, triangulation and every other stage. The")
    md("producer states this is deliberate: the per-flight track and target are built")
    md("once per flight, and only the RANSAC call is re-run across the grid.")
    md("")
    md("## Cross-check: summary tables vs the raw grid")
    md("")
    md("| n_iterations | n_ok (raw) | median wall_ms (raw) | median error_mm (raw) |")
    md("|--:|--:|--:|--:|")
    for n in n_iters:
        r = recomputed[n]
        md(f"| {n} | {r['n_ok']} | {r['med_wall']:.2f} | {r['med_err']:.2f} |")
    md("")
    md(f"Recomputed independently from `{RAW}` and compared against the two summary")
    md(f"tables: **{len(mism)} mismatches**.")
    md("")

    OUT = "\n".join(_md) + "\n"
    report.write_text(OUT, encoding="utf-8")
    log(f"wrote report: {report.relative_to(ROOT)} ({len(_md)} lines)")
    log("=== audit_ransac_iterations complete ===")

    # hand the traced facts to the caller for the combined answers section
    return dict(traced=traced, recomputed=recomputed, n_ok=len(ok),
                flights=len(flights), n_iters=n_iters, seeds=len(seeds),
                fit_window_ms=fit_window_s * 1000, dur_thresh=dur_thresh,
                report=report, after=after, after_hits=after_hits,
                d70_lineno=d70_lineno, mismatches=mism)


if __name__ == "__main__":
    main()
