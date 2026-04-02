"""Tests for annotation loading and image helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from napari_annotation_plugin.data_io import (
    CsvAnnotationLoader,
    ensure_2d_image,
    find_annotation_path,
    list_image_paths,
    load_annotations,
    output_csv_path,
    save_annotations_csv,
)
from napari_annotation_plugin.models import AnnotationRow


def test_find_annotation_path(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x\n")
    assert find_annotation_path("a", tmp_path) == tmp_path / "a.csv"
    assert find_annotation_path("missing", tmp_path) is None


def test_find_annotation_path_predictions_fallback(tmp_path: Path) -> None:
    """Same folder as image.tif + predictions.csv (test-data layout)."""
    (tmp_path / "predictions.csv").write_text("center_x,center_y,width,height,class_id\n")
    assert find_annotation_path("image", tmp_path) == tmp_path / "predictions.csv"


def test_csv_loader_good_and_bad_rows(tmp_path: Path) -> None:
    p = tmp_path / "f.csv"
    p.write_text(
        "center_x, center_y, width, height, class_id\n"
        "10, 20, 4, 6, 1\n"
        "not_a_row\n"
        "1, 2, 3\n"
        "1, 2, 3, 4, nanclass\n"
    )
    rows, warns = CsvAnnotationLoader().load(p)
    assert len(rows) == 1
    assert rows[0].class_id == 1
    assert warns, "expected warnings for bad rows"
    assert any("malformed" in w or "expected 5" in w for w in warns)


def test_csv_empty_and_missing(tmp_path: Path) -> None:
    empty = tmp_path / "e.csv"
    empty.write_text("")
    rows, _ = load_annotations(empty)
    assert rows == []
    rows2, _ = load_annotations(tmp_path / "nope.csv")
    assert rows2 == []


def test_save_round_trip(tmp_path: Path) -> None:
    rows = [
        AnnotationRow(1.5, 2.5, 3.0, 4.0, 2),
    ]
    out = tmp_path / "out.csv"
    save_annotations_csv(out, rows)
    loaded, warns = load_annotations(out)
    assert not warns
    assert len(loaded) == 1
    assert loaded[0].class_id == 2
    assert pytest.approx(loaded[0].center_x) == 1.5


def test_output_csv_path() -> None:
    p = output_csv_path(Path("/tmp/out"), "img_001")
    assert p.name == "img_001.csv"


def test_ensure_2d_image() -> None:
    a = np.zeros((5, 10, 12), dtype=np.uint8)
    b = ensure_2d_image(a)
    assert b.ndim == 2
    assert b.shape == (10, 12)


def test_ensure_2d_image_channels_last_hwc() -> None:
    """(H, W, C) must not collapse to a single row (regression vs test-data TIFs)."""
    a = np.zeros((182, 459, 2), dtype=np.uint16)
    b = ensure_2d_image(a)
    assert b.shape == (182, 459)


def test_ensure_2d_image_channels_first_chw() -> None:
    a = np.zeros((2, 100, 200), dtype=np.uint8)
    b = ensure_2d_image(a)
    assert b.shape == (100, 200)


def test_list_image_paths(tmp_path: Path) -> None:
    (tmp_path / "a.tif").write_bytes(b"")
    (tmp_path / "b.txt").write_text("x")
    paths = list_image_paths(tmp_path)
    assert len(paths) == 1
