"""Contour-based item cropping for fraud-search segmentation previews."""

from __future__ import annotations

import base64
import io
from typing import Any, List

from PIL import Image, ImageDraw


def extract_image_bytes_from_contours(
    image_bytes: bytes, contours: List[Any], padding: int = 0
) -> bytes:
    """
    Crop a single item from the full image using contours.
    Outside-mask pixels are white (matches aurum search crops).
    """
    if not contours:
        raise ValueError('Contours cannot be empty')

    with Image.open(io.BytesIO(image_bytes)) as img:
        image = img.convert('RGB')

    all_points: list[tuple[int, int]] = []
    polygon_groups: list[list[tuple[int, int]]] = []
    for contour_group in contours:
        if not contour_group:
            continue
        points: list[tuple[int, int]] = []
        for pt in contour_group:
            if not pt or len(pt) < 2:
                continue
            points.append((int(pt[0]), int(pt[1])))
        if len(points) >= 3:
            polygon_groups.append(points)
            all_points.extend(points)

    if not polygon_groups:
        raise ValueError('No valid contour points found')

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    x0 = max(0, min(xs) - padding)
    y0 = max(0, min(ys) - padding)
    x1 = min(image.width, max(xs) + 1 + padding)
    y1 = min(image.height, max(ys) + 1 + padding)
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Invalid contour bounding box')

    crop = image.crop((x0, y0, x1, y1))
    mask = Image.new('L', crop.size, 0)
    draw = ImageDraw.Draw(mask)
    for points in polygon_groups:
        offset_pts = [(x - x0, y - y0) for x, y in points]
        draw.polygon(offset_pts, fill=255)

    white = Image.new('RGB', crop.size, (255, 255, 255))
    result = Image.composite(crop, white, mask)

    buffer = io.BytesIO()
    result.save(buffer, format='JPEG', quality=85)
    return buffer.getvalue()


def bytes_to_data_url(image_bytes: bytes, mime_type: str = 'image/jpeg') -> str:
    encoded = base64.b64encode(image_bytes).decode('utf-8')
    return f'data:{mime_type};base64,{encoded}'
