# flight_velocity_angle_binner.py
#
# Batch: for every flight in data/2026_07_21_gym/ball_flights AND
# data/2026_07_15_gym/ball_flights (whichever have completed ball_in_frame
# curation), compute initial launch speed + elevation angle (world frame) at
# two fit-window sizes, so Chin Wei can choose stratified hand-labelling bin
# edges (Link B, context.md §4.9) from the real distribution instead of
# guessing bins upfront. This script computes and plots the distribution
# ONLY -- it does not choose or apply bin edges.
#
# Reuses (imports, does not re-derive or modify):
#   triangulate, load_calib, ACCEL_HARD_LO/HI, ACCEL_NOMINAL_LO/HI, FRAME_DT
#       <- src/stereo/label_vs_detection.py
#   fit_constant_accel
#       <- src/stereo/trajectory_fit.py
#   filter_trajectory_outliers
#       <- src/image_processing/02_adjacent_frame_differencing/detector_core.py
#          (imported via a sys.path trick, matching the existing pattern used
#          by src/stereo/pixel_velocity_correction.py and
#          src/stereo/triangulate_flight.py, since that folder name starts
#          with a digit and isn't importable as a normal dotted module path)
#
# Each session has its OWN extrinsics (calibration_outputs/<session_calib>/
# stereo_extrinsic.npz) and its OWN world-frame registration (world-
# registration does not survive across sessions/mountings, unlike extrinsics
# -- context.md SS4.8):
#   2026_07_21_gym: TWO registrations (flights <=60 -> registration1, >60 ->
#     registration2) -- data/2026_07_21_gym/flight_binning/
#     world_frame_validation/registration{1,2}_world_transform.npz, from
#     src/registration/world_frame_validate_2026_07_21.py.
#   2026_07_15_gym: ONE registration for the whole session --
#     data/2026_07_15_gym/flight_binning/world_frame_validation/
#     registration_world_transform.npz, from
#     src/registration/world_frame_validate_2026_07_15.py.
#
# Flight-list source: the tuned-detector detection CSVs themselves
# (results/detector_tuning/detections/<STAGE>/<session>/, from
# src/image_processing/02_adjacent_frame_differencing/
# 11_generate_detections_csv.py) -- a flight only appears here if it already
# had completed ball_in_frame curation, so flights that haven't been curated
# yet are simply not enumerated (not written as per-row "skipped" CSV
# entries -- see the worklog for why this changed from the single-session
# version, which explicitly listed them).
#
# Usage:
#   python src/stereo/flight_velocity_angle_binner.py

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from src.stereo.label_vs_detection import (
    triangulate, load_calib, ACCEL_HARD_LO, ACCEL_HARD_HI,
    ACCEL_NOMINAL_LO, ACCEL_NOMINAL_HI, FRAME_DT,
)
from src.stereo.trajectory_fit import fit_constant_accel

DETECTOR_DIR = ROOT / "src" / "image_processing" / "02_adjacent_frame_differencing"
if str(DETECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(DETECTOR_DIR))
import detector_core as dc  # noqa: E402

# ---- paths ------------------------------------------------------------
CALIB_DIR = ROOT / "calibration_outputs"
OUT_DIR = ROOT / "results/flight_binning"  # cross-session output, NOT under either session's own folder
LOG_PATH = ROOT / "claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md"

DETECTIONS_ROOT = ROOT / "results/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3"

SESSIONS = {
    "2026_07_21_gym": dict(
        extrinsics_path=ROOT / "calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz",
        detections_dir=DETECTIONS_ROOT / "2026_07_21_gym",
        world_frame_dir=ROOT / "data/2026_07_21_gym/flight_binning/world_frame_validation",
        registrations=["registration1", "registration2"],
    ),
    "2026_07_15_gym": dict(
        extrinsics_path=ROOT / "calibration_outputs/2026_07_15/stereo_extrinsic.npz",
        detections_dir=DETECTIONS_ROOT / "2026_07_15_gym",
        world_frame_dir=ROOT / "data/2026_07_15_gym/flight_binning/world_frame_validation",
        registrations=["registration"],
    ),
}

