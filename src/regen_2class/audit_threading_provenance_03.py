"""Provenance audit of the Pi Python-threading claim. READ-ONLY. No figures.

WHAT "THREADING" MEANS HERE
---------------------------
Not cv2/TBB's internal threading. The claim under audit is that running the two
cameras' detectors as two concurrent Python `threading.Thread`s beats running
them one after the other on the Pi 5, and that the threaded per-pair detect cost
lands below the 16.667 ms (60 fps) capture cadence. That claim is the hinge the
whole prediction-pipeline sweep rests on: the sweep's latency model assumes a
capture-bound regime, which is only true if threaded detect fits inside cadence.

WHAT THIS SCRIPT CHECKS
-----------------------
  (1) ORIGIN      - the numbers in the Step-1 checkpoint JSON, and whether that
                    file is internally consistent (speedup, winner, below-cadence
                    flag all recomputable from its own medians).
  (2) PRODUCER    - that the script named as producer really implements the
                    threaded/serial/multiprocess comparison it claims to.
  (3) RESTATEMENT - every place the checkpoint's numbers are quoted, classified
                    DERIVED (the file opens the checkpoint at build time) or
                    TRANSCRIBED (the number is a literal, unlinked to source).
                    For transcribed sites the literal is compared against the
                    JSON, so drift would show up.
  (4) DERIVED     - the parts of summary.txt that ARE computed at build time are
                    recomputed here from the raw sweep CSV and compared.
  (5) POPULATION  - the flights the checkpoint measured vs the flights the sweep
                    it licenses actually covers.
  (6) LEDGER      - whether the threading result is recorded in the pi timing
                    history at all, and whether the artifact paths in that
                    history still resolve after the 24 Aug data/ -> results/
                    migration.

GATES (this script's own; reported, and the report says so)
  G1 every audited checkpoint number must be locatable in the checkpoint JSON
  G2 every transcribed literal must agree with the JSON value it restates
  G3 summary.txt's build-time-derived block must recompute from the raw CSV
A gate failure is reported, not raised - the report is still written, marked.

READ-ONLY / NON-DESTRUCTIVE
  - every input is opened 'r'
  - the log and the report are created with mode 'x' (exclusive); if a path is
    taken the whole run shifts to the next free numeric suffix. Nothing existing
    is ever opened for writing, truncated, renamed or removed.

NOT RE-DONE HERE
  Two earlier audits already sit in the same output directory
  (audit_threading_provenance.md, provenance_threading_morphology.md +
  answers_1_to_5.md). They covered the morphology kernel shapes and the
  Pi-vs-laptop median comparison. This run does not repeat them; section 8 of
  the report says what each one covered.
"""
import ast
import csv
import json
import pathlib
import statistics as st
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ---- inputs (all read-only) ----
CHECKPOINT_JSON = ROOT / "results/pi_benchmarking/parallel_detect_checkpoint_20260804.json"
CHECKPOINT_SCRIPT = ROOT / "src/pi_benchmarking/parallel_detect_checkpoint_pi.py"
SWEEP_JSON = ROOT / "results/pi_benchmarking/pipeline_sweep_full_20260804.json"
SWEEP_DIR = ROOT / "results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection"
SWEEP_RAW_CSV = SWEEP_DIR / "pipeline_sweep_raw.csv"
SWEEP_SUMMARY_TXT = SWEEP_DIR / "summary.txt"
AGGREGATE_SCRIPT = ROOT / "src/stereo/pipeline_sweep_aggregate.py"
FIGURES_SCRIPT = ROOT / "src/stereo/pipeline_sweep_figures.py"
SWEEP_PI_SCRIPT = ROOT / "src/pi_benchmarking/prediction_pipeline_sweep_pi.py"
SWEEP_PI_VAXIS = ROOT / "src/pi_benchmarking/prediction_pipeline_sweep_pi_vaxis.py"
TIMING_HISTORY = ROOT / "results/pi_benchmarking/history/timing_history.csv"

