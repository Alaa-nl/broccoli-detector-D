"""
ImageUploader: handles file uploads, format checks, and saving.

This service keeps all the file-handling logic in one place,
so the API route stays short and clear.
"""

import uuid
from io import BytesIO
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

# Reject images whose decoded pixel count would blow up memory
# (a "decompression bomb": a tiny file that expands to enormous
# dimensions). Setting this at import time also arms Pillow's own
# guard, which raises Image.DecompressionBombError during decode.
Image.MAX_IMAGE_PIXELS = 25_000_000  # ~25 megapixels


class ImageUploader:
    """Save user-uploaded images to disk after basic validation."""

    # Only these file types are allowed (matches the Upload screen).
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}

    # Max file size in bytes. 10 MB is enough for any field photo
    # and matches the limit shown on the Upload screen.
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    # Max decoded image size in pixels (width * height). Bounds the
    # memory used by .convert("RGB") and the later np.array() in the
    # detector, independent of the on-disk file size above.
    MAX_IMAGE_PIXELS = 25_000_000  # ~25 megapixels

    # Read the upload in chunks so we can abort on an oversized body
    # before the whole thing is buffered into memory.
    READ_CHUNK_BYTES = 64 * 1024  # 64 KB

    def __init__(self, upload_dir: Path):
        """Set up the uploader with the target folder.

        Args:
            upload_dir: Folder where uploaded files will be saved.
        """
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile) -> Tuple[Path, str, Image.Image]:
        """Validate and save an uploaded image.

        Args:
            upload: The UploadFile object from FastAPI.

        Returns:
            Tuple of (saved_path, image_id, pil_image).
            'image_id' is a unique short ID used to link the
            original and the annotated copy on disk.

        Raises:
            HTTPException: If the file is missing, too big,
                or not a valid image.
        """
        # Check that a file name is present.
        if not upload.filename:
            raise HTTPException(
                status_code=400,
                detail="No file name was sent with the upload.",
            )

        # Check the extension.
        ext = Path(upload.filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File type '{ext}' is not allowed. "
                    f"Please upload a JPG or PNG image."
                ),
            )

        # Read the upload in chunks with a running size cap. This aborts
        # an oversized upload before the whole body is buffered into
        # memory, instead of reading everything first and checking the
        # size after the fact (which would already have spent the RAM).
        total = 0
        chunks = []
        while chunk := await upload.read(self.READ_CHUNK_BYTES):
            total += len(chunk)
            if total > self.MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="File is too large. The maximum size is 10 MB.",
                )
            chunks.append(chunk)
        content = b"".join(chunks)

        if total == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # Open the file header to confirm it is a real image and to read
        # its dimensions. Image.open() only parses the header (it does
        # not decode the pixels yet), so this is cheap and safe to do
        # before the pixel cap below.
        try:
            pil_image = Image.open(BytesIO(content))
        except (UnidentifiedImageError, OSError):
            raise HTTPException(
                status_code=400,
                detail="The file is not a valid image.",
            )

        # Reject decompression bombs (tiny file, huge dimensions) before
        # the expensive .convert("RGB") full decode, which would expand
        # to width * height * 3 bytes in memory.
        width, height = pil_image.size
        if width * height > self.MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=413,
                detail="Image dimensions are too large.",
            )

        # Convert to RGB to make sure we can run YOLO on it (PNGs may
        # have an alpha channel that YOLO does not like). This is the
        # full decode, so it is also where Pillow's own bomb guard and
        # truncated-file errors surface.
        try:
            pil_image = pil_image.convert("RGB")
        except Image.DecompressionBombError:
            raise HTTPException(
                status_code=413,
                detail="Image dimensions are too large.",
            )
        except OSError:
            raise HTTPException(
                status_code=400,
                detail="The image file is truncated or corrupt.",
            )

        # Build a unique image ID using uuid4 (random and short).
        image_id = uuid.uuid4().hex[:12]
        saved_filename = f"{image_id}{ext}"
        saved_path = self.upload_dir / saved_filename

        # Save the original image to disk.
        pil_image.save(saved_path)

        return saved_path, image_id, pil_image