# ---- constants ----------------------------------------------------------
# N=5/N=10 (frame COUNT) were tuned implicitly against the OLD, sparser
# detector, where 10 paired frames typically spanned 166-350 ms of real time
# -- enough to resolve gravity's ~9.8 m/s^2 curvature against detector noise.
# The tuned detector's ~3x higher combined_rate means paired frames are now
# nearly consecutive, so "first 10 paired frames" spans only ~150 ms for
# almost every flight -- too short (confirmed empirically: N=10 gave 21/30
# implausible-accel fits in a 30-flight check, N=20 gave 0/29, N=30 gave
# 0/28 -- see worklog). N=20/N=30 restores a comparable real-time span to
# what N=10 used to cover under the old detector.
N_VALUES = [20, 30]
MIN_FIT_FRAMES = 3  # predict_sweep.py's own gate value (inline there, not a named constant)
GRAVITY_CROSSCHECK_WARN_DEG = 45.0  # predict_sweep.py's own inline threshold, value reused
REGISTRATION1_MAX_FLIGHT = 60  # 2026_07_21_gym only: flights <= 60 -> registration1, > 60 -> registration2


def log_append(message: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {message}\n")


# ---- I/O ------------------------------------------------------------------

def load_detections3(csv_path: Path) -> dict:
    """Detections CSV (frame_number,u,v) -> {frame_number: (u,v)}."""
    dets = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            dets[int(row["frame_number"])] = (float(row["u"]), float(row["v"]))
    return dets


def flight_sort_key(flight_id: str):
    m = re.search(r"(\d+)$", flight_id)
    return int(m.group(1)) if m else flight_id


def find_flight_ids(detections_dir: Path) -> list:
    """Flight ids present as BOTH cam0 and cam1 detection CSVs in detections_dir."""
    cam0_ids = {p.name[:-len("_cam0_detections.csv")]
                for p in detections_dir.glob("*_cam0_detections.csv")}
    cam1_ids = {p.name[:-len("_cam1_detections.csv")]
                for p in detections_dir.glob("*_cam1_detections.csv")}
    return sorted(cam0_ids & cam1_ids, key=flight_sort_key)


def load_world_transform(world_frame_dir: Path, reg_name: str):
    npz_path = world_frame_dir / f"{reg_name}_world_transform.npz"
    data = np.load(npz_path)
    return data["Z_world"].astype(np.float64), str(data["img_stem"])


def registration_for(session: str, flight_id: str) -> str:
    if session == "2026_07_21_gym":
        fid_num = int(re.search(r"(\d+)$", flight_id).group(1))
        return "registration1" if fid_num <= REGISTRATION1_MAX_FLIGHT else "registration2"
    return "registration"


# ---- per-flight processing --------------------------------------------------

def process_flight(session: str, flight_id: str, detections_dir: Path,
                    K0, D0, K1, D1, P0, P1, Z_world_by_reg: dict, rows: list) -> None:
    registration = registration_for(session, flight_id)
    Z_world, reg_img_stem = Z_world_by_reg[registration]

    cam0_csv = detections_dir / f"{flight_id}_cam0_detections.csv"
    cam1_csv = detections_dir / f"{flight_id}_cam1_detections.csv"
    log_prefix = f"{session}/{flight_id}"

    def skip_row(N, reason):
        rows.append(dict(session=session, flight_id=flight_id, N_requested=N, N_used="",
                          status="skipped", speed_m_s="", elevation_deg="", accel_mag_m_s2="",
                          gravity_crosscheck_diff_deg="", registration_used=registration,
                          n_paired_frames="", flag_reason=reason))

    raw0 = load_detections3(cam0_csv)
    raw1 = load_detections3(cam1_csv)
    filt0 = dc.filter_trajectory_outliers(raw0)
    filt1 = dc.filter_trajectory_outliers(raw1)

    paired_frames = sorted(set(filt0) & set(filt1))
    if len(paired_frames) < MIN_FIT_FRAMES:
        for N in N_VALUES:
            skip_row(N, f"only {len(paired_frames)} paired frames after filtering (< {MIN_FIT_FRAMES})")
        log_append(f"{log_prefix}: SKIPPED (both N) -- only {len(paired_frames)} paired frames "
                   f"after filtering (raw cam0={len(raw0)}, cam1={len(raw1)}, "
                   f"filtered cam0={len(filt0)}, cam1={len(filt1)})")
        return

    fit_frames_all = paired_frames[:max(N_VALUES)]
    uv0 = np.array([filt0[f] for f in fit_frames_all])
    uv1 = np.array([filt1[f] for f in fit_frames_all])
    xyz_pts = triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)

    t0_frame = fit_frames_all[0]
    t_all = np.array([(f - t0_frame) * FRAME_DT for f in fit_frames_all])

    for N in N_VALUES:
        actual_N = min(N, len(fit_frames_all))
        if actual_N < MIN_FIT_FRAMES:
            skip_row(N, f"adjusted window ({actual_N} frames) still < {MIN_FIT_FRAMES}")
            log_append(f"{log_prefix} N={N}: SKIPPED -- adjusted window only {actual_N} frames")
            continue

        adjusted_note = f" (adjusted from {N} -> {actual_N}, flight has fewer usable frames)" \
            if actual_N != N else ""

        t_win = t_all[:actual_N]
        xyz_win = xyz_pts[:actual_N]
        p0, v0, a = fit_constant_accel(t_win, xyz_win)

        accel_mag_m_s2 = float(np.linalg.norm(a)) / 1000.0
        if not (ACCEL_HARD_LO <= accel_mag_m_s2 <= ACCEL_HARD_HI):
            skip_row(N, f"implausible |a|={accel_mag_m_s2:.2f} m/s^2 outside hard gate "
                         f"[{ACCEL_HARD_LO},{ACCEL_HARD_HI}]{adjusted_note}")
            log_append(f"{log_prefix} N={N}: SKIPPED -- implausible |a|={accel_mag_m_s2:.2f} m/s^2 "
                       f"(hard gate [{ACCEL_HARD_LO},{ACCEL_HARD_HI}]){adjusted_note}")
            continue

        speed_m_s = float(np.linalg.norm(v0)) / 1000.0
        elevation_deg = float(np.degrees(np.arcsin(
            np.clip(np.dot(v0, Z_world) / np.linalg.norm(v0), -1.0, 1.0))))

        fit_up = -a / np.linalg.norm(a)
        cross_check_diff_deg = float(np.degrees(np.arccos(
            np.clip(np.dot(fit_up, Z_world), -1.0, 1.0))))

        flags = []
        if not (ACCEL_NOMINAL_LO <= accel_mag_m_s2 <= ACCEL_NOMINAL_HI):
            flags.append(f"|a|={accel_mag_m_s2:.2f} outside nominal band "
                          f"[{ACCEL_NOMINAL_LO},{ACCEL_NOMINAL_HI}]")
        if cross_check_diff_deg > GRAVITY_CROSSCHECK_WARN_DEG:
            flags.append(f"gravity crosscheck diff={cross_check_diff_deg:.1f} deg "
                          f"> {GRAVITY_CROSSCHECK_WARN_DEG}")
        if adjusted_note:
            flags.append(adjusted_note.strip(" ()"))
        flag_reason = "; ".join(flags)

        rows.append(dict(session=session, flight_id=flight_id, N_requested=N, N_used=actual_N,
                          status="ok", speed_m_s=f"{speed_m_s:.4f}", elevation_deg=f"{elevation_deg:.4f}",
                          accel_mag_m_s2=f"{accel_mag_m_s2:.4f}",
                          gravity_crosscheck_diff_deg=f"{cross_check_diff_deg:.4f}",
                          registration_used=registration, n_paired_frames=len(paired_frames),
                          flag_reason=flag_reason))

        if flag_reason:
            log_append(f"{log_prefix} N={N}: FLAGGED -- {flag_reason} "
                       f"(speed={speed_m_s:.2f} m/s, elev={elevation_deg:.1f} deg)")


