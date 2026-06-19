"""USB output: copy DST, colour-order report, and preview PNG to a removable drive."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def find_usb(label_hint: str | None = None) -> Path | None:
    """Detect a connected USB removable drive and return its root path.

    Returns ``None`` if no suitable drive is found.  *label_hint*, when given,
    is matched as a case-insensitive substring of the volume label (Windows) or
    mount-point name (Linux/macOS).
    """
    system = platform.system()
    if system == "Windows":
        return _find_usb_windows(label_hint)
    return _find_usb_unix(label_hint)


def write_to_usb(
    dst_path: Path | str,
    color_report_path: Path | str,
    usb_root: Path | str,
    preview_path: Path | str | None = None,
    layout: str = "root",
) -> Path:
    """Copy embroidery files to *usb_root*.

    Parameters
    ----------
    dst_path          : Path to the ``.dst`` file.
    color_report_path : Path to ``renk_sirasi.txt``.
    usb_root          : Root path of the target USB drive.
    preview_path      : Optional path to ``onizleme.png``; skipped if None or missing.
    layout            : Tajima file-tree layout.

                        * ``"root"`` — files go directly into *usb_root*.
                        * Any other string — files go into ``usb_root / layout``.
                          Use this to match your machine's expected subdirectory
                          (e.g. ``"PATTERN"``, ``"EMBF"``, or a model-specific path).

    Returns the destination directory that was written to.
    """
    dst_path          = Path(dst_path)
    color_report_path = Path(color_report_path)
    usb_root          = Path(usb_root)

    dest_dir = usb_root if layout == "root" else usb_root / layout
    dest_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(dst_path,          dest_dir / dst_path.name)
    shutil.copy2(color_report_path, dest_dir / color_report_path.name)

    if preview_path is not None:
        preview_path = Path(preview_path)
        if preview_path.exists():
            shutil.copy2(preview_path, dest_dir / preview_path.name)

    return dest_dir


# ── Platform-specific USB detection ───────────────────────────────────────────

def _find_usb_windows(label_hint: str | None) -> Path | None:
    """Enumerate logical drives with ctypes and return the first removable one."""
    try:
        import ctypes

        DRIVE_REMOVABLE = 2
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]

        for i in range(26):
            if not (bitmask & (1 << i)):
                continue
            letter = chr(ord("A") + i)
            drive  = Path(f"{letter}:\\")
            if ctypes.windll.kernel32.GetDriveTypeW(str(drive)) != DRIVE_REMOVABLE:  # type: ignore[attr-defined]
                continue
            if label_hint is not None:
                vol = _windows_volume_label(str(drive))
                if label_hint.lower() not in vol.lower():
                    continue
            return drive
    except Exception:
        pass
    return None


def _windows_volume_label(drive: str) -> str:
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            drive, buf, len(buf), None, None, None, None, 0
        )
        return buf.value
    except Exception:
        return ""


def _find_usb_unix(label_hint: str | None) -> Path | None:
    """Scan common Linux/macOS mount points for a removable drive."""
    import getpass

    user = getpass.getuser()
    search_roots = [
        Path(f"/media/{user}"),
        Path("/media"),
        Path("/run/media"),
        Path("/mnt"),
    ]

    for base in search_roots:
        if not base.is_dir():
            continue
        try:
            entries = sorted(base.iterdir())
        except PermissionError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if label_hint is not None and label_hint.lower() not in entry.name.lower():
                continue
            if os.path.ismount(str(entry)):
                return entry

    return None
