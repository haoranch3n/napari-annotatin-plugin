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


# If `{stem}.csv` is missing, try these names (one CSV per folder workflows).
_FALLBACK_ANNOTATION_NAMES: tuple[str, ...] = (
    "predictions.csv",
    "labels.csv",
)


def find_annotation_path(
    stem: str,
    input_dir: Path,
    exts: Sequence[str] = (".csv",),
) -> Path | None:
    """
    Return companion annotation file path if it exists, else None.

    First tries ``{stem}{ext}`` (e.g. ``image.csv`` for ``image.tif``). If not
    found, tries common single-file names such as ``predictions.csv`` so
    layouts like ``case_dir/image.tif`` + ``case_dir/predictions.csv`` work.
    """
    if not input_dir.is_dir():
        return None
    for ext in exts:
        candidate = input_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    for name in _FALLBACK_ANNOTATION_NAMES:
        candidate = input_dir / name
        if candidate.is_file():
            return candidate
    return None


def _reduce_3d_to_2d(a: np.ndarray) -> np.ndarray:
    """Pick one 2D plane from a 3D array (channels or Z-stack)."""
    # Channels last: (rows, cols, C), C small
    if (
        a.shape[-1] in (2, 3, 4)
        and a.shape[0] > a.shape[-1]
        and a.shape[1] > a.shape[-1]
    ):
        return a[..., 0]
    # Channels first: (C, rows, cols), C small
    if (
        a.shape[0] in (2, 3, 4)
        and a.shape[1] > a.shape[0]
        and a.shape[2] > a.shape[0]
    ):
        return a[0]
    # Otherwise (Z, H, W) or ambiguous
    return a[0]


def ensure_2d_image(arr: np.ndarray) -> np.ndarray:
    """
    Reduce multi-dimensional TIF data to a single 2D plane (float32).

    Handles common layouts:

    - **(H, W, C)** with C in ``{2, 3, 4}`` (channels last): use the first channel.
    - **(C, H, W)** with C in ``{2, 3, 4}`` (channels first): use the first channel.
    - **(Z, H, W)** or other 3D stacks: use the first slice along axis 0.
    - **4D+**: take the leading slice until 3D, then apply the same rules.

    This avoids interpreting ``(H, W, 2)`` as ``(Z, H, W)`` with ``Z=H``,
    which would incorrectly slice a single image row.
    """
    a = np.asarray(arr)
    if a.ndim == 0:
        raise ValueError("Empty array")
    a = np.squeeze(a)
    while a.ndim > 2:
        if a.ndim == 3:
            a = _reduce_3d_to_2d(a)
        else:
            a = np.squeeze(a[0])
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
