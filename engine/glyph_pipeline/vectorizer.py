"""
Converts a raster glyph (PIL Image) to SVG paths, then to PDF content-stream
path operators in a 1000-unit em coordinate space.

Vectorisation cascade: vtracer Python binding → potrace subprocess → None.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from PIL import Image


# ---------------------------------------------------------------------------
# Binarisation
# ---------------------------------------------------------------------------

def _binarize(img: Image.Image, threshold: int = 128) -> Image.Image:
    """Return a 1-bit-equivalent L-mode image: glyph pixels = 0 (black)."""
    gray = img.convert("L")
    return gray.point(lambda x: 0 if x < threshold else 255, "L")


# ---------------------------------------------------------------------------
# Vectorisation backends
# ---------------------------------------------------------------------------

def _svg_via_vtracer(img: Image.Image) -> Optional[str]:
    try:
        import vtracer  # type: ignore
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return vtracer.convert_raw_image_to_svg(
            buf.getvalue(),
            img_format="png",
            colormode="binary",
            filter_speckle=2,
            color_precision=6,
            layer_difference=16,
            mode="spline",
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3,
        )
    except Exception:
        return None


def _svg_via_potrace(img: Image.Image) -> Optional[str]:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bmp = Path(tmp) / "g.bmp"
            svg = Path(tmp) / "g.svg"
            # potrace reads BMP; save as grayscale BMP
            img.convert("L").save(str(bmp))
            rc = subprocess.call(
                ["potrace", "--svg", "-o", str(svg), str(bmp)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if rc == 0 and svg.exists():
                return svg.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass
    return None


def image_to_svg(img: Image.Image) -> Optional[str]:
    """Vectorise a glyph image. Returns SVG string or None if all methods fail."""
    binary = _binarize(img)
    return _svg_via_vtracer(binary) or _svg_via_potrace(binary)


# ---------------------------------------------------------------------------
# SVG path → PDF path operators
# ---------------------------------------------------------------------------

def _parse_svg_paths(svg: str) -> List[str]:
    return re.findall(r'<path[^>]+\bd="([^"]+)"', svg, re.IGNORECASE | re.DOTALL)


def _svg_path_to_pdf_ops(
    d: str,
    w_px: float,
    h_px: float,
    em: float = 1000.0,
) -> str:
    """
    Convert one SVG path `d` string to PDF content-stream operators.

    Coordinate mapping:
      SVG space : origin top-left, x ∈ [0, w_px], y ∈ [0, h_px]  (y down)
      Glyph space: origin bottom-left, x ∈ [0, em*w_px/h_px], y ∈ [0, em] (y up)

    Scale factor: s = em / h_px  (uniform, preserves aspect ratio)
    x_glyph = svg_x * s
    y_glyph = (h_px - svg_y) * s   (flip Y)
    """
    s = em / h_px

    def fx(v: float) -> str:
        return f"{v * s:.4f}"

    def fy(v: float) -> str:
        return f"{(h_px - v) * s:.4f}"

    # Tokenise: commands or numbers
    tokens = re.findall(
        r'[MmLlCcQqZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',
        d,
    )

    ops: List[str] = []
    idx = 0
    cx, cy = 0.0, 0.0   # current position in SVG space

    CMDS = set("MmLlCcQqZz")

    def peek() -> Optional[str]:
        return tokens[idx] if idx < len(tokens) else None

    def num() -> float:
        nonlocal idx
        v = float(tokens[idx])
        idx += 1
        return v

    while idx < len(tokens):
        cmd = tokens[idx]
        if cmd not in CMDS:
            idx += 1
            continue
        idx += 1

        if cmd == 'M':
            x, y = num(), num()
            cx, cy = x, y
            ops.append(f"{fx(x)} {fy(y)} m")
            while peek() and peek() not in CMDS:
                x, y = num(), num()
                cx, cy = x, y
                ops.append(f"{fx(x)} {fy(y)} l")

        elif cmd == 'm':
            x, y = cx + num(), cy + num()
            cx, cy = x, y
            ops.append(f"{fx(x)} {fy(y)} m")
            while peek() and peek() not in CMDS:
                x, y = cx + num(), cy + num()
                cx, cy = x, y
                ops.append(f"{fx(x)} {fy(y)} l")

        elif cmd == 'L':
            while peek() and peek() not in CMDS:
                x, y = num(), num()
                cx, cy = x, y
                ops.append(f"{fx(x)} {fy(y)} l")

        elif cmd == 'l':
            while peek() and peek() not in CMDS:
                x, y = cx + num(), cy + num()
                cx, cy = x, y
                ops.append(f"{fx(x)} {fy(y)} l")

        elif cmd == 'C':
            while peek() and peek() not in CMDS:
                x1, y1 = num(), num()
                x2, y2 = num(), num()
                x,  y  = num(), num()
                cx, cy = x, y
                ops.append(f"{fx(x1)} {fy(y1)} {fx(x2)} {fy(y2)} {fx(x)} {fy(y)} c")

        elif cmd == 'c':
            while peek() and peek() not in CMDS:
                x1 = cx + num(); y1 = cy + num()
                x2 = cx + num(); y2 = cy + num()
                x  = cx + num(); y  = cy + num()
                cx, cy = x, y
                ops.append(f"{fx(x1)} {fy(y1)} {fx(x2)} {fy(y2)} {fx(x)} {fy(y)} c")

        elif cmd == 'Q':
            # Approximate quadratic with cubic (degree-elevation formula)
            while peek() and peek() not in CMDS:
                qx, qy = num(), num()
                x,  y  = num(), num()
                cp1x = cx + 2/3 * (qx - cx); cp1y = cy + 2/3 * (qy - cy)
                cp2x = x  + 2/3 * (qx - x);  cp2y = y  + 2/3 * (qy - y)
                cx, cy = x, y
                ops.append(f"{fx(cp1x)} {fy(cp1y)} {fx(cp2x)} {fy(cp2y)} {fx(x)} {fy(y)} c")

        elif cmd == 'q':
            while peek() and peek() not in CMDS:
                qx = cx + num(); qy = cy + num()
                x  = cx + num(); y  = cy + num()
                cp1x = cx + 2/3 * (qx - cx); cp1y = cy + 2/3 * (qy - cy)
                cp2x = x  + 2/3 * (qx - x);  cp2y = y  + 2/3 * (qy - y)
                cx, cy = x, y
                ops.append(f"{fx(cp1x)} {fy(cp1y)} {fx(cp2x)} {fy(cp2y)} {fx(x)} {fy(y)} c")

        elif cmd in ('Z', 'z'):
            ops.append("h")

    return "\n".join(ops)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

EM = 1000.0  # glyph-space em height (per-mille convention)


def glyph_to_pdf_ops(
    img: Image.Image,
) -> Optional[str]:
    """
    Full pipeline: PIL image → SVG → PDF path operators (without d1/d0 header).

    The returned string uses a 1000-unit em-square coordinate system:
      advance_width = EM * (w_px / h_px)
      glyph bbox   = [0, 0, advance_width, EM]

    Returns None if vectorisation fails.
    """
    w_px, h_px = img.size
    if w_px == 0 or h_px == 0:
        return None

    svg = image_to_svg(img)
    if not svg:
        return None

    path_ds = _parse_svg_paths(svg)
    if not path_ds:
        return None

    all_ops: List[str] = []
    for d in path_ds:
        ops = _svg_path_to_pdf_ops(d, w_px, h_px, em=EM)
        if ops:
            all_ops.append(ops)

    if not all_ops:
        return None

    return "\n".join(all_ops) + "\nf"


def advance_width(w_px: int, h_px: int) -> float:
    """Advance width in glyph-space units (per-mille em) for a w_px × h_px crop."""
    if h_px == 0:
        return EM
    return EM * w_px / h_px
