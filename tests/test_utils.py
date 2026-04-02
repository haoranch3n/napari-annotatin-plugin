"""Tests for geometry utilities."""

from __future__ import annotations

import numpy as np
import pytest

from napari_annotation_plugin.models import AnnotationRow
from napari_annotation_plugin.utils import (
    annotation_rows_to_shapes_data,
    center_size_to_corners_yx,
    corners_yx_to_center_size,
    shapes_data_to_annotation_rows,
)


def test_center_corners_round_trip() -> None:
    cx, cy, w, h = 100.0, 50.0, 20.0, 10.0
    c = center_size_to_corners_yx(cx, cy, w, h)
    assert c.shape == (4, 2)
    cx2, cy2, w2, h2 = corners_yx_to_center_size(c)
    assert pytest.approx(cx2) == cx
    assert pytest.approx(cy2) == cy
    assert pytest.approx(w2) == w
    assert pytest.approx(h2) == h


def test_annotation_rows_shapes_round_trip() -> None:
    rows = [
        AnnotationRow(10.0, 20.0, 4.0, 6.0, 1),
        AnnotationRow(0.0, 0.0, 2.0, 2.0, 2),
    ]
    data, cids = annotation_rows_to_shapes_data(rows)
    assert len(data) == 2
    assert cids == [1, 2]
    back = shapes_data_to_annotation_rows(data, cids)
    assert len(back) == 2
    for a, b in zip(rows, back):
        assert pytest.approx(a.center_x) == b.center_x
        assert pytest.approx(a.center_y) == b.center_y
        assert pytest.approx(a.width) == b.width
        assert pytest.approx(a.height) == b.height
        assert a.class_id == b.class_id


def test_corners_wrong_shape() -> None:
    with pytest.raises(ValueError):
        corners_yx_to_center_size(np.zeros((3, 2)))
