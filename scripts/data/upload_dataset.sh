#!/usr/bin/env bash
#
# Upload a dataset archive to the team's Azure Blob container and print the
# blob URL to record in data/registry.json.
#
# Auth is your own Azure AD session (az login) via --auth-mode login, so no
# storage key or connection string ever needs to exist in this repo.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: upload_dataset.sh --account <storage-account> --archive <path/to.zip> \
                         --version <dataset-version> [--container <name>]

Uploads the archive as <container>/<version>.zip.

Options:
  --account    Azure storage account name (required)
  --archive    Path to the dataset .zip, built after make_manifest.py so the
               manifest travels inside it (required)
  --version    Dataset version string, e.g. broccoli-rgb-v1; becomes the
               blob name <version>.zip (required)
  --container  Blob container name (default: datasets)
  -h, --help   Show this help

Prerequisites: Azure CLI installed and logged in (az login) with the
"Storage Blob Data Contributor" role on the storage account.
EOF
}

ACCOUNT=""
CONTAINER="datasets"
ARCHIVE=""
VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --account)   ACCOUNT="$2";   shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --archive)   ARCHIVE="$2";   shift 2 ;;
    --version)   VERSION="$2";   shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$ACCOUNT" || -z "$ARCHIVE" || -z "$VERSION" ]]; then
  echo "Error: --account, --archive and --version are all required." >&2
  usage >&2
  exit 1
fi

# Check the archive before anything that needs Azure: a typo'd path should
# fail immediately, not after a container has already been created.
if [[ ! -f "$ARCHIVE" ]]; then
  echo "Error: archive not found: $ARCHIVE" >&2
  echo "Zip the dataset first (after running scripts/data/make_manifest.py" >&2
  echo "inside it, so the manifest is included in the archive)." >&2
  exit 1
fi

if ! command -v az >/dev/null 2>&1; then
  echo "Error: Azure CLI (az) not found. Install it and run 'az login' first." >&2
  exit 1
fi

BLOB_NAME="${VERSION}.zip"

# Container create is idempotent: it succeeds whether or not the container
# already exists, so re-running this script is always safe.
az storage container create \
  --account-name "$ACCOUNT" \
  --name "$CONTAINER" \
  --auth-mode login \
  --output none

# --overwrite false: a published dataset version is immutable. If this fails
# because the blob already exists, bump the version instead of replacing
# bytes that a model in backend/weights/registry.json may already claim it
# was trained on.
az storage blob upload \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB_NAME" \
  --file "$ARCHIVE" \
  --auth-mode login \
  --overwrite false \
  --output none

BLOB_URL="https://${ACCOUNT}.blob.core.windows.net/${CONTAINER}/${BLOB_NAME}"

echo "Uploaded: $BLOB_URL"
echo
echo "Now record this version in data/registry.json:"
echo "  archive_sha256: scripts/data/make_manifest.py --archive \"$ARCHIVE\""
echo "  storage url:    $BLOB_URL"
