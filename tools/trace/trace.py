"""Trace the siddur's letters from photos into outlines (tools/trace/glyphs.json).

For each letter in picks.json: take its ink component(s) from the photo (plus legs that print as
separate pieces, e.g. ה), measure the line's baseline and letter-body height from the neighbouring
letters, upsample 4x, threshold and vectorise with potrace. Coordinates are written in units where
the baseline is y=0 and the letter body (top line to baseline) is 1000 high. The printed tagin are
separated from the letters: the build redraws them crisply at `tag_x` (they print too thin to trace).

Usage: python trace.py <photo-dir> [sheet.png]      (needs numpy, scikit-image, pillow, potracer)
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from skimage.filters import threshold_sauvola, threshold_otsu
from skimage.measure import label, regionprops
from scipy.ndimage import binary_dilation
import potrace

HERE = Path(__file__).parent
UP = 4


def load(photo_dir, n, cache={}):
    if n not in cache:
        g = np.asarray(Image.open(Path(photo_dir) / f'p{n}.jpg').convert('L'), dtype=float) / 255
        ink = g < threshold_sauvola(g, window_size=151, k=0.2) - 0.04
        lab = label(ink, connectivity=2)
        cache[n] = (g, lab, {p.label: p for p in regionprops(lab)})
    return cache[n]


def line_metrics(g, lab, main):
    """Top line and baseline (px) of the line `main` sits on, from the row density of ink across
    the line: the heads and bases of the letters are the densest rows; tagin, ascenders, descenders
    and nikud are thin."""
    y0, x0, y1, x1 = main.bbox
    xa, xb = max(0, x0 - 900), min(lab.shape[1], x1 + 900)
    ya, yb = max(0, y0 - 40), min(lab.shape[0], y1 + 40)
    prof = (lab[ya:yb, xa:xb] > 0).sum(axis=1).astype(float)
    prof = np.convolve(prof, np.ones(5) / 5, mode='same')
    top = ya + np.nonzero(prof > 0.5 * prof.max())[0][0]
    # baseline: the median bottom of the big letters on the line (descenders are the minority)
    near = [p for p in regionprops(lab[ya:yb, xa:xb]) if p.area > 1500 and y0 - ya <= (p.bbox[0] + p.bbox[2]) / 2 <= y1 - ya]
    base = ya + float(np.median([p.bbox[2] for p in near]))
    return base, float(base - top)


def extract(g, lab, props, labels):
    main = props[labels[0]]
    base, body = line_metrics(g, lab, main)
    sel = list(labels)
    y0, x0, y1, x1 = main.bbox
    for p in props.values():                          # separate legs (ה, ק …): tall pieces under the letter
        py0, px0, py1, px1 = p.bbox
        if p.label not in sel and px0 >= x0 - 6 and px1 <= x1 + 6 and py0 >= y0 - 6 and py1 <= y1 + 0.7 * body \
                and (py1 - py0) > 0.3 * body:
            sel.append(p.label)
    boxes = [props[l].bbox for l in sel]
    Y0, X0 = min(b[0] for b in boxes) - 8, min(b[1] for b in boxes) - 8
    Y1, X1 = max(b[2] for b in boxes) + 8, max(b[3] for b in boxes) + 8
    mask = binary_dilation(np.isin(lab[Y0:Y1, X0:X1], sel), iterations=3)
    crop = g[Y0:Y1, X0:X1]
    big = np.asarray(Image.fromarray((crop * 255).astype(np.uint8)).resize(
        ((X1 - X0) * UP, (Y1 - Y0) * UP), Image.LANCZOS), dtype=float) / 255
    bigmask = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(big.shape[::-1], Image.NEAREST)) > 0
    from scipy.ndimage import gaussian_filter, binary_opening, binary_closing
    big = gaussian_filter(big, sigma=0.009 * body * UP)          # smooth away paper grain
    t = threshold_otsu(big[bigmask]) if bigmask.any() else threshold_otsu(big)
    ink = (big < t) & bigmask
    ink = binary_closing(binary_opening(ink, iterations=3), iterations=3)   # tagin are redrawn, so smooth freely
    from skimage.morphology import remove_small_holes
    ink = remove_small_holes(ink, max_size=int((0.08 * body * UP) ** 2))  # paper grain inside strokes
    return ink, (X0, Y0), base, body


# letters that hang below the baseline (ע's tail dips a little), or (י) stop above it: their baseline comes from the line
LINE_BASE = set('ךןץקףיע')
# letters that rise above the top line (ל): their top comes from the line
LINE_TOP = set('ל')
NARROW = set('וזןינג')


def own_metrics(ch, ink, origin, base, body):
    """Measure the letter's own top line and baseline so every letter gets exactly the same body
    height (line measurements vary a little between lines and photos)."""
    X0, Y0 = origin
    top = (base - body - Y0) * UP                    # upsampled px, from the line
    bot = (base - Y0) * UP
    rows = np.nonzero(ink.any(axis=1))[0]
    width = ink.sum(axis=1)
    if ch not in LINE_TOP:
        # the head: first row (below any tagin) whose ink is wider than a third of the letter
        # (a solid band at least 10% of the body tall — the round tag balls are shorter)
        # narrow letters: the head is the widest part, so only it passes; wide letters: a third
        wide = width > (0.7 if ch in NARROW else 0.4) * width.max()
        need = int(0.1 * body * UP)
        for r in np.nonzero(wide)[0]:
            if wide[r:r + need].all():
                top = r
                break
    if ch not in LINE_BASE:
        bot = rows[-1]
    return Y0 + bot / UP, (bot - top) / UP


TRIPLE = set('שעטנזגצץן')
SINGLE = set('בדקחיה')


def split_tagin(ch, ink, origin, base, body):
    """Separate the printed tagin from the letter: the thin stems are removed by a morphological
    opening, the balls then float free above the head and are dropped. The letter keeps its heads
    exactly as printed (e.g. ט's sloping head). Returns (body_ink, tag_x): tag_x is where the tagin
    stand, in px of the crop — for a cluster of three, the centre of the head block beneath it
    (the siddur centres the cluster on its head); for a single tag, the stem itself."""
    from scipy.ndimage import binary_opening, binary_dilation, label as nd_label
    from skimage.morphology import disk
    if ch not in TRIPLE | SINGLE:
        return ink, None
    X0, Y0 = origin
    top = int(round((base - body - Y0) * UP))         # head line, px in the crop
    r = max(2, int(0.035 * body * UP))               # wider than a stem, narrower than a head
    opened = binary_opening(ink, structure=disk(r))
    lab, n = nd_label(opened)
    keep = np.zeros_like(ink)
    for i in range(1, n + 1):
        ys = np.nonzero((lab == i).any(axis=1))[0]
        if ys[-1] > top + 0.12 * body * UP:          # reaches down into the letter: body, not a ball
            keep |= lab == i
    body_ink = ink & binary_dilation(keep, structure=disk(3))      # (tight: no stubs of the old stems)
    body_ink[top + int(0.04 * body * UP):] = ink[top + int(0.04 * body * UP):]   # below the head line: untouched
    tags = ink & ~body_ink
    tags[top + int(0.05 * body * UP):] = False       # (only what stands above the head)
    ty, tx = np.nonzero(tags)
    if len(tx) == 0:
        return body_ink, None
    if ch in SINGLE:
        stem_rows = ty > ty.min() + 0.5 * (ty.max() - ty.min())
        x = float(np.median(tx[stem_rows]))
        w = int(0.14 * body * UP)
        return straighten_top(body_ink, int(x) - w, int(x) + w, top, body), x
    guess = float(np.median(tx))
    band = body_ink[top:top + int(0.12 * body * UP)]
    blab, bn = nd_label(band)
    best = None
    for i in range(1, bn + 1):
        xs = np.nonzero((blab == i).any(axis=0))[0]
        d = 0 if xs[0] <= guess <= xs[-1] else min(abs(xs[0] - guess), abs(xs[-1] - guess))
        if best is None or d < best[0]:
            best = (d, (xs[0] + xs[-1]) / 2, (int(xs[0]), int(xs[-1])))
    if not best:
        return body_ink, guess
    x0b, x1b = best[2]
    return straighten_top(body_ink, x0b, x1b, top, body), float(best[1])


def straighten_top(ink, xa, xb, top, body):
    """Give the head between columns xa..xb a clean straight top edge through its two ends (keeping
    any slope, as on ט), removing the stubs left where the printed stems were cut off."""
    xa, xb = max(0, xa), min(ink.shape[1] - 1, xb)
    lim = top + int(0.25 * body * UP)
    tops = np.array([np.argmax(ink[:lim, x]) if ink[:lim, x].any() else -1 for x in range(xa, xb + 1)])
    ok = tops >= 0
    if ok.sum() < 6:
        return ink
    xs = np.arange(xa, xb + 1)[ok]
    ys = tops[ok]
    flat = np.abs(ys - np.median(ys)) < 0.06 * body * UP   # drop rounded corners and the letter's edges
    xs, ys = xs[flat], ys[flat]
    if len(xs) < 6:
        return ink
    e = max(2, len(xs) // 6)                         # the outer sixth at each end: clear of the stems
    ends = np.r_[0:e, len(xs) - e:len(xs)]
    k, c = np.polyfit(xs[ends], ys[ends], 1)
    out = ink.copy()
    for x, y in zip(xs, ys):
        line = int(round(k * x + c))
        out[:line, x] = False
        out[line:max(line, y) + 1, x] = True        # (fill small dents too)
    return out


def vectorise(ink, origin, base, body):
    """potrace → contours in body units (y up, baseline 0, body height 1000)."""
    X0, Y0 = origin
    s = 1000 / (body * UP)
    def P(pt):
        x, y = (pt.x, pt.y) if hasattr(pt, "x") else pt
        return [round(x * s, 1), round((base - Y0) * 1000 / body - y * s, 1)]
    paths = potrace.Bitmap(~ink).trace(                  # potracer fills the False pixels
        turdsize=300, alphamax=1.1, opticurve=True, opttolerance=0.8)
    out = []
    for curve in paths:
        segs = [['M', P(curve.start_point)]]
        for sg in curve.segments:
            if sg.is_corner:
                segs.append(['L', P(sg.c)]); segs.append(['L', P(sg.end_point)])
            else:
                segs.append(['C', P(sg.c1), P(sg.c2), P(sg.end_point)])
        out.append(segs)
    return out


def main():
    photo_dir = sys.argv[1]
    picks = {k: v for k, v in json.loads((HERE / 'picks.json').read_text()).items() if not k.startswith('_')}
    glyphs, tiles = {}, []
    for ch, (n, labels) in picks.items():
        g, lab, props = load(photo_dir, n)
        ink, origin, base, body = extract(g, lab, props, labels)
        base, body = own_metrics(ch, ink, origin, base, body)
        ink, tag_x = split_tagin(ch, ink, origin, base, body)
        glyphs[ch] = {'outline': vectorise(ink, origin, base, body)}
        if tag_x is not None:
            glyphs[ch]['tag_x'] = round(tag_x * 1000 / (body * UP), 1)   # same units as the outline
        tile = Image.fromarray(((~ink) * 255).astype(np.uint8)).convert('RGB')
        d = ImageDraw.Draw(tile)
        by = (base - origin[1]) * UP
        d.line([(0, by), (tile.width, by)], fill=(255, 0, 0), width=3)
        d.line([(0, by - body * UP), (tile.width, by - body * UP)], fill=(0, 160, 0), width=3)
        tiles.append((ch, tile))
    (HERE / 'glyphs.json').write_text(json.dumps(glyphs, ensure_ascii=False))
    if len(sys.argv) > 2:                             # contact sheet for checking the picks
        th = 360
        tiles = [(c, t.resize((max(1, int(t.width * th / t.height)), th))) for c, t in tiles]
        W = 2400
        rows, row, x = [], [], 0
        for c, t in tiles:
            if x + t.width + 20 > W:
                rows.append(row); row, x = [], 0
            row.append(t); x += t.width + 20
        rows.append(row)
        sheet = Image.new('RGB', (W, len(rows) * (th + 20)), 'white')
        for i, r in enumerate(rows):
            x = W - 10
            for t in r:
                x -= t.width; sheet.paste(t, (x, i * (th + 20))); x -= 20
        sheet.save(sys.argv[2])
    print(len(glyphs), 'glyphs')


main()
