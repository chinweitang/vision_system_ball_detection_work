# world_registration.py
# Registers a world frame to a checkerboard held in view of cam0, reusing the
# same corner-detection convention as src/calibration/extrinsic/solve_extrinsic.py
# (PATTERN_SIZE, SQUARE_SIZE_MM, detect_corners -- imported, not re-derived).
#
# Requested world axes: x = left-to-right across the board (as the camera
# sees it), y = bottom-to-up, z = into the checkerboard (away from the camera).
#
# x=right, y=down, z=into-the-scene is OpenCV's own standard right-handed
# camera-coordinate convention. So this SOLVES in that frame (x=left-to-right,
# y=TOP-to-bottom -- i.e. z-via-right-hand-rule already comes out pointing
# into the board, matching the requested z with no extra flip), then flips
# the sign of y ONLY in the final output to present bottom-to-up.
#
# This flip is not optional bookkeeping: x=left-to-right + y=bottom-to-up +
# z=into-the-board is, taken literally, a LEFT-HANDED frame (for a normal
# forward-facing view, x=right/y=up gives z=TOWARD the viewer by the
# right-hand rule, not away). No choice of rotation alone can produce it --
# only an explicit, documented axis flip can. Getting this backwards would
# silently produce a mirrored world frame.

import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))
from src.calibration.extrinsic.solve_extrinsic import PATTERN_SIZE, SQUARE_SIZE_MM, detect_corners


def solve_world_frame(image_path, K, D):
    """
    Detect the checkerboard in `image_path` (must be a cam0 view) and solve
    its pose. Returns (R_wc, T_wc) such that, for Nx3 points X_cam in cam0's
    raw camera frame (mm):
        X_world = (X_cam - T_wc) @ R_wc   with X_world[:, 1] negated
    (see world_transform below) gives world coordinates: x=left-to-right,
    y=bottom-to-up, z=into-the-checkerboard (mm), origin at the checkerboard
    corner where column-index 0 meets the empirically-lowest row.
    """
    image_path = Path(image_path)
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(image_path)
    found, corners = detect_corners(gray)
    if not found:
        raise RuntimeError(f"Checkerboard not found in {image_path}")
    corners = corners.astype(np.float64)

    n_cols, n_rows = PATTERN_SIZE   # PATTERN_SIZE = (columns, rows) of internal corners
    grid = corners.reshape(n_rows, n_cols, 2)   # detected order: row-major, columns fast-varying

    # -- empirically determine axis directions from the actual pixel data,
    # rather than assuming detection always starts at a particular physical
    # corner (it does not: corner 0's physical location depends on the board
    # pose, per solve_extrinsic.py's own corner-order debug images). --
    x_left_avg  = float(grid[:, 0, 0].mean())
    x_right_avg = float(grid[:, -1, 0].mean())
    flip_col = x_right_avg < x_left_avg   # raw column order runs image-RIGHT-to-LEFT -> flip
    print(f"world registration: raw col0 avg pixel-x={x_left_avg:.1f}, "
          f"col{n_cols - 1} avg pixel-x={x_right_avg:.1f}  "
          f"-> {'flipping' if flip_col else 'keeping'} column order for left-to-right x")

    y_row0_avg    = float(grid[0, :, 1].mean())
    y_rowlast_avg = float(grid[-1, :, 1].mean())
    flip_row = y_row0_avg > y_rowlast_avg   # raw row 0 is LOWER on screen (larger pixel-y) -> flip
    print(f"world registration: raw row0 avg pixel-y={y_row0_avg:.1f}, "
          f"row{n_rows - 1} avg pixel-y={y_rowlast_avg:.1f}  "
          f"-> {'flipping' if flip_row else 'keeping'} row order so row-index 0 = top of image")

    # Solve-frame object points: x=left-to-right, y=TOP-to-bottom (image-like).
    objp = np.zeros((n_rows * n_cols, 3), np.float64)
    for r in range(n_rows):
        for c in range(n_cols):
            adj_c = (n_cols - 1 - c) if flip_col else c
            adj_r = (n_rows - 1 - r) if flip_row else r
            objp[r * n_cols + c] = (adj_c * SQUARE_SIZE_MM, adj_r * SQUARE_SIZE_MM, 0.0)

    undist = cv2.fisheye.undistortPoints(corners.reshape(-1, 1, 2), K, D)
    ok, rvec, tvec = cv2.solvePnP(objp.reshape(-1, 1, 3), undist, np.eye(3), None,
                                   flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise RuntimeError(f"solvePnP failed for {image_path}")
    R_wc = cv2.Rodrigues(rvec)[0]
    T_wc = tvec.reshape(3)

    # -- sanity check: reprojection error of the solved pose --
    reproj, _ = cv2.fisheye.projectPoints(objp.reshape(-1, 1, 3), rvec, tvec, K, D)
    err = np.linalg.norm(reproj.reshape(-1, 2) - corners, axis=1)
    print(f"world registration: checkerboard pose reprojection error: "
          f"median={np.median(err):.3f} px, max={float(err.max()):.3f} px  (n={len(err)} corners)")

    return R_wc, T_wc


def world_transform(pts, R_wc, T_wc):
    """
    Camera-frame Nx3 points (mm, cam0 frame) -> world frame (mm): x=left-to-
    right, y=bottom-to-up, z=into-the-checkerboard. Rigid transform (rotation
    + translation) plus the documented y-flip -- see module docstring.
    """
    pts = np.atleast_2d(pts)
    solved = (pts - T_wc) @ R_wc      # x=left-right, y=TOP-to-bottom, z=into-board
    world = solved.copy()
    world[:, 1] = -world[:, 1]        # top-to-bottom -> bottom-to-up
    return world
