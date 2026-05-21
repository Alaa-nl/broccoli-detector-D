"""
Annotator: draws bounding boxes and labels on the result image.

We do this on the backend so the frontend can show one simple
<img> tag instead of drawing boxes with HTML canvas.
"""

from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont


# Inholland green colour theme (from the TFGD design).
BOX_COLOUR = (34, 197, 94)       # Tailwind green-500
TEXT_BG_COLOUR = (22, 163, 74)   # Tailwind green-600
TEXT_COLOUR = (255, 255, 255)    # white


def _load_font(size: int = 16) -> ImageFont.ImageFont:
    """Try to load a clear font. Fall back to the default if missing."""
    # We try a few common system fonts in this order.
    for font_name in ("DejaVuSans-Bold.ttf", "Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except (OSError, IOError):
            continue
    # If no TrueType font is on the system, use the basic default.
    return ImageFont.load_default()


def draw_detections(
    image: Image.Image,
    crowns: List[dict],
    output_path: Path,
) -> Path:
    """Draw boxes and crown info on the image and save it.

    Args:
        image: The original PIL image (RGB).
        crowns: List of detection dicts. Each one must contain:
            crown_id, bbox (with x1,y1,x2,y2), diameter_cm,
            size_category, confidence.
        output_path: Where to save the annotated image.

    Returns:
        The output_path (so the caller can build a URL from it).
    """
    # Make a copy so we do not draw on the original.
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)

    # Scale the line width and font size with the image size,
    # so the boxes look good on both small and large photos.
    img_width = annotated.width
    line_width = max(2, img_width // 400)
    font_size = max(14, img_width // 60)
    font = _load_font(font_size)

    for crown in crowns:
        bbox = crown["bbox"]
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]

        # Draw the green box.
        draw.rectangle(
            [x1, y1, x2, y2],
            outline=BOX_COLOUR,
            width=line_width,
        )

        # Build the label text.
        label = (
            f"#{crown['crown_id']}  "
            f"{crown['diameter_cm']:.1f} cm  "
            f"({crown['size_category']})"
        )

        # Measure the text size so we can draw a filled background
        # box behind the text, which makes it easy to read.
        bbox_text = draw.textbbox((0, 0), label, font=font)
        text_w = bbox_text[2] - bbox_text[0]
        text_h = bbox_text[3] - bbox_text[1]

        # Position the label just above the box (or below if the
        # box is at the top of the image).
        padding = 4
        label_y = y1 - text_h - 2 * padding
        if label_y < 0:
            label_y = y2 + padding

        # Draw the filled label background.
        draw.rectangle(
            [x1, label_y, x1 + text_w + 2 * padding, label_y + text_h + 2 * padding],
            fill=TEXT_BG_COLOUR,
        )
        # Draw the label text on top.
        draw.text(
            (x1 + padding, label_y + padding),
            label,
            fill=TEXT_COLOUR,
            font=font,
        )

    annotated.save(output_path)
    return output_path
