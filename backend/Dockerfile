# Dockerfile for the FastAPI backend.
# We use the official slim Python image to keep the size small.
FROM python:3.11-slim

# Set the working folder inside the container.
WORKDIR /app

# Install system libraries that OpenCV / Pillow need.
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first.
# Doing this in a separate step lets Docker cache the pip install
# layer when only the app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Copy the rest of the backend code (including the weights folder).
COPY . .

# Make sure the uploads folder exists.
RUN mkdir -p uploads

# Run as a non-root user so a parsing/deserialization bug (image parsing,
# torch.load of the weights, or a library CVE) cannot gain root inside the
# container. Create the user, then give it ownership of /app AFTER the code
# and weights are copied and uploads/ exists, so it can read the model and
# write annotated images.
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Tell Docker which port the app uses.
EXPOSE 8000

# Report container health from /api/health (200 = model loaded; 503 = degraded
# when the model isn't loaded). The slim image has no curl, so use Python's
# stdlib urllib, which exits non-zero on any non-2xx or connection error.
# start-period gives the YOLO model time to load before failures count.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"]

# Start the server as a single uvicorn process. We use 0.0.0.0 so it is
# reachable from outside the container. --limit-concurrency caps how many
# requests can be in flight at once so a burst of uploads can't pile up
# unbounded; excess requests get a fast 503 instead of exhausting memory.
#
# Running one process is deliberate, not a limitation: CPU-bound inference is
# offloaded to a worker thread, so the event loop stays responsive and the
# single process handles concurrent uploads fine on a small instance.
#
# We do NOT add more workers here. On the small hosting tier this app targets
# (~0.1-0.5 CPU, 512 MB RAM) extra workers would hurt rather than help:
#   - each worker loads its own copy of the model + torch into RAM, so two or
#     more workers can exceed the memory limit and get OOM-killed;
#   - the rate limiter and the upload-retention sweep keep their state inside
#     the process, so N workers make the rate limit N times looser and run N
#     redundant sweeps over the same uploads folder.
# To scale on a larger multi-CPU instance, first move rate-limit state to a
# shared store (e.g. Redis), then add a process manager / extra workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "32"]
