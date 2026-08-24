"""flight_22: effect of RANSAC on the fixed-gravity-with-drag fit.

Single panel. Three series, all for the SAME model - the one that fixes gravity
and adds quadratic drag. Only the source of the points, and whether RANSAC is
applied, differ between them.

Inputs, all read-only and never written back:
    results/trajectory_fit_comparison/phase2/prediction_sweep.csv         (plain)
    results/trajectory_fit_comparison/phase2/prediction_sweep_ransac.csv  (RANSAC)
    data/2026_07_15_gym/ball_flights/flight_22/timestamps.csv             (real times)
    results/detector_tuning/detections/03_.../flight_22_cam{0,1}_detections.csv
    data/2026_07_15_gym/ball_flights/flight_22_cam{0,1}_labels.csv

X-AXIS IS REAL ELAPSED TIME, NOT A NOMINAL CADENCE
The pipeline that produced the two sweep CSVs converts frames to seconds with a
constant (`FRAME_DT = 16.652e-3  # s per frame, as given`,
label_vs_detection.py:42). This figure does not. It reads the flight's own
per-frame sensor timestamps and takes, for each frame present on both cameras,

    t_frame = (sensor_timestamp_ns[cam0] + sensor_timestamp_ns[cam1]) / 2

then

    observation window (ms) = (t_frame[last_fit_frame] - t_frame[first_fit_frame]) / 1e6

The cam0/cam1 AVERAGE is used rather than cam0 alone, matching
all_flights_common.py:167 - the two cameras' timestamps are not identical, which
is the whole reason sub-frame correction exists in this project.

first_fit_frame is not stored in either CSV, so the fit-frame sequence is
reconstructed from its definition in the source pipeline
(labels ∩ detections, target excluded) and then VALIDATED: the reconstruction
must reproduce the CSV's own `last_fit_frame` column exactly for every N, or the
script stops. Without that check the window start would be a guess.

STOP conditions:
  - the three series do not share an identical set of x values
  - the reconstructed fit-frame sequence disagrees with the CSVs
  - a series label contains a forbidden model code

Outputs:
    results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22.png
    results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22.csv
"""
import csv
import pathlib
import statistics as st
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import clean_figures as CF
import common as C

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAIN_CSV = "results/trajectory_fit_comparison/phase2/prediction_sweep.csv"
RANSAC_CSV = "results/trajectory_fit_comparison/phase2/prediction_sweep_ransac.csv"
TS_CSV = "data/2026_07_15_gym/ball_flights/flight_22/timestamps.csv"
LABEL_CSV = "data/2026_07_15_gym/ball_flights/flight_22/flight_22_cam{cam}_labels.csv"
DET_CSV = ("results/detector_tuning/detections/"
           "03_stride1_thresh16_openk3_area30_circ0.3/2026_07_15_gym/"
           "flight_22_cam{cam}_detections.csv")
OUT_DIR = ROOT / "results/regenerate_figures/ransac_effect_flight22"
OUT_PNG = OUT_DIR / "ransac_effect_flight22.png"
OUT_CSV = OUT_DIR / "ransac_effect_flight22.csv"

FLIGHT = "flight_22"
# trajectory_model_prediction_sweep.py:172 -- scoped to flight_22 only, because
# flight_01's fit frames happen to start at 44 as well and an unscoped set
# produced a false-positive tag in an earlier run.
HANDPICKUP_FRAMES = (44, 47)

SERIES = [
    ("label_plain", "fitted on hand-labelled points", "#2a78d6", "-"),
    ("det_plain", "fitted on detected points, no RANSAC", "#e34948", "-"),
    ("det_ransac", "fitted on detected points, with RANSAC", "#1baf7a", "-"),
]
FORBIDDEN = ["model a", "model b", "model c"]

