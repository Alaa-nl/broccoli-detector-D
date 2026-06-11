# Retraining strategy

How BroccoliDetect decides **when** to retrain, how to **demo** that decision
end-to-end on a laptop, and what the actual retraining **procedure** looks
like once a trigger fires.

The tooling lives in [`scripts/retraining/`](../scripts/retraining/):

| File | Purpose |
|---|---|
| `check_triggers.py` | Queries Prometheus and evaluates the four triggers below. Exit 0 = all clear, 1 = trigger fired, 2 = Prometheus unreachable — cron/CI friendly. |
| `simulate_drift.py` | Sends synthetic "bad field condition" images to `/api/detect` so the triggers have something to fire on during a demo. |
| `baseline.json` | The reference distribution the drift check compares against. |

---

## Why retraining matters for this model

The deployed model is a YOLOv8n trained on a **small dataset** captured under
one set of conditions: one camera (Intel RealSense D415), a narrow range of
heights, one field, one stretch of the season. That makes it unusually
sensitive to drift:

- **Seasonal and growth-stage drift.** Crowns look different early vs. late
  season (size, colour, how much leaf cover surrounds them). A model trained
  on mid-season crowns will under-detect — or mis-size — early plantings.
- **Field-condition drift.** New lighting (dawn/dusk runs, overcast vs.
  harsh sun), wet foliage, fog, dust on the lens. None of these are
  represented in the training set, so confidence degrades quietly rather
  than failing loudly.
- **New operating points.** The size estimator assumes the configured camera
  height; if growers start mounting the camera at 1.8 m instead of 1 m, the
  *images* change (smaller crowns in frame, more context) even though the
  maths compensates for the *scale*. New cultivars or new fields have the
  same effect.

A model like this doesn't break — it **fades**. The monitoring stack exists
so the fade shows up as numbers, and the triggers below turn those numbers
into a decision.

## The triggers

`check_triggers.py` evaluates four conditions, each backed by one of the
Prometheus metrics the backend exports. All queries default to a **1 h
window** (`--window`).

| ID | Signal | PromQL (window `1h`) | Default threshold | Why this signal |
|---|---|---|---|---|
| **T1** | Low mean confidence | `rate(broccoli_detection_confidence_sum[1h]) / rate(broccoli_detection_confidence_count[1h])` | mean < **0.55** (`--min-confidence`) | The earliest drift symptom: the model still finds crowns but is no longer sure about them. Falls well before the empty rate rises. |
| **T2** | Empty-result spike | `increase(broccoli_empty_detections_total[1h]) / increase(broccoli_detection_requests_total[1h])` | > **0.30** (`--max-empty-rate`), only with ≥ **20** requests in the window (`--min-requests`) | Users photograph fields *because* there is broccoli in them; a third of images coming back empty means the model misses what is there. The minimum-request gate stops 2-of-3 overnight noise from looking like drift — below it the script reports `INSUFFICIENT DATA`, not a trigger. |
| **T3** | Size-distribution drift | `histogram_quantile(0.5, rate(broccoli_crown_diameter_mm_bucket[1h]))` vs. `baseline.json` | median deviates > **25 %** from baseline (`--max-diameter-drift`) | Catches drift T1/T2 can't see: the model is confident and finds crowns, but the *population* changed (new growth stage, new cultivar — or a wrong `camera_height_mm`, which is checked first). Median, not mean, so a few mis-scaled outliers can't fake it. |
| **T4** | Operational error rate | `sum(rate(broccoli_http_requests_total{status=~"5.."}[1h])) / sum(rate(broccoli_http_requests_total[1h]))` | > **5 %** (`--max-error-rate`) | **An ops alert, not a model alert.** A dying backend drags T1/T2 around (failed requests never reach the ML counters), so this check sits next to them as a guard: when T4 fires, investigate the service first — a broken service is not a drifted model, and retraining won't fix it. |

A fired T1/T2/T3 means "start the retraining procedure below"; a fired T4
means "stop and debug the deployment before trusting any of the others".

### The baseline file

`baseline.json` currently holds **seed values** from the Deliverable B
test-set evaluation (mean confidence 0.80, diameter median 124 mm, empty
rate 0.05). Lab numbers are a stand-in, not truth: after the first healthy
production window (a week or so of normal field traffic), re-capture the
baseline from Prometheus and overwrite the file:

```promql
# mean confidence over a healthy week
rate(broccoli_detection_confidence_sum[7d]) / rate(broccoli_detection_confidence_count[7d])

# diameter median over the same week
histogram_quantile(0.5, rate(broccoli_crown_diameter_mm_bucket[7d]))

# empty-detection rate over the same week
increase(broccoli_empty_detections_total[7d]) / increase(broccoli_detection_requests_total[7d])
```

Update `captured` and `window` in the file when you do, so future readers
know what the numbers represent. The baseline should also be re-captured
after every successful retrain — the new model defines a new "normal".

## Demoing a scenario end-to-end

This walks the full loop on a laptop: healthy service → simulated drift →
dashboard moves → trigger fires.

1. **Start the app**: `docker compose up --build` (frontend on :8080,
   backend on :8000). For a smooth demo raise the per-IP rate limit so the
   drift burst isn't throttled: `RATE_LIMIT_MAX=60` in the backend
   environment (default is 10/min).
