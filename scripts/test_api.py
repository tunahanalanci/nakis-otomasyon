"""API endpoint testi: logo 100mm DST uretimi."""
import urllib.request
import json
import uuid

LOGO = "samples/gelin_tekstil_logo.jpg"
boundary = uuid.uuid4().hex
CRLF = b"\r\n"


def field(name, value):
    return (
        b"--" + boundary.encode() + CRLF
        + b'Content-Disposition: form-data; name="' + name.encode() + b'"' + CRLF
        + CRLF
        + value.encode() + CRLF
    )


with open(LOGO, "rb") as f:
    file_data = f.read()

parts = (
    b"--" + boundary.encode() + CRLF
    + b'Content-Disposition: form-data; name="image"; filename="gelin_tekstil_logo.jpg"' + CRLF
    + b"Content-Type: image/jpeg" + CRLF
    + CRLF
    + file_data + CRLF
)
for name, val in [
    ("width_mm", "100"),
    ("height_mm", "0"),
    ("max_colors", "2"),
    ("hoop", "200x200"),
    ("spacing_mm", "0.4"),
    ("angle_deg", "45"),
    ("underlay", "true"),
]:
    parts += field(name, val)
parts += b"--" + boundary.encode() + b"--" + CRLF

req = urllib.request.Request(
    "http://localhost:5000/api/generate",
    data=parts,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
)

print("POST /api/generate ...  (logo 100mm, 2 renk)")
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
except Exception as e:
    print(f"HATA: {e}")
    raise SystemExit(1)

s = data["stats"]
print(f"\n=== SONUC ===")
print(f"Durum        : OK  (job={data['job_id']})")
print(f"Dikis        : {s['total_stitches']}")
print(f"Renk blok    : {s['n_color_blocks']}")
print(f"Gercek boyut : {s['actual_w_mm']} x {s['actual_h_mm']} mm")
print(f"Hedef boyut  : {s['target_w_mm']} x {s['target_h_mm']} mm")
print(f"SVG mevcut   : {data['has_svg']}")
print(f"Validation   : {'OK' if s['validation_ok'] else 'UYARI'}")
if s["errors"]:
    print(f"Hatalar      : {s['errors']}")
if s["warnings"]:
    print(f"Uyarilar     : {s['warnings']}")

print("\nIplik listesi:")
for t in data["thread_list"]:
    print(f"  {t['sira']}. {t['iplik_kodu']:8s}  {t['iplik_adi']:<30s}  "
          f"hex={t['iplik_hex']}  dE={t['delta_e']}")

# DST dosyasini indir
job_id = data["job_id"]
dst_url = f"http://localhost:5000/api/download/{job_id}/dst"
with urllib.request.urlopen(dst_url) as r:
    dst_bytes = r.read()
print(f"\nDST boyutu   : {len(dst_bytes)} bayt")

# SVG dosyasini indir
if data["has_svg"]:
    svg_url = f"http://localhost:5000/api/download/{job_id}/svg"
    with urllib.request.urlopen(svg_url) as r:
        svg_bytes = r.read()
    print(f"SVG boyutu   : {len(svg_bytes)} bayt")

print("\nTest BASARILI.")
