"""USB output: copy DST file, colour-order report, and preview PNG to a removable drive."""

from __future__ import annotations

import shutil
from pathlib import Path


def find_usb(label_hint: str | None = None) -> Path | None:
    """Detect a connected USB removable drive and return its root path.

    Returns ``None`` if no suitable drive is found.

    TODO: on Windows, enumerate win32api.GetLogicalDriveStrings() and filter by
          GetDriveType() == DRIVE_REMOVABLE; optionally match *label_hint*.
    TODO: on Linux, scan /media/$USER/ or /run/media/ mount points.
    """
    raise NotImplementedError


def write_to_usb(
    dst_path: Path,
    color_report_path: Path,
    preview_path: Path,
    usb_root: Path,
) -> None:
    """Copy embroidery output files to *usb_root*.

    Creates a subdirectory named after the design on the USB drive.

    TODO: create usb_root / dst_path.stem / directory.
    TODO: copy dst_path, color_report_path, and preview_path into it.
    TODO: call usb_root drive flush / sync to ensure write completion before removal.
    """
    raise NotImplementedError
