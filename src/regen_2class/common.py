"""Shared constants and helpers for the two-class (SHORT/LONG) figure set.

Extracted so the numbered step scripts do not duplicate the palette, the axis
naming, the percentile definition or the class/deadline rules. Per
claude_rules.md Section 3: shared logic lives in an unnumbered importable module.

Every step script reads only existing CSVs under data/. Nothing here re-runs the
Pi sweep, detection, or any fitting job.
"""
import csv
import math

# ---- paths (all read-only inputs, except OUT_DIR) ----
SWEEP_CSV = "data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv"
LTC_CSV = "data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv"
CROSSING_CSV = "data/prediction/01_crossing_plane_setup/crossing_classification.csv"
OUT_DIR = "data/regenerate_figures/"
JOIN_CSV = OUT_DIR + "two_class_join.csv"

# ---- class scheme ----
# SHORT = FLAT union MID, LONG = LOB. Equivalent to a 45 degree elevation cut;
# step_1_classes.py asserts that equivalence against elevation_deg.
CLASS_OF_BIN = {"FLAT": "SHORT", "MID": "SHORT", "LOB": "LONG"}
CLASSES = ["SHORT", "LONG"]
ELEVATION_CUT_DEG = 45.0

# ---- axis naming ----
# "observation window" rather than "prediction cutoff T", matching the pipeline
# timing diagram. Used in axis labels, annotations, legends and captions alike.
X_LABEL = "observation window (ms)"

# ---- target-mode budget ----
# 100 ms perceptual window minus 16 ms projector input lag. The projector spec
# (BenQ X500i, 4K@60Hz, 16 ms) is measured END TO END and already includes the
# frame period, so panel / quantisation / render terms must NOT be added on top -
# doing so double-counts. Pi render and compositor latency is neglected.
TARGET_SLACK_MS = 84.0
BUDGET_MS = -TARGET_SLACK_MS
BUDGET_LABEL = "-84 ms  -  target mode budget (4K@60Hz, 16ms input lag, BenQ X500i)"

# ---- surface / ink ----
SURF, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8a84"

# Categorical slots 1 and 8. validate_palette.js --mode light: all six checks PASS
# (CVD dE 21.6 protan, normal-vision dE 32.3).
CLASS_COLOR = {"SHORT": "#2a78d6", "LONG": "#e34948"}

# Outcome bands, bottom -> top. The reserved status palette FAILS here: its
# warning/serious pair measures normal-vision dE 13.6, under the hard 15 floor,
# and those two are adjacent in the mandated band order. These four validate:
# lightness PASS, chroma PASS, CVD PASS (worst adjacent 9.1 protan),
# normal-vision PASS (22.9). Contrast WARNs on two slots, relieved by the legend,
# the direct best-window labels and the companion summary CSV as a table view.
BAND_ORDER = ["success", "wrong", "late", "no_response"]
BAND_COLOR = {"success": "#1baf7a", "wrong": "#eda100",
              "late": "#4a3aa7", "no_response": "#e34948"}


def percentile(values, p):
    """Linear-interpolated percentile, matching numpy's default method."""
    v = sorted(values)
    if not v:
        raise ValueError("percentile of an empty sequence")
    k = (len(v) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def read_csv(path):
    """csv.DictReader, not a naive comma split - crossing_classification.csv
    carries crossing_vel_xyz as a quoted JSON-style list inside one field."""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_join():
    """Rows of the step-3 join, one per (session, flight, observation window)."""
    return read_csv(JOIN_CSV)


def windows_of(rows):
    return sorted({int(r["T_ms"]) for r in rows})


def per_flight_map(rows):
    """Collapse the 24-rows-per-flight grid to {(session, flight): (class, ltc)}.
    Keyed on the FULL (session, flight) pair - flight_13 exists in two sessions,
    so a bare flight id silently merges two different flights."""
    return {(r["session"], r["flight"]):
            (r["cls2"], float(r["launch_to_crossing_ms"])) for r in rows}


def class_durations(rows):
    per = per_flight_map(rows)
    return {c: [d for cls, d in per.values() if cls == c] for c in CLASSES}


def deadlines(rows):
    """deadline(class) = floor(min(launch_to_crossing_ms) / 10) * 10.

    Min-anchored so no flight in the class can cross before its own deadline
    elapses. Computed from data on every call; no deadline value is hardcoded
    anywhere in this file set.
    """
    return {c: math.floor(min(v) / 10.0) * 10.0
            for c, v in class_durations(rows).items()}


def margin_p95(rows, windows=None):
    """{class: [deadline - window - latency_p95(window)]} over the window grid.

    latency_ms exists only on status=='ok' rows, so the p95 is taken over those.
    Returns (margins, n_ok_counts).
    """
    windows = windows or windows_of(rows)
    dl = deadlines(rows)
    margins, n_ok = {}, {}
    for c in CLASSES:
        margins[c], n_ok[c] = [], []
        for w in windows:
            lat = [float(r["latency_ms"]) for r in rows
                   if r["cls2"] == c and int(r["T_ms"]) == w and r["status"] == "ok"]
            n_ok[c].append(len(lat))
            margins[c].append(dl[c] - w - percentile(lat, 0.95))
    return margins, n_ok


def max_usable_window(rows, windows=None):
    """Largest observation window whose margin_p95 still sits inside the target
    budget, i.e. margin_p95 >= BUDGET_MS. Same inequality as the outcome sweep's
    in_time test (t_obs + latency <= crossing + TARGET_SLACK_MS), rearranged."""
    windows = windows or windows_of(rows)
    margins, _ = margin_p95(rows, windows)
    out = {}
    for c in CLASSES:
        feasible = [w for w, m in zip(windows, margins[c]) if m >= BUDGET_MS]
        out[c] = max(feasible) if feasible else None
    return out


def style_axes(ax, grid_axis="both"):
    ax.set_facecolor(SURF)
    ax.grid(True, axis=grid_axis, color="#e5e4df", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d5d4cf")
    ax.tick_params(colors=INK2, labelsize=9)
