#!/usr/bin/env python3
"""Render a 'וידויים של תלמידים' quote post from the PSD-derived template."""
import sys, os, re, json, argparse
from PIL import Image, ImageDraw, ImageFont

HERE   = os.path.dirname(os.path.abspath(__file__))
# assets/ sits beside this file in the bot bundle, and one level up in the skill
# layout; resolve rather than assume so the same file works in both.
# Also accept a flat layout (everything in one directory), because GitHub's web
# uploader cannot create folders from a phone.
ASSETS = next((c for c in (os.path.join(HERE, 'assets'),
                           os.path.join(os.path.dirname(HERE), 'assets'),
                           HERE)
               if os.path.isfile(os.path.join(c, 'template_plate.webp'))), HERE)
PLATE  = os.path.join(ASSETS, 'template_plate.webp')
FONT   = os.path.join(ASSETS, 'RubikBold-subset.ttf')

COLOR      = (29, 79, 120)
RIGHT_EDGE = 1900          # absolute x of the text column's right edge
CENTER_Y   = 950           # y the block prefers to centre on (lowered from the design 847)
MAX_W      = 1820          # max ink width; the gap to RIGHT_EDGE is the left margin
CENTER_X   = RIGHT_EDGE - MAX_W // 2   # 990: the text column's horizontal midpoint

# Two independent knobs. LINE_ALIGN is how the lines sit relative to each other;
# BLOCK_X is where the resulting block sits on the canvas. The default -- lines
# sharing a right edge, block centred -- is not the same as either extreme:
# right-aligned lines pinned right leave a growing hole on the left as the text
# gets shorter, and centred lines lose the common right edge that makes a block
# read as Hebrew.
LINE_ALIGN = 'right'       # 'right' (default) or 'center'
BLOCK_X    = 'center'      # 'center' (default) or 'right'
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


def drop_unsupported(text, font_path):
    """Remove codepoints the bundled font has no glyph for.

    The font is subsetted to Hebrew, Latin, digits and punctuation, so emoji and
    other exotic characters would otherwise render as empty .notdef boxes. Silently
    dropping them looks far better in a finished post than a row of tofu squares.
    """
    try:
        from fontTools.ttLib import TTFont
        cmap = TTFont(font_path, fontNumber=0, lazy=True).getBestCmap()
    except Exception:
        return text
    keep = []
    for ch in text:
        if ch in '\n\r\t' or ord(ch) in cmap:
            keep.append(ch)
    out = ''.join(keep)
    return re.sub(r'[ \t]{2,}', ' ', out)


def ink_w(font, s):
    bb = font.getbbox(s, direction='rtl', language='he')
    return bb[2] - bb[0]


def layout(text, quotes=True, align=None, block_x=None):
    """Pick the largest font size at which the text fits, return (font, lines, size).

    Explicit newlines in the input are treated as hard line breaks and are never
    re-flowed; only the font size shrinks until those lines fit. Text with no
    newlines is word-wrapped.

    The fit test must use the same alignment and block placement the final
    render will use, or the chosen size can be one that does not actually clear
    the avatar once placed.
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
        ink = compose(lines, font, size, align)
        if place(ink, block_x) is not None:
            return font, lines, size

    font = ImageFont.truetype(FONT, MIN_SIZE)
    lines = wrap(body, font, MAX_W)                      # last resort: force a re-flow
    return font, lines, MIN_SIZE


def compose(lines, font, size, align=None):
    """Draw the block on a scratch layer and return its cropped ink.

    With align='right' the lines share a common right edge; with 'center' each
    is centred on a shared axis. Only the anchor changes -- the RTL shaping is
    identical either way, so the block is still laid out right-to-left
    internally and only its ragged edge moves.

    The returned ink is cropped to its bounding box, which is what lets place()
    centre the *block* independently of how the lines are aligned inside it.
    """
    align = align or LINE_ALIGN
    pad = 400
    scratch = Image.new('L', (MAX_W + pad * 2, len(lines) * size + pad * 2), 0)
    d = ImageDraw.Draw(scratch)
    right = MAX_W + pad
    axis = pad + MAX_W // 2
    for i, line in enumerate(lines):
        if align == 'center':
            d.text((axis, pad + i * size), line, font=font, fill=255,
                   anchor='ms', direction='rtl', language='he')
        else:
            d.text((right, pad + i * size), line, font=font, fill=255,
                   anchor='rs', direction='rtl', language='he')
    bbox = scratch.getbbox()
    if bbox is None:
        raise SystemExit('nothing rendered')
    return scratch.crop(bbox)


def place(ink, block_x=None):
    """Return (x, y) for this ink block, or None if it cannot fit.

    block_x='center' centres the block's ink on CENTER_X; 'right' pins its right
    edge to RIGHT_EDGE. This is deliberately independent of how the lines are
    aligned within the block -- the default is right-aligned lines in a centred
    block, so the ragged edge is on the left while the mass sits mid-frame.

    The clearance is checked row by row rather than against the block's overall
    width. Because the lines are ragged, the lower ones are often shorter than
    the widest, and a short row can legitimately sit beside the avatar where a
    full-width row could not. Judging the whole block by its widest line would
    throw away exactly the space at the bottom of the design that is most usable.

    Centring the block shifts every row left by half the block's slack, so the
    lookup must be done against the placed x -- not against RIGHT_EDGE minus the
    row width, which was equivalent only while blocks were pinned right.
    """
    block_x = block_x or BLOCK_X
    x = CENTER_X - ink.width // 2 if block_x == 'center' else RIGHT_EDGE - ink.width
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


def render(text, out_path, quotes=True, export_px=1080, align=None, block_x=None):
    align = align or LINE_ALIGN
    block_x = block_x or BLOCK_X
    plate = Image.open(PLATE).convert('RGB')
    font, lines, size = layout(text, quotes, align, block_x)
    ink = compose(lines, font, size, align)
    fallback_x = CENTER_X - ink.width // 2 if block_x == 'center' else RIGHT_EDGE - ink.width
    pos = place(ink, block_x) or (fallback_x, TOP_LIMIT)
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
    ap.add_argument('--align', choices=('right', 'center'), default=LINE_ALIGN,
                    help='how lines align to each other (default right)')
    ap.add_argument('--block', choices=('center', 'right'), default=BLOCK_X,
                    help='where the block sits on the canvas (default center)')
    a = ap.parse_args()
    txt = open(a.file, encoding='utf-8').read() if a.file else (a.text or '').replace('\\n', '\n')
    if not txt.strip():
        ap.error('need --text or --file')
    p, s, n = render(txt, a.out, quotes=not a.no_quotes, export_px=a.px,
                     align=a.align, block_x=a.block)
    print(f'{p}  (font {s}pt, {n} lines)')
