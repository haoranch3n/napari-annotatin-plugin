"""Dataclasses and helpers for annotation rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class AnnotationRow:
    """One detection: center and size in pixel coordinates, integer class id."""

    center_x: float
    center_y: float
    width: float
    height: float
    class_id: int

    def as_tuple(self) -> tuple[float, float, float, float, int]:
        return (
            self.center_x,
            self.center_y,
            self.width,
            self.height,
            self.class_id,
        )


def rows_to_dataframe(rows: Iterable[AnnotationRow]) -> pd.DataFrame:
    """Build a DataFrame with columns matching the CSV format."""
    data = [r.as_tuple() for r in rows]
    if not data:
        return pd.DataFrame(
            columns=[
                "center_x",
                "center_y",
                "width",
                "height",
                "class_id",
            ]
        )
    return pd.DataFrame(
        data,
        columns=["center_x", "center_y", "width", "height", "class_id"],
    )


def dataframe_to_rows(df: pd.DataFrame) -> list[AnnotationRow]:
    """Convert a loaded DataFrame to AnnotationRow instances."""
    rows: list[AnnotationRow] = []
    for _, row in df.iterrows():
        rows.append(
            AnnotationRow(
                center_x=float(row["center_x"]),
                center_y=float(row["center_y"]),
                width=float(row["width"]),
                height=float(row["height"]),
                class_id=int(row["class_id"]),
            )
        )
    return rows
