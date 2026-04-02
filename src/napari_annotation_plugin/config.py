"""Editable class labels and default UI values for the annotation review plugin."""

from __future__ import annotations

# Map class_id (stored in CSV) to display names. Edit this dict for your project.
CLASS_NAMES: dict[int, str] = {
    0: "background_or_unknown",
    1: "class_a",
    2: "class_b",
    3: "class_c",
}

# Default fixed box size for one-click add (pixels in image coordinates).
DEFAULT_BOX_WIDTH: float = 32.0
DEFAULT_BOX_HEIGHT: float = 32.0

# Suggested folder names (documentation / optional defaults in README).
DEFAULT_INPUT_ANNOTATION_SUBDIR: str = "predictions"
DEFAULT_OUTPUT_ANNOTATION_SUBDIR: str = "annotations_corrected"
