"""Validates and saves user-uploaded images. Filename and format are
server-controlled (decoded from content, not the user-supplied name).
"""

import uuid
from io import BytesIO
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app import config

# Arm Pillow's decompression bomb guard at import time; raises
# Image.DecompressionBombError during decode if exceeded.
Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS


class ImageUploader:
    """Save user-uploaded images to disk after basic validation."""
    
    # Cheap pre-filter on the claimed extension; real check is FORMAT_TO_EXT.
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

    # Map decoded Pillow format to extension. The saved filename uses this,
    # not the user's filename, so it always reflects real content.
    FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png"}

    MAX_FILE_SIZE_BYTES = config.MAX_FILE_SIZE_BYTES

    # Decoded pixel cap; bounds memory in .convert() and downstream np.array().
    MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS

    # Chunk size for streaming reads; lets us abort oversized uploads early.
    READ_CHUNK_BYTES = config.READ_CHUNK_BYTES

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
        if not upload.filename:
            raise HTTPException(
                status_code=400,
                detail="No file name was sent with the upload.",
            )

        # Quick reject on extension before reading the body; the real check
        # is the decoded format below.
        claimed_ext = Path(upload.filename).suffix.lower()
        if claimed_ext not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File type '{claimed_ext}' is not allowed. "
                    f"Please upload a JPG or PNG image."
                ),
            )

        # Stream into a BytesIO with a running size cap: aborts oversized
        # uploads without buffering them, and reuses the same buffer for
        # Image.open() below.
        total = 0
        buffer = BytesIO()
        while chunk := await upload.read(self.READ_CHUNK_BYTES):
            total += len(chunk)
            if total > self.MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "File is too large. The maximum size is "
                        f"{self.MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                    ),
                )
            buffer.write(chunk)

        if total == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # Rewind the buffer before reading it: write() above left the cursor
        # at the end, so without this Image.open() would start at EOF and fail.
        buffer.seek(0)

        # Image.open() only parses the header (no pixel decode), so it's
        # cheap to do before the pixel cap check below.
        try:
            pil_image = Image.open(buffer)
        except (UnidentifiedImageError, OSError):
            raise HTTPException(
                status_code=400,
                detail="The file is not a valid image.",
            )

        # Reject bombs (small file, huge pixel count) before the full RGB
        # decode would allocate width*height*3 bytes.
        width, height = pil_image.size
        if width * height > self.MAX_IMAGE_PIXELS:
            raise HTTPException(
                status_code=413,
                detail="Image dimensions are too large.",
            )

        # Use the decoded format, not the filename: catches PNG bytes
        # named "photo.jpg". Read .format here before .convert() below
        # resets it to None.
        img_format = pil_image.format
        ext = self.FORMAT_TO_EXT.get(img_format)
        if ext is None:
            raise HTTPException(
                status_code=400,
                detail="Unsupported image format. Please upload a JPG or PNG image.",
            )

        # Convert to RGB for YOLO (alpha channels cause issues). This is
        # the full decode, so bomb/truncation errors surface here.
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

        # Server-controlled filename: random UUID + format-derived extension.
        image_id = uuid.uuid4().hex[:12]
        saved_filename = f"{image_id}{ext}"
        saved_path = self.upload_dir / saved_filename

        # Save the original image to disk. The extension matches the true
        # format, so Pillow encodes it consistently.
        pil_image.save(saved_path)

        return saved_path, image_id, pil_image
