"""Step 14 - replot results/flight_binning/distribution_N30.png with uniform markers.

A REPLOT of frozen results. Reads the existing per-flight CSV that the binner
already wrote; no trajectory fit is re-run, no detection job is re-run. The
original figure is left in place - this writes a NEW file under
results/regenerate_figures/.

Two changes from the original:
  1. Every point is a blue circle. The original split the sample into "ok" (blue
     circles) and "flagged" (red triangles) on the |a| nominal-band and
     gravity-crosscheck tests. All 162 flights are RETAINED - only the styling
     distinction is dropped, so n is unchanged.
  2. All text and numbers enlarged.

Layout, bins, colour and figure proportions otherwise match
flight_velocity_angle_binner.make_joint_plot() so the two are comparable.

Source model, for the record: the speed and elevation plotted here come from
fit_constant_accel (Model A, free gravity, no drag, no RANSAC) over the first
N=30 paired frames. speed = |v0|, elevation = asin(v0 . Z_world / |v0|).
"""
import csv

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC_CSV = "results/flight_binning/flight_velocity_angle.csv"
OUT_PNG = "results/regenerate_figures/distribution_N30_uniform_markers.png"
N_REQUESTED = "30"

# enlarged from the original defaults (~10 pt / 8 pt legend)
FS_LABEL, FS_TICK, FS_TITLE = 17, 15, 19


def main():
    with open(SRC_CSV, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["N_requested"] == N_REQUESTED and r["status"] == "ok"]
    angles = np.array([float(r["elevation_deg"]) for r in rows])
    speeds = np.array([float(r["speed_m_s"]) for r in rows])
    n_flagged = sum(1 for r in rows if r["flag_reason"].strip())
    print(f"N={N_REQUESTED}: {len(rows)} flights with status=ok "
          f"({n_flagged} of them were red triangles in the original, now drawn "
          f"identically; none dropped)")

    fig = plt.figure(figsize=(10.5, 9.5))
    gs = fig.add_gridspec(4, 4, hspace=0.05, wspace=0.05)
    ax_top = fig.add_subplot(gs[0, 0:3])
    ax_main = fig.add_subplot(gs[1:4, 0:3])
    ax_right = fig.add_subplot(gs[1:4, 3])

    # single marker style for the whole sample
    ax_main.scatter(angles, speeds, s=42, alpha=0.65, c="tab:blue")
    ax_main.set_xlabel("elevation angle (deg, world frame)", fontsize=FS_LABEL)
    ax_main.set_ylabel("speed (m/s)", fontsize=FS_LABEL)
    ax_main.tick_params(labelsize=FS_TICK)
    ax_main.grid(alpha=0.3)

    ax_top.hist(angles, bins=20, color="tab:blue", alpha=0.7)
    ax_top.set_title(f"Speed vs elevation angle, N={N_REQUESTED} (n={len(rows)})",
                     fontsize=FS_TITLE)
    ax_top.tick_params(labelbottom=False, labelsize=FS_TICK)

    ax_right.hist(speeds, bins=20, orientation="horizontal", color="tab:blue", alpha=0.7)
    ax_right.tick_params(labelleft=False, labelsize=FS_TICK)

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PNG}")
    print("original results/flight_binning/distribution_N30.png left untouched")


if __name__ == "__main__":
    main()
