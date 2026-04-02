"""Dock widget: dataset navigation, editing, add-box mode, save/autosave."""

from __future__ import annotations

import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from napari_annotation_plugin import config
from napari_annotation_plugin.data_io import (
    find_annotation_path,
    list_image_paths,
    load_annotations,
    load_tif_image,
    output_csv_path,
    save_annotations_csv,
)
from napari_annotation_plugin.models import AnnotationRow
from napari_annotation_plugin.utils import (
    annotation_rows_to_shapes_data,
    center_size_to_corners_yx,
    colors_for_class_ids,
    corners_yx_to_center_size,
    legend_text,
    shapes_data_to_annotation_rows,
)

try:
    from napari.viewer import Viewer
except Exception:  # pragma: no cover - typing fallback
    Viewer = object  # type: ignore[misc, assignment]


IMAGE_LAYER_NAME = "review_image"
SHAPES_LAYER_NAME = "review_boxes"


class QDoubleSpinBoxFixed(QDoubleSpinBox):
    """Spin box for fixed box width/height (pixels)."""

    def __init__(self) -> None:
        super().__init__()
        self.setDecimals(2)
        self.setSingleStep(1.0)
        self.setRange(1.0, 1e6)


class QComboBoxClass(QWidget):
    """Dropdown listing configured class names; stores class_id."""

    def __init__(self, mapping: dict[int, str]) -> None:
        super().__init__()
        self._combo = QComboBox()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)
        for cid in sorted(mapping.keys()):
            self._combo.addItem(f"{cid}: {mapping[cid]}", cid)

    def current_class_id(self) -> int:
        data = self._combo.currentData()
        return int(data) if data is not None else 0

    def set_class_id(self, cid: int) -> None:
        for i in range(self._combo.count()):
            if int(self._combo.itemData(i)) == cid:
                self._combo.setCurrentIndex(i)
                return


def _edge_colors_from_faces(face: np.ndarray) -> np.ndarray:
    """Slightly darker opaque edges from RGBA face colors."""
    if face.size == 0:
        return face
    out = face.astype(np.float32, copy=True)
    out[:, :3] *= 0.85
    out[:, 3] = 1.0
    return out