# ---- plotting ---------------------------------------------------------------

def joint_scatter(ax_main, ax_top, ax_right, angles, speeds, flagged_mask, title):
    ok = ~flagged_mask
    ax_main.scatter(angles[ok], speeds[ok], s=25, alpha=0.65, c="tab:blue", label="ok")
    if flagged_mask.any():
        ax_main.scatter(angles[flagged_mask], speeds[flagged_mask], s=45, alpha=0.85,
                         c="tab:red", marker="^", label="flagged (gravity crosscheck / accel)")
    ax_main.set_xlabel("elevation angle (deg, world frame)")
    ax_main.set_ylabel("speed (m/s)")
    ax_main.legend(fontsize=8, loc="best")
    ax_main.grid(alpha=0.3)

    ax_top.hist(angles, bins=20, color="tab:blue", alpha=0.7)
    ax_top.set_title(title)
    ax_top.tick_params(labelbottom=False)

    ax_right.hist(speeds, bins=20, orientation="horizontal", color="tab:blue", alpha=0.7)
    ax_right.tick_params(labelleft=False)


def make_joint_plot(rows_N, N, out_path):
    fig = plt.figure(figsize=(9, 8))
    gs = fig.add_gridspec(4, 4, hspace=0.05, wspace=0.05)
    ax_top = fig.add_subplot(gs[0, 0:3])
    ax_main = fig.add_subplot(gs[1:4, 0:3])
    ax_right = fig.add_subplot(gs[1:4, 3])

    angles = np.array([float(r["elevation_deg"]) for r in rows_N])
    speeds = np.array([float(r["speed_m_s"]) for r in rows_N])
    flagged_mask = np.array([bool(r["flag_reason"]) for r in rows_N])

    joint_scatter(ax_main, ax_top, ax_right, angles, speeds, flagged_mask,
                  f"Speed vs elevation angle, N={N} (n={len(rows_N)}, "
                  f"{int(flagged_mask.sum())} flagged)")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")


