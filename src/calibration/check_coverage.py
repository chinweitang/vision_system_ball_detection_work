"""
Validate checkerboard coverage for an intrinsic calibration image set, so gaps
can be caught (and fill-in frames shot) before tearing down the rig.

Run from anywhere:
    python src/calibration/check_coverage.py [camA|camB|<path-to-folder>]

Defaults to camA, i.e. ..\\..\\data\\calibration_captures\\calib_intrinsic_camA\\
relative to this script. Pass "camB" for the other camera, or a full path to
check an arbitrary folder of img_????.png frames.

Outputs:
  - Per-image DETECTED/FAILED report, and a list of FAILED images at the end
    (these are reshoot/discard candidates, and explain bare heatmap regions).
  - coverage_heatmap.png saved into the image folder.
  - A 3x3 zone report plus an explicit check of the 4 frame corners and 4
    edges (worst region for fisheye distortion), and a final PASS/GAPS summary.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt

PATTERN_SIZE = (7, 11)  # internal corners (columns, rows)
IMG_WIDTH, IMG_HEIGHT = 1456, 1088

# Fraction of width/height used for the corner/edge margin regions below.
EDGE_MARGIN_FRAC = 0.15
# Zones (of 9) or corner/edge regions with fewer than this fraction of the
# total detected corners are flagged as under-covered.
UNDERCOVERED_FRAC = 0.05


def detect_corners(gray):
    """
    Detect the PATTERN_SIZE internal chessboard corners in a grayscale image.
    Tries findChessboardCornersSB first (robust to the fisheye distortion at
    frame edges); falls back to the classic detector + cornerSubPix.
    This block is reused as-is by the intrinsic calibration script.

    Returns (found: bool, corners: np.ndarray of shape (N, 2) or None).
    """
    found, corners = cv2.findChessboardCornersSB(
        gray, PATTERN_SIZE,
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
    )
    if found:
        return True, corners.reshape(-1, 2)

    found, corners = cv2.findChessboardCorners(
        gray, PATTERN_SIZE,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if found:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        return True, corners.reshape(-1, 2)

    return False, None


def resolve_image_dir(target):
    root = Path(__file__).resolve().parents[2]
    candidate = Path(target)
    if candidate.is_dir():
        return candidate.resolve()
    return (root / "data/calibration_captures" / f"calib_intrinsic_{target}").resolve()


def region_counts(points, regions):
    """points: (N,2) array of (x, y). regions: dict of name -> (x0, x1, y0, y1)."""
    counts = {}
    for name, (x0, x1, y0, y1) in regions.items():
        mask = (points[:, 0] >= x0) & (points[:, 0] < x1) & (points[:, 1] >= y0) & (points[:, 1] < y1)
        counts[name] = int(mask.sum())
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="camA",
                         help="camA / camB, or a full path to the image folder")
    args = parser.parse_args()

    image_dir = resolve_image_dir(args.target)
    image_paths = sorted(image_dir.glob("img_*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No img_*.png frames found in: {image_dir}")

    print(f"Checking coverage in: {image_dir}")
    print(f"Found {len(image_paths)} image(s).\n")

    all_corners = []
    failed = []

    for path in image_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"{path.name}: FAILED (could not read image)")
            failed.append(path.name)
            continue

        found, corners = detect_corners(img)
        if found:
            print(f"{path.name}: DETECTED")
            all_corners.append(corners)
        else:
            print(f"{path.name}: FAILED")
            failed.append(path.name)

    print()
    if failed:
        print(f"{len(failed)} image(s) FAILED detection:")
        for name in failed:
            print(f"  - {name}")
    else:
        print("All images passed detection.")
    print()

    if not all_corners:
        print("No corners detected in any image - cannot build coverage report.")
        sys.exit(1)

    points = np.concatenate(all_corners, axis=0)
    total = len(points)

    # -- Heatmap ------------------------------------------------------------
    bins_x, bins_y = 73, 55  # ~20px per bin at this resolution
    heatmap, _, _ = np.histogram2d(
        points[:, 0], points[:, 1],
        bins=[bins_x, bins_y],
        range=[[0, IMG_WIDTH], [0, IMG_HEIGHT]],
    )
    heatmap = heatmap.T  # so rows correspond to y for imshow

    plt.figure(figsize=(8, 6))
    plt.imshow(heatmap, extent=[0, IMG_WIDTH, IMG_HEIGHT, 0], cmap="inferno", interpolation="nearest")
    plt.colorbar(label="corner count")
    plt.title(f"Corner coverage heatmap - {args.target} ({len(all_corners)}/{len(image_paths)} images detected)")
    plt.xlabel("x (px)")
    plt.ylabel("y (px)")
    plt.tight_layout()
    heatmap_path = image_dir / "coverage_heatmap.png"
    plt.savefig(heatmap_path, dpi=150)
    print(f"Saved heatmap to: {heatmap_path}\n")

    # -- 3x3 zone report ------------------------------------------------------
    zone_w, zone_h = IMG_WIDTH / 3, IMG_HEIGHT / 3
    zone_regions = {}
    for row in range(3):
        for col in range(3):
            name = f"zone[{row},{col}]"
            zone_regions[name] = (col * zone_w, (col + 1) * zone_w, row * zone_h, (row + 1) * zone_h)

    zone_counts = region_counts(points, zone_regions)
    undercovered_threshold = UNDERCOVERED_FRAC * total

    print("3x3 zone report:")
    gaps = []
    for name, count in zone_counts.items():
        pct = 100 * count / total
        flag = ""
        if count < undercovered_threshold:
            flag = "  <-- UNDER-COVERED"
            gaps.append(f"{name} ({count} corners, {pct:.1f}% of total)")
        print(f"  {name}: {count} corners ({pct:.1f}%){flag}")
    print()

    # -- Explicit corner / edge check -----------------------------------------
    mx = int(IMG_WIDTH * EDGE_MARGIN_FRAC)
    my = int(IMG_HEIGHT * EDGE_MARGIN_FRAC)

    corner_regions = {
        "top-left corner":     (0, mx, 0, my),
        "top-right corner":    (IMG_WIDTH - mx, IMG_WIDTH, 0, my),
        "bottom-left corner":  (0, mx, IMG_HEIGHT - my, IMG_HEIGHT),
        "bottom-right corner": (IMG_WIDTH - mx, IMG_WIDTH, IMG_HEIGHT - my, IMG_HEIGHT),
    }
    edge_regions = {
        "top edge":    (mx, IMG_WIDTH - mx, 0, my),
        "bottom edge": (mx, IMG_WIDTH - mx, IMG_HEIGHT - my, IMG_HEIGHT),
        "left edge":   (0, mx, my, IMG_HEIGHT - my),
        "right edge":  (IMG_WIDTH - mx, IMG_WIDTH, my, IMG_HEIGHT - my),
    }

    print("Frame corner / edge check (worst region for fisheye distortion):")
    for label, regions in (("corners", corner_regions), ("edges", edge_regions)):
        counts = region_counts(points, regions)
        for name, count in counts.items():
            pct = 100 * count / total
            flag = ""
            if count < undercovered_threshold:
                flag = "  <-- UNDER-COVERED"
                gaps.append(f"{name} ({count} corners, {pct:.1f}% of total)")
            print(f"  {name}: {count} corners ({pct:.1f}%){flag}")
    print()

    # -- Summary --------------------------------------------------------------
    if not gaps:
        print("PASS: coverage looks complete.")
    else:
        print("GAPS: the following regions need fill-in frames before you tear down the rig:")
        for gap in gaps:
            print(f"  - {gap}")


if __name__ == "__main__":
    main()
