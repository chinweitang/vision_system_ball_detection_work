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
    #
    # cam0 second entry: a static wall-corner/structural edge at ~(1322,390)
    # that only surfaces at lower DIFF_THRESHOLD/smaller OPEN_KERNEL (found
    # during the 2026-07 param sweep, flight_126). Bounded to x in
    # [1270,1456], y in [375,425] -- checked against every existing cam0
    # detection across both 2026_07_15_gym and 2026_07_21_gym (default
    # params): zero real detections fall in this box (the nearest real
    # cluster in this y-band is at x~1000-1050, ~230-270px clear of this box).
    #
    # The following 4 entries came from the full-dataset artifact audit
    # (`07_artifact_audit.py`, 2026-07-23): pooled every point
    # `filter_trajectory_outliers` rejected across all 163 flights x both
    # cams, binned spatially, and found bins hit by dozens to 100+ DISTINCT
    # flights - too many to be coincidental real ball positions. Visually
    # confirmed each via cropped frames (see
    # data/detector_tuning/inspection_crops/hotspot_*.png). IMPORTANT: the
    # raw rejected-point bounding box for each was NOT used directly - it
    # was contaminated by cases where the trajectory filter itself wrongly
    # rejected real ball frames near these fixtures (see flight_1 cam0
    # frames 152/155/156 in the worklog), inflating the apparent footprint.
    # Used the densest 15px-bin sub-cluster (by distinct-flight count)
    # instead, then verified zero real detections (across every existing
    # analysis_3 CSV, both sessions, default params) fall in the final box
    # before adding it.
    #
    # cam1: static wall corner/edge, x in [1380,1456], y in [395,445].
    # cam0: exit sign (reflective running-person + arrow icon),
    #   x in [1115,1165], y in [615,648].
    # cam0: wall-mounted fixture/panel pair, x in [1010,1040], y in [638,655].
    # cam0: a third, smaller static cluster between the above two,
    #   x in [1040,1057], y in [638,650] - not yet visually identified as a
    #   specific object, but same audit criteria (spatial recurrence across
    #   many distinct flights, zero real-detection overlap) applied.
    #
    # The following 5 entries came from re-running the full-dataset audit at
    # min_area=30 (round 3, 2026-07-24 - a much looser area threshold surfaces
    # smaller signals, including these same physical objects visible from the
    # OTHER camera's angle, and spillover beyond the original tightly-fit
    # boxes above). Same safety process: dense 15px-bin sub-cluster, verified
    # against every existing analysis_3 detection. One near-miss caught here
    # too: the cam1 fixture box's first draft (v starting at 680) clipped a
    # verified real trajectory (flight_53/cam1 frames 103->104->108, smooth
    # 22-30px/frame descent through (1153,682)) - narrowed the floor to
    # v=684 (the actual fixture cluster sits at v>=685) which alone brought
    # it to zero real hits.
    #
    # cam0: exit sign, spillover to the right of the original box,
    #   x in [1175,1192], y in [605,624].
    # cam0: fixture's broader footprint at this looser threshold,
    #   x in [1070,1090], y in [620,633].
    # cam1: same wall corner as above, extends below the original box,
    #   x in [1385,1400], y in [448,462].
    # cam1: the wall fixture (see cam0 entries above), now visible from
    #   cam1's angle too, x in [1135,1172], y in [684,693].
    # cam1: the exit sign (see cam0 entries above), now visible from cam1's
    #   angle too, x in [1238,1270], y in [668,685] - only 3 distinct flights
    #   (lower than the other entries here) but visually unambiguous (the
    #   same running-person/arrow icon), so masked despite the lower count.
    "cam0": [
        [(1456, 0), (1456, 375), (1000, 375), (1000, 0)],
        [(1456, 375), (1456, 425), (1270, 425), (1270, 375)],
        [(1165, 615), (1165, 648), (1115, 648), (1115, 615)],
        [(1040, 638), (1040, 655), (1010, 655), (1010, 638)],
        [(1057, 638), (1057, 650), (1040, 650), (1040, 638)],
        [(1192, 605), (1192, 624), (1175, 624), (1175, 605)],
        [(1090, 620), (1090, 633), (1070, 633), (1070, 620)],
    ],
    "cam1": [
        [(1456, 0), (1456, 400), (1100, 400), (1100, 0)],
        [(1456, 445), (1456, 395), (1380, 395), (1380, 445)],
        [(1400, 448), (1400, 462), (1385, 462), (1385, 448)],
        [(1172, 684), (1172, 693), (1135, 693), (1135, 684)],
        [(1270, 668), (1270, 685), (1238, 685), (1238, 668)],
    ],
}

_mask_cache = {}


def apply_exclusion(mask, cam_name):
    """Zero out this camera's excluded region(s) in a post-morphology binary
    mask. Returns a new array; does not mutate the input in place."""
    polys = EXCLUSION_TRIANGLES.get(cam_name)
    if not polys:
        return mask
    key = (cam_name, mask.shape)
    if key not in _mask_cache:
        keep = np.full(mask.shape, 255, dtype=np.uint8)
        cv2.fillPoly(keep, [np.array(p, dtype=np.int32) for p in polys], 0)
        _mask_cache[key] = keep
    return cv2.bitwise_and(mask, _mask_cache[key])