class AnnotationReviewWidget(QWidget):
    """Main UI for reviewing and correcting bounding boxes."""

    def __init__(self, napari_viewer: Viewer) -> None:
        super().__init__()
        self._viewer = napari_viewer
        self._dataset_dir: Path | None = None
        self._input_ann_dir: Path | None = None
        self._output_ann_dir: Path | None = None
        self._image_paths: list[Path] = []
        self._index: int = 0
        self._dirty: bool = False
        self._suppress_dirty: bool = False
        self._add_mode: bool = False
        self._image_layer = None
        self._shapes_layer = None
        self._mouse_press_cb = None
        self._mouse_release_cb = None
        self._about_to_quit_hooked = False

        self._build_ui()
        self._wire_viewer_shortcuts()
        self._hook_application_quit()

    # --- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        main = QVBoxLayout(self)

        paths_box = QGroupBox("Folders")
        paths_form = QFormLayout()
        self._dataset_edit = QLineEdit()
        self._dataset_btn = QPushButton("Open Dataset Folder…")
        self._dataset_btn.clicked.connect(self._pick_dataset)
        row_ds = QHBoxLayout()
        row_ds.addWidget(self._dataset_edit)
        row_ds.addWidget(self._dataset_btn)
        paths_form.addRow("Images", row_ds)

        self._input_edit = QLineEdit()
        self._input_btn = QPushButton("Input annotations…")
        self._input_btn.clicked.connect(self._pick_input_ann)
        row_in = QHBoxLayout()
        row_in.addWidget(self._input_edit)
        row_in.addWidget(self._input_btn)
        paths_form.addRow("Input (predictions)", row_in)

        self._output_edit = QLineEdit()
        self._output_btn = QPushButton("Output annotations…")
        self._output_btn.clicked.connect(self._pick_output_ann)
        row_out = QHBoxLayout()
        row_out.addWidget(self._output_edit)
        row_out.addWidget(self._output_btn)
        paths_form.addRow("Output (corrected)", row_out)
        paths_box.setLayout(paths_form)

        self._info_label = QLabel("No dataset loaded.")
        self._info_label.setWordWrap(True)

        class_box = QGroupBox("Classes")
        class_layout = QVBoxLayout()
        self._class_combo = QComboBoxClass(config.CLASS_NAMES)
        class_layout.addWidget(QLabel("Active class (add / apply):"))
        class_layout.addWidget(self._class_combo)
        legend = QLabel(legend_text())
        legend.setTextInteractionFlags(Qt.TextSelectableByMouse)
        legend.setStyleSheet("font-family: monospace; font-size: 11px;")
        class_layout.addWidget(QLabel("Class map:"))
        class_layout.addWidget(legend)
        class_box.setLayout(class_layout)

        size_box = QGroupBox("Fixed box size (add mode)")
        size_grid = QGridLayout()
        self._w_spin = QDoubleSpinBoxFixed()
        self._w_spin.setRange(1.0, 1e6)
        self._w_spin.setValue(float(config.DEFAULT_BOX_WIDTH))
        self._h_spin = QDoubleSpinBoxFixed()
        self._h_spin.setRange(1.0, 1e6)
        self._h_spin.setValue(float(config.DEFAULT_BOX_HEIGHT))
        size_grid.addWidget(QLabel("Width"), 0, 0)
        size_grid.addWidget(self._w_spin, 0, 1)
        size_grid.addWidget(QLabel("Height"), 1, 0)
        size_grid.addWidget(self._h_spin, 1, 1)
        size_box.setLayout(size_grid)

        self._add_mode_btn = QPushButton("Add Box Mode: OFF")
        self._add_mode_btn.setCheckable(True)
        self._add_mode_btn.toggled.connect(self._on_add_mode_toggled)

        actions = QHBoxLayout()
        self._btn_delete = QPushButton("Delete Selected")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_apply = QPushButton("Apply Class To Selected")
        self._btn_apply.clicked.connect(self._apply_class_to_selected)
        self._btn_save = QPushButton("Save")
        self._btn_save.clicked.connect(self._save_clicked)
        actions.addWidget(self._btn_delete)
        actions.addWidget(self._btn_apply)
        actions.addWidget(self._btn_save)

        nav = QHBoxLayout()
        self._btn_prev = QPushButton("Previous Image")
        self._btn_next = QPushButton("Next Image")
        self._btn_prev.clicked.connect(self._previous_image)
        self._btn_next.clicked.connect(self._next_image)
        nav.addWidget(self._btn_prev)
        nav.addWidget(self._btn_next)

        self._status = QPlainTextEdit()
        self._status.setReadOnly(True)
        self._status.setMaximumBlockCount(500)
        self._status.setFixedHeight(120)

        main.addWidget(paths_box)
        main.addWidget(self._info_label)
        main.addWidget(class_box)
        main.addWidget(size_box)
        main.addWidget(self._add_mode_btn)
        main.addLayout(actions)
        main.addLayout(nav)
        main.addWidget(QLabel("Status"))
        main.addWidget(self._status)

    def _log(self, msg: str) -> None:
        self._status.appendPlainText(msg)

    # --- Folder pickers -----------------------------------------------------
    def _pick_dataset(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dataset folder (TIF images)")
        if not d:
            return
        self._dataset_edit.setText(d)
        self._open_dataset(Path(d))

    def _pick_input_ann(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Input annotation folder (CSV)")
        if not d:
            return
        self._input_edit.setText(d)
        self._input_ann_dir = Path(d)

    def _pick_output_ann(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output annotation folder (corrected CSV)")
        if not d:
            return
        self._output_edit.setText(d)
        self._output_ann_dir = Path(d)

    def _open_dataset(self, dataset_dir: Path) -> None:
        self._dataset_dir = dataset_dir
        self._dataset_edit.setText(str(dataset_dir))
        if self._input_edit.text().strip():
            self._input_ann_dir = Path(self._input_edit.text().strip())
        if self._output_edit.text().strip():
            self._output_ann_dir = Path(self._output_edit.text().strip())
        self._image_paths = list_image_paths(dataset_dir)
        if not self._image_paths:
            self._log(f"No TIF files in {dataset_dir}")
            self._info_label.setText("No TIF files found.")
            return
        self._index = 0
        self._ensure_layers()
        self._load_current_image()

    # --- Layers -------------------------------------------------------------
    def _ensure_layers(self) -> None:
        if self._image_layer is not None and self._shapes_layer is not None:
            return
        self._image_layer = self._viewer.add_image(
            np.zeros((1, 1), dtype=np.float32),
            name=IMAGE_LAYER_NAME,
        )
        self._shapes_layer = self._viewer.add_shapes(
            [],
            name=SHAPES_LAYER_NAME,
            shape_type="rectangle",
            ndim=2,
        )
        self._shapes_layer.text.visible = False
        self._connect_layer_events()
        self._mouse_press_cb = self._on_viewer_mouse_press
        self._viewer.mouse_press_callbacks.append(self._mouse_press_cb)
        self._mouse_release_cb = self._on_viewer_mouse_release
        self._viewer.mouse_release_callbacks.append(self._mouse_release_cb)

    def _connect_layer_events(self) -> None:
        assert self._shapes_layer is not None
        sl = self._shapes_layer
        sl.events.data.connect(self._on_shapes_event)
        if hasattr(sl.events, "features"):
            sl.events.features.connect(self._on_shapes_event)
        emitter = getattr(sl.events, "selection", None)
        if emitter is not None:
            emitter.connect(self._sync_class_from_selection)

    def _on_shapes_event(self, event) -> None:
        if self._suppress_dirty:
            return
        self._dirty = True

    def _on_viewer_mouse_release(self, viewer, event) -> None:
        if self._shapes_layer is None:
            return
        active = _active_layer(viewer)
        if active is not self._shapes_layer:
            return
        self._sync_class_from_selection()

    # --- Load / save current ------------------------------------------------
    def _current_stem(self) -> str | None:
        if not self._image_paths or self._index < 0 or self._index >= len(self._image_paths):
            return None
        return self._image_paths[self._index].stem

    def _load_current_image(self) -> None:
        if not self._image_paths:
            return
        path = self._image_paths[self._index]
        stem = path.stem
        self._suppress_dirty = True
        try:
            img = load_tif_image(path)
            self._image_layer.data = img
            self._image_layer.name = IMAGE_LAYER_NAME
            self._image_layer.reset_contrast_limits()

            input_dir = self._input_ann_dir or self._dataset_dir
            if self._input_edit.text().strip():
                input_dir = Path(self._input_edit.text().strip())
            ann_path = find_annotation_path(stem, input_dir) if input_dir else None
            rows, warns = load_annotations(ann_path)
            for w in warns:
                self._log(w)
            self._set_shapes_from_rows(rows)
            self._dirty = False
            self._update_info_label()
        except Exception as e:
            self._log(f"Error loading {path}: {e}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "Load error", str(e))
        finally:
            self._suppress_dirty = False

    def _set_shapes_from_rows(self, rows: list[AnnotationRow]) -> None:
        assert self._shapes_layer is not None
        data, class_ids = annotation_rows_to_shapes_data(rows)
        df = pd.DataFrame({"class_id": class_ids})
        self._shapes_layer.data = data
        self._shapes_layer.shape_type = ["rectangle"] * len(data)
        self._shapes_layer.features = df
        face = colors_for_class_ids(class_ids)
        self._shapes_layer.face_color = face
        self._shapes_layer.edge_color = _edge_colors_from_faces(face)
        self._shapes_layer.selected_data = set()

    def _rows_from_shapes(self) -> list[AnnotationRow]:
        if self._shapes_layer is None:
            return []
        data = list(self._shapes_layer.data)
        if not data:
            return []
        if self._shapes_layer.features is None or len(self._shapes_layer.features) == 0:
            return []
        cids = [int(x) for x in self._shapes_layer.features["class_id"].tolist()]
        return shapes_data_to_annotation_rows(data, cids)

    def _output_path_for_current(self) -> Path | None:
        stem = self._current_stem()
        if stem is None:
            return None
        out = self._output_ann_dir
        if self._output_edit.text().strip():
            out = Path(self._output_edit.text().strip())
        if out is None:
            self._log("Set output annotation folder before saving.")
            return None
        return output_csv_path(out, stem)

    def _save_current(self) -> bool:
        """Write current shapes to output CSV. Returns False on failure."""
        path = self._output_path_for_current()
        if path is None:
            return False
        try:
            rows = self._rows_from_shapes()
            save_annotations_csv(path, rows)
            self._dirty = False
            self._log(f"Saved {path}")
            return True
        except Exception as e:
            self._log(f"Save failed: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Save failed", str(e))
            return False

    def _save_clicked(self) -> None:
        self._save_current()

    def _try_autosave(self) -> bool:
        """Autosave if output dir set; if nothing to save, succeed."""
        if not self._image_paths:
            return True
        if self._output_ann_dir is None and not self._output_edit.text().strip():
            self._log("Set output folder before navigating away (unsaved edits).")
            return False
        if not self._dirty:
            return True
        return self._save_current()

    # --- Navigation ---------------------------------------------------------
    def _update_info_label(self) -> None:
        if not self._image_paths:
            self._info_label.setText("No dataset.")
            return
        n = len(self._image_paths)
        p = self._image_paths[self._index]
        self._info_label.setText(f"Image {self._index + 1} / {n}\n{p.name}")

    def _next_image(self) -> None:
        if not self._image_paths:
            self._log("No dataset loaded.")
            return
        if not self._try_autosave():
            return
        if self._index >= len(self._image_paths) - 1:
            self._log("Already at last image.")
            return
        self._index += 1
        self._load_current_image()

    def _previous_image(self) -> None:
        if not self._image_paths:
            self._log("No dataset loaded.")
            return
        if not self._try_autosave():
            return
        if self._index <= 0:
            self._log("Already at first image.")
            return
        self._index -= 1
        self._load_current_image()

    # --- Delete / class -----------------------------------------------------
    def _delete_selected(self) -> None:
        if self._shapes_layer is None:
            return
        sel = list(self._shapes_layer.selected_data)
        if not sel:
            self._log("No selection to delete.")
            return
        self._suppress_dirty = True
        try:
            data = [d for i, d in enumerate(self._shapes_layer.data) if i not in sel]
            df = self._shapes_layer.features.drop(index=sel).reset_index(drop=True)
            self._shapes_layer.data = data
            self._shapes_layer.shape_type = ["rectangle"] * len(data)
            self._shapes_layer.features = df
            cids = [int(x) for x in df["class_id"].tolist()] if len(df) else []
            face = colors_for_class_ids(cids)
            self._shapes_layer.face_color = face
            self._shapes_layer.edge_color = _edge_colors_from_faces(face)
            self._shapes_layer.selected_data = set()
        finally:
            self._suppress_dirty = False
        self._dirty = True
        self._log(f"Deleted {len(sel)} shape(s).")

    def _apply_class_to_selected(self) -> None:
        if self._shapes_layer is None:
            return
        sel = list(self._shapes_layer.selected_data)
        if not sel:
            self._log("No selection for class apply.")
            return
        cid = self._class_combo.current_class_id()
        df = self._shapes_layer.features.copy()
        for i in sel:
            df.at[i, "class_id"] = cid
        self._suppress_dirty = True
        try:
            self._shapes_layer.features = df
            cids = [int(x) for x in df["class_id"].tolist()]
            face = colors_for_class_ids(cids)
            self._shapes_layer.face_color = face
            self._shapes_layer.edge_color = _edge_colors_from_faces(face)
        finally:
            self._suppress_dirty = False
        self._dirty = True
        self._log(f"Applied class {cid} to {len(sel)} shape(s).")

    def _sync_class_from_selection(self) -> None:
        if self._shapes_layer is None:
            return
        sel = list(self._shapes_layer.selected_data)
        if len(sel) != 1:
            return
        idx = sel[0]
        df = self._shapes_layer.features
        if df is None or idx >= len(df):
            return
        cid = int(df.iloc[idx]["class_id"])
        self._class_combo.set_class_id(cid)

    # --- Add box mode -------------------------------------------------------
    def _on_add_mode_toggled(self, on: bool) -> None:
        self._add_mode = on
        self._add_mode_btn.setText("Add Box Mode: ON" if on else "Add Box Mode: OFF")
        self._log("Add box mode " + ("on" if on else "off") + ".")

    def _on_viewer_mouse_press(self, viewer, event) -> None:
        if not self._add_mode or self._image_layer is None or self._shapes_layer is None:
            return
        btn = getattr(event, "button", None)
        if btn not in (None, 1, "left"):
            return
        # Map click to image data coordinates (y, x)
        try:
            world = np.asarray(event.position)
        except Exception:
            return
        if world.ndim != 1:
            return
        # napari uses at least 2 dims for 2D layers; take leading components
        nd = self._image_layer.ndim
        w = world[:nd]
        data_coords = self._image_layer.world_to_data(w)
        y = float(data_coords[0])
        x = float(data_coords[1])
        cx, cy = x, y
        w_box = float(self._w_spin.value())
        h_box = float(self._h_spin.value())
        cid = self._class_combo.current_class_id()
        corners = center_size_to_corners_yx(cx, cy, w_box, h_box)
        self._append_rectangle(corners, cid)
        if hasattr(event, "handled"):
            event.handled = True

    def _append_rectangle(self, corners: np.ndarray, class_id: int) -> None:
        assert self._shapes_layer is not None
        self._suppress_dirty = True
        try:
            data = list(self._shapes_layer.data)
            data.append(corners)
            df = self._shapes_layer.features
            if df is None or len(df) == 0:
                new_df = pd.DataFrame({"class_id": [class_id]})
            else:
                new_df = pd.concat(
                    [df, pd.DataFrame({"class_id": [class_id]})],
                    ignore_index=True,
                )
            self._shapes_layer.data = data
            self._shapes_layer.shape_type = ["rectangle"] * len(data)
            self._shapes_layer.features = new_df
            cids = [int(x) for x in new_df["class_id"].tolist()]
            face = colors_for_class_ids(cids)
            self._shapes_layer.face_color = face
            self._shapes_layer.edge_color = _edge_colors_from_faces(face)
        finally:
            self._suppress_dirty = False
        self._dirty = True
        cx, cy, _, _ = corners_yx_to_center_size(corners)
        self._log(f"Added box class={class_id} at center ({cx:.1f}, {cy:.1f}).")

    # --- Shortcuts / quit ---------------------------------------------------
    def _wire_viewer_shortcuts(self) -> None:
        v = self._viewer

        def bind(key: str, fn) -> None:
            try:
                v.bind_key(key, fn, overwrite=True)
            except Exception:
                pass

        bind("n", lambda v: self._next_image())
        bind("p", lambda v: self._previous_image())
        bind("s", lambda v: self._save_clicked())
        bind("d", lambda v: self._delete_selected())
        bind("a", lambda v: self._add_mode_btn.toggle())

        try:
            v.bind_key("Delete", lambda v: self._delete_selected(), overwrite=True)
            v.bind_key("Backspace", lambda v: self._delete_selected(), overwrite=True)
        except Exception:
            pass

    def _hook_application_quit(self) -> None:
        if self._about_to_quit_hooked:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.aboutToQuit.connect(self._on_application_quit)
        self._about_to_quit_hooked = True

    def _on_application_quit(self) -> None:
        if not self._dirty or not self._image_paths:
            return
        stem = self._current_stem()
        if stem is None:
            return
        out = self._output_ann_dir
        if out is None and self._output_edit.text().strip():
            out = Path(self._output_edit.text().strip())
        if out is None:
            return
        try:
            save_annotations_csv(output_csv_path(out, stem), self._rows_from_shapes())
            self._dirty = False
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        if self._dirty and self._output_path_for_current() is not None:
            self._save_current()
        super().closeEvent(event)


def _active_layer(viewer: Viewer):
    """Return the active napari layer, across napari versions."""
    layers = viewer.layers
    sel = getattr(layers, "selection", None)
    if sel is not None:
        active = getattr(sel, "active", None)
        if active is not None:
            return active
    return getattr(layers, "active", None)


