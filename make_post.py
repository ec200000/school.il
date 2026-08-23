#!/usr/bin/env python3
"""Render a 'וידויים של תלמידים' quote post from the PSD-derived template."""
import sys, os, re, json, argparse
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

# The three assets live in two different layouts and this file is shared by
# both: beside the script in the flat GitHub repo, and in a sibling assets/
# directory in the skill. Probing for the plate rather than assuming one layout
# means copying this file between them cannot silently break the other.
_CANDIDATES = [
    HERE,                                          # flat: repo root
    os.path.join(os.path.dirname(HERE), 'assets'),  # skill: scripts/ + assets/
    os.path.join(HERE, 'assets'),                   # assets/ underneath
]
ASSETS = next(
    (d for d in _CANDIDATES if os.path.exists(os.path.join(d, 'template_plate.webp'))),
    HERE,
)
PLATE  = os.path.join(ASSETS, 'template_plate.webp')
FONT   = os.path.join(ASSETS, 'RubikBold-subset.ttf')

COLOR      = (29, 79, 120)
RIGHT_EDGE = 1900          # absolute x of the text block's right ink edge
CENTER_Y   = 950           # y the block prefers to centre on (lowered from the design 847)
MAX_W      = 1820          # max ink width; the gap to RIGHT_EDGE is the left margin
TOP_LIMIT  = 300           # first ink may not rise above this (clears the title)
CLEARANCE  = 8             # gap kept above the wave/avatar
BASE_SIZE  = 140
MIN_SIZE   = 60

# safe_bottom[left_x] = lowest y the text may occupy when its ink spans
# [left_x, RIGHT_EDGE]. Precomputed from the alpha of the wave, the avatar and
# the footer, so a narrow block is allowed to sit lower than a wide one -- the
# wave curves down to the right, and the avatar only blocks the left third.
with open(os.path.join(ASSETS, 'safe_bottom.json'), encoding='utf-8') as _f:
    SAFE_BOTTOM = json.load(_f)


OPEN_Q, CLOSE_Q = '“', '”'


def wrap(text, font, max_w):
    """Greedy word-wrap on ink width; respects explicit newlines."""
    out = []
    for para in text.split('\n'):
        words, line = para.split(), ''
        for w in words:
            trial = (line + ' ' + w).strip()
            bb = font.getbbox(trial, direction='rtl', language='he')
            if bb[2] - bb[0] <= max_w or not line:
                line = trial
            else:
                out.append(line); line = w
        if line:
            out.append(line)
    return out or ['']


# Quote marks the subset font cannot draw, folded onto ones it can. Kept in step
# with QUOTE_MAP in Code.gs, so text approved in Telegram is character-for-
# character what gets drawn.
#
# The curly quotes “ ” ‘ ’ all have glyphs and are deliberately NOT in this map --
# they pass through untouched. Only the forms with no glyph are folded, because
# an unmapped missing glyph is dropped silently: של״ח would reach Instagram
# reading שלח, which looks like a spelling mistake rather than a bug.
SUBSTITUTES = {
    '״': '"',      # gershayim -- Hebrew acronyms: של״ח, ארה״ב
    '׳': "'",      # geresh
    '„': '“',     # low double
    '‚': '‘',     # low single
    '‟': '“',     # reversed double
    '‛': '‘',     # reversed single
    '«': '“', '»': '”',
    '‹': '‘', '›': '’',
    '″': '"',      # double prime
    '′': "'",      # prime
    '–': '—',
    ' ': ' ',
}


def drop_unsupported(text, font_path):
    """Remove codepoints the bundled font has no glyph for.

    The font is subsetted to Hebrew, Latin, digits and punctuation, so emoji and
    other exotic characters would otherwise render as empty .notdef boxes. Silently
    dropping them looks far better in a finished post than a row of tofu squares.

    Anything in SUBSTITUTES is swapped for a supported equivalent first, so a
    missing glyph that carries meaning is preserved rather than deleted.
    """
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(font_path, fontNumber=0, lazy=True).getBestCmap()
    except Exception:
        return text
    text = ''.join(
        SUBSTITUTES[ch] if ch in SUBSTITUTES and ord(ch) not in cmap else ch
        for ch in text
    )
    keep = []
    for ch in text:
        if ch in '\n\r\t' or ord(ch) in cmap:
            keep.append(ch)
    out = ''.join(keep)
    return re.sub(r'[ \t]{2,}', ' ', out)


