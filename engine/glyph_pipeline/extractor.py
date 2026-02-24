"""
Renders PDF pages to high-DPI images and extracts per-character glyph crops
using Tesseract (image_to_boxes for character-level bounding boxes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

DPI = 300


@dataclass
class CharBox:
    char: str
    x1: int   # left  (px, top-left origin)
    y1: int   # top   (px, top-left origin)
    x2: int   # right (px)
    y2: int   # bottom(px)
    page_idx: int
    confidence: float = 0.0


@dataclass
class PageInfo:
    page_idx: int
    image: Image.Image
    width_px: int
    height_px: int
    width_pt: float   # page width in PDF points
    height_pt: float  # page height in PDF points
    char_boxes: List[CharBox] = field(default_factory=list)


def render_pages(pdf_path: Path, dpi: int = DPI) -> List[PageInfo]:
    """Open PDF and render each page to a PIL RGB image."""
    doc = fitz.open(str(pdf_path))
    scale = dpi / 72.0
    pages: List[PageInfo] = []
    for idx, page in enumerate(doc):
        rect = page.rect
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pages.append(PageInfo(
            page_idx=idx,
            image=img,
            width_px=pix.width,
            height_px=pix.height,
            width_pt=rect.width,
            height_pt=rect.height,
        ))
    doc.close()
    return pages


def extract_char_boxes(page: PageInfo, lang: str = "eng") -> None:
    """
    Run Tesseract on the page image and populate page.char_boxes with
    per-character bounding boxes.

    pytesseract.image_to_boxes() returns char-level boxes with Tesseract's
    bottom-left origin; we convert to top-left (PIL/image) origin.
    """
    img = page.image
    h = page.height_px

    # Try legacy engine first (more reliable char-level boxes), fall back to LSTM
    for config in ("--oem 0 --psm 6", "--oem 1 --psm 6"):
        try:
            raw = pytesseract.image_to_boxes(
                img,
                lang=lang,
                config=config,
                output_type=pytesseract.Output.STRING,
            )
            break
        except Exception:
            raw = ""

    page.char_boxes.clear()
    for line in raw.strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        char = parts[0]
        if not char.strip():
            continue
        # Tesseract format: char x1 y1_bottom x2 y2_bottom page
        x1 = int(parts[1])
        y1_tess = int(parts[2])
        x2 = int(parts[3])
        y2_tess = int(parts[4])
        # Convert from bottom-left to top-left origin
        y1 = h - y2_tess
        y2 = h - y1_tess
        if x2 <= x1 or y2 <= y1:
            continue
        page.char_boxes.append(CharBox(
            char=char,
            x1=x1, y1=y1, x2=x2, y2=y2,
            page_idx=page.page_idx,
        ))


def crop_glyph(page: PageInfo, box: CharBox) -> Image.Image:
    """Crop a character glyph from the page image (no padding)."""
    x1 = max(0, box.x1)
    y1 = max(0, box.y1)
    x2 = min(page.width_px, box.x2)
    y2 = min(page.height_px, box.y2)
    return page.image.crop((x1, y1, x2, y2))


def collect_glyphs(pages: List[PageInfo]) -> Dict[str, List[Tuple[PageInfo, CharBox]]]:
    """Group all CharBoxes by character. Returns {char: [(page, box), ...]}."""
    glyphs: Dict[str, List[Tuple[PageInfo, CharBox]]] = {}
    for page in pages:
        for box in page.char_boxes:
            glyphs.setdefault(box.char, []).append((page, box))
    return glyphs


def pick_representative(instances: List[Tuple[PageInfo, CharBox]]) -> Tuple[PageInfo, CharBox]:
    """Choose the best instance of a character (largest bounding-box area)."""
    return max(instances, key=lambda t: (t[1].x2 - t[1].x1) * (t[1].y2 - t[1].y1))
