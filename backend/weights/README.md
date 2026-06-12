# Model weights folder

The trained YOLOv8n weights live here, tracked by `registry.json` — the
model registry. Each released version has an entry mapping the version tag
to a filename, its SHA-256, the dataset version it was trained on, and its
evaluation metrics. The backend loads the version selected by the
`MODEL_VERSION` env var (default `v1.0.0` → `best.pt`) and verifies the
file's hash against the registry (or `EXPECTED_WEIGHTS_SHA256`, which wins
when set) before `torch.load` touches it.

## Releasing a new model version

1. Train in the Deliverable-B pipeline; note the dataset version used
   (see `data/registry.json` at the repo root).
2. Compute the hash: `shasum -a 256 path/to/new.pt`
3. Add a new entry to `registry.json` (e.g. `v1.1.0`, file
   `model-v1.1.0.pt`) with the hash, dataset version, and eval metrics.
   Never edit a released entry.
4. Upload the file to the team's Azure Blob container (see
   `scripts/data/upload_dataset.sh` for the pattern), or commit it here if
   it must ship baked into the image.
5. Deploy by setting `MODEL_VERSION=v1.1.0` (plus `MODEL_WEIGHTS_URL` with
   a SAS URL when the file isn't baked into the image). Rollback is the
   same step with the previous version.

If you do not put a weights file here, the backend will only start with
`ALLOW_MISSING_WEIGHTS=1`, and every detection call returns 503 until the
weights are present.
