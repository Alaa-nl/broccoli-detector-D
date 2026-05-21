# Model weights folder

Put your trained YOLOv8n weights file here as `best.pt`.

You can copy it from your Deliverable B training output:

```
broccoli-detector-B/runs/detect/yolov8n_v1/weights/best.pt
```

The file is about 6 MB. If you do not put a weights file here,
the backend will still start, but every detection call will
return an empty result.
