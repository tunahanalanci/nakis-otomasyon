"""Faz 2 testleri: genislik tahmini, iplik esleme, E2E."""

from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path


# ── estimate_contour_width_mm ─────────────────────────────────────────────────

class TestEstimateWidth:
    """Width estimation via distance transform."""

    def _make_strip_cnt(self, width_px: int, length_px: int):
        """Thin horizontal rectangle → single OpenCV contour."""
        import cv2
        mask = np.zeros((length_px + 4, width_px + 4), dtype=np.uint8)
        mask[2:length_px + 2, 2:width_px + 2] = 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return cnts[0]

    def _make_square_cnt(self, side_px: int):
        import cv2
        mask = np.zeros((side_px + 4, side_px + 4), dtype=np.uint8)
        mask[2:side_px + 2, 2:side_px + 2] = 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return cnts[0]

    def test_narrow_strip_under_3mm(self):
        """1 mm wide strip at 10 px/mm → width ~1 mm."""
        from src.inkstitch_engine import estimate_contour_width_mm
        px_per_mm = 10.0
        # 1 mm wide, 30 mm long
        cnt = self._make_strip_cnt(width_px=10, length_px=300)
        w = estimate_contour_width_mm(cnt, px_per_mm)
        assert w < 3.0, f"Beklenen <3mm, alindi {w:.2f}mm"
        assert w > 0.5, f"Beklenen >0.5mm, alindi {w:.2f}mm"

    def test_wide_square_over_3mm(self):
        """20 mm square at 10 px/mm → width ~20 mm (>> 3 mm)."""
        from src.inkstitch_engine import estimate_contour_width_mm
        px_per_mm = 10.0
        cnt = self._make_square_cnt(side_px=200)
        w = estimate_contour_width_mm(cnt, px_per_mm)
        assert w > 3.0, f"Beklenen >3mm, alindi {w:.2f}mm"


class TestChooseStitchType:
    """Stitch type selection logic."""

    def _cfg(self, satin_max=3.0, running_max=1.0):
        from src.config import Config
        c = Config()
        c.satin_max_width_mm = satin_max
        c.running_max_width_mm = running_max
        return c

    def test_very_narrow_running(self):
        from src.inkstitch_engine import choose_stitch_type
        assert choose_stitch_type(0.5, self._cfg()) == "running_stitch"

    def test_medium_contour_fill(self):
        from src.inkstitch_engine import choose_stitch_type
        assert choose_stitch_type(2.0, self._cfg()) == "contour_fill"

    def test_wide_auto_fill(self):
        from src.inkstitch_engine import choose_stitch_type
        assert choose_stitch_type(5.0, self._cfg()) == "auto_fill"

    def test_boundary_satin_max(self):
        from src.inkstitch_engine import choose_stitch_type
        # Exactly at threshold → auto_fill (not strictly less than)
        assert choose_stitch_type(3.0, self._cfg(satin_max=3.0)) == "auto_fill"


# ── Thread matching ───────────────────────────────────────────────────────────

class TestThreadMatching:
    """Lab color distance matching against catalog."""

    def test_black_matches_isacord_0010(self):
        from src.threads import match_palette
        matches = match_palette([(10, 10, 10)])
        assert matches[0].thread_code == "0010", (
            f"Siyah icin beklenen 0010, alindi {matches[0].thread_code}"
        )

    def test_navy_matches_dark_blue(self):
        """Logo laciverdine (#2b3b4a) en yakin iplik koyu mavi olmali."""
        from src.threads import match_palette
        matches = match_palette([(43, 59, 74)])
        code = matches[0].thread_code
        # Koyu mavi tonlari: 0561, 3544, 0570, 0553
        dark_blues = {"0561", "3544", "0570", "0553", "0545", "0588"}
        assert code in dark_blues, (
            f"Lacivert icin beklenen koyu mavi, alindi {code} ({matches[0].thread_name})"
        )

    def test_gold_matches_gold_tone(self):
        """Logo altinina (#aa8a50) en yakin iplik altin tonu olmali."""
        from src.threads import match_palette
        matches = match_palette([(170, 138, 80)])
        code = matches[0].thread_code
        gold_tones = {"0131", "0142", "0151", "0163", "0842", "0852", "0741"}
        assert code in gold_tones, (
            f"Altin icin beklenen altin tonu, alindi {code} ({matches[0].thread_name})"
        )

    def test_lab_distance_not_rgb(self):
        """Renk eslemesi Lab uzayinda yapilmali (RGB degil).
        Lab'da iki farkli renk secilmeli: sari ve yesil.
        """
        from src.threads import match_palette
        # Pure yellow vs pure green — in Lab these are well separated
        m_yellow = match_palette([(255, 215, 0)])[0]
        m_green  = match_palette([(0, 160, 60)])[0]
        assert m_yellow.thread_code != m_green.thread_code

    def test_white_matches_soft_white_or_cream(self):
        from src.threads import match_palette
        matches = match_palette([(255, 255, 255)])
        whites = {"0020", "0800", "3600", "3620", "3640", "0821"}
        assert matches[0].thread_code in whites, (
            f"Beyaz icin beklenen beyaz tonu, alindi {matches[0].thread_code}"
        )

    def test_delta_e_reasonable(self):
        """Delta-E skoru mantikli aralikta olmali (0-100)."""
        from src.threads import match_palette
        matches = match_palette([(100, 150, 200)])
        assert 0 <= matches[0].delta_e <= 100


