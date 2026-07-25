const todos = [
 # Todos - 2026-07-25

## Critical / Blocking

- [ ] Double-check triangulation timestamp offset is under 7ms
      - Re-verify **per session**, not once - sync offset is stable within a session but random between sessions.
- [ ] 21/07 flights (flight 61 onwards) use a **new world frame**
      - Do not mix with pre-flight-61 world registration in any batch analysis. Flag in filenames or a session manifest.

## Detection Validation

- [x] Sort flights into full flight vs non-full flights, extract ball frames
      - A couple flights may remain if still needed.
- [x] Run detector on all ball frames, get detection rate, tune (stride variations, 3-frame AND threshold)
- [ ] Label flights 1, 11, 33 to refine detection algorithm
  - [x] Label flight 1
  - [ ] Label flight 11
  - [ ] Label flight 33
- [ ] Decide: label more flights to validate recall, or iterate `min_run_length`?
      - **[Likely]** Do `min_run_length` sweep FIRST (cheap, no new labeling). Only label more flights afterward if false-positive rate is still unclear post-sweep. Labeling is the expensive step - don't spend it before the cheap lever is pulled.

## Error Decomposition

- [ ] **Model error**: manual labels (early frames) → predict → compare to manual label at crossing
      - Reports: Position (mm), Speed, Incoming angle
      - Isolates physics/fit quality. No detection error.
- [ ] **End-to-end error**: detector points (early frames) → predict → compare to manual label at crossing
      - Reports: Position (mm), Speed, Incoming angle
      - This is the operational number the ±100mm spec applies to. Velocity IS reported here since it feeds the actuator controller.
- [ ] Determine how many frames need manual labeling for accuracy-cost comparison
      - Depends on above - run a small pilot (5-10 flights) before committing to a full labeling pass.
- [ ] Apply pixel velocity correction from time offset
      - **Must happen BEFORE** the manual-vs-detector comparison above, or sync error contaminates the detection-error estimate. This is a C-term correction (per your A/B/C error framework) - it needs to land before B is measured.

## Prediction Model

- [ ] Try fixed gravity acceleration instead of fitting gravity
      - **[Certain]** Fewer free parameters improves conditioning at low N - correct instinct.
      - **BLOCKED by unresolved 29.8° gravity-direction discrepancy** (context_master priority #1). Fixing the wrong direction just locks in a bias instead of fitting it out. Resolve discrepancy first.
- [ ] Try robust regression (RANSAC) for trajectory fitting
      - Overlaps with existing pipeline priority #5 (RANSAC outlier rejection pre-triangulation) - confirm this is the same task, not duplicate work.

## Adaptive Detection Near Apex

- [ ] Switch detection strategy near apex (increase stride, or appearance-based e.g. Hough) when ball slows down
      - Option A: trigger based on when ball is not visible/detectable
      - Option B: switch even earlier (proactive, before dropout)
      - Option C: threshold-based - set detected centroid pixel displacement threshold to trigger stride switch
      - **[Guessing]** Option C is most robust since it's tied to actual signal degradation rather than a fixed frame index, which won't generalize across arc heights/velocities. Build this *after* the frames 85-98 apex dropout root cause is understood - a detector fix may remove the problem entirely.

---

**Ordering flags:**
- `Try fixed gravity acceleration` depends on resolving the gravity-direction discrepancy - don't work it in list order.
- `How many frames to label` and `Apply pixel velocity correction` are sequence-dependent, not parallel - correction must land first.



## 2026-07-15 - detector tuning

- I'm skimming the outputs of data\detector_tuning\contact_sheets\03_stride1_thresh16_openk3_area30_circ0.3. I'm looking at the contact sheets to look for like gross error e.g the detection is complete wrong - like picking up hand instead of the ball. Then I need to decide what to do next. 



- flight_12_cam1:../../data/detector_tuning/contact_sheets/03_stride1_thresh16_openk3_area30_circ0.3/2026_07_15_gym_flight_12_cam1_contact.png
![Hand being picked up by detector](screenshots/image.png)
- Hand being picked up significantly by detector - trajectory filter needs tuning. Like maybe look into changing min run length or like sweep it - however currently I'm mainly using detection rate as my validation metric however it hides incorrect detections - like above image is picked up as correct detection. I think for proper validation I'll need more manual labels? What i could do is label the flights where there's artifacts e.g hand getting picked up

- flight_13_cam0:../../data/detector_tuning/contact_sheets/03_stride1_thresh16_openk3_area30_circ0.3/2026_07_15_gym_flight_13_cam0_contact.png

![Hand being picked up by detector](screenshots/image2.png)

- There’s a stretch (frames 85 - 98) near the apex where detection drops out. 
- But the thing is in the the mask images, I can see the ball in the differencing, so does that mean I need to retune the diff threshold? or like tune the AND. Because in the forward and backward differences, I can see the the ball but it's bno there in the and so maybe the AND criteria is too harsh? 



# Thoughts:
- honestly overall, the detection seems pretty good - i've skimmed a couple of flights. I don't think there's any point going through every single flight since i think the failures e.g hand getting picked up is similar for others and I'm not going ot see anything new. 
- What do I need to do next? Like should i continue tuning the detector? Or should i run try build the velocity binner next? Or should i continue with trajectory prediction and different prediction methods because maybe I don’t need the later frames where detection drops out anyway - like if i only need teh first 10 frames for prediction, then the later frames don’t matter. Or should i label more flights first to continue tuning the flights? 
- The other thing is, for my velocity binning and trajectory prediction, I can just apply a trajectory filter as well to remove unreasonable points where the detected centroid jumps from like in the in the ball arc to the person's hand. So in that case do i still have to continue tuning the detector? 
- Feed in the full project context into claude code - as well as my to dos - like the automated binning 
- Should I also try an appearance based approach like hough detection just to see how good it is? 
- but i guess like with the artifact audit run on all flights - it's already picked up some of the false detections e.g like the hands being picked up rihgt? Can that be used to make the detection rate more accurate - like with artifact audit, when it picks up stuff that doesn't fit the trajectory, you kind of know it's a incorrect detection then no? 
- I don't fully understand how Trajectory-consistency filter works and teh alternatives rejected