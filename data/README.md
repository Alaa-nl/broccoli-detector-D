# Data versioning

Why this folder exists, where the actual images live, and how to publish a
new dataset version.

## Purpose

This folder is the dataset half of the project's lineage chain:

```
deployed container  →  model version (backend/weights/registry.json)
                          →  dataset version (data/registry.json)
                                →  archive in Azure Blob Storage
```

Every model version recorded in `backend/weights/registry.json` names the
dataset version it was trained on; `data/registry.json` is where those
dataset versions are defined. Given any deployed model you can walk back to
the exact set of images — and their checksums — that produced it.

The images themselves are **not** in this repo. The repo holds only the
registry: for each version a description, source, blob-storage location,
archive checksum, image counts, annotation format, and which model versions
consumed it. The current entry, `broccoli-rgb-v1`, is the Deliverable B
training data (the RGB channel of the original RGB-D capture); its image
counts are `null` until the team archives the dataset, because only the
27-image test split is certain today.

## Adding a new dataset version

1. **Build the manifest.** Inside the dataset directory, run:

   ```bash
   scripts/data/make_manifest.py path/to/dataset --version broccoli-rgb-v2
   ```

   This writes `manifest.json` (per-file sha256 + size) into the dataset
   directory, so the integrity record travels inside the archive.

2. **Zip the dataset** (manifest included), named after the version:

   ```bash
   cd path/to && zip -r broccoli-rgb-v2.zip dataset/
   ```

3. **Hash the archive** for the registry:

   ```bash
   scripts/data/make_manifest.py --archive broccoli-rgb-v2.zip
   ```

4. **Upload to blob storage** (uses your own `az login`, no stored keys):

   ```bash
   scripts/data/upload_dataset.sh --account <storage-account> \
       --archive broccoli-rgb-v2.zip --version broccoli-rgb-v2
   ```

5. **Add the entry to `data/registry.json`** — copy the `broccoli-rgb-v1`
   entry and fill in every field, including `archive_sha256` from step 3 and
   the blob URL printed in step 4. A published version is immutable: never
   replace an uploaded archive, publish a new version instead.

6. **Reference it from the model registry.** When a model is retrained on
   the new data, its entry in `backend/weights/registry.json` should name
   this dataset version, keeping the lineage chain unbroken.

## Why the images are not in Git

Git is the right home for the registry but the wrong home for the dataset
itself:

- **Repo bloat.** Git stores binary files as full snapshots, not deltas, and
  keeps every historical version forever. A few hundred JPGs re-added per
  dataset revision would grow the repo permanently — deleting them later
  does not shrink history.
- **Clone times.** Everyone (and every CI run) clones the full history. A
  backend developer changing one line of Python should not have to pull
  gigabytes of field photos first.
- **No live updating.** A Git checkout is a frozen snapshot wired to the
  commit/PR workflow. Datasets grow as new field photos are captured, and
  that flow — append images, re-annotate, re-archive — does not fit code
  review. Blob storage holds the live artifacts; Git only pins which frozen
  version each model used.
