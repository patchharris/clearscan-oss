"""
Reconstructs the output PDF by:
  1. Keeping the original page content (background raster image).
  2. Appending a new content stream that white-outs each character's bounding
     box, then draws the vectorised Type 3 glyph in its place.

This replicates the ClearScan effect: raster scan → crisp vector text.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pikepdf

from .extractor import CharBox, PageInfo
from .type3_font import char_code, glyph_name, EM

DPI = 300


def _pt(px: float) -> float:
    """Convert pixels (at 300 DPI) to PDF points."""
    return px * 72.0 / DPI


def _encode_char(char: str) -> str:
    """
    Encode a character for use in a PDF string literal.
    Returns the octal escape sequence (safe for any byte value).
    """
    code = char_code(char)
    return f"\\{code:03o}"


def _build_page_stream(
    page: PageInfo,
    char_glyphs: Dict[str, Tuple[float, str]],
    font_name: str = "VF1",
) -> bytes:
    """
    Build the overlay content stream for one page.

    For each character box whose glyph was successfully vectorised:
      - Draw a white filled rectangle to cover the raster glyph.
      - Draw the vector glyph in black at the same position/size.

    Characters whose glyph could not be vectorised are left untouched
    (the raster scan shows through).
    """
    page_h_pt = _pt(page.height_px)
    lines: List[str] = ["q"]   # save graphics state

    for box in page.char_boxes:
        char = box.char
        if char not in char_glyphs:
            continue

        adv_w, _ = char_glyphs[char]

        # Bounding box in PDF points (origin bottom-left)
        x_pt    = _pt(box.x1)
        y_pt    = page_h_pt - _pt(box.y2)   # bottom of glyph in PDF coords
        w_pt    = _pt(box.x2 - box.x1)
        h_pt    = _pt(box.y2 - box.y1)

        if w_pt <= 0 or h_pt <= 0:
            continue

        # 1. White-out rectangle (covers the raster glyph)
        lines.append(
            f"1 g  {x_pt:.4f} {y_pt:.4f} {w_pt:.4f} {h_pt:.4f} re f"
        )

        # 2. Draw vector glyph in black
        #    FontMatrix=[0.001…], so font size = h_pt makes 1000 em units = h_pt
        #    Use Tm to position: [size 0 0 size x y]
        enc = _encode_char(char)
        lines.append(
            f"0 g  BT  /{font_name} {h_pt:.4f} Tf  "
            f"1 0 0 1 {x_pt:.4f} {y_pt:.4f} Tm  "
            f"({enc}) Tj  ET"
        )

    lines.append("Q")   # restore graphics state
    return "\n".join(lines).encode("latin-1")


def overlay_type3_text(
    doc: pikepdf.Pdf,
    pages: List[PageInfo],
    char_glyphs: Dict[str, Tuple[float, str]],
    font_obj: pikepdf.Object,
    font_name: str = "VF1",
) -> None:
    """
    Mutate `doc` in-place: for each page add the overlay content stream and
    register the Type 3 font in the page's Resources.
    """
    for page_info in pages:
        if not page_info.char_boxes:
            continue

        pdf_page = doc.pages[page_info.page_idx]

        # Build overlay stream
        stream_bytes = _build_page_stream(page_info, char_glyphs, font_name)
        if not stream_bytes.strip():
            continue

        overlay = pikepdf.Stream(doc, stream_bytes)

        # Append overlay to existing Contents
        existing = pdf_page.get("/Contents")
        if existing is None:
            pdf_page["/Contents"] = overlay
        elif isinstance(existing, pikepdf.Array):
            existing.append(overlay)
        else:
            pdf_page["/Contents"] = pikepdf.Array([existing, overlay])

        # Register font resource
        if "/Resources" not in pdf_page:
            pdf_page["/Resources"] = pikepdf.Dictionary()
        resources = pdf_page["/Resources"]
        if "/Font" not in resources:
            resources["/Font"] = pikepdf.Dictionary()
        resources["/Font"][f"/{font_name}"] = font_obj


def save(doc: pikepdf.Pdf, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f"[vectorscan] saved → {out_path}", file=sys.stderr)
