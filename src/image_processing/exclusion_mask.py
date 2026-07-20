# exclusion_mask.py
# Static per-camera exclusion triangles for a fixed ceiling light that produces
# false-positive "ball" candidates after threshold+open+close. Derived by
# eyeballing per-pixel activation-frequency of the post-morphology mask across
# flight_11 (93 frames): both cameras' light footprints cleanly touch the top
# and right image edges, so a triangle cut between those two edges covers the
# oscillating blob without excluding the unused far corner a full rectangle
# would. Cross-checked against every labelled ball centroid currently
# available (flight_01, "2 ball contacts ground before plane") -- none fall
# inside either triangle.
#
# If the light fixture moves or a camera is repositioned, redo the same
# eyeball-from-a-few-frames check and update the vertices below.

import numpy as np
import cv2

EXCLUSION_TRIANGLES = {
    # Both cams: plain rectangles, not triangles -- checked across 5 flights
    # (flight_01, 11, 17, 33, and the labelled "2 ball contacts.../flight_01"),
    # the light shows up as multiple distinct static clusters per camera
    # (e.g. cam0 ~x1150,y65 AND ~x1340,y360; cam1 ~x1280,y140, ~x1337,y270,
    # AND ~x1428,y365) that a single diagonal cut can't cover without either
    # missing one cluster or cutting much further into the frame than needed.
    # Rectangles are simplest and safe: distinguished real ball detections
    # from light artifacts by checking for frame-to-frame smoothness (a real
    # ball moves continuously; the light sits at a fixed position) -- a
    # separate smoothly-moving cluster at x in [957,1039], y in [241,408] in
    # cam1 (flight_11/flight_17) is real ball motion and stays clear of the
    # x>=1100 bound below. No labelled ball position ever has y<640 either.
    "cam0": [(1456, 0), (1456, 375), (1000, 375), (1000, 0)],
    "cam1": [(1456, 0), (1456, 400), (1100, 400), (1100, 0)],
}

_mask_cache = {}


def apply_exclusion(mask, cam_name):
    """Zero out this camera's excluded triangle in a post-morphology binary
    mask. Returns a new array; does not mutate the input in place."""
    tri = EXCLUSION_TRIANGLES.get(cam_name)
    if not tri:
        return mask
    key = (cam_name, mask.shape)
    if key not in _mask_cache:
        keep = np.full(mask.shape, 255, dtype=np.uint8)
        cv2.fillPoly(keep, [np.array(tri, dtype=np.int32)], 0)
        _mask_cache[key] = keep
    return cv2.bitwise_and(mask, _mask_cache[key])
