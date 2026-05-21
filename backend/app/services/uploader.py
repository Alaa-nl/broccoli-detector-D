"""
ImageUploader: handles file uploads, format checks, and saving.

This service keeps all the file-handling logic in one place,
so the API route stays short and clear.
"""

import uuid
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError


class ImageUploader:
    """Save user-uploaded images to disk after basic validation."""

    # Only these file types are allowed (matches the Upload screen).
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}

    # Max file size in bytes. 10 MB is enough for any field photo
    # and matches the limit shown on the Upload screen.
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

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

        # Read the file content into memory.
        # We need the full bytes to check the size and to open
        # the image with PIL.
        content = await upload.read()

        if len(content) > self.MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File is too large ({len(content) / 1024 / 1024:.1f} MB). "
                    f"The maximum size is 10 MB."
                ),
            )

        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty.",
            )

        # Try to open the file as an image. If this fails, the
        # file is not a real image (it just has the right extension).
        try:
            from io import BytesIO
            pil_image = Image.open(BytesIO(content))
            # Convert to RGB to make sure we can run YOLO on it
            # (PNGs may have an alpha channel that YOLO does not like).
            pil_image = pil_image.convert("RGB")
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=400,
                detail="The file is not a valid image.",
            )

        # Build a unique image ID using uuid4 (random and short).
        image_id = uuid.uuid4().hex[:12]
        saved_filename = f"{image_id}{ext}"
        saved_path = self.upload_dir / saved_filename

        # Save the original image to disk.
        pil_image.save(saved_path)

        return saved_path, image_id, pil_image
