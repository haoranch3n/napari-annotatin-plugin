"""Diagnostics: run with the same interpreter you use to start napari.

    python -m napari_annotation_plugin
"""

from __future__ import annotations

import importlib.util
import sys


def main() -> int:
    print("Python executable:", sys.executable)
    print("Python version:", sys.version.split("\n", 1)[0])

    try:
        import napari  # noqa: F401
    except ImportError as e:
        print("ERROR: napari is not importable in this environment:", e)
        print(
            "Install napari here, or use this module's Python (e.g. recreate your venv "
            "with `python -m venv .venv --system-site-packages` after `module load napari`)."
        )
        return 1

    try:
        import npe2  # noqa: F401
    except ImportError as e:
        print("ERROR: npe2 is not importable:", e)
        print("npe2 must be available to the same Python as napari (usually bundled with napari).")
        return 1

    try:
        from npe2 import PluginManifest

        pm = PluginManifest.from_distribution("napari-annotation-plugin")
    except Exception as e:
        print("ERROR: could not load plugin manifest for 'napari-annotation-plugin':", e)
        print(
            "Install this package into this exact environment, e.g. "
            "`pip install -e /path/to/napari-annotation-plugin`."
        )
        return 1

    print("Manifest OK:", pm.name, "-", pm.display_name)
    if pm.contributions.widgets:
        for w in pm.contributions.widgets:
            print("  Widget:", w.display_name)

    ep_ok = False
    try:
        from importlib.metadata import entry_points

        for ep in entry_points(group="napari.manifest"):
            if ep.name == "napari-annotation-plugin":
                ep_ok = True
                print("Entry point napari.manifest:", ep.name, "->", ep.value)
    except Exception as e:
        print("WARNING: could not list entry points:", e)

    if not ep_ok:
        print("ERROR: no napari.manifest entry point named 'napari-annotation-plugin'.")
        return 1

    spec = importlib.util.find_spec("napari_annotation_plugin")
    if spec is None or not spec.origin:
        print("ERROR: package napari_annotation_plugin is not importable.")
        return 1

    try:
        from napari_annotation_plugin.widget import AnnotationReviewWidget  # noqa: F401
    except Exception as e:
        print("ERROR: widget factory failed to import:", e)
        return 1

    print("Widget class import OK.")
    print(
        "\nIf napari still does not list this plugin, you are almost certainly running napari "
        "with a different Python than the one above. Start napari from a shell where "
        "`which python` matches, or reinstall with that interpreter's pip."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
