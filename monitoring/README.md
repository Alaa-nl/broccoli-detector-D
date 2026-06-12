# Monitoring (local Prometheus + Grafana)

A local, containerised monitoring stack for the BroccoliDetect backend — a
deliberately lightweight setup for a PoC, where a cloud-hosted monitoring
service would add cost without adding insight. Prometheus scrapes the
backend's `/metrics` endpoint; Grafana ships with a pre-provisioned
dashboard — no manual setup clicks.

## How to start

The monitoring stack attaches to the main app's Docker network
(`broccoli-net`), so the main stack must be up first:

```bash
# 1. From the repo root: start backend + frontend (creates broccoli-net)
docker compose up --build

# 2. From this directory: start Prometheus + Grafana
docker compose -f docker-compose.monitoring.yml up -d
```

| Service    | URL                              | Notes                                      |
| ---------- | -------------------------------- | ------------------------------------------ |
| Grafana    | http://localhost:3000            | Dashboard "BroccoliDetect - Operational & ML" loads automatically |
| Prometheus | http://localhost:9090            | Raw queries / target status under Status > Targets |
| Backend    | http://localhost:8000/metrics    | The scraped endpoint, plain Prometheus text |

To generate data for the functional panels, upload a few field photos through
the UI at http://localhost:8080 (or POST to `/api/detect` directly).

> **Security note:** Grafana runs with anonymous **Admin** access
> (`GF_AUTH_ANONYMOUS_ENABLED=true`). That is a deliberate demo convenience so
> anyone opening port 3000 lands straight on the dashboard with no login. It is
> not acceptable for production: anyone who can reach port 3000 can change or
> delete everything. A real deployment would use proper auth and keep Grafana
> off the public internet.

## What we monitor and why

We split metrics into two families, mirroring the two ways an ML service can
fail: it can break as a *web service* (operational) or it can silently get
*worse at its job* while returning 200s (functional). The second family is the
one classic infra monitoring misses, and the reason ML systems need their own
metrics.

### Operational (is the service healthy?)

1. **Request rate + 5xx error ratio** (`broccoli_http_requests_total`) — the
   baseline "is it up and is it erroring" signal. A rising 5xx ratio is the
   fastest indicator of a broken deploy or an exhausted backend; the rate by
   status also shows 429s, i.e. when the per-IP rate limiter starts rejecting
   real users.
2. **`/api/detect` p95 latency** (`broccoli_http_request_duration_seconds`) —
   detect is the only expensive endpoint (CPU YOLO inference) and the backend
   intentionally runs a single uvicorn worker, so requests queue behind each
   other. p95 latency is the first thing that degrades under load, well before
   anything errors. We track p95 rather than the average because the average
   hides the queueing tail that users actually feel.
3. **Process memory + CPU** (`process_resident_memory_bytes`,
   `process_cpu_seconds_total`) — torch + a loaded YOLO model put the process
   around 1 GB RSS, which is exactly why the app does not fit the 512 MB
   free tier. On any small instance, memory is the resource that kills this
   service (OOM), so watching RSS trend over time catches leaks from the
   image-processing path before the kernel does.

### Functional (is the model still doing its job?)

1. **Detection confidence distribution / mean**
   (`broccoli_detection_confidence`) — the model was trained on particular
   field conditions. A gradual slide in the confidence distribution, with no
   code change, is the classic signature of input drift: different season,
   different lighting, different camera height, mud on the lens. Confidence
   drift is the early warning that arrives *before* the model starts missing
   crowns outright.
2. **Empty-detection ratio** (`broccoli_empty_detections_total` /
   `broccoli_detection_requests_total`) — some empty results are legitimate
   (bare soil between rows), but a rising share of uploads returning zero
   crowns signals a mismatch between the confidence threshold and what the
   model now sees — or a model that no longer recognises the crop. It is the
   bluntest "the product stopped working" metric a farmer would notice, made
   visible to us first.
3. **Crown diameter distribution (p50/p90)** (`broccoli_crown_diameter_mm`) —
   diameter is the app's actual output of value (it drives the harvest-ready
   decision), and it depends on both the model's boxes and the camera-height
   geometry. Broccoli crowns have a known plausible size range, so a shifting
   p50 or a fat tail of 300 mm+ "crowns" flags either seasonal/growth-stage
   drift or a calibration bug (wrong `camera_height_mm`) producing
   confidently wrong agronomic numbers.

The dashboard also charts crowns-per-image p50 and YOLO inference p95 as
supporting context for the metrics above (density drift and the inference
share of request latency, respectively).

## What we would monitor next (in priority order)

1. **Alerting** — dashboards only help when someone is looking. Prometheus
   alert rules (5xx ratio, empty-rate jump, RSS ceiling) plus a notifier would
   be the first addition, because every metric below is worthless at 3 a.m.
   without it.
2. **Ground-truth feedback loop** — confidence and diameter distributions are
   *proxies* for accuracy. A way for users to flag wrong detections (or a
   periodically labelled sample of uploads) would let us monitor true
   precision/recall instead of inferring it.
3. **Input-image statistics** — brightness, blur and resolution histograms of
   uploads would let us distinguish "model drifted" from "users started
   sending bad photos", which need opposite fixes.
4. **Per-model-version breakdown** — labelling the functional metrics with
   `model_version` would turn every model rollout into an A/B comparison and
   make regressions attributable to a specific weights file.
5. **Container/host metrics** (cAdvisor / node-exporter) — process metrics
   show the app's view; container throttling and disk pressure (the uploads
   volume grows) need an outside view.
6. **Frontend/user-side signals** — upload failure rate and time-to-result as
   experienced in the browser, since backend p95 misses network and proxy
   issues.

## Monitoring is not free

Worth stating in a PoC that lives on small instances: the monitoring stack
itself consumes resources. Prometheus and Grafana add two always-on
containers (a few hundred MB of RAM plus disk for the TSDB), the 5-second
scrape interval trades CPU and storage for demo responsiveness (production
would use 15-60 s), and every histogram we add grows the `/metrics` payload
and the backend's per-request bookkeeping. Observability spend should stay
proportional to what it protects — which is why this stack is a separate,
optional compose file rather than part of the main app.
