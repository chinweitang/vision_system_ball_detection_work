import cv2
import numpy as np


def triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T):
    """
    Triangulate corresponding pixel points from the two fisheye cameras.

    pts0, pts1: (N, 2) pixel coords, cam0/right and cam1/left, OpenCV
        convention (origin top-left, x right, y down).
    K, D: fisheye intrinsics for each camera.
    R, T: extrinsics mapping cam0/right -> cam1/left
        (X_left = R @ X_right + T).

    Returns (N, 3) 3D points in the cam0/right frame (P1=[I|0], P2=[R|T]).
    """
    P1 = np.hstack([np.eye(3), np.zeros((3, 1))])
    P2 = np.hstack([R, T.reshape(3, 1)])

    pts0 = np.asarray(pts0, dtype=np.float64).reshape(-1, 1, 2)
    pts1 = np.asarray(pts1, dtype=np.float64).reshape(-1, 1, 2)

    norm0 = cv2.fisheye.undistortPoints(pts0, K0, D0).reshape(-1, 2)
    norm1 = cv2.fisheye.undistortPoints(pts1, K1, D1).reshape(-1, 2)

    pts4d = cv2.triangulatePoints(P1, P2, norm0.T, norm1.T)
    pts3d = (pts4d[:3] / pts4d[3]).T
    return pts3d
