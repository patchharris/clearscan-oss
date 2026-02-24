"""
Assembles a PDF Type 3 font dictionary from vectorised glyph procedures,
using pikepdf.

Type 3 font coordinate convention used here:
  FontMatrix = [0.001 0 0 0.001 0 0]   (1000 glyph units = 1 user-space unit)
  Glyphs defined in a 1000-unit em-square.
  Advance width per glyph = EM * (w_px / h_px) glyph units.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pikepdf

EM = 1000.0

# Map printable-ASCII characters to Adobe standard glyph names.
_GLYPH_NAMES: Dict[str, str] = {
    ' ': 'space', '!': 'exclam', '"': 'quotedbl', '#': 'numbersign',
    '$': 'dollar', '%': 'percent', '&': 'ampersand', "'": 'quotesingle',
    '(': 'parenleft', ')': 'parenright', '*': 'asterisk', '+': 'plus',
    ',': 'comma', '-': 'hyphen', '.': 'period', '/': 'slash',
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
    ':': 'colon', ';': 'semicolon', '<': 'less', '=': 'equal', '>': 'greater',
    '?': 'question', '@': 'at',
    'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'E': 'E', 'F': 'F',
    'G': 'G', 'H': 'H', 'I': 'I', 'J': 'J', 'K': 'K', 'L': 'L',
    'M': 'M', 'N': 'N', 'O': 'O', 'P': 'P', 'Q': 'Q', 'R': 'R',
    'S': 'S', 'T': 'T', 'U': 'U', 'V': 'V', 'W': 'W', 'X': 'X',
    'Y': 'Y', 'Z': 'Z',
    '[': 'bracketleft', '\\': 'backslash', ']': 'bracketright',
    '^': 'asciicircum', '_': 'underscore', '`': 'grave',
    'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd', 'e': 'e', 'f': 'f',
    'g': 'g', 'h': 'h', 'i': 'i', 'j': 'j', 'k': 'k', 'l': 'l',
    'm': 'm', 'n': 'n', 'o': 'o', 'p': 'p', 'q': 'q', 'r': 'r',
    's': 's', 't': 't', 'u': 'u', 'v': 'v', 'w': 'w', 'x': 'x',
    'y': 'y', 'z': 'z',
    '{': 'braceleft', '|': 'bar', '}': 'braceright', '~': 'asciitilde',
}


def glyph_name(char: str) -> str:
    """Return the PDF glyph name for a character."""
    if char in _GLYPH_NAMES:
        return _GLYPH_NAMES[char]
    # Fall back to uniXXXX form
    return f"uni{ord(char):04X}"


def char_code(char: str) -> int:
    """Return the character code (byte value) to use for this character."""
    cp = ord(char)
    # Use direct byte for Latin-1 range; clamp others to avoid collisions
    return cp if cp <= 0xFF else (cp % 128 + 128)


def build_type3_font(
    char_glyphs: Dict[str, Tuple[float, str]],
    doc: pikepdf.Pdf,
) -> pikepdf.Object:
    """
    Build and return a pikepdf Type 3 font indirect object.

    Parameters
    ----------
    char_glyphs : {char: (advance_width_in_em, pdf_path_ops_string)}
        Only characters with successful vectorisation should be included.
    doc : pikepdf.Pdf
        The target PDF document (needed to create Stream objects).

    Returns
    -------
    pikepdf.Object (indirect reference to the font dictionary)
    """
    if not char_glyphs:
        raise ValueError("char_glyphs is empty")

    codes = sorted(char_code(c) for c in char_glyphs)
    first_char = codes[0]
    last_char = codes[-1]

    # Build CharProcs and Widths
    char_procs = pikepdf.Dictionary()
    widths: Dict[int, float] = {}

    for char, (adv, path_ops) in char_glyphs.items():
        code = char_code(char)
        adv_w = round(adv, 3)
        # d1 operator: wx wy llx lly urx ury d1
        glyph_stream_src = (
            f"{adv_w:.3f} 0 0 0 {adv_w:.3f} {EM:.3f} d1\n"
            f"{path_ops}\n"
        ).encode("latin-1")

        stream = pikepdf.Stream(doc, glyph_stream_src)
        name = pikepdf.Name(f"/{glyph_name(char)}")
        char_procs[name] = stream
        widths[code] = adv_w

    # Widths array: one entry per code from FirstChar to LastChar
    widths_array = pikepdf.Array([
        pikepdf.Real(widths.get(code, 0.0))
        for code in range(first_char, last_char + 1)
    ])

    # Encoding differences: map code → name
    differences: list = []
    prev_code: int | None = None
    for code in range(first_char, last_char + 1):
        # Find which char has this code
        matching = [c for c in char_glyphs if char_code(c) == code]
        if matching:
            if prev_code is None or code != prev_code + 1:
                differences.append(code)
            differences.append(pikepdf.Name(f"/{glyph_name(matching[0])}"))
            prev_code = code

    encoding = pikepdf.Dictionary(
        Type=pikepdf.Name("/Encoding"),
        Differences=pikepdf.Array(differences),
    )

    font_dict = pikepdf.Dictionary(
        Type=pikepdf.Name("/Font"),
        Subtype=pikepdf.Name("/Type3"),
        FontBBox=pikepdf.Array([
            pikepdf.Real(0), pikepdf.Real(0),
            pikepdf.Real(EM), pikepdf.Real(EM),
        ]),
        FontMatrix=pikepdf.Array([
            pikepdf.Real(0.001), pikepdf.Real(0),
            pikepdf.Real(0),     pikepdf.Real(0.001),
            pikepdf.Real(0),     pikepdf.Real(0),
        ]),
        FirstChar=first_char,
        LastChar=last_char,
        Widths=widths_array,
        Encoding=encoding,
        CharProcs=char_procs,
        Resources=pikepdf.Dictionary(),
    )

    return doc.make_indirect(font_dict)
