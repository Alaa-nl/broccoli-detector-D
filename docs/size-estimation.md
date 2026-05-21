# How we calculate crown size

This explains exactly how BroccoliDetect turns a bounding box in an
image into a real-world crown diameter in millimetres — and what
happens when you change the camera height in **Settings**.

The code lives in
[`backend/app/services/size_estimator.py`](../backend/app/services/size_estimator.py).

---

## The four steps

### 1. Pretend the camera is a perfect pinhole, pointing straight down

The Intel RealSense D415 that recorded your dataset has a
**horizontal field of view of 69.4°** (from Intel's datasheet —
hardcoded as `DEFAULT_FOV_HORIZONTAL_DEG` in the code).

That's the angle of the cone of vision spreading out from the lens.
If the camera sits at height `H` above the ground and points straight
down, simple trigonometry tells us how wide the patch of ground in the
photo is:

```
ground_width_mm = 2 × H × tan(FOV / 2)
```

With the default `H = 1000 mm` (1 metre):

```
ground_width_mm = 2 × 1000 × tan(34.7°) ≈ 1383 mm    (about 1.4 m wide)
```

### 2. Figure out how big one pixel is on the ground

The uploaded image is, say, 1280 pixels wide. Those 1280 pixels are
spread across that 1383 mm of ground:

```
mm_per_pixel = 1383 / 1280 ≈ 1.08 mm/pixel
```

This is the **scale factor**: every pixel in the photo represents
about 1 mm on the ground.

### 3. Measure the bounding box and convert

YOLO gives a rectangular bounding box around each crown — say,
120 px wide and 110 px tall. We **average** the two sides because
broccoli crowns are roughly circular when seen from above (the box
itself is always rectangular):

```
avg_side_px = (120 + 110) / 2 = 115 px
diameter_mm = 115 × 1.08 ≈ 124 mm    (12.4 cm)
```

### 4. Assign a size category

The mm result is bucketed into a label using common retail grades
(`SMALL_MAX_MM`, `MEDIUM_MAX_MM` in the code):

| Diameter | Label | Meaning |
| --- | --- | --- |
| `< 8 cm` | **small** | immature; leave to grow |
| `8–13 cm` | **medium** | retail-ready |
| `≥ 13 cm` | **large** | export grade |

---

## What happens when you change the camera height in Settings

The slider sets one number: the value of `H` in step 1. Every other
piece of the calculation cascades from it. The relationship is
**linear** — doubling the height doubles every reported diameter.

### Where the value flows

```
Settings.jsx                  ← user types 1200
   │
   ▼
App.jsx state (cameraHeight)  ← React state, also written to localStorage
   │
   ▼
Upload.jsx                    ← attached to FormData as `camera_height_mm`
   │
   ▼  POST /api/detect
   │
backend/app/api/detect.py     ← reads the form field
   │
   ▼
SizeEstimator(camera_height_mm=1200)
   │
   ▼
Step 1 above uses H = 1200    ← every diameter in the response shifts
```

The Settings page validates the input to `100 mm < H < 5000 mm`
before it's accepted. Values outside that range are silently reset to
the last good value — so you can't crash the math by typing `0`.

### Concrete examples — same crown, different heights

Suppose YOLO detects a crown with a 115 px average bounding box side,
in a 1280 px wide image:

| Camera height (Settings) | mm/pixel | Reported diameter | Size label |
| --- | --- | --- | --- |
| 500 mm  (low — hand-held close) | 0.54 | **62 mm** (6.2 cm) | small |
| 1000 mm (default — waist height) | 1.08 | **124 mm** (12.4 cm) | medium |
| 1500 mm (chest height) | 1.62 | **186 mm** (18.6 cm) | large |
| 2000 mm (overhead arm) | 2.16 | **248 mm** (24.8 cm) | large |

The same crown looks tiny if you tell the system the camera was
right above it, and huge if you tell it the camera was far away.
**Telling the truth about how high you held the camera is what
makes the estimate accurate.**

### Quick-and-dirty calibration

If your detections look too big or too small but you don't know the
exact height the camera was at, you can calibrate by photographing
something of a **known size** alongside your crops:

1. Put a ruler or a tennis ball (≈ 67 mm) in the field of view.
2. Upload the photo.
3. Note the reported diameter of the reference object.
4. Adjust the Settings height by the same ratio:
   - Reported too big? *Lower* the height.
   - Reported too small? *Raise* the height.
5. Re-upload and check. One or two iterations should converge.

This is a one-shot calibration — the same height value will then
apply to every subsequent photo taken under similar conditions.

---

## Things this model gets wrong

These are the same limitations called out in the top-level README's
"Known limits", explained from the size-estimation angle:

- **Assumes the camera is exactly vertical.** A tilted camera turns
  the ground patch into a trapezoid; pixels in the "far" half cover
  more ground than pixels in the "near" half. We treat all pixels as
  equal, so tilted shots over-estimate near crowns and under-estimate
  far ones.
- **Ignores lens distortion.** Pixels near the corners of the image
  represent slightly more ground than central pixels (especially on
  wide-angle lenses like the D415). Edge crowns are under-estimated
  by a few percent.
- **Bounding box ≠ crown shape.** YOLO can't tell a leaf-with-stem
  from a clean crown; the box stretches to fit everything the model
  considers part of one detection. The averaging trick partly hides
  this, but uneven boxes still inflate the estimate. The **Leaf
  Filter** toggle in Settings drops the most egregious cases
  (boxes where `max(w, h) / min(w, h) > 1.6`).
- **One fixed FOV.** If you photograph with a different camera, the
  69.4° assumption silently breaks the math. There's currently no
  Settings control for FOV; you'd need to edit the
  `DEFAULT_FOV_HORIZONTAL_DEG` constant in the code.

## Why not just use the depth data?

The original dataset is RGB-D, which means each pixel also has a
depth value — and depth would give us the true ground distance per
pixel without any of the pinhole-model assumptions. But the dataset
we received only contains the JPGs (the RGB channel), not the depth
maps. A fixed-height assumption is the simplest reasonable fallback.

A future version that ingests the original RGB-D data (or pairs the
JPGs with a separate depth file) could drop most of the limitations
listed above and just read the ground distance directly from each
pixel.
