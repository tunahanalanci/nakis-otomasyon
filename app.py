"""Flask web application for nakis-otomasyon."""

from __future__ import annotations

import base64
import sys
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config, FillConfig, HoopConfig, SatinConfig, load
from src.pipeline import run as pipeline_run

app = Flask(__name__)

DEFAULT_CONFIG = Path(__file__).parent / "config" / "default.json"
JOBS_DIR       = Path(__file__).parent / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

HOOP_SIZES = {
    "100x100": (100, 100),
    "130x110": (130, 110),
    "150x200": (150, 200),
    "200x200": (200, 200),
    "300x200": (300, 200),
    "360x200": (360, 200),
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    if "image" not in request.files:
        return jsonify({"error": "Gorsel dosyasi gonderilmedi."}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "Dosya adi bos."}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        return jsonify({"error": "Sadece PNG ve JPG kabul edilir."}), 400

    # ── Parse parameters ──────────────────────────────────────────────────────
    try:
        width_mm   = float(request.form.get("width_mm",  80))
        height_mm  = float(request.form.get("height_mm", 60))
        max_colors = int(request.form.get("max_colors",  2))
        spacing_mm = float(request.form.get("spacing_mm", 0.4))
        angle_deg  = float(request.form.get("angle_deg",  45))
        underlay   = request.form.get("underlay", "true").lower() == "true"
        trim_jumps = request.form.get("trim_jumps", "true").lower() == "true"
        pull_comp  = float(request.form.get("pull_compensation_mm", 0.2))
        hoop_key   = request.form.get("hoop", "200x200")
        hoop_w, hoop_h = HOOP_SIZES.get(hoop_key, (200, 200))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Gecersiz parametre: {exc}"}), 400

    # ── Save uploaded file ────────────────────────────────────────────────────
    job_id  = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    img_path = job_dir / f"input{suffix}"
    file.save(str(img_path))

    # ── Aspect-ratio preservation ─────────────────────────────────────────────
    from PIL import Image as PilImage
    with PilImage.open(str(img_path)) as pil:
        iw, ih = pil.size
    if width_mm <= 0 and height_mm > 0:
        width_mm = height_mm * iw / ih
    elif height_mm <= 0 and width_mm > 0:
        height_mm = width_mm * ih / iw
    elif width_mm <= 0 and height_mm <= 0:
        width_mm, height_mm = 80.0, 60.0

    # ── Build config ──────────────────────────────────────────────────────────
    cfg = load(DEFAULT_CONFIG)
    cfg.width_mm              = width_mm
    cfg.height_mm             = height_mm
    cfg.max_colors            = max(1, max_colors)
    cfg.fill                  = FillConfig(
        spacing_mm = spacing_mm,
        angle_deg  = angle_deg,
        underlay   = underlay,
    )
    cfg.satin                 = SatinConfig(
        min_width_mm = 1.0,
        max_width_mm = 8.0,
        density_mm   = spacing_mm,
    )
    cfg.hoop                  = HoopConfig(w=hoop_w, h=hoop_h)
    cfg.pull_compensation_mm  = pull_comp
    cfg.trim_jumps            = trim_jumps

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        result = pipeline_run(str(img_path), cfg, str(job_dir))
    except Exception as exc:
        return jsonify({"error": f"Pipeline hatasi: {exc}"}), 500

    # ── Sanity check: fill actually produced stitches ─────────────────────────
    if result.total_stitches < 10:
        return jsonify({
            "error": (
                "Dolgu uretilemedi: cok az dikis uretildi. "
                "Kontur/esikleme kontrol edin veya gorsel boyutunu buyutin."
            )
        }), 422

    # ── Encode preview as base64 ──────────────────────────────────────────────
    preview_b64 = base64.b64encode(result.preview_path.read_bytes()).decode()

    minx, miny, maxx, maxy = result.bounds_mm
    actual_w = round(maxx - minx, 1)
    actual_h = round(maxy - miny, 1)

    return jsonify({
        "job_id":      job_id,
        "preview_b64": preview_b64,
        "stats": {
            "total_stitches": result.total_stitches,
            "n_color_blocks": result.n_color_blocks,
            "actual_w_mm":   actual_w,
            "actual_h_mm":   actual_h,
            "target_w_mm":   round(width_mm, 1),
            "target_h_mm":   round(height_mm, 1),
            "validation_ok": result.validation.ok,
            "errors":        result.validation.errors,
            "warnings":      result.validation.warnings,
        },
    })


@app.route("/api/download/<job_id>/<filetype>")
def download(job_id: str, filetype: str):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Is bulunamadi."}), 404

    if filetype == "dst":
        files = sorted(job_dir.glob("*.dst"))
        if files:
            return send_file(str(files[0]), as_attachment=True,
                             download_name=files[0].name)
    elif filetype == "report":
        p = job_dir / "renk_sirasi.txt"
        if p.exists():
            return send_file(str(p), as_attachment=True,
                             download_name="renk_sirasi.txt")
    elif filetype == "preview":
        files = sorted(job_dir.glob("*_preview.png"))
        if files:
            return send_file(str(files[0]), as_attachment=True,
                             download_name="onizleme.png")

    return jsonify({"error": "Dosya bulunamadi."}), 404


if __name__ == "__main__":
    print("=" * 50)
    print("  Nakis Otomasyon Web Arayuzu")
    print("  Adres: http://localhost:5000")
    print("=" * 50)
    webbrowser.open("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
