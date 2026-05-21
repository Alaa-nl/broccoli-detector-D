# BroccoliDetect - Proof of Concept

**Deliverable D - Applied AI Minor, Group B4**
**Inholland University of Applied Sciences, Haarlem**
**Client: Robotics | Smart Farming, Inholland Alkmaar**

A web application that finds broccoli crowns in field images using a
YOLOv8n deep learning model, and estimates the diameter of each crown.

## What this app does

1. The user uploads a broccoli field photo (JPG or PNG).
2. The backend runs the trained YOLOv8n model on the image.
3. Bounding boxes are drawn around each crown.
4. The pixel size of each box is turned into a real-world diameter
   (in millimetres) using a pinhole camera model.
5. The user sees the result image and a list of crowns with sizes.

## Team

- Alaa Aldrobe
- Manol Draganov
- Diego Baez de la Cruz
- Rienat Zhuravlov
- Fatmanur Vardar

## Project structure

```
broccoli-app/
├── backend/                # FastAPI server
│   ├── app/
│   │   ├── main.py         # Server entry point
│   │   ├── api/            # Route handlers (detect, health)
│   │   ├── services/       # Detector, size estimator, uploader, annotator
│   │   └── models/         # Pydantic data shapes
│   ├── weights/            # Put best.pt here (from Deliverable B)
│   ├── uploads/            # Uploaded and annotated images (created at runtime)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/               # React + Vite + Tailwind app
│   ├── src/
│   │   ├── App.jsx         # Main component with routing
│   │   ├── pages/          # Home, Upload, Results, Settings, About
│   │   └── components/     # Header, BottomNav
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docker-compose.yml      # Run both services together
└── README.md               # You are here
```

## Quick start with Docker (easiest)

You need Docker Desktop installed.

1. Copy your trained weights file from Deliverable B into the backend:

   ```bash
   cp /path/to/broccoli-detector-B/runs/detect/yolov8n_v1/weights/best.pt \
      backend/weights/best.pt
   ```

2. Start the whole app:

   ```bash
   docker compose up --build
   ```

3. Open your browser at:

   - Frontend (the app): http://localhost:8080
   - Backend API docs:   http://localhost:8000/docs

## Quick start without Docker (development mode)

### Backend (Python 3.11+)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy the trained model.
cp /path/to/best.pt weights/best.pt

# Start the dev server.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be at http://localhost:8000 and the auto-generated docs at
http://localhost:8000/docs.

### Frontend (Node.js 20+)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The UI will open at http://localhost:5173. The Vite dev server forwards
`/api` calls to http://localhost:8000, so you do not need any extra
configuration.

## How crown size is calculated

We use a simple pinhole camera model:

```
ground_width_mm  = 2 * camera_height_mm * tan(FOV_horizontal / 2)
mm_per_pixel     = ground_width_mm / image_width_px
diameter_mm      = bbox_avg_side_px * mm_per_pixel
```

Default values:

| Parameter             | Value     | Source                        |
| --------------------- | --------- | ----------------------------- |
| Camera height         | 1000 mm   | Adjustable in Settings        |
| Horizontal FOV        | 69.4°     | Intel RealSense D415 datasheet |
| Reference image width | uploaded  | Read at runtime               |

The user can change the camera height in the Settings screen to
calibrate the estimate. We use the average of the bounding box width
and height as a proxy for the crown diameter, because broccoli crowns
are roughly circular when seen from above.

**Why no actual depth data?** The dataset we received contains only
JPG images (the RGB channel of the original RGB-D capture). Without
per-pixel depth, a fixed-height assumption is the simplest reasonable
estimate. The team emailed Surya Giri to confirm whether the camera
height stays constant during recording.

## API endpoints

| Method | Path           | What it does                                        |
| ------ | -------------- | --------------------------------------------------- |
| GET    | `/api/health`  | Returns `{status, model_loaded}` for monitoring.    |
| POST   | `/api/detect`  | Runs detection on an uploaded image. Returns JSON.  |
| GET    | `/uploads/...` | Serves saved images (original and annotated).       |
| GET    | `/docs`        | Auto-generated Swagger UI.                          |

### Example `/api/detect` request

```bash
curl -X POST http://localhost:8000/api/detect \
  -F "file=@field_image.jpg" \
  -F "camera_height_mm=1000"
```

Returns:

```json
{
  "image_id": "a3b8c1d2e4f5",
  "image_url": "/uploads/a3b8c1d2e4f5.jpg",
  "annotated_url": "/uploads/a3b8c1d2e4f5_annotated.jpg",
  "image_width": 1280,
  "image_height": 720,
  "crowns": [
    {
      "crown_id": 1,
      "bbox": { "x1": 540, "y1": 270, "x2": 660, "y2": 380 },
      "confidence": 0.94,
      "diameter_mm": 119.5,
      "diameter_cm": 11.95,
      "size_category": "medium"
    }
  ],
  "num_crowns": 1,
  "inference_time_ms": 187.3,
  "camera_height_mm": 1000.0
}
```

## Technology stack

| Layer        | Technology              | Version    |
| ------------ | ----------------------- | ---------- |
| Frontend     | React + Vite + Tailwind | React 18.3 |
| Routing      | React Router            | 6.26       |
| Icons        | lucide-react            | 0.441      |
| Backend      | FastAPI + Uvicorn       | 0.115      |
| Model        | Ultralytics YOLOv8      | 8.2.103    |
| Deep learning | PyTorch                | 2.2.2      |
| Image processing | Pillow + OpenCV     | 10.4 / 4.10 |
| Container    | Docker + docker compose | latest     |

## Known limits

- **Camera height is assumed constant.** If the operator's hand moves
  up or down, the crown size estimate will be off by the same ratio.
- **No lens distortion correction.** Crowns near the corners of the
  image may be slightly under-estimated.
- **One image at a time.** No batch upload yet (could be future work).
- **Small training set.** The YOLOv8n model was trained on only 119
  images. Precision is 86.5% (with perfect recall). For production,
  the team would annotate more images.

## Future work

- Use real per-pixel depth from the RGB-D recordings.
- Add a "growth tracking" view that links several photos of the same
  field over time.
- Support batch uploads (multiple images at once).
- Add CSV export of all detections.

## Licence

This project is part of the Applied AI Minor at Inholland University
and is shared with the Professorship Robotics | Smart Farming.
