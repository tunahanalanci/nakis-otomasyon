"""Tests for src/usb_writer.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.usb_writer import find_usb, write_to_usb


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_files(tmp_path: Path):
    """Create minimal placeholder files for DST, colour report, and preview."""
    dst     = tmp_path / "nakis.dst"
    report  = tmp_path / "renk_sirasi.txt"
    preview = tmp_path / "onizleme.png"

    dst.write_bytes(b"\x00" * 32)          # dummy DST bytes
    report.write_text("1 -> RGB(255,0,0)\n", encoding="utf-8")
    preview.write_bytes(b"\x89PNG\r\n")    # minimal PNG header

    return dst, report, preview


# ── write_to_usb ──────────────────────────────────────────────────────────────

class TestWriteToUsb:
    def test_root_layout_copies_to_usb_root(self, tmp_path, sample_files):
        dst, report, preview = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        dest = write_to_usb(dst, report, usb, preview_path=preview, layout="root")

        assert dest == usb
        assert (usb / dst.name).exists()
        assert (usb / report.name).exists()
        assert (usb / preview.name).exists()

    def test_named_layout_copies_to_subfolder(self, tmp_path, sample_files):
        dst, report, preview = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        dest = write_to_usb(dst, report, usb, preview_path=preview, layout="PATTERN")

        assert dest == usb / "PATTERN"
        assert (usb / "PATTERN" / dst.name).exists()
        assert (usb / "PATTERN" / report.name).exists()
        assert (usb / "PATTERN" / preview.name).exists()

    def test_creates_subfolder_if_missing(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        write_to_usb(dst, report, usb, layout="NEWDIR")
        assert (usb / "NEWDIR").is_dir()

    def test_no_preview_does_not_raise(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        dest = write_to_usb(dst, report, usb, preview_path=None, layout="root")
        assert (dest / dst.name).exists()
        assert (dest / report.name).exists()

    def test_missing_preview_file_skipped(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()
        missing_preview = tmp_path / "nonexistent_preview.png"

        # Must not raise even though the preview file does not exist
        dest = write_to_usb(dst, report, usb, preview_path=missing_preview, layout="root")
        assert (dest / dst.name).exists()
        assert not (dest / missing_preview.name).exists()

    def test_returns_path_object(self, tmp_path, sample_files):
        dst, report, preview = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        result = write_to_usb(dst, report, usb, preview_path=preview)
        assert isinstance(result, Path)

    def test_default_layout_is_root(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        dest = write_to_usb(dst, report, usb)
        assert dest == usb   # default layout is "root"

    def test_accepts_string_paths(self, tmp_path, sample_files):
        dst, report, preview = sample_files
        usb = tmp_path / "USB"
        usb.mkdir()

        dest = write_to_usb(str(dst), str(report), str(usb),
                             preview_path=str(preview), layout="root")
        assert dest.is_dir()

    def test_nested_usb_root_created(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        # Pass a non-existent nested path as usb_root
        usb = tmp_path / "media" / "USB_DRIVE"

        write_to_usb(dst, report, usb, layout="root")
        assert usb.is_dir()
        assert (usb / dst.name).exists()

    def test_file_contents_preserved(self, tmp_path, sample_files):
        dst, report, _ = sample_files
        original_bytes = dst.read_bytes()
        usb = tmp_path / "USB"
        usb.mkdir()

        write_to_usb(dst, report, usb, layout="root")
        assert (usb / dst.name).read_bytes() == original_bytes


# ── find_usb ─────────────────────────────────────────────────────────────────

class TestFindUsb:
    def test_returns_none_or_path(self):
        """find_usb must not raise; it may return None if no USB is connected."""
        result = find_usb()
        assert result is None or isinstance(result, Path)

    def test_label_hint_does_not_raise(self):
        result = find_usb(label_hint="TAJIMA_DRIVE")
        assert result is None or isinstance(result, Path)
