"""Geometry between CSV (center_x, center_y) and napari shapes (y, x vertices)."""

from __future__ import annotations

import numpy as np

from napari_annotation_plugin.config import CLASS_NAMES
from napari_annotation_plugin.models import AnnotationRow


def center_size_to_corners_yx(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
) -> np.ndarray:
    """
    Build rectangle corners for napari Shapes (2D), vertex order (row, col) = (y, x).

    CSV convention: center_x is horizontal (column index), center_y is vertical (row index).
    """
    half_w = width / 2.0
    half_h = height / 2.0
    # Counter-clockwise from top-left in image coordinates
    corners = np.array(
        [
            [center_y - half_h, center_x - half_w],
            [center_y - half_h, center_x + half_w],
            [center_y + half_h, center_x + half_w],
            [center_y + half_h, center_x - half_w],
        ],
        dtype=np.float32,
    )
    return corners


def corners_yx_to_center_size(corners_yx: np.ndarray) -> tuple[float, float, float, float]:
    """
    Recover center and size from a rectangle vertex array (4, 2) in (y, x) order.

    Works for axis-aligned rectangles; uses min/max of vertices.
    """
    c = np.asarray(corners_yx, dtype=np.float64)
    if c.shape != (4, 2):
        raise ValueError(f"Expected shape (4, 2), got {c.shape}")
    ys = c[:, 0]
    xs = c[:, 1]
    min_y, max_y = float(ys.min()), float(ys.max())
    min_x, max_x = float(xs.min()), float(xs.max())
    center_y = (min_y + max_y) / 2.0
    center_x = (min_x + max_x) / 2.0
    width = max_x - min_x
    height = max_y - min_y
    return center_x, center_y, width, height


def annotation_rows_to_shapes_data(
    rows: list[AnnotationRow],
) -> tuple[list[np.ndarray], list[int]]:
    """Convert annotation rows to napari shapes data and parallel class ids."""
    data: list[np.ndarray] = []
    class_ids: list[int] = []
    for row in rows:
        data.append(
            center_size_to_corners_yx(
                row.center_x,
                row.center_y,
                row.width,
                row.height,
            )
        )
        class_ids.append(row.class_id)
    return data, class_ids


def shapes_data_to_annotation_rows(
    shapes_data: list[np.ndarray],
    class_ids: list[int],
) -> list[AnnotationRow]:
    """Convert napari rectangle data back to AnnotationRow list."""
    if len(shapes_data) != len(class_ids):
        raise ValueError("shapes_data and class_ids length mismatch")
    rows: list[AnnotationRow] = []
    for corners, cid in zip(shapes_data, class_ids):
        cx, cy, w, h = corners_yx_to_center_size(np.asarray(corners))
        rows.append(
            AnnotationRow(
                center_x=cx,
                center_y=cy,
                width=w,
                height=h,
                class_id=int(cid),
            )
        )
    return rows


def class_id_to_color_rgba(class_id: int) -> np.ndarray:
    """Deterministic distinct colors per class_id (RGBA float 0..1)."""
    import colorsys

    hue = (class_id * 0.1313) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.95)
    return np.array([r, g, b, 0.45], dtype=np.float32)


def colors_for_class_ids(class_ids: list[int]) -> np.ndarray:
    """(N, 4) RGBA array for napari Shapes face_color."""
    if not class_ids:
        return np.zeros((0, 4), dtype=np.float32)
    return np.stack([class_id_to_color_rgba(c) for c in class_ids])


def legend_text() -> str:
    """Human-readable class id -> name mapping for the dock widget."""
    lines = []
    for cid in sorted(CLASS_NAMES.keys()):
        lines.append(f"{cid}: {CLASS_NAMES[cid]}")
    return "\n".join(lines) if lines else "(no classes configured)"