PAGE_W_IN = 6.6
FS_TITLE, FS_AXIS, FS_TICK, FS_LEGEND, FS_CAP = 11, 9.5, 8, 7.5, 6.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read(path):
    with open(ROOT / path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def frame_times():
    """{frame_index: mean sensor timestamp (ns)} for frames seen on BOTH cameras."""
    per = {}
    with open(ROOT / TS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            per.setdefault(int(r["frame_index"]), {})[r["cam"]] = \
                int(r["sensor_timestamp_ns"])
    return {k: (v["0"] + v["1"]) / 2.0 for k, v in per.items()
            if "0" in v and "1" in v}


def _frames_in(path_tmpl, col_candidates):
    """Frame indices present in a per-camera label or detection CSV."""
    out = {}
    for cam in ("0", "1"):
        p = ROOT / path_tmpl.format(cam=cam)
        if not p.is_file():
            stop(f"missing input: {p.relative_to(ROOT)}")
        with open(p, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            col = next((c for c in col_candidates if c in rd.fieldnames), None)
            if col is None:
                stop(f"no frame column in {p.name}; looked for {col_candidates}, "
                     f"found {rd.fieldnames}")
            out[cam] = {int(float(r[col])) for r in rd if r[col].strip()}
    return out["0"] & out["1"]


def reconstruct_fit_frames(rows):
    """Rebuild the fit-frame sequence the pipeline used, then prove it.

    Definition, from trajectory_model_prediction_sweep.py:143:
        fit_frames = sorted((label_common & det_common) - {target_frame})
    where target_frame = max(label_common).
    """
    label_common = _frames_in(LABEL_CSV, ("frame_number", "frame", "frame_index"))
    det_common = _frames_in(DET_CSV, ("frame_number", "frame", "frame_index"))
    target = max(label_common)
    fit = sorted((label_common & det_common) - {target})

    # PROOF: last_fit_frame(N) must equal fit[N-1] for every N in the CSVs.
    bad = []
    for r in rows:
        n = int(r["N"])
        if n - 1 >= len(fit) or fit[n - 1] != int(r["last_fit_frame"]):
            bad.append((n, int(r["last_fit_frame"]),
                        fit[n - 1] if n - 1 < len(fit) else None))
    if bad:
        stop(f"reconstructed fit-frame sequence disagrees with the CSV at "
             f"{len(bad)} of {len(rows)} windows. First few (N, csv, mine): "
             f"{bad[:5]}. The window START cannot be trusted, so no figure.")
    return fit, target, label_common, det_common


def main():
    plain = [r for r in read(PLAIN_CSV) if r["flight"] == FLIGHT]
    ransac = [r for r in read(RANSAC_CSV) if r["flight"] == FLIGHT]
    print(f"read {PLAIN_CSV}  -> {len(plain)} {FLIGHT} rows")
    print(f"read {RANSAC_CSV} -> {len(ransac)} {FLIGHT} rows")

    ts = frame_times()
    dts = [(ts[b] - ts[a]) / 1e6 for a, b in zip(sorted(ts), sorted(ts)[1:])]
    print(f"\nreal timestamps: {len(ts)} frames on both cameras "
          f"({min(ts)}..{max(ts)})")
    print(f"  inter-frame dt (ms): min {min(dts):.4f}  median {st.median(dts):.4f}"
          f"  max {max(dts):.4f}   [pipeline's nominal constant: 16.6520]")

    fit_frames, target, lab, det = reconstruct_fit_frames(plain)
    print(f"\nfit-frame reconstruction VALIDATED against last_fit_frame for all "
          f"{len(plain)} windows")
    print(f"  label frames {len(lab)}, detection frames {len(det)}, "
          f"target frame {target}")
    print(f"  fit_frames: {len(fit_frames)}, "
          f"[{fit_frames[0]}..{fit_frames[-1]}]")
    f0 = fit_frames[0]
    if f0 not in ts:
        stop(f"first fit frame {f0} has no two-camera timestamp")

    def window_ms(n):
        last = fit_frames[n - 1]
        if last not in ts:
            stop(f"frame {last} has no two-camera timestamp")
        return (ts[last] - ts[f0]) / 1e6

    # ---- assemble, keeping only windows where ALL THREE have a value -----
    p_by = {int(r["N"]): r for r in plain}
    r_by = {int(r["N"]): r for r in ransac}
    cols = {"label_plain": ("err_C_label_mm", p_by),
            "det_plain": ("err_C_det_mm", p_by),
            "det_ransac": ("err_C_det_ransac_mm", r_by)}

    have = {}
    for key, (col, src) in cols.items():
        have[key] = {n for n, r in src.items()
                     if r.get(col, "").strip()}
    common_n = sorted(set.intersection(*have.values()))
    dropped = {key: sorted(set(p_by) - v) for key, v in have.items()}
    print("\nwindows carrying a value, per series:")
    for key, lbl, _, _ in SERIES:
        print(f"  {lbl:<42} {len(have[key]):>3}"
              + (f"   missing N={dropped[key]}" if dropped[key] else ""))
    print(f"  {'-> intersection kept':<42} {len(common_n):>3}")

    series = {}
    for key, (col, src) in cols.items():
        series[key] = [(window_ms(n), float(src[n][col])) for n in common_n]

    # ---- STOP GATE: identical x across the three series ------------------
    xsets = {key: tuple(round(x, 6) for x, _ in v) for key, v in series.items()}
    if len({xsets[k] for k in xsets}) != 1:
        sizes = {k: len(v) for k, v in xsets.items()}
        stop(f"the three series do not share an identical set of x values: {sizes}")
    print(f"\nGATE 1 PASS: all three series share an identical x set "
          f"({len(common_n)} windows, "
          f"{series['label_plain'][0][0]:.1f}..{series['label_plain'][-1][0]:.1f} ms)")

    # ---- shaded band, converted from frames to ms ------------------------
    hp_lo, hp_hi = HANDPICKUP_FRAMES
    if hp_lo not in ts or hp_hi not in ts:
        stop(f"hand-pickup frames {HANDPICKUP_FRAMES} lack two-camera timestamps")
    band = ((ts[hp_lo] - ts[f0]) / 1e6, (ts[hp_hi] - ts[f0]) / 1e6)
    print(f"GATE 2: hand-pickup frames {hp_lo}-{hp_hi} -> "
          f"{band[0]:.1f}..{band[1]:.1f} ms on this axis")

    # ---- caption + terminology gate --------------------------------------
    caption = [
        f"flight_22 only. All three series use the SAME trajectory model - gravity held fixed, quadratic drag added. What differs is the",
        f"source of the fitted points and whether RANSAC is applied, nothing else.",
        f"The hand-labelled series is the PLAIN fit, not a RANSAC one: the contrast being drawn is RANSAC vs no RANSAC on DETECTED points,",
        f"and applying it to the reference as well would blur that.",
        f"x is real elapsed time between the first and last frame of each fit window, from this flight's own per-frame sensor timestamps",
        f"(cam0/cam1 mean). It is NOT the nominal 16.652 ms/frame constant the source pipeline uses; on this flight the two agree to about",
        f"6 microseconds over the longest window, so the distinction is one of provenance rather than a correction.",
        f"Shaded band: confirmed hand-pickup frames {hp_lo}-{hp_hi}, converted to the same ms axis ({band[0]:.0f}-{band[1]:.0f} ms).",
        f"Windows where any series had no value are excluded from ALL THREE, so the x set is identical by construction"
        + (f" - N={dropped['det_ransac']}" if dropped["det_ransac"] else "."),
        f"   dropped, where the RANSAC fit produced no value." if dropped["det_ransac"] else "",
        f"Log y: the series span several orders of magnitude at short windows.",
        f"Sources: {PLAIN_CSV}",
        f"         {RANSAC_CSV}",
    ]
    surfaced = ([lbl for _, lbl, _, _ in SERIES] + caption
                + ["observation window (ms)", "prediction error at target (mm)",
                   "flight_22: effect of RANSAC on the fixed-gravity, drag-included fit"])
    hits = [s for s in surfaced if any(f in s.lower() for f in FORBIDDEN)]
    if hits:
        stop(f"a forbidden model code appears in {len(hits)} user-facing string(s):\n"
             + "\n".join(f"  - {h[:90]}" for h in hits))
    print(f"GATE 3 PASS: none of {FORBIDDEN} appear in the "
          f"{len(surfaced)} user-facing strings")

    # ---- draw -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, 5.0))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)
    ax.set_yscale("log")
    ax.axvspan(band[0], band[1], color="#e34948", alpha=0.10, zorder=1,
               label=f"confirmed hand-pickup frames {hp_lo}-{hp_hi}")
    for key, lbl, colour, ls in SERIES:
        xs = [x for x, _ in series[key]]
        ys = [y for _, y in series[key]]
        ax.plot(xs, ys, ls, color=colour, lw=1.5, zorder=4, label=lbl)
    ax.set_xlabel("observation window (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("prediction error at target (mm)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2, loc="upper right")
    ax.set_title("flight_22: effect of RANSAC on the fixed-gravity, drag-included fit",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=8)

    if CF.clean():
        CF.write_clean(fig, caption, OUT_PNG)
    else:
        gap, floor_y = 0.0163, 0.008
        start_y = floor_y + (len(caption) - 1) * gap
        for i, line in enumerate(caption):
            fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
        fig.tight_layout(rect=[0, start_y + 0.018, 1, 1])
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT_PNG, dpi=300, facecolor=C.SURF)
    plt.close(fig)
    print(f"\nwrote {OUT_PNG.relative_to(ROOT)}")

    # ---- companion CSV ----------------------------------------------------
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["N_frames", "last_fit_frame", "observation_window_ms",
                    "err_hand_labelled_mm", "err_detected_no_ransac_mm",
                    "err_detected_with_ransac_mm", "in_handpickup_band"])
        for i, n in enumerate(common_n):
            x = series["label_plain"][i][0]
            w.writerow([n, fit_frames[n - 1], f"{x:.3f}",
                        f"{series['label_plain'][i][1]:.4f}",
                        f"{series['det_plain'][i][1]:.4f}",
                        f"{series['det_ransac'][i][1]:.4f}",
                        "yes" if band[0] <= x <= band[1] else "no"])
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print("\ninputs not modified")


if __name__ == "__main__":
    main()