def ink_w(font, s):
    bb = font.getbbox(s, direction='rtl', language='he')
    return bb[2] - bb[0]


def layout(text, quotes=True):
    """Pick the largest font size at which the text fits, return (font, lines, size).

    Explicit newlines in the input are treated as hard line breaks and are never
    re-flowed; only the font size shrinks until those lines fit. Text with no
    newlines is word-wrapped.
    """
    body = drop_unsupported(text, FONT).strip()
    hard = '\n' in body
    if quotes:
        body = OPEN_Q + body + CLOSE_Q

    for size in range(BASE_SIZE, MIN_SIZE - 1, -2):
        font = ImageFont.truetype(FONT, size)
        lines = [l.strip() for l in body.split('\n')] if hard else wrap(body, font, MAX_W)
        if max(ink_w(font, l) for l in lines) > MAX_W:
            continue
        ink = compose(lines, font, size)
        if place(ink) is not None:
            return font, lines, size

    font = ImageFont.truetype(FONT, MIN_SIZE)
    lines = wrap(body, font, MAX_W)                      # last resort: force a re-flow
    return font, lines, MIN_SIZE


def compose(lines, font, size):
    """Draw the block on a scratch layer and return its cropped ink."""
    pad = 400
    scratch = Image.new('L', (MAX_W + pad * 2, len(lines) * size + pad * 2), 0)
    d = ImageDraw.Draw(scratch)
    right = MAX_W + pad
    for i, line in enumerate(lines):
        d.text((right, pad + i * size), line, font=font, fill=255,
               anchor='rs', direction='rtl', language='he')
    bbox = scratch.getbbox()
    if bbox is None:
        raise SystemExit('nothing rendered')
    return scratch.crop(bbox)


def place(ink):
    """Return (x, y) for this ink block, or None if it cannot fit.

    The clearance is checked row by row rather than against the block's overall
    width. Because the text is right-aligned, its lower lines are often shorter
    than its widest one, and a short row can legitimately sit beside the avatar
    where a full-width row could not. Judging the whole block by its widest line
    would throw away exactly the space at the bottom of the design that is most
    usable.
    """
    x = RIGHT_EDGE - ink.width
    px = ink.load()
    limit = None
    for row in range(ink.height):
        left = None
        for col in range(ink.width):
            if px[col, row]:
                left = col
                break
        if left is None:
            continue
        allowed = SAFE_BOTTOM[max(0, min(len(SAFE_BOTTOM) - 1, x + left))] - CLEARANCE - row
        limit = allowed if limit is None else min(limit, allowed)
    if limit is None:
        limit = SAFE_BOTTOM[-1]

    y = min(CENTER_Y - ink.height // 2, limit)           # prefer the design's centre
    return None if y < TOP_LIMIT else (x, y)


def render(text, out_path, quotes=True, export_px=1080):
    plate = Image.open(PLATE).convert('RGB')
    font, lines, size = layout(text, quotes)
    ink = compose(lines, font, size)
    pos = place(ink) or (RIGHT_EDGE - ink.width, TOP_LIMIT)
    colored = Image.new('RGB', ink.size, COLOR)
    plate.paste(colored, pos, ink)
    if out_path.lower().endswith(('.jpg', '.jpeg')):
        plate.resize((export_px, export_px), Image.LANCZOS).save(
            out_path, quality=88, optimize=True, progressive=True)
    else:
        plate.save(out_path)
    return out_path, size, len(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('-t', '--text', help='quote text; \\n for explicit line breaks')
    ap.add_argument('-f', '--file', help='read quote text from a file')
    ap.add_argument('-o', '--out', default='post.png')
    ap.add_argument('--no-quotes', action='store_true', help='do not add curly quote marks')
    ap.add_argument('--px', type=int, default=1080, help='export size for .jpg output (default 1080)')
    a = ap.parse_args()
    txt = open(a.file, encoding='utf-8').read() if a.file else (a.text or '').replace('\\n', '\n')
    if not txt.strip():
        ap.error('need --text or --file')
    p, s, n = render(txt, a.out, quotes=not a.no_quotes, export_px=a.px)
    print(f'{p}  (font {s}pt, {n} lines)')
