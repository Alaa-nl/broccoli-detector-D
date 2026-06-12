"""Resolves which model weights file to load, and fetches remote weights.

Model versioning works in two layers:

  - weights/registry.json is the model registry: each released version maps
    to a filename, its SHA-256, the dataset version it was trained on, and
    its evaluation metrics. /api/metadata surfaces this as a model card.
  - MODEL_VERSION selects the entry to load. When that file is not on disk
    (an image without baked weights, or a version newer than the image),
    MODEL_WEIGHTS_URL (typically an Azure Blob SAS URL) is downloaded once
    into the weights dir and reused on later restarts.

Integrity stays in BroccoliDetector: it hashes the file before torch.load
unpickles anything. This module only decides WHICH file to load and what
the expected hash is (env pin wins over the registry).
"""

import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from app import config

logger = logging.getLogger(__name__)

_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 60

# Version tags become filenames for unregistered versions, so restrict them
# to safe characters - "../x" must never escape the weights dir.
_VERSION_RE = re.compile(r"[A-Za-z0-9._-]+\Z")


def load_registry() -> dict:
    """Parse the model registry; a missing/corrupt file degrades to {}.

    Degrading (rather than raising) keeps frontend-dev setups working when
    the registry is absent - the version then simply has no metadata.
    """
    try:
        with open(config.MODEL_REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(
            "Model registry not found (%s).", config.MODEL_REGISTRY_PATH.name
        )
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Model registry unreadable: %s", exc)
        return {}


def get_registry_entry(version: str) -> Optional[dict]:
    """Return the registry entry for `version`, or None if unregistered."""
    for entry in load_registry().get("models", []):
        if entry.get("version") == version:
            return entry
    return None


def expected_sha256(version: str) -> Optional[str]:
    """Expected weights hash: the env pin wins, else the registry entry.

    The env var stays as a deploy-time override so an operator can pin a
    hash without shipping a registry change (and so existing deployments
    keep working unchanged).
    """
    if config.EXPECTED_WEIGHTS_SHA256:
        return config.EXPECTED_WEIGHTS_SHA256
    entry = get_registry_entry(version)
    if entry:
        return entry.get("sha256")
    return None


def compute_sha256(path: Path) -> str:
    """Lowercase hex SHA-256 of a file, read in chunks to bound memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_DOWNLOAD_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_weights(
    version: Optional[str] = None,
    url: Optional[str] = None,
) -> Tuple[Path, str]:
    """Decide which weights file MODEL_VERSION refers to, fetching if needed.

    Returns (path, source) where source is:
      - "local":   the file was already on disk (baked into the image or
                   cached by an earlier download),
      - "remote":  it was just downloaded from MODEL_WEIGHTS_URL,
      - "missing": not on disk and not downloadable. The caller decides
                   whether that is fatal (it is, unless ALLOW_MISSING_WEIGHTS).

    A download failure deliberately degrades to "missing" instead of raising:
    the existing missing-weights startup path already produces the right
    behaviour for both dev (ALLOW_MISSING_WEIGHTS) and prod (refuse to start).
    """
    version = version or config.MODEL_VERSION
    url = url if url is not None else config.MODEL_WEIGHTS_URL

    entry = get_registry_entry(version)
    # Unregistered versions still get a deterministic filename so a download
    # is cached under a name that identifies it. The tag is validated first:
    # it is operator-controlled env config, but failing loudly on "../x"
    # beats quietly writing outside the weights dir.
    filename = (entry or {}).get("file")
    if not filename:
        if not _VERSION_RE.fullmatch(version):
            raise ValueError(
                f"MODEL_VERSION {version!r} contains unsupported characters; "
                "use letters, digits, dots, dashes and underscores."
            )
        filename = f"model-{version}.pt"
    path = config.WEIGHTS_DIR / filename

    if path.exists():
        return path, "local"

    if url:
        try:
            _download(url, path)
            return path, "remote"
        except Exception as exc:  # noqa: BLE001 - degrade to "missing"
            logger.error("Model weights download failed: %s", exc)

    return path, "missing"


def _redact_url(url: str) -> str:
    """Strip the query string before logging - SAS tokens are credentials."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _download(url: str, dest: Path) -> None:
    """Stream the weights to a temp file, then atomically rename into place.

    Temp-then-rename means a crashed or partial download can never be
    mistaken for real weights on the next boot. The size cap is a backstop
    against a misconfigured URL serving something enormous. Integrity is
    NOT checked here - the detector hashes the final file before loading.
    """
    if not url.lower().startswith("https://"):
        # SAS URLs are credentials; sending one over plain HTTP leaks it.
        logger.warning("Model weights URL is not HTTPS; credentials may leak.")

    logger.info("Downloading model weights %s -> %s", _redact_url(url), dest.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    request = urllib.request.Request(url, headers={"User-Agent": "broccoli-detect"})
    total = 0
    try:
        with urllib.request.urlopen(
            request, timeout=_DOWNLOAD_TIMEOUT_SECONDS
        ) as response, open(tmp, "wb") as out:
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > config.MAX_WEIGHTS_DOWNLOAD_BYTES:
                    raise RuntimeError(
                        "Weights download exceeded the size cap; aborting."
                    )
                out.write(chunk)
        tmp.replace(dest)
        logger.info("Downloaded %d bytes of model weights (%s).", total, dest.name)
    finally:
        # No-op after a successful replace; cleans up after any failure.
        tmp.unlink(missing_ok=True)