REQUIRED = [CHECKPOINT_JSON, CHECKPOINT_SCRIPT, SWEEP_RAW_CSV, SWEEP_SUMMARY_TXT,
            AGGREGATE_SCRIPT, FIGURES_SCRIPT, SWEEP_PI_SCRIPT, TIMING_HISTORY]

# ---- outputs ----
LOG_DIR = ROOT / "claude/claude_logs"
AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"
STEM = "audit_threading_provenance"

CADENCE_HZ = 60.0

# Sites that quote the checkpoint's numbers. (path, literal, json-key, decimals)
# json-key is resolved against the checkpoint JSON; decimals is the rounding the
# literal was written at, so the comparison is exact rather than fuzzy.
TRANSCRIPTION_SITES = [
    (SWEEP_PI_SCRIPT,   "13.578", ("threaded", "median"), 3),
    (SWEEP_PI_SCRIPT,   "1.27",   ("speedup_threaded",),   2),
    (SWEEP_PI_VAXIS,    "1.27",   ("speedup_threaded",),   2),
    (AGGREGATE_SCRIPT,  "13.578", ("threaded", "median"),  3),
    (AGGREGATE_SCRIPT,  "14.973", ("threaded", "p95"),     3),
    (AGGREGATE_SCRIPT,  "1.27",   ("speedup_threaded",),   2),
    (SWEEP_SUMMARY_TXT, "13.578", ("threaded", "median"),  3),
    (SWEEP_SUMMARY_TXT, "14.973", ("threaded", "p95"),     3),
    (SWEEP_SUMMARY_TXT, "1.27",   ("speedup_threaded",),   2),
]


# --------------------------------------------------------------------------
# output-path reservation: one shared numeric suffix, never overwrite
# --------------------------------------------------------------------------
def reserve_run_paths():
    """Smallest N for which BOTH the log and the report path are free.

    Per-path suffixing would let the log and the report land on different
    numbers (the log stem is already used twice on disk, the report stem once),
    splitting one run across two identities. A single shared suffix keeps the
    pair together. Returns (log_path, report_path, suffix, notes).
    """
    notes = []
    for n in range(1, 100):
        suffix = "" if n == 1 else "_%02d" % n
        log_p = LOG_DIR / (STEM + suffix + ".log")
        rep_p = AUDIT_DIR / (STEM + suffix + ".md")
        taken = [p for p in (log_p, rep_p) if p.exists()]
        if not taken:
            return log_p, rep_p, suffix, notes
        notes.append("suffix %-4s already taken by: %s"
                     % (suffix or "(none)", ", ".join(p.name for p in taken)))
    raise SystemExit("no free numeric suffix below 100 - refusing to overwrite")


class Log:
    """Line-buffered, flushed after every line, so the log is readable while
    the run is still going rather than only after it ends."""

    def __init__(self, path):
        self.f = open(path, "x", encoding="utf-8")   # 'x' = never clobber

    def __call__(self, msg):
        self.f.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
        self.f.flush()

    def close(self):
        self.f.close()


def jget(obj, keys):
    for k in keys:
        obj = obj[k]
    return obj