# ── rgb_to_lab sanity ─────────────────────────────────────────────────────────

class TestRgbToLab:
    def test_black_is_zero_lightness(self):
        from src.threads import rgb_to_lab
        L, a, b = rgb_to_lab(0, 0, 0)
        assert abs(L) < 1.0

    def test_white_is_high_lightness(self):
        from src.threads import rgb_to_lab
        L, a, b = rgb_to_lab(255, 255, 255)
        assert L > 95.0

    def test_gray_neutral(self):
        """Pure gray should have a~0, b~0."""
        from src.threads import rgb_to_lab
        _, a, b = rgb_to_lab(128, 128, 128)
        assert abs(a) < 2.0
        assert abs(b) < 2.0


# ── E2E: logo → DST + renk raporu ────────────────────────────────────────────

class TestE2ELogo:
    """End-to-end: Gelin Tekstil logo → DST with Ink/Stitch engine."""

    LOGO = Path(__file__).resolve().parent.parent / "samples" / "gelin_tekstil_logo.jpg"

    @pytest.mark.skipif(
        not Path(r"C:\Program Files\Inkscape\bin\inkscape.exe").exists(),
        reason="Inkscape kurulu degil",
    )
    def test_logo_produces_dst_and_report(self, tmp_path):
        from src.config import Config
        from src.pipeline import run

        cfg = Config(width_mm=80.0, height_mm=80.0, max_colors=2,
                     use_inkstitch=True)
        result = run(self.LOGO, cfg, tmp_path)

        assert result.dst_path.exists(), "DST dosyasi olusturulamadi"
        assert result.dst_path.stat().st_size > 100

        assert result.color_report_path.exists(), "Renk raporu olusturulamadi"
        report = result.color_report_path.read_text(encoding="utf-8")
        assert "IPLIK SIRASI" in report

        assert result.total_stitches > 500, (
            f"Cok az stitch: {result.total_stitches}"
        )
        assert result.n_color_blocks >= 2

    @pytest.mark.skipif(
        not Path(r"C:\Program Files\Inkscape\bin\inkscape.exe").exists(),
        reason="Inkscape kurulu degil",
    )
    def test_stitch_type_selection(self, tmp_path):
        """Logo islenmeli ve genis alanlar auto_fill, dar alanlar diger tip olmali."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from src.config import Config
        from src.preprocess import load_and_scale
        from src.colors import quantise
        from src.separate import masks_from_labels, clean_mask
        from src.threads import match_palette
        from src.inkstitch_engine import build_svg

        cfg = Config(width_mm=80.0, height_mm=80.0, max_colors=2,
                     use_inkstitch=True)
        img, px_per_mm = load_and_scale(self.LOGO, cfg)
        label_map, palette = quantise(img, cfg)
        masks = [clean_mask(m) for m in masks_from_labels(label_map, len(palette))]
        matches = match_palette(palette)

        summary = build_svg(masks, matches, px_per_mm, 80.0, 80.0, cfg,
                             tmp_path / "test_logo.svg")

        all_types = [t for types in summary.values() for t, _ in types]
        assert "auto_fill" in all_types, "Genis alanlar auto_fill olmali"