def make_overlay_histograms(rows_ok, out_path):
    fig, (ax_speed, ax_angle) = plt.subplots(1, 2, figsize=(12, 5))
    plot_colors = ["tab:blue", "tab:orange"]
    colors = dict(zip(N_VALUES, plot_colors))
    for N in N_VALUES:
        sub = [r for r in rows_ok if r["N_requested"] == N]
        speeds = [float(r["speed_m_s"]) for r in sub]
        angles = [float(r["elevation_deg"]) for r in sub]
        ax_speed.hist(speeds, bins=20, alpha=0.5, label=f"N={N} (n={len(sub)})", color=colors[N])
        ax_angle.hist(angles, bins=20, alpha=0.5, label=f"N={N} (n={len(sub)})", color=colors[N])
    n_label = f"N={N_VALUES[0]} vs N={N_VALUES[1]}"
    ax_speed.set_xlabel("speed (m/s)")
    ax_speed.set_ylabel("count")
    ax_speed.set_title(f"Speed distribution, {n_label}")
    ax_speed.legend()
    ax_speed.grid(alpha=0.3)
    ax_angle.set_xlabel("elevation angle (deg)")
    ax_angle.set_title(f"Elevation angle distribution, {n_label}")
    ax_angle.legend()
    ax_angle.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")


def make_sensitivity_plot(rows_ok, out_path):
    """For each (session, flight) with BOTH N_VALUES[0] and N_VALUES[1]
    surviving, draw a line from its lower-N point to its higher-N point in
    (angle, speed) space -- visualises how much the window-size choice moves
    an individual flight's result."""
    N_lo, N_hi = N_VALUES[0], N_VALUES[1]
    by_flight = {}
    for r in rows_ok:
        by_flight.setdefault((r["session"], r["flight_id"]), {})[r["N_requested"]] = r

    fig, ax = plt.subplots(figsize=(8, 7))
    n_both = 0
    for key, by_N in by_flight.items():
        if N_lo in by_N and N_hi in by_N:
            n_both += 1
            a_lo, s_lo = float(by_N[N_lo]["elevation_deg"]), float(by_N[N_lo]["speed_m_s"])
            a_hi, s_hi = float(by_N[N_hi]["elevation_deg"]), float(by_N[N_hi]["speed_m_s"])
            ax.plot([a_lo, a_hi], [s_lo, s_hi], "-", color="grey", alpha=0.4, linewidth=1, zorder=1)
            ax.scatter([a_lo], [s_lo], c="tab:blue", s=20, zorder=2)
            ax.scatter([a_hi], [s_hi], c="tab:orange", s=20, zorder=2)

    ax.scatter([], [], c="tab:blue", s=30, label=f"N={N_lo}")
    ax.scatter([], [], c="tab:orange", s=30, label=f"N={N_hi}")
    ax.plot([], [], "-", color="grey", alpha=0.6, label=f"same flight, N={N_lo} -> N={N_hi}")
    ax.set_xlabel("elevation angle (deg, world frame)")
    ax.set_ylabel("speed (m/s)")
    ax.set_title(f"N-sensitivity: same flight at N={N_lo} vs N={N_hi} (n={n_both} flights with both)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")


