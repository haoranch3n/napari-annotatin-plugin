# napari-annotation-plugin

Napari plugin for **fast review and correction** of 2D object detection results on TIF images: load predictions from CSV, edit boxes (delete, reclassify, one-click add), and save corrected annotations to a separate output folder so original model outputs stay untouched.

## What it does

- Open a folder of `.tif` / `.tiff` images.
- Load companion prediction CSV files (same **stem** as the image) from an **input** folder (e.g. model `predictions/`).
- Display the image and rectangles on a Shapes layer, colored by `class_id`.
- Edit boxes: delete, change class, add fixed-size boxes with one click (**Add Box Mode**).
- Save corrections to an **output** folder (e.g. `annotations_corrected/`) as CSV.
- **Autosave** when moving to next/previous image, on widget close, and on application quit (when output folder is set and there are unsaved changes).

## Install

You need **napari** and **npe2** available to the same Python you use to install this package. Two common setups:

### A. System / module-provided napari (no pip install of napari)

Use this when your site provides napari via **Environment Modules**, **Lmod**, etc. (e.g. `module load napari`).

1. Load napari (and anything your site documents for the GUI stack).
2. Use the **same** `python` / `pip` from that stack so the plugin registers with that interpreter:

```bash
module load napari          # example; name may differ on your cluster
python -c "import napari, npe2"   # should succeed

cd /path/to/napari-annotation-plugin
pip install -U pip
pip install -e .            # installs only: numpy, pandas, qtpy, tifffile
# optional: pip install -e ".[dev]"   # pytest, etc.
```

This project **does not** list `napari` or `npe2` as required pip dependencies, so `pip install -e .` will not try to download napari from PyPI.

If you use a **venv**, create it from that module’s Python and consider **`--system-site-packages`** so the venv can see napari from the module, for example:

```bash
module load napari
python -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e .
```

Adjust to match your admin’s recommendations.

### B. Standalone virtual environment (pip installs napari)

When you are not using a preinstalled napari, install napari and npe2 together with the plugin:

```bash
cd /path/to/napari-annotation-plugin
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[bundled,dev]"   # napari[all] + npe2 + dev tools
```

If **PyQt** fails to build on pip, prefer **conda-forge** for napari, then `pip install -e .` (without `[bundled]`) in that environment.

## Run in napari

```bash
napari
```

Then: **Plugins → napari-annotation-plugin → Annotation Review** (or open the **Annotation Review** widget from the Plugins menu; exact labels follow your napari version).

## Example folder layout

```text
project/
  images/
    img_001.tif
    img_002.tif
  predictions/              # input: model outputs (read-only for this workflow)
    img_001.csv
    img_002.csv
  annotations_corrected/    # output: your edits (created automatically)
    img_001.csv
    img_002.csv
```

In the widget:

1. **Open Dataset Folder** → choose `images/` (or a single case folder; see below).
2. **Input annotations** → choose `predictions/` (CSV files matched by stem: `img_001.tif` ↔ `img_001.csv`). If `{stem}.csv` is missing, the plugin also looks for `predictions.csv` or `labels.csv` in the same folder (one-file-per-directory layouts).
3. **Output annotations** → choose `annotations_corrected/`.

### Nested case folders (e.g. `test-data/`)

The plugin lists TIFs **only in the folder you select** (not subfolders). For layouts like `test-data/case01/.../image.tif` + `predictions.csv`, open **that case folder** as the dataset folder and set **input** and **output** to the same folder (or input = that folder). The image stem is `image`, so corrected CSVs save as `image.csv` in the output folder unless you use a separate output directory.

Original files under `predictions/` are never overwritten; saves go only to the output folder.

## Annotation file format (CSV)

One row per object, columns:

```text
center_x, center_y, width, height, class_id
```

- **center_x**, **center_y**: center of the box in **pixel coordinates** (x = column, y = row).
- **width**, **height**: full width and height in pixels.
- **class_id**: integer label (see class map in `config.py`).

Lines starting with `#` are ignored. Malformed rows are skipped and a warning is shown in the status area.

## Class names

Edit [`src/napari_annotation_plugin/config.py`](src/napari_annotation_plugin/config.py): dictionary `CLASS_NAMES` maps `class_id` → display name. Saved files always store **numeric** `class_id`.

## Main controls

| Control | Action |
|--------|--------|
| Open Dataset Folder | List all TIFs in the folder and show the first |
| Input Annotation Folder | Where to read prediction CSVs (stem-matched) |
| Output Annotation Folder | Where to write corrected CSVs |
| Class dropdown | Active class for **Add Box Mode** and **Apply Class** |
| Fixed width / height | Size of boxes added in Add Box Mode |
| Add Box Mode | When ON, left-click adds a box centered at the cursor |
| Delete Selected | Remove selected rectangle(s) |
| Apply Class To Selected | Set `class_id` on selected shapes |
| Save | Save current image’s annotations to the output folder |
| Previous / Next Image | Navigate; triggers autosave if there are unsaved edits |

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `N` | Next image |
| `P` | Previous image |
| `S` | Save |
| `D` | Delete selected |
| `A` | Toggle Add Box Mode |
| `Delete` / `Backspace` | Delete selected |

Shortcuts apply when the napari viewer handles the key (focus on the canvas). If a key does nothing, use the buttons.

## Assumptions and limitations

- **2D images** are the primary target. If a TIF has more than two dimensions (Z, T, channels, etc.), the plugin **takes a single 2D plane** by repeatedly indexing the first axis and squeezing singleton dimensions until the array is `(height, width)`. See `ensure_2d_image()` in `data_io.py` and the README “Assumptions” section above.
- **Grayscale** is typical; multi-channel stacks are reduced to one plane as above without crashing.
- **Very large images** may be slow; there is no tiling.
- **Add Box Mode** uses the viewer’s mouse callback; if interaction conflicts with other tools, turn Add Box Mode off while manually moving vertices.

## Develop and test

With **module-loaded napari** (only plugin deps + pytest):

```bash
pip install -e ".[dev]"
pytest
```

With a **full pip stack** (includes napari for local GUI testing):

```bash
pip install -e ".[bundled,dev]"
pytest
```

## Geometry note (napari vs CSV)

CSV stores **(center_x, center_y)** in image axes (x = columns, y = rows). Napari Shapes vertices use **(row, col) = (y, x)** per vertex. Conversions live in `utils.py` (`center_size_to_corners_yx`, `corners_yx_to_center_size`).
