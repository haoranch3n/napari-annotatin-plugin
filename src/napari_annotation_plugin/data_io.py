"""Load/save TIF images and CSV annotations; discover files by stem."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence

import numpy as np
import tifffile

from napari_annotation_plugin.models import AnnotationRow, rows_to_dataframe

TIF_SUFFIXES: tuple[str, ...] = (".tif", ".tiff", ".TIF", ".TIFF")


def list_image_paths(dataset_dir: Path) -> list[Path]:
    """Sorted list of TIF paths under dataset_dir (non-recursive)."""
    if not dataset_dir.is_dir():
        return []
    paths: list[Path] = []
    for p in dataset_dir.iterdir():
        if p.is_file() and p.suffix in TIF_SUFFIXES:
            paths.append(p)
    return sorted(paths, key=lambda x: x.name.lower())


def find_annotation_path(
    stem: str,
    input_dir: Path,
    exts: Sequence[str] = (".csv",),
) -> Path | None:
    """Return companion annotation file path if it exists, else None."""
    if not input_dir.is_dir():
        return None
    for ext in exts:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def ensure_2d_image(arr: np.ndarray) -> np.ndarray:
    """
    Reduce multi-dimensional TIF data to a single 2D plane (float32).

    Assumptions documented in README: last two dimensions are height and width.
    Extra dimensions (Z, T, C, etc.) are collapsed by taking the first slice
    along leading axes until the array is 2D.
    """
    a = np.asarray(arr)
    if a.ndim == 0:
        raise ValueError("Empty array")
    a = np.squeeze(a)
    while a.ndim > 2:
        a = a[0]
        a = np.squeeze(a)
    if a.ndim != 2:
        raise ValueError(f"Could not reduce to 2D, shape was {np.asarray(arr).shape}")
    return a.astype(np.float32, copy=False)


def load_tif_image(path: Path) -> np.ndarray:
    """Load a TIF and return a 2D float32 array."""
    raw = tifffile.imread(path)
    return ensure_2d_image(raw)


class AnnotationLoader(ABC):
    """Pluggable annotation file loader."""

    @abstractmethod
    def load(self, path: Path) -> tuple[list[AnnotationRow], list[str]]:
        """Return rows and warning messages."""


class CsvAnnotationLoader(AnnotationLoader):
    """CSV with columns: center_x, center_y, width, height, class_id."""

    def load(self, path: Path) -> tuple[list[AnnotationRow], list[str]]:
        warnings: list[str] = []
        if not path.is_file():
            return [], []

        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return [], []

        lines = text.splitlines()
        rows_out: list[AnnotationRow] = []
        for lineno, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                warnings.append(f"{path.name}:{lineno}: expected 5 fields, skipped")
                continue
            if parts[0].lower() in ("center_x", "centerx", "x0"):
                continue
            try:
                vals: list[float] = []
                for p in parts[:4]:
                    if not self._looks_numeric(p):
                        raise ValueError("non-numeric")
                    vals.append(float(p))
                class_id = int(float(parts[4]))
            except (ValueError, IndexError):
                warnings.append(f"{path.name}:{lineno}: malformed row, skipped")
                continue
            rows_out.append(
                AnnotationRow(
                    center_x=vals[0],
                    center_y=vals[1],
                    width=vals[2],
                    height=vals[3],
                    class_id=class_id,
                )
            )
        return rows_out, warnings

    @staticmethod
    def _looks_numeric(s: str) -> bool:
        if s == "":
            return False
        try:
            float(s)
            return True
        except ValueError:
            return False


def load_annotations(
    path: Path | None,
    loader: AnnotationLoader | None = None,
) -> tuple[list[AnnotationRow], list[str]]:
    """Load annotations using the given loader (default CSV)."""
    if path is None:
        return [], []
    impl = loader or CsvAnnotationLoader()
    return impl.load(path)


def save_annotations_csv(path: Path, rows: list[AnnotationRow]) -> None:
    """Write corrected annotations as CSV (overwrites)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = rows_to_dataframe(rows)
    df.to_csv(path, index=False, lineterminator="\n")


def output_csv_path(output_dir: Path, stem: str, suffix: str = ".csv") -> Path:
    """Target path for corrected annotations for a given image stem."""
    return output_dir / f"{stem}{suffix}"