def make_session_scatter(rows_ok, out_path):
    """Speed vs elevation, colored by session, at the larger N value --
    lets the user see whether the two sessions (library vs gym) occupy
    different regions of the distribution before combining them."""
    N_hi = N_VALUES[1]
    fig, ax = plt.subplots(figsize=(8, 7))
    session_colors = {"2026_07_21_gym": "tab:green", "2026_07_15_gym": "tab:purple"}
    for session, color in session_colors.items():
        sub = [r for r in rows_ok if r["N_requested"] == N_hi and r["session"] == session]
        angles = [float(r["elevation_deg"]) for r in sub]
        speeds = [float(r["speed_m_s"]) for r in sub]
        ax.scatter(angles, speeds, s=25, alpha=0.7, c=color, label=f"{session} (n={len(sub)})")
    ax.set_xlabel("elevation angle (deg, world frame)")
    ax.set_ylabel("speed (m/s)")
    ax.set_title(f"Speed vs elevation angle by session, N={N_hi}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"-> {out_path}")


# ---- main ---------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_append("=== flight_velocity_angle_binner.py: batch run starting (multi-session) ===")

    rows = []
    for session, cfg in SESSIONS.items():
        log_append(f"--- session {session} ---")

        K0, D0, K1, D1, R, T = load_calib(CALIB_DIR, cfg["extrinsics_path"])
        P0 = np.hstack([np.eye(3), np.zeros((3, 1))])
        P1 = np.hstack([R, T.reshape(3, 1)])

        Z_world_by_reg = {}
        for reg in cfg["registrations"]:
            Z_world_by_reg[reg] = load_world_transform(cfg["world_frame_dir"], reg)
        log_append(f"{session}: loaded world transform(s): " +
                   ", ".join(f"{reg} from {Z_world_by_reg[reg][1]}" for reg in cfg["registrations"]))

        flight_ids = find_flight_ids(cfg["detections_dir"])
        log_append(f"{session}: {len(flight_ids)} flights with tuned-detector detection CSVs")

        for i, flight_id in enumerate(flight_ids, start=1):
            process_flight(session, flight_id, cfg["detections_dir"],
                            K0, D0, K1, D1, P0, P1, Z_world_by_reg, rows)
            if i % 20 == 0:
                log_append(f"{session}: progress {i}/{len(flight_ids)} flights processed")

        log_append(f"{session}: done, {len(flight_ids)} flights processed")

    log_append(f"batch loop complete across all sessions: {len(rows)} rows written")

    csv_path = OUT_DIR / "flight_velocity_angle.csv"
    fieldnames = ["session", "flight_id", "N_requested", "N_used", "status", "speed_m_s",
                  "elevation_deg", "accel_mag_m_s2", "gravity_crosscheck_diff_deg",
                  "registration_used", "n_paired_frames", "flag_reason"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"-> {csv_path}")
    log_append(f"wrote CSV -> {csv_path} ({len(rows)} rows)")

    rows_ok = [r for r in rows if r["status"] == "ok"]
    n_skipped = sum(1 for r in rows if r["status"] == "skipped")
    n_flagged = sum(1 for r in rows if r["status"] == "ok" and r["flag_reason"])
    for session in SESSIONS:
        n_ok_sess = sum(1 for r in rows_ok if r["session"] == session)
        log_append(f"summary [{session}]: {n_ok_sess} ok rows")
    log_append(f"summary [overall]: {len(rows_ok)} ok rows, {n_skipped} skipped rows, "
               f"{n_flagged} flagged (of the ok rows), out of {len(rows)} total attempted rows")

    for N in N_VALUES:
        rows_N = [r for r in rows_ok if r["N_requested"] == N]
        if not rows_N:
            log_append(f"N={N}: no surviving rows -- skipping its plot")
            continue

        make_joint_plot(rows_N, N, OUT_DIR / f"distribution_N{N}.png")
        log_append(f"plotted distribution_N{N}.png ({len(rows_N)} points, "
                   f"{int(sum(1 for r in rows_N if r['flag_reason']))} flagged)")

    make_overlay_histograms(rows_ok, OUT_DIR / "distribution_overlay_histograms.png")
    log_append("plotted distribution_overlay_histograms.png")

    make_sensitivity_plot(rows_ok, OUT_DIR / "distribution_N_sensitivity.png")
    log_append("plotted distribution_N_sensitivity.png")

    make_session_scatter(rows_ok, OUT_DIR / "distribution_by_session.png")
    log_append("plotted distribution_by_session.png")

    log_append("=== flight_velocity_angle_binner.py: batch run complete ===")


if __name__ == "__main__":
    main()
