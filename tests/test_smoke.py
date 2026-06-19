"""Smoke tests: verify all modules are importable and Config loads correctly."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_import_config():
    from src import config  # noqa: F401


def test_import_preprocess():
    from src import preprocess  # noqa: F401


def test_import_colors():
    from src import colors  # noqa: F401


def test_import_separate():
    from src import separate  # noqa: F401


def test_import_vectorize():
    from src import vectorize  # noqa: F401


def test_import_stitch_fill():
    from src.stitch import fill  # noqa: F401


def test_import_stitch_satin():
    from src.stitch import satin  # noqa: F401


def test_import_stitch_running():
    from src.stitch import running  # noqa: F401


def test_import_stitch_underlay():
    from src.stitch import underlay  # noqa: F401


def test_import_optimize():
    from src import optimize  # noqa: F401


def test_import_export_dst():
    from src import export_dst  # noqa: F401


def test_import_validate():
    from src import validate  # noqa: F401


def test_import_usb_writer():
    from src import usb_writer  # noqa: F401


def test_import_pipeline():
    from src import pipeline  # noqa: F401


def test_config_loads_default():
    from src.config import load

    conf = load(Path(__file__).parent.parent / "config" / "default.json")
    assert conf.width_mm == 80.0
    assert conf.height_mm == 60.0
    assert conf.max_colors == 6
    assert conf.hoop.w == 200
    assert conf.fill.spacing_mm == 0.4
    assert conf.satin.density_mm == 0.4
    assert conf.trim_jumps is True


def test_pipeline_runs_to_completion(tmp_path):
    """Complete pipeline must produce a valid DST without raising."""
    import numpy as np
    from PIL import Image as PilImage
    from src.config import load
    from src.pipeline import run

    # Minimal 2-colour synthetic PNG (small so the test stays fast)
    arr = np.zeros((40, 60, 3), dtype=np.uint8)
    arr[:20, :] = [200, 40, 40]
    arr[20:, :] = [40, 80, 200]
    png_path = tmp_path / "test.png"
    PilImage.fromarray(arr).save(str(png_path))

    conf = load(Path(__file__).parent.parent / "config" / "default.json")
    conf.max_colors  = 2
    conf.width_mm    = 30.0
    conf.height_mm   = 20.0
    # Coarse settings for speed
    conf.fill.spacing_mm = 2.0
    conf.fill.underlay   = False

    result = run(str(png_path), conf, str(tmp_path / "out"))
    assert result.dst_path.exists()
    assert result.preview_path.exists()
