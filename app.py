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
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload limit

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
        width_mm      = float(request.form.get("width_mm",  80))
        height_mm     = float(request.form.get("height_mm", 60))
        max_colors    = int(request.form.get("max_colors",  2))
        spacing_mm    = float(request.form.get("spacing_mm", 0.4))
        angle_deg     = float(request.form.get("angle_deg",  45))
        underlay      = request.form.get("underlay", "true").lower() == "true"
        trim_jumps    = request.form.get("trim_jumps", "true").lower() == "true"
        pull_comp     = float(request.form.get("pull_compensation_mm", 0.2))
        hoop_key      = request.form.get("hoop", "200x200")
        hoop_w, hoop_h = HOOP_SIZES.get(hoop_key, (200, 200))
        thread_brand  = request.form.get("thread_brand", "isacord.json")
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Gecersiz parametre: {exc}"}), 400

    # ── Save uploaded file ────────────────────────────────────────────────────
    job_id  = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    img_path = job_dir / f"input{suffix}"
    file.save(str(img_path))

    # ── Aspect-ratio preservation + complexity check ──────────────────────────
    from PIL import Image as PilImage
    complexity_warning = None
    with PilImage.open(str(img_path)) as pil:
        iw, ih = pil.size
        unique_colors = len(set(pil.convert("RGB").getdata()))
        if unique_colors > 500:
            complexity_warning = (
                "Fotograf veya cok renkli gorsel tespit edildi. "
                "Sade, az renkli logolar cok daha iyi sonuc verir."
            )
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
    cfg.thread_brand          = thread_brand
    # Inkscape --batch-process crashes on this system; use pure-Python engine
    cfg.use_inkstitch         = False

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

    # ── Thread matching ───────────────────────────────────────────────────────
    from src.threads import match_palette
    thread_matches = match_palette(result.palette, cfg.thread_brand)
    thread_list = [
        {
            "sira":       i + 1,
            "iplik_kodu": m.thread_code,
            "iplik_adi":  m.thread_name,
            "bulunan_hex": "#{:02x}{:02x}{:02x}".format(*m.found_rgb),
            "iplik_hex":   "#{:02x}{:02x}{:02x}".format(*m.thread_rgb),
            "delta_e":     round(m.delta_e, 1),
        }
        for i, m in enumerate(thread_matches)
    ]

    # ── Encode preview as base64 ──────────────────────────────────────────────
    preview_b64 = base64.b64encode(result.preview_path.read_bytes()).decode()

    minx, miny, maxx, maxy = result.bounds_mm
    actual_w = round(maxx - minx, 1)
    actual_h = round(maxy - miny, 1)

    # ── Build stitch sequence for canvas animation + GIF ─────────────────────
    # Source: raw blocks in Y-down mm — same as preview renderer (single path).
    # Format: [x_mm, y_mm, cmd(0=stitch,1=jump), block_idx, r, g, b]
    # No Y-flip here; JS canvas toPx() and _build_gif both use Y-down directly.
    _palette = result.palette or [(30, 30, 200)]
    stitch_seq = []
    for blk_obj in result.blocks:
        r, g, b = _palette[blk_obj.color_idx % len(_palette)]
        first = True
        for x, y in blk_obj.points:
            cmd = 1 if first else 0   # 1=jump (block start), 0=stitch
            stitch_seq.append([round(x, 2), round(y, 2), cmd,
                                blk_obj.color_idx, r, g, b])
            first = False

    # Persist for on-demand GIF generation (no need to re-run pipeline).
    import json as _json
    (job_dir / "stitch_seq.json").write_text(
        _json.dumps(stitch_seq), encoding="utf-8"
    )

    warnings_all = list(result.validation.warnings)
    if complexity_warning:
        warnings_all.insert(0, complexity_warning)

    return jsonify({
        "job_id":        job_id,
        "preview_b64":   preview_b64,
        "stitch_seq":    stitch_seq,
        "palette":       list(result.palette),
        "bounds_mm":     [minx, miny, maxx, maxy],
        "thread_list":   thread_list,
        "has_svg":       result.svg_path is not None and result.svg_path.exists(),
        "stats": {
            "total_stitches": result.total_stitches,
            "n_color_blocks": result.n_color_blocks,
            "actual_w_mm":   actual_w,
            "actual_h_mm":   actual_h,
            "target_w_mm":   round(width_mm, 1),
            "target_h_mm":   round(height_mm, 1),
            "validation_ok": result.validation.ok,
            "errors":        result.validation.errors,
            "warnings":      warnings_all,
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
    elif filetype == "svg":
        files = sorted(job_dir.glob("*.svg"))
        if files:
            return send_file(str(files[0]), as_attachment=True,
                             download_name="nakis_tasarim.svg")

    return jsonify({"error": "Dosya bulunamadi."}), 404


@app.route("/api/animation/<job_id>")
def animation_gif(job_id: str):
    """Generate and serve an animated GIF of the stitch process."""
    import json as _json
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Is bulunamadi."}), 404

    seq_path = job_dir / "stitch_seq.json"
    if not seq_path.exists():
        return jsonify({"error": "Stitch verisi bulunamadi."}), 404

    gif_path = job_dir / "surec.gif"
    if not gif_path.exists():
        seq = _json.loads(seq_path.read_text(encoding="utf-8"))
        _build_gif(seq, gif_path)

    return send_file(str(gif_path), as_attachment=True, download_name="surec.gif")


def _build_gif(
    stitch_seq: list,
    out_path: Path,
    scale: float = 3.0,
    n_frames: int = 180,
    fps: int = 30,
) -> None:
    """Render animated GIF from stitch_seq (Y-down mm, same as preview renderer).

    stitch_seq format: [[x_mm, y_mm, cmd(0=stitch,1=jump), blk, r, g, b], ...]
    No Y-flip — Y-down mm maps directly to PIL Y-down pixels.
    """
    from PIL import Image as _Img, ImageDraw as _Draw

    stitch_pts = [[s[0], s[1], s[4], s[5], s[6]] for s in stitch_seq if s[2] == 0]
    if not stitch_pts:
        _Img.new("RGB", (100, 100), "white").save(str(out_path))
        return

    xs = [p[0] for p in stitch_pts]
    ys = [p[1] for p in stitch_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 20

    img_w = max(1, int((max_x - min_x) * scale)) + 2 * pad
    img_h = max(1, int((max_y - min_y) * scale)) + 2 * pad

    def to_px(x_mm: float, y_mm: float) -> tuple[int, int]:
        # Y-down mm → Y-down px (no flip, same convention as preview)
        return (int((x_mm - min_x) * scale) + pad,
                int((y_mm - min_y) * scale) + pad)

    step = max(1, len(stitch_pts) // n_frames)
    canvas = _Img.new("RGB", (img_w, img_h), "white")
    frames: list[_Img.Image] = []
    last_px = None
    last_jump = True   # reset pen on block boundary
    stitch_i = 0
    seq_i = 0

    for frame_n in range(n_frames):
        target = (frame_n + 1) * step
        draw = _Draw.Draw(canvas)

        while stitch_i < target and seq_i < len(stitch_seq):
            row = stitch_seq[seq_i]
            seq_i += 1
            x, y, cmd, _, r, g, b = row
            if cmd == 1:   # jump / block start → lift pen
                last_px = None
            else:           # stitch
                px, py = to_px(x, y)
                if last_px is not None:
                    draw.line([last_px, (px, py)], fill=(r, g, b), width=2)
                last_px = (px, py)
                stitch_i += 1

        frame = canvas.copy()
        if last_px:
            fd = _Draw.Draw(frame)
            nx, ny = last_px
            fd.ellipse([nx - 4, ny - 4, nx + 4, ny + 4], fill=(220, 40, 40))

        frames.append(frame.convert("P", palette=_Img.ADAPTIVE, colors=64))

    if not frames:
        return

    frames[0].save(
        str(out_path),
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    print("=" * 50)
    print("  Nakis Otomasyon Web Arayuzu")
    print("  Adres: http://localhost:5000")
    print("=" * 50)
    webbrowser.open("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