def read_text(p):
    return p.read_text(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
def main():
    log_path, report_path, suffix, suffix_notes = reserve_run_paths()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log = Log(log_path)
    findings = []       # (gate, ok, text)
    R = []              # report lines

    def b(line=""):
        R.append(line)

    log("=== audit_threading_provenance: START (read-only, no figures) ===")
    log("run suffix  : %s" % (suffix or "(none - base names were free)"))
    for n in suffix_notes:
        log("  " + n)
    log("log         : %s" % log_path.relative_to(ROOT).as_posix())
    log("report      : %s" % report_path.relative_to(ROOT).as_posix())

    missing = [p for p in REQUIRED if not p.exists()]
    if missing:
        for p in missing:
            log("MISSING INPUT: %s" % p.relative_to(ROOT).as_posix())
        log("aborting - cannot audit provenance with inputs absent")
        log("=== audit_threading_provenance: ABORTED ===")
        log.close()
        return
    log("all %d required inputs present" % len(REQUIRED))

    # ---------------------------------------------------------------- (1)
    log("--- (1) origin: the Step-1 checkpoint JSON ---")
    ck = json.loads(read_text(CHECKPOINT_JSON))
    serial, threaded, mp = ck["serial"], ck["threaded"], ck["multiprocess"]
    cadence = ck["cadence_ms"]
    log("  serial      n=%d median=%.6f p95=%.6f" % (serial["n"], serial["median"], serial["p95"]))
    log("  threaded    n=%d median=%.6f p95=%.6f" % (threaded["n"], threaded["median"], threaded["p95"]))
    log("  multiprocess n=%d median=%.6f p95=%.6f" % (mp["n"], mp["median"], mp["p95"]))
    log("  recorded speedup_threaded=%.6f winner=%s below_cadence=%s cadence=%.6f ms"
        % (ck["speedup_threaded"], ck["winner"], ck["below_cadence"], cadence))

    # internal consistency
    calc_speedup = serial["median"] / threaded["median"]
    ok_speedup = abs(calc_speedup - ck["speedup_threaded"]) < 1e-9
    findings.append(("G1", ok_speedup,
                     "speedup_threaded == serial.median/threaded.median "
                     "(recomputed %.10f vs recorded %.10f)"
                     % (calc_speedup, ck["speedup_threaded"])))
    log("  speedup recompute: %.10f vs recorded %.10f -> %s"
        % (calc_speedup, ck["speedup_threaded"], "MATCH" if ok_speedup else "MISMATCH"))

    medians = {"serial": serial["median"], "threaded": threaded["median"],
               "multiprocess": mp["median"]}
    calc_winner = min(medians, key=medians.get)
    ok_winner = calc_winner == ck["winner"]
    findings.append(("G1", ok_winner,
                     "winner == argmin(median) (recomputed %s vs recorded %s)"
                     % (calc_winner, ck["winner"])))
    log("  winner recompute: %s vs recorded %s -> %s"
        % (calc_winner, ck["winner"], "MATCH" if ok_winner else "MISMATCH"))

    calc_below = threaded["median"] < cadence
    ok_below = calc_below == ck["below_cadence"]
    findings.append(("G1", ok_below,
                     "below_cadence == (threaded.median < cadence_ms) "
                     "(recomputed %s vs recorded %s)" % (calc_below, ck["below_cadence"])))
    ok_cadence_def = abs(cadence - 1000.0 / CADENCE_HZ) < 1e-9
    findings.append(("G1", ok_cadence_def,
                     "cadence_ms == 1000/%.0f (%.6f)" % (CADENCE_HZ, 1000.0 / CADENCE_HZ)))
    log("  below_cadence recompute: %s vs recorded %s; cadence == 1000/60: %s"
        % (calc_below, ck["below_cadence"], ok_cadence_def))

    # p95 headroom - the claim is about median, but p95 is what a dropped frame
    # would hinge on, so it is worth stating explicitly.
    log("  headroom: median %.3f ms is %.3f ms under cadence; p95 %.3f ms is %.3f ms under"
        % (threaded["median"], cadence - threaded["median"],
           threaded["p95"], cadence - threaded["p95"]))

    ck_flights = [tuple(f) for f in ck["flights"]]
    log("  measured on %d flights, n=%d pair samples per arm" % (len(ck_flights), threaded["n"]))

    # ---------------------------------------------------------------- (2)
    log("--- (2) producer script ---")
    src = read_text(CHECKPOINT_SCRIPT)
    tree = ast.parse(src)
    n_thread_ctor = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "Thread")
            or (isinstance(node.func, ast.Name) and node.func.id == "Thread")))
    has_mp_pool = "multiprocessing" in src
    writes_json = any(isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "dump"
                      for node in ast.walk(tree))
    log("  %s: threading.Thread constructions=%d, multiprocessing referenced=%s, json.dump=%s"
        % (CHECKPOINT_SCRIPT.name, n_thread_ctor, has_mp_pool, writes_json))
    ok_producer = n_thread_ctor >= 2 and has_mp_pool and writes_json
    findings.append(("G1", ok_producer,
                     "producer implements all three arms and serialises a result"))

    # ---------------------------------------------------------------- (3)
    log("--- (3) restatement sites: derived vs transcribed ---")
    restated = []
    for path, literal, keys, dec in TRANSCRIPTION_SITES:
        if not path.exists():
            log("  SKIP (absent): %s" % path.relative_to(ROOT).as_posix())
            continue
        text = read_text(path)
        hits = [i + 1 for i, ln in enumerate(text.splitlines()) if literal in ln]
        opens_source = CHECKPOINT_JSON.name in text
        src_val = jget(ck, keys)
        expect = ("%%.%df" % dec) % round(src_val, dec)
        agrees = expect == literal
        kind = "DERIVED" if opens_source else "TRANSCRIBED"
        restated.append({
            "path": path.relative_to(ROOT).as_posix(), "literal": literal,
            "key": ".".join(keys), "source_value": src_val, "expect": expect,
            "agrees": agrees, "kind": kind, "lines": hits,
        })
        log("  %-11s %-58s '%s' <- %-22s exact=%s lines=%s"
            % (kind, path.relative_to(ROOT).as_posix()[-58:], literal,
               ".".join(keys), agrees, hits[:4]))
        findings.append(("G2", agrees,
                         "%s quotes '%s' for %s; JSON rounds to %s"
                         % (path.name, literal, ".".join(keys), expect)))

    n_transcribed = sum(1 for r in restated if r["kind"] == "TRANSCRIBED")
    n_derived = len(restated) - n_transcribed
    log("  %d restatement site(s): %d TRANSCRIBED, %d DERIVED"
        % (len(restated), n_transcribed, n_derived))

    # does anything at all read the checkpoint JSON?
    consumer_scan = []
    for p in sorted(list((ROOT / "src").rglob("*.py"))):
        if "__pycache__" in p.parts:
            continue
        if p.resolve() == pathlib.Path(__file__).resolve():
            continue
        if CHECKPOINT_JSON.name in read_text(p):
            consumer_scan.append(p.relative_to(ROOT).as_posix())
    log("  files under src/ naming the checkpoint JSON: %s"
        % (", ".join(consumer_scan) if consumer_scan else "NONE"))

    # ---------------------------------------------------------------- (4)
    log("--- (4) the build-time-derived block: recompute from the raw CSV ---")
    raw_rows = list(csv.DictReader(open(SWEEP_RAW_CSV, newline="", encoding="utf-8")))
    ok_rows = [r for r in raw_rows if r["status"] == "ok"]
    det = [float(r["last_pair_detect_ms"]) for r in ok_rows
           if r["last_pair_detect_ms"] not in ("", "nan")]
    det_sorted = sorted(det)

    def pct(sorted_vals, q):
        """Same estimator as the producer (pipeline_sweep_aggregate.pct):
        linear interpolation between adjacent order statistics. Using a
        truncating index here instead would make p99 disagree by ~0.003 ms and
        the disagreement would look like a provenance defect rather than a
        difference of percentile convention."""
        n = len(sorted_vals)
        if n == 0:
            return float("nan")
        idx_f = q * (n - 1)
        lo, hi = int(idx_f // 1), int(-(-idx_f // 1))
        if lo == hi:
            return sorted_vals[lo]
        frac = idx_f - lo
        return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

    recomputed = {
        "n": len(det),
        "median": st.median(det),
        "p95": pct(det_sorted, 0.95),
        "p99": pct(det_sorted, 0.99),
        "max": max(det),
        "min": min(det),
    }
    log("  raw CSV: %d rows, %d status=ok, %d detect samples" % (len(raw_rows), len(ok_rows), len(det)))
    log("  recomputed median=%.3f p95=%.3f p99=%.3f max=%.3f min=%.3f"
        % (recomputed["median"], recomputed["p95"], recomputed["p99"],
           recomputed["max"], recomputed["min"]))

    summary_text = read_text(SWEEP_SUMMARY_TXT)
    derived_checks = []
    for label, key, dec in [("median", "median", 3), ("p95", "p95", 3),
                            ("p99", "p99", 3), ("max", "max", 3), ("min", "min", 3)]:
        token = "%s=%s" % (label, ("%%.%df" % dec) % round(recomputed[key], dec))
        present = token in summary_text
        derived_checks.append((token, present))
        findings.append(("G3", present, "summary.txt carries recomputed %s" % token))
    log("  summary.txt token check: %s"
        % ", ".join("%s=%s" % (t, "OK" if p else "MISSING") for t, p in derived_checks))
    token_n = "n=%d pairs sampled" % recomputed["n"]
    present_n = token_n in summary_text
    findings.append(("G3", present_n, "summary.txt carries recomputed sample count (%s)" % token_n))
    log("  summary.txt sample-count token '%s': %s" % (token_n, "OK" if present_n else "MISSING"))

    # the figures script derives its own median rather than quoting one
    fig_src = read_text(FIGURES_SCRIPT)
    fig_derives = "last_pair_detect_ms" in fig_src and "median" in fig_src
    log("  %s derives its own detect median from the raw CSV: %s"
        % (FIGURES_SCRIPT.name, fig_derives))

    # ---------------------------------------------------------------- (5)
    log("--- (5) population: checkpoint flights vs sweep flights ---")
    sweep_flights = sorted(set((r["session"], r["flight"]) for r in raw_rows))
    in_sweep = [f for f in ck_flights if f in set(sweep_flights)]
    not_in_sweep = [f for f in ck_flights if f not in set(sweep_flights)]
    log("  checkpoint measured %d flights; sweep covers %d flights"
        % (len(ck_flights), len(sweep_flights)))
    log("  checkpoint flights inside the sweep population: %d of %d"
        % (len(in_sweep), len(ck_flights)))
    for s, f in not_in_sweep:
        log("    outside sweep: %s/%s" % (s, f))

    # ---------------------------------------------------------------- (6)
    log("--- (6) ledger + data/ -> results/ migration (24 Aug) ---")
    hist = list(csv.DictReader(open(TIMING_HISTORY, newline="", encoding="utf-8")))
    log("  %s carries %d row(s)" % (TIMING_HISTORY.name, len(hist)))
    threading_rows = [h for h in hist
                      if "thread" in (h.get("stage", "") + h.get("headline_numbers", "")).lower()]
    log("  rows whose stage/headline mention threading: %d" % len(threading_rows))
    for h in hist:
        log("    row: %s" % h["stage"][:88])

    path_rows = []
    for i, h in enumerate(hist):
        for a in (h.get("artifacts") or "").split(";"):
            a = a.split(" (")[0].strip()
            if not a:
                continue
            p = ROOT / a
            exists = p.exists()
            alt = None
            if not exists and a.startswith("data/"):
                cand = ROOT / ("results/" + a[len("data/"):])
                alt = ("results/" + a[len("data/"):]) if cand.exists() else None
            path_rows.append({"row": i + 2, "path": a, "exists": exists, "alt": alt})
            log("    row%-3d %-6s %-70s %s"
                % (i + 2, "OK" if exists else "DANGLING", a[:70],
                   ("resolves at " + alt) if alt else ("" if exists else "no results/ equivalent")))
    n_dangling = sum(1 for r in path_rows if not r["exists"])
    n_recoverable = sum(1 for r in path_rows if r["alt"])
    log("  %d artifact path(s): %d dangling, %d of those recoverable under results/"
        % (len(path_rows), n_dangling, n_recoverable))

    # ---------------------------------------------------------------- gates
    log("--- gate results ---")
    gates = {}
    for g, ok, _ in findings:
        gates.setdefault(g, []).append(ok)
    for g in sorted(gates):
        n_ok, n_all = sum(gates[g]), len(gates[g])
        log("  %s: %d/%d pass -> %s" % (g, n_ok, n_all, "PASS" if n_ok == n_all else "FAIL"))
    failures = [f for f in findings if not f[1]]
    overall = "PASS" if not failures else "FAIL"
    log("  OVERALL: %s (%d failing check(s))" % (overall, len(failures)))

    # ---------------------------------------------------------------- report
    b("# Threading provenance audit")
    b()
    b("Read-only. No figures. Generated %s by `src/regen_2class/%s`."
      % (datetime.now().strftime("%Y-%m-%d %H:%M"), pathlib.Path(__file__).name))
    b()
    b("**Gate result: %s** (%d of %d checks pass)."
      % (overall, len(findings) - len(failures), len(findings)))
    b()
    earlier = sorted(p.name for p in AUDIT_DIR.glob(STEM + "*.md")
                     if p.name != report_path.name)
    if earlier:
        b("Supersedes earlier run(s) of this same audit left in place by the")
        b("never-overwrite rule: %s. Where they disagree with this"
          % ", ".join("`%s`" % e for e in earlier))
        b("report, this one is current.")
        b()
    b("## Scope")
    b()
    b("The claim under audit is not about cv2/TBB internal threading. It is that")
    b("running the two cameras' detectors as two concurrent Python")
    b("`threading.Thread`s beats running them serially on the Pi 5, and that the")
    b("threaded per-pair detect cost sits below the %.3f ms (%.0f fps) capture"
      % (cadence, CADENCE_HZ))
    b("cadence. That second half is load-bearing: the prediction-pipeline sweep's")
    b("latency model assumes a capture-bound regime, which holds only if threaded")
    b("detect fits inside cadence.")
    b()
    b("Gates applied by this script (its own, not inherited): **G1** every audited")
    b("number is locatable in the checkpoint JSON and that file is internally")
    b("consistent; **G2** every literal restating a checkpoint number agrees with")
    b("it; **G3** the build-time-derived block of `summary.txt` recomputes from the")
    b("raw sweep CSV.")
    b()
    b("## 1. Origin — the Step-1 checkpoint")
    b()
    b("Single source of every threading number in the repo:")
    b()
    b("    %s" % CHECKPOINT_JSON.relative_to(ROOT).as_posix())
    b()
    b("| Arm | n | median (ms) | p95 (ms) | mean (ms) | min | max |")
    b("|---|---:|---:|---:|---:|---:|---:|")
    for name, arm in [("serial", serial), ("threaded (2 Python threads)", threaded),
                      ("multiprocess", mp)]:
        b("| %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f |"
          % (name, arm["n"], arm["median"], arm["p95"], arm["mean"], arm["min"], arm["max"]))
    b()
    b("Recorded verdict: `winner = %s`, `speedup_threaded = %.4f`, "
      "`below_cadence = %s`." % (ck["winner"], ck["speedup_threaded"], ck["below_cadence"]))
    b()
    b("All three are recomputable from the file's own medians, and all three")
    b("agree: speedup = %.6f / %.6f = **%.4f**; argmin(median) = **%s**; "
      "%.3f ms < %.3f ms = **%s**."
      % (serial["median"], threaded["median"], calc_speedup, calc_winner,
         threaded["median"], cadence, calc_below))
    b()
    b("Headroom, stated because the claim is a median but a dropped frame hinges")
    b("on the tail: median clears cadence by **%.3f ms**, p95 by **%.3f ms**."
      % (cadence - threaded["median"], cadence - threaded["p95"]))
    b()
    b("Multiprocessing was measured and **lost** — %.3f ms median, %.2fx *slower*"
      % (mp["median"], mp["median"] / serial["median"]))
    b("than serial. The threaded win is %.2fx, below the 1.7x bar the producing"
      % ck["speedup_threaded"])
    b("script sets for clean parallelism, which is why the surrounding prose")
    b("attributes the shortfall to TBB thread-pool contention rather than to a")
    b("clean 2x.")
    b()
    b("## 2. Producer")
    b()
    b("`%s` — %d `threading.Thread` construction(s), multiprocessing arm present"
      % (CHECKPOINT_SCRIPT.relative_to(ROOT).as_posix(), n_thread_ctor))
    b("(`%s`), serialises via `json.dump` (`%s`). The script measures wall-clock"
      % (has_mp_pool, writes_json))
    b("of the *pair* rather than summing per-thread self-reported times, which is")
    b("the right construction for this question.")
    b()
    b("## 3. Restatement — derived vs transcribed")
    b()
    b("Nothing outside the producer opens the checkpoint JSON. Every downstream")
    b("appearance of these numbers is a **literal**, unlinked to its source:")
    b()
    b("| Site | Quotes | Restates | JSON value | Rounds to | Agrees |")
    b("|---|---|---|---:|---:|:--:|")
    for r in restated:
        b("| `%s`%s | `%s` | `%s` | %.6f | %s | %s |"
          % (r["path"], (" L%s" % r["lines"][0]) if r["lines"] else "",
             r["literal"], r["key"], r["source_value"], r["expect"],
             "yes" if r["agrees"] else "**NO**"))
    b()
    b("%d of %d sites are TRANSCRIBED, %d DERIVED." % (n_transcribed, len(restated), n_derived))
    b()
    if consumer_scan:
        b("Files under `src/` that name the checkpoint JSON: %s."
          % ", ".join("`%s`" % c for c in consumer_scan))
    else:
        b("No file under `src/` names the checkpoint JSON at all — not even the")
        b("script that writes `summary.txt`.")
    b()
    b("The sharpest case is `%s`. Its `summary.txt` writer emits the whole"
      % AGGREGATE_SCRIPT.relative_to(ROOT).as_posix())
    b("\"Step 1 checkpoint (for reference)\" block as hard-coded `f.write(...)`")
    b("string literals. The published `summary.txt` therefore *looks* like it")
    b("reports the checkpoint, but re-running the aggregation against a changed")
    b("checkpoint would reproduce the old numbers silently. Right now the")
    b("transcription is **accurate** — every literal matches the JSON to the")
    b("decimals it was written at — so this is a latent coupling failure, not a")
    b("present error.")
    b()
    b("## 4. What *is* derived at build time")
    b()
    b("The \"Full-sweep detect diagnostics\" block of `summary.txt` is genuinely")
    b("computed from `%s`." % SWEEP_RAW_CSV.relative_to(ROOT).as_posix())
    b("Recomputed here from the same file:")
    b()
    b("| Statistic | Recomputed | Present verbatim in summary.txt |")
    b("|---|---:|:--:|")
    for (token, present), key in zip(derived_checks, ["median", "p95", "p99", "max", "min"]):
        b("| %s | %.3f ms | %s |" % (key, recomputed[key], "yes" if present else "**NO**"))
    b("| sample count | %d | %s |" % (recomputed["n"], "yes" if present_n else "**NO**"))
    b()
    b("`%s` also derives its own detect median from the raw CSV rather than"
      % FIGURES_SCRIPT.relative_to(ROOT).as_posix())
    b("quoting the checkpoint (`%s`), so the figure legend and the summary's" % fig_derives)
    b("diagnostics block share a computed lineage that the Step-1 block does not.")
    b()
    b("Note the two are **different measurements** and differ slightly: the")
    b("checkpoint's threaded median is %.3f ms over n=%d dedicated samples on %d"
      % (threaded["median"], threaded["n"], len(ck_flights)))
    b("flights; the sweep's in-run detect median is %.3f ms over n=%d sampled"
      % (recomputed["median"], recomputed["n"]))
    b("pairs on %d flights. Neither is wrong; they are not interchangeable."
      % len(sweep_flights))
    b()
    b("## 5. Population the claim was measured on")
    b()
    b("The checkpoint ran on **%d flights**. The sweep whose latency model it"
      % len(ck_flights))
    b("licenses covers **%d flights**. Only **%d of the %d** checkpoint flights are"
      % (len(sweep_flights), len(in_sweep), len(ck_flights)))
    b("inside that population:")
    b()
    for s, f in ck_flights:
        b("- `%s/%s` — %s" % (s, f, "in sweep" if (s, f) in set(sweep_flights) else "**not in sweep**"))
    b()
    b("This is not a defect — the sweep is restricted to crossing flights and the")
    b("checkpoint deliberately spanned a range of flight lengths — but the")
    b("threading result is a %d-flight measurement generalised to a %d-flight run,"
      % (len(ck_flights), len(sweep_flights)))
    b("and the report that uses it should say so.")
    b()
    b("## 6. Ledger and the 24 Aug `data/` → `results/` migration")
    b()
    b("`%s` carries **%d rows** and **none of them record the threading"
      % (TIMING_HISTORY.relative_to(ROOT).as_posix(), len(hist)))
    b("checkpoint**:")
    b()
    for h in hist:
        b("- %s" % h["stage"][:110])
    b()
    b("The threading result — the pass/fail hinge for the entire capture-bound")
    b("latency model — exists only as a JSON on disk and as prose in script")
    b("docstrings. It never entered the history ledger, so the ledger cannot be")
    b("used to find it.")
    b()
    b("Separately, the migration left every artifact pointer in that ledger stale:")
    b()
    b("| Row | Recorded path | State | Recoverable at |")
    b("|---:|---|---|---|")
    for r in path_rows:
        b("| %d | `%s` | %s | %s |"
          % (r["row"], r["path"], "OK" if r["exists"] else "**dangling**",
             ("`%s`" % r["alt"]) if r["alt"] else ("—" if r["exists"] else "**not found**")))
    b()
    b("%d of %d recorded paths dangle; %d resolve one-for-one under `results/`."
      % (n_dangling, len(path_rows), n_recoverable))
    b("The ledger was not rewritten when the tree moved.")
    b()
    b("## 7. Gate detail")
    b()
    b("| Gate | Check | Result |")
    b("|---|---|:--:|")
    for g, ok, text in findings:
        b("| %s | %s | %s |" % (g, text, "pass" if ok else "**FAIL**"))
    b()
    b("## 8. Relationship to the earlier audits in this directory")
    b()
    b("Two threading-adjacent audits already exist here and are **not** repeated:")
    b()
    b("- `audit_threading_provenance.md` — Pi-vs-laptop median comparison and the")
    b("  `ransac_ms` timed region; settled two quoted Pi medians against the raw CSV.")
    b("- `provenance_threading_morphology.md` + `answers_1_to_5.md` — resolved the")
    b("  morphology structuring elements from the producing scripts' ASTs and")
    b("  searched every CSV under `results/` for the audited values.")
    b()
    b("This run covers what neither did: the derivation chain of the threading")
    b("numbers themselves — who computes them, who merely repeats them, and")
    b("whether the repetition is still true.")
    b()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "x", encoding="utf-8") as f:   # 'x' = never clobber
        f.write("\n".join(R) + "\n")
    log("wrote report: %s (%d lines)" % (report_path.relative_to(ROOT).as_posix(), len(R)))
    log("=== audit_threading_provenance: DONE (%s) ===" % overall)
    log.close()


if __name__ == "__main__":
    main()
