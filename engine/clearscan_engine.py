#!/usr/bin/env python3
"""
ClearScan OSS (production v0.5.4) — Smart OCR + compression

- Uses OCRmyPDF with --skip-text so born-digital PDFs are not OCR'd again.
- Scanned PDFs get OCR text layer + optimization.
- Mode 'best' uses deskew/clean/rotate.
- Auto-fallbacks:
  - if 'unpaper' missing, retry without --clean
  - if 'pngquant' missing (needed for --optimize 2/3), retry with --optimize 1
"""

import argparse
import subprocess
from pathlib import Path

def run_capture(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, (p.stdout or "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lang", type=str, default="eng")
    ap.add_argument("--mode", type=str, choices=["fast", "best"], default="best")
    ap.add_argument("--force-ocr", action="store_true")
    ap.add_argument("--output-type", type=str, default="pdf", choices=["pdf", "pdfa-2"])
    ap.add_argument("--optimize", type=str, default="3", choices=["0","1","2","3"])
    args = ap.parse_args()

    inp = args.pdf.resolve()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    base = ["ocrmypdf", "--optimize", args.optimize, "--jobs", "2", "--language", args.lang]
    if not args.force_ocr:
        base.append("--skip-text")

    if args.mode == "best":
        base += ["--deskew", "--clean", "--rotate-pages"]

    cmd = base + ["--output-type", args.output_type, str(inp), str(out)]
    rc, txt = run_capture(cmd)
    if rc == 0:
        return

    lower = txt.lower()

    # unpaper missing -> drop --clean
    if "--clean" in cmd and "unpaper" in lower and ("was not found" in lower or "could not find program" in lower or "could not be executed" in lower):
        cmd2 = [c for c in cmd if c != "--clean"]
        rc2, txt2 = run_capture(cmd2)
        if rc2 == 0:
            return
        cmd, txt, lower = cmd2, txt2, txt2.lower()

    # pngquant missing -> reduce optimize to 1
    if "--optimize" in cmd and "pngquant" in lower and ("was not found" in lower or "could not find program" in lower or "could not be executed" in lower):
        cmd3 = cmd[:]
        for i, tok in enumerate(cmd3):
            if tok == "--optimize" and i + 1 < len(cmd3):
                cmd3[i+1] = "1"
                break
        rc3, txt3 = run_capture(cmd3)
        if rc3 == 0:
            return
        txt = txt3

    raise RuntimeError(txt)

if __name__ == "__main__":
    main()
