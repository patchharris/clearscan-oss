#!/usr/bin/env python3
"""
VectorScan engine — ClearScan-style vectorised font pipeline.

Pipeline
--------
1. PyMuPDF   : render each PDF page to a 300 DPI raster image.
2. Tesseract : extract per-character bounding boxes (image_to_boxes).
3. VTracer / potrace : rasterised glyph crop → SVG vector path.
4. Custom converter  : SVG path commands → PDF Type 3 charstring operators.
5. pikepdf   : assemble Type 3 font dict + overlay onto the original PDF.

The output PDF retains the original page content (raster scan background) but
adds an overlay content stream where each recognised character's bounding box
is white-filled and then re-drawn using a vectorised Type 3 font glyph.

Falls back to standard ocrmypdf if the vector pipeline fails entirely.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run_ocrmypdf_fallback(args: argparse.Namespace) -> None:
    """Last-resort fallback: run the original clearscan_engine.py."""
    engine = Path(__file__).resolve().parent / "clearscan_engine.py"
    cmd = [
        sys.executable, str(engine),
        str(args.pdf),
        "--out", str(args.out),
        "--lang", args.lang,
        "--mode", args.mode,
        "--output-type", args.output_type,
        "--optimize", args.optimize,
    ]
    if args.force_ocr:
        cmd.append("--force-ocr")
    rc = subprocess.call(cmd)
    if rc != 0:
        raise RuntimeError(f"ocrmypdf fallback failed with exit code {rc}")


def process(args: argparse.Namespace) -> None:
    try:
        import fitz        # PyMuPDF
        import pikepdf
        import pytesseract
    except ImportError as exc:
        print(f"[vectorscan] missing dependency ({exc}), falling back to ocrmypdf", file=sys.stderr)
        _run_ocrmypdf_fallback(args)
        return

    # Add engine dir to path so glyph_pipeline is importable
    engine_dir = Path(__file__).resolve().parent
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    from glyph_pipeline import extractor, vectorizer, type3_font, pdf_builder

    inp = args.pdf.resolve()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    print("[vectorscan] rendering pages…", file=sys.stderr)
    pages = extractor.render_pages(inp, dpi=300)

    print(f"[vectorscan] {len(pages)} page(s) — running Tesseract…", file=sys.stderr)
    for page in pages:
        extractor.extract_char_boxes(page, lang=args.lang)
        total = len(page.char_boxes)
        print(f"  page {page.page_idx}: {total} character box(es)", file=sys.stderr)

    # Collect unique characters and vectorise a representative glyph for each
    glyphs = extractor.collect_glyphs(pages)
    print(f"[vectorscan] {len(glyphs)} unique character(s) to vectorise…", file=sys.stderr)

    char_glyphs: dict[str, tuple[float, str]] = {}
    failed = 0
    for char, instances in glyphs.items():
        page, box = extractor.pick_representative(instances)
        img = extractor.crop_glyph(page, box)
        w_px = box.x2 - box.x1
        h_px = box.y2 - box.y1
        pdf_ops = vectorizer.glyph_to_pdf_ops(img)
        if pdf_ops:
            adv = vectorizer.advance_width(w_px, h_px)
            char_glyphs[char] = (adv, pdf_ops)
        else:
            failed += 1

    print(
        f"[vectorscan] vectorised {len(char_glyphs)}/{len(glyphs)} glyphs "
        f"({failed} failed)", file=sys.stderr
    )

    if not char_glyphs:
        print("[vectorscan] no glyphs vectorised — falling back to ocrmypdf", file=sys.stderr)
        _run_ocrmypdf_fallback(args)
        return

    print("[vectorscan] building Type 3 font…", file=sys.stderr)
    doc = pikepdf.open(str(inp))
    font_obj = type3_font.build_type3_font(char_glyphs, doc)

    print("[vectorscan] overlaying vector text layer…", file=sys.stderr)
    pdf_builder.overlay_type3_text(doc, pages, char_glyphs, font_obj)

    pdf_builder.save(doc, out)
    print("[vectorscan] complete.", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="VectorScan: ClearScan-style vectorised font engine")
    ap.add_argument("pdf", type=Path, help="Input PDF")
    ap.add_argument("--out", type=Path, required=True, help="Output PDF")
    ap.add_argument("--lang", type=str, default="eng", help="Tesseract language code(s)")
    ap.add_argument("--mode", type=str, choices=["fast", "best"], default="best")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--output-type", type=str, default="pdf", choices=["pdf", "pdfa-2"])
    ap.add_argument("--optimize", type=str, default="3", choices=["0", "1", "2", "3"])
    args = ap.parse_args()
    process(args)


if __name__ == "__main__":
    main()
