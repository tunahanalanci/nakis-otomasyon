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


def test_pipeline_raises_not_implemented():
    from src.config import load
    from src.pipeline import run

    conf = load(Path(__file__).parent.parent / "config" / "default.json")
    with pytest.raises(NotImplementedError):
        run("dummy.png", conf, "out/")
