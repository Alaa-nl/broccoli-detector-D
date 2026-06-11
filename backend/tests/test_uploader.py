"""Unit tests for ImageUploader.save, driven directly (no HTTP layer).

Starlette's UploadFile wraps a BytesIO so we exercise the real async
read loop. save() is a coroutine, hence the asyncio.run calls.
"""

import asyncio
import io

import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import UploadFile

from app.services.uploader import ImageUploader


def _upload(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


def _image_bytes(fmt: str, size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (34, 120, 60)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def uploader(tmp_path):
    return ImageUploader(upload_dir=tmp_path)


def _save_expecting_http_error(uploader, upload) -> HTTPException:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(uploader.save(upload))
    return exc_info.value


def test_rejects_disallowed_extension(uploader):
    exc = _save_expecting_http_error(uploader, _upload(b"hello", "notes.txt"))
    assert exc.status_code == 400


def test_rejects_empty_file(uploader):
    exc = _save_expecting_http_error(uploader, _upload(b"", "empty.jpg"))
    assert exc.status_code == 400


def test_rejects_non_image_bytes_with_image_extension(uploader):
    # The extension passes the cheap pre-filter; the decode must catch it.
    exc = _save_expecting_http_error(
        uploader, _upload(b"definitely not pixels", "fake.jpg")
    )
    assert exc.status_code == 400


def test_decoded_format_wins_over_filename(uploader, tmp_path):
    # PNG bytes wearing a .jpg name: the saved file must carry the real
    # format's extension, since the filename is attacker-controlled.
    png_named_jpg = _upload(_image_bytes("PNG"), "photo.jpg")

    saved_path, image_id, pil_image = asyncio.run(uploader.save(png_named_jpg))

    assert saved_path.suffix == ".png"
    assert saved_path.parent == tmp_path
    assert saved_path.exists()


def test_oversized_stream_returns_413(uploader):
    # Shrink the cap on this instance only; the size check streams, so the
    # 413 fires before any image decoding happens.
    uploader.MAX_FILE_SIZE_BYTES = 1024
    exc = _save_expecting_http_error(
        uploader, _upload(b"x" * 2048, "big.jpg")
    )
    assert exc.status_code == 413


def test_valid_jpeg_is_saved(uploader, tmp_path):
    saved_path, image_id, pil_image = asyncio.run(
        uploader.save(_upload(_image_bytes("JPEG"), "crown.jpg"))
    )

    assert saved_path.exists()
    assert saved_path.parent == tmp_path
    assert saved_path.suffix == ".jpg"
    # The id links the original to its annotated copy; 12 hex chars.
    assert len(image_id) == 12
    assert saved_path.stem == image_id
    # YOLO needs RGB; the uploader converts on the way in.
    assert pil_image.mode == "RGB"
    assert pil_image.size == (64, 48)
