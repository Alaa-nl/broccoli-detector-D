"""Unit tests for model weights resolution, registry lookup and download."""

import functools
import hashlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app import config
from app.services import model_store

REGISTRY_SHA = "bf5f8500bba6a3b52bb55aec0212eef64581bff199e0e64a9f42322bf04acf6f"


@pytest.fixture
def local_http_server(tmp_path):
    """Serve tmp_path/served over a real loopback HTTP server.

    A genuine socket exercises _download's urllib + streaming + temp-rename
    path end to end, which mocking urlopen would not.
    """
    served_dir = tmp_path / "served"
    served_dir.mkdir()

    handler = functools.partial(
        SimpleHTTPRequestHandler, directory=str(served_dir)
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield served_dir, base_url

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def isolated_weights_dir(tmp_path, monkeypatch):
    """Point the model store at an empty weights dir under tmp_path.

    Download tests must never write into the real backend/weights/.
    The registry path is redirected too (to a nonexistent file, which
    load_registry treats as an empty registry).
    """
    weights_dir = tmp_path / "weights"
    monkeypatch.setattr(config, "WEIGHTS_DIR", weights_dir)
    monkeypatch.setattr(config, "MODEL_REGISTRY_PATH", tmp_path / "registry.json")
    return weights_dir


def test_get_registry_entry_finds_released_version():
    entry = model_store.get_registry_entry("v1.0.0")
    assert entry is not None
    assert entry["file"] == "best.pt"
    assert entry["sha256"] == REGISTRY_SHA


def test_get_registry_entry_unknown_version_is_none():
    assert model_store.get_registry_entry("v9.9.9") is None


def test_expected_sha256_env_pin_wins_over_registry(monkeypatch):
    pinned = "f" * 64
    monkeypatch.setattr(config, "EXPECTED_WEIGHTS_SHA256", pinned)
    assert model_store.expected_sha256("v1.0.0") == pinned


def test_expected_sha256_falls_back_to_registry(monkeypatch):
    monkeypatch.setattr(config, "EXPECTED_WEIGHTS_SHA256", None)
    assert model_store.expected_sha256("v1.0.0") == REGISTRY_SHA
    # An unregistered version with no pin has no expectation at all.
    assert model_store.expected_sha256("v9.9.9") is None


def test_resolve_weights_local_for_released_version(monkeypatch):
    monkeypatch.setattr(config, "MODEL_WEIGHTS_URL", None)
    path, source = model_store.resolve_weights(version="v1.0.0")
    assert source == "local"
    assert path.name == "best.pt"
    assert path.exists()


def test_resolve_weights_unregistered_version_is_missing(
    isolated_weights_dir, monkeypatch
):
    monkeypatch.setattr(config, "MODEL_WEIGHTS_URL", None)
    path, source = model_store.resolve_weights(version="v9.9.9")
    assert source == "missing"
    # Unregistered versions still get a deterministic cache filename.
    assert path.name == "model-v9.9.9.pt"
    assert not path.exists()


def test_resolve_weights_downloads_remote_then_caches(
    isolated_weights_dir, local_http_server
):
    served_dir, base_url = local_http_server
    payload = b"pretend-weights " * 64
    (served_dir / "weights.bin").write_bytes(payload)
    url = f"{base_url}/weights.bin"

    path, source = model_store.resolve_weights(version="v2.0.0", url=url)

    assert source == "remote"
    assert path == isolated_weights_dir / "model-v2.0.0.pt"
    assert path.read_bytes() == payload
    # The temp-then-rename download leaves no partial file behind.
    assert list(isolated_weights_dir.iterdir()) == [path]

    # Second resolve finds the cached file without re-downloading.
    path_again, source_again = model_store.resolve_weights(
        version="v2.0.0", url=url
    )
    assert (path_again, source_again) == (path, "local")


def test_download_over_size_cap_degrades_to_missing(
    isolated_weights_dir, local_http_server, monkeypatch
):
    served_dir, base_url = local_http_server
    (served_dir / "huge.bin").write_bytes(b"x" * 4096)
    # Tiny cap so the served file trips the backstop immediately.
    monkeypatch.setattr(config, "MAX_WEIGHTS_DOWNLOAD_BYTES", 1024)

    path, source = model_store.resolve_weights(
        version="v3.0.0", url=f"{base_url}/huge.bin"
    )

    assert source == "missing"
    assert not path.exists()
    # Neither the final file nor the .tmp may survive an aborted download.
    assert list(isolated_weights_dir.iterdir()) == []


def test_compute_sha256_of_known_file(tmp_path):
    content = b"broccoli bytes for hashing\n"
    target = tmp_path / "blob.bin"
    target.write_bytes(content)
    assert model_store.compute_sha256(target) == hashlib.sha256(content).hexdigest()