2. **Start the monitoring stack** (Prometheus on :9090, Grafana on :3000 —
   see `monitoring/` for the compose entry point).
3. **Establish normal traffic**: upload a few real field photos through the
   UI at http://localhost:8080 so the dashboard shows healthy values first.
4. **Verify the healthy state**:
   `python3 scripts/retraining/check_triggers.py --window 15m`
   → everything `OK` (or `INSUFFICIENT DATA` where there's no traffic yet).
5. **Inject drift**:
   `python3 scripts/retraining/simulate_drift.py`
   sends 30 dark/low-contrast images to `/api/detect` (Pillow is its only
   dependency: `pip install pillow`).
6. **Watch Grafana**: mean detection confidence sinks, the empty-result
   rate climbs, `broccoli_detections_per_image` piles up in the 0 bucket.
7. **Re-run the check**:
   `python3 scripts/retraining/check_triggers.py --window 15m`
   → **T1** and **T2** report `TRIGGERED`, exit code 1. The short window
   matters for the demo: at the default `1h` the 30-image burst is diluted
   by the hour of healthy traffic around it — which is exactly the
   conservatism you want from the scheduled production check.

The same script is what a cron job (or a CI scheduled workflow) would run
hourly with default settings, alerting on a non-zero exit code.

## The retraining procedure

When T1/T2/T3 fires (and T4 is clean), retraining follows the same
pipeline that produced the current model — Deliverable B — with versioning
at every step so the deployment side only ever consumes immutable,
checksummed artifacts:

1. **Collect and annotate.** Pull recent production uploads from the period
   that fired the trigger (the `/uploads` retention window is short, so act
   promptly), plus fresh field captures of the new condition. Annotate
   crowns in the same format as the original dataset.
2. **Version the dataset.** Register the new dataset version in
   `data/registry.json` — what was added, where it came from, which trigger
   motivated it. Never mutate an existing dataset version.
3. **Retrain** with the Deliverable-B training pipeline on the new dataset
   version, and evaluate against the held-out test set. The candidate must
   beat (or at minimum match) the incumbent on the original test set *and*
   improve on a slice representing the drifted condition — otherwise the new
   data goes back for re-annotation, not deployment.
4. **Register the model.** Add the new version to
   `backend/weights/registry.json` with its `sha256`, the dataset version it
   was trained on, and its eval numbers.
5. **Publish the weights.** Upload `best.pt` to blob storage and note the
   download URL (the backend can fetch weights at startup via
   `MODEL_WEIGHTS_URL`, verifying them against `EXPECTED_WEIGHTS_SHA256`).
6. **Deploy.** Bump `MODEL_VERSION` (and `MODEL_WEIGHTS_URL` /
   `EXPECTED_WEIGHTS_SHA256`) in the deployment environment and redeploy via
   the CI pipeline. The version surfaces in `/api/metadata` and in the
   `broccoli_app_info` metric, so Grafana shows exactly which model produced
   which stretch of the time series.
7. **Re-baseline and watch.** Re-capture `baseline.json` from the new
   model's first healthy window, then watch the triggers: the deploy is only
   "done" when the metric that fired has recovered.

**Rollback** is the same lever in reverse: revert `MODEL_VERSION` (and the
weights URL/checksum) to the previous registry entry and redeploy. Because
every model version is immutable and checksummed in
`backend/weights/registry.json`, rollback is a config change, not a build.

## With infinite time (prioritized)

1. **Human-in-the-loop labeling queue.** Low-confidence and empty-result
   images flow into an annotation queue instead of vanishing when the upload
   retention sweep runs. Highest value: it converts every drift event into
   training data automatically, which is the scarcest resource here.
2. **Shadow deployment / champion–challenger.** Run the candidate model
   beside the incumbent on the same live uploads and compare their metrics
   for a week before switching. Removes the biggest remaining risk in the
   procedure above — that the held-out test set no longer represents the
   field.
3. **Scheduled evaluation against a golden set.** A nightly CI job that runs
   the deployed weights against a frozen, curated image set and publishes
   mAP/recall as metrics. Catches *model-side* regressions (bad weights
   upload, dependency bump changing inference) that production-traffic
   triggers can't separate from data drift.
4. **Data-quality gates on ingest.** Reject or flag blurred, under-exposed,
   or non-field images before they reach the model. Keeps junk uploads from
   polluting both the triggers and the labeling queue — last on the list
   because the API's input validation already catches the worst offenders.

## Cost awareness

Retraining is the most expensive action this system can take: field capture
trips, manual annotation, GPU time, evaluation, and a deployment that itself
carries regression risk. A false-positive trigger costs days of team time; a
slightly-late true positive costs a few percent of recall for a week. That
trade is why every threshold above is deliberately conservative — confidence
has to fall well below the ~0.80 baseline before T1 fires, a *third* of
images must come back empty for T2, and T2 refuses to fire at all on thin
traffic. The triggers are tuned to ask for retraining when it is clearly
needed, not whenever the metrics wobble; the cheap actions (check the camera
height, check T4, look at the actual images) always come first.
