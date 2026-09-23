"""Build the app's fonts from Culmus (+ the Schwarz Ari font).

1. "Stam Siddur": Culmus Stam Ashkenaz with its tagin redrawn like the user's siddur — hair-thin
   straight stems with large round balls: three on שעטנ"ז ג"ץ (middle one tallest), one on בד"ק י"ה,
   ח rebuilt as two ז halves joined by a pointed peak with one tag, and ל redrawn with the siddur's
   short neck and curved tail (all traced from photos of the siddur).
2. Nikud for the STAM fonts: Frank Ruehl CLM's vowel glyphs are copied in and GPOS mark positioning
   is rebuilt — each Frank anchor is mapped onto the matching STAM letter by bounding box.
3. Every font gets three private-use pieces of ה for the siddur's stretched ה in שם הוי"ה:
   U+E000 right part (roof + stem), U+E001 left end (roof end + leg), U+E002 a 3-em roof bar.

Usage:  python tools/build-fonts.py <culmus-dir> <SchwarzStamAri.ttf>
Needs fonttools, skia-pathops and brotli (tools/requirements.txt). Writes fonts/*.woff2.
"""
import sys, unicodedata
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.subset import Subsetter, Options
import pathops

MARKS = [*range(0x05B0, 0x05BE), 0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7]
SPACING = [0x05BE, 0x05C3, 0x05F3, 0x05F4]
BASES = [*range(0x05D0, 0x05EB), *range(0xFB1D, 0xFB50)]
# תגים: 3 on שעטנ"ז ג"ץ, 1 on בדק חיה, none on מלאכת סופר
TRIPLE_TAGIN = 'שעטנןזגצץ'
SINGLE_TAG = 'בדקיה'
OUT = Path(__file__).resolve().parent.parent / 'fonts'
UNICODES = [*range(0x20, 0x7F), 0xA0, *range(0x05B0, 0x05C8), *range(0x05D0, 0x05F5), *range(0x2010, 0x2028),
            0x25CC, *range(0xFB1D, 0xFB50), 0xE000, 0xE001, 0xE002]


# ── outline helpers ──
def bounds(font, name):
    gs = font.getGlyphSet()
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    return bp.bounds


def glyph_path(font, name):
    p = pathops.Path()
    font.getGlyphSet()[name].draw(p.getPen())
    return p


def rect(x0, y0, x1, y1):
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return p


def circle(cx, cy, r):
    k = 0.5523 * r
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo((cx + r, cy))
    pen.curveTo((cx + r, cy + k), (cx + k, cy + r), (cx, cy + r))
    pen.curveTo((cx - k, cy + r), (cx - r, cy + k), (cx - r, cy))
    pen.curveTo((cx - r, cy - k), (cx - k, cy - r), (cx, cy - r))
    pen.curveTo((cx + k, cy - r), (cx + r, cy - k), (cx + r, cy))
    pen.closePath()
    return p


def op(a, b, kind):
    return pathops.op(a, b, kind, fix_winding=True, keep_starting_points=False)


def components(path):
    """Each contour of a path as its own path."""
    out = []
    for c in path.contours:
        p = pathops.Path()
        c.draw(p.getPen())
        out.append(p)
    return out


def set_glyph(font, name, path, advance, dx=0):
    """Write a pathops path into a glyf font as `name` (adding the glyph if new)."""
    pen = TTGlyphPen(None)
    target = Cu2QuPen(pen, max_err=1, reverse_direction=False)
    path.draw(TransformPen(target, (1, 0, 0, 1, dx, 0)) if dx else target)
    glyf = font['glyf']
    glyf[name] = pen.glyph()
    order = font.getGlyphOrder()
    if name not in order:
        font.setGlyphOrder(order + [name])
    glyf[name].recalcBounds(glyf)
    font['hmtx'][name] = (round(advance), getattr(glyf[name], 'xMin', 0))


def smooth_path(points, closed=True):
    """A closed outline through `points` (Catmull-Rom → cubic Béziers); points marked with a
    trailing True are corners (straight in and out)."""
    pts = [(p[0], p[1]) for p in points]
    corner = [len(p) > 2 and p[2] for p in points]
    n = len(pts)
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        if corner[i] or corner[(i + 1) % n]:
            pen.lineTo(p2)
            continue
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        pen.curveTo(c1, c2, p2)
    pen.closePath()
    return path


def siddur_lamed(T, body_top):
    """ל as the siddur draws it: a thick top bar whose right end curves down into a tail that
    sweeps down-left to a point on the baseline, and a short thin neck with a block head.
    Coordinates traced from a photo (letter body = 1050 units high)."""
    k = body_top / 1050
    P = lambda *pts: [(x * k, y * k, *c) for x, y, *c in pts]
    bar = rect(201 * k, 799 * k, 900 * k, body_top)
    neck = rect(197 * k, body_top - 20, 272 * k, 1440 * k)
    head = smooth_path(P((60, 1677, True), (101, 1732, True), (311, 1640, True), (311, 1426, True),
                         (195, 1410, True), (60, 1448, True)))
    # right end of the bar with a rounded shoulder, dropping nearly straight, then sweeping left to a point
    tail = smooth_path(P((780, 1050, True), (930, 1048), (995, 1000), (1010, 900), (1005, 760), (975, 600),
                         (915, 440), (820, 290), (690, 140), (499, -6, True),
                         (575, 150), (665, 310), (730, 480), (765, 640), (781, 799, True)))
    g = bar
    for part in (neck, head, tail):
        g = op(g, part, pathops.PathOp.UNION)
    name = T.getBestCmap()[ord('ל')]
    set_glyph(T, name, g, 1070 * k)


# ── 1. straight, ball-topped tagin ──
def straight_tagin(T):
    cm = T.getBestCmap()
    upm = T['head'].unitsPerEm
    body_top = bounds(T, cm[ord('כ')])[3]            # כ has no tagin: its top is the letters' top line
    cut = body_top                                  # heads cut flat at the letter line, like the siddur's
    # proportions measured from photos of the siddur (letter body ≈ 0.52 em)
    stem_w, ball_r = 0.015 * upm, 0.029 * upm
    outer_h, middle_h = 0.118 * upm, 0.205 * upm
    spacing = 0.074 * upm
    head_w, head_h = 0.2 * upm, 0.15 * upm           # the siddur's square head blocks

    def tag(x, h, lean=0.0):
        # a thin stem from the head up to a round ball; `lean` shifts the top sideways (outer stems)
        stem = pathops.Path()
        pen = stem.getPen()
        b, t = body_top - 0.02 * upm, body_top + h
        pen.moveTo((x - stem_w / 2, b)); pen.lineTo((x + stem_w / 2, b))
        pen.lineTo((x + lean + stem_w / 2, t)); pen.lineTo((x + lean - stem_w / 2, t)); pen.closePath()
        return op(stem, circle(x + lean * 1.08, body_top + h + ball_r * 0.6, ball_r), pathops.PathOp.UNION)

    # ז as in the siddur: a square head block over a diamond-shaped leg that tapers to a point
    zayin, chet = cm[ord('ז')], cm[ord('ח')]
    zb = bounds(T, zayin)
    zc = (zb[0] + zb[2]) / 2
    leg_w = 0.47 * head_w
    hb = body_top - head_h                           # bottom of the head
    leg = smooth_path([(zc - 0.12 * head_w, hb + 20, True), (zc + 0.12 * head_w, hb + 20, True),
                       (zc + leg_w / 2, hb - 0.28 * hb), (zc + 0.05 * head_w, 0.12 * hb), (zc, -0.02 * hb, True),
                       (zc - 0.05 * head_w, 0.12 * hb), (zc - leg_w / 2, hb - 0.28 * hb)])
    set_glyph(T, zayin, op(rect(zc - head_w / 2, hb, zc + head_w / 2, body_top), leg, pathops.PathOp.UNION),
              T['hmtx'][zayin][0])
    # its dagesh sits just left of the leg, right under the head (a dot centre, used by add_nikud)
    T.dagesh_at = {zayin: (zc - leg_w / 2 - 0.045 * upm, hb - 0.2 * hb)}

    # ח as in the siddur: two ז halves joined by a pointed peak, one tag on the left half
    z = glyph_path(T, zayin)
    zx0, zy0, zx1, zy1 = z.bounds
    z = op(z, rect(zx0 - 10, zy0 - 10, zx1 + 10, cut), pathops.PathOp.INTERSECTION)
    zx0, zy0, zx1, top = z.bounds
    half, gap = zx1 - zx0, 0.45 * (zx1 - zx0)
    lsb = bounds(T, chet)[0]
    rsb = T['hmtx'][chet][0] - bounds(T, chet)[2]
    halves = pathops.Path()
    for x in (lsb, lsb + half + gap):
        z.draw(TransformPen(halves.getPen(), (1, 0, 0, 1, x - zx0, 0)))
    body_h = top - zy0
    xl, xr = lsb + half, lsb + half + gap                   # inner edges of the two heads
    xc, apex, base, th, reach = (xl + xr) / 2, top + 0.42 * body_h, top - 0.16 * body_h, 0.14 * upm, 0.55 * half
    peak = pathops.Path()
    pen = peak.getPen()
    for i, pt in enumerate([(xl - reach, base), (xc, apex), (xr + reach, base), (xr + reach - th, base),
                            (xc, apex - 1.6 * th), (xl - reach + th, base)]):
        (pen.moveTo if i == 0 else pen.lineTo)(pt)
    pen.closePath()
    new = op(op(halves, peak, pathops.PathOp.UNION), tag(lsb + 0.4 * half, outer_h), pathops.PathOp.UNION)
    set_glyph(T, chet, new, lsb + 2 * half + gap + rsb)

    siddur_lamed(T, body_top)

    for ch in TRIPLE_TAGIN + SINGLE_TAG:
        name = cm[ord(ch)]
        g = glyph_path(T, name)
        x0, y0, x1, y1 = g.bounds
        if y1 <= cut and ch not in TRIPLE_TAGIN:
            continue
        body = op(g, rect(x0 - 10, y0 - 10, x1 + 10, cut), pathops.PathOp.INTERSECTION)
        old = op(g, rect(x0 - 10, cut, x1 + 10, y1 + 10), pathops.PathOp.INTERSECTION) if y1 > cut else pathops.Path()
        centres = sorted((b.bounds[0] + b.bounds[2]) / 2 for b in components(old)) or [(x0 + x1) / 2]
        new = body
        if ch in SINGLE_TAG:
            new = op(new, tag(centres[0], outer_h), pathops.PathOp.UNION)
        else:
            # centre the cluster on the head it stands on, widening that head into a square block
            # when it is narrower than the cluster (the siddur's heads are wide square blocks)
            guess = sum(centres) / len(centres)
            heads = components(op(body, rect(x0 - 10, body_top - 0.04 * upm, x1 + 10, cut + 1),
                                  pathops.PathOp.INTERSECTION))
            hd = min(heads, key=lambda h: abs((h.bounds[0] + h.bounds[2]) / 2 - guess)).bounds
            cx = (hd[0] + hd[2]) / 2
            if hd[2] - hd[0] < head_w:
                new = op(new, rect(cx - head_w / 2, body_top - head_h, cx + head_w / 2, body_top),
                         pathops.PathOp.UNION)
            lean = 0.018 * upm                        # outer stems lean out slightly, as printed
            for dx, h, ln in ((-spacing, outer_h, -lean), (0, middle_h, 0), (spacing, outer_h, lean)):
                new = op(new, tag(cx + dx, h, ln), pathops.PathOp.UNION)
        set_glyph(T, name, new, T['hmtx'][name][0])


# ── dagesh placement: the centre of the letter's largest open area (as the siddur prints it) ──
COUNTER_LETTERS = 'בגדהחטכךלמםסעפףצץקשת'


class _Flatten:
    """Pen that flattens outlines into polygons (for rasterising)."""
    def __init__(self):
        self.polys, self.cur = [], []
    def moveTo(self, p): self.cur = [p]
    def lineTo(self, p): self.cur.append(p)
    def curveTo(self, *pts):
        p0 = self.cur[-1]
        if len(pts) == 3:
            c1, c2, p3 = pts
            for i in range(1, 9):
                t = i / 8
                mt = 1 - t
                self.cur.append((mt**3 * p0[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * p3[0],
                                 mt**3 * p0[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * p3[1]))
        else:
            for q in pts:
                self.cur.append(q)
    def qCurveTo(self, *pts):
        p0 = self.cur[-1]
        # expand implied on-curve points
        offs, end = list(pts[:-1]), pts[-1]
        segs = []
        for i, c in enumerate(offs):
            nxt = end if i == len(offs) - 1 else ((c[0] + offs[i + 1][0]) / 2, (c[1] + offs[i + 1][1]) / 2)
            segs.append((c, nxt))
        for c, e in segs:
            for j in range(1, 7):
                t = j / 6
                mt = 1 - t
                self.cur.append((mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * e[0],
                                 mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * e[1]))
            p0 = e
    def closePath(self):
        if self.cur: self.polys.append(self.cur)
        self.cur = []
    endPath = closePath
    def addComponent(self, *a): pass


def counter_centre(T, name, body_top):
    """Point (font units) inside the glyph's box, below the letter line, farthest from any ink."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageChops
    x0, y0, x1, y1 = bounds(T, name)
    px = body_top / 120                              # ~120 px per letter height
    W, H = int((x1 - x0) / px) + 3, int(body_top / px) + 3
    img = Image.new('1', (W, H), 0)
    fp = _Flatten()
    T.getGlyphSet()[name].draw(fp)
    for poly in fp.polys:                            # even-odd fill
        layer = Image.new('1', (W, H), 0)
        ImageDraw.Draw(layer).polygon([((x - x0) / px + 1, (body_top - y) / px + 1) for x, y in poly], fill=1)
        img = ImageChops.logical_xor(img, layer)
    ink = np.array(img, dtype=bool)
    ink[0, :] = ink[-1, :] = ink[:, 0] = ink[:, -1] = True    # the letter's box bounds the space
    iy, ix = np.nonzero(ink)
    ey, ex = np.nonzero(~ink)
    keep = (ey > 0.2 * H) & (ey < 0.85 * H)          # stay within the body, off the head and the baseline
    ey, ex = ey[keep], ex[keep]
    if len(ey) == 0:
        return None
    best, bi = -1, 0
    for s0 in range(0, len(ey), 2000):
        dy = ey[s0:s0 + 2000, None] - iy[None, :]
        dx = ex[s0:s0 + 2000, None] - ix[None, :]
        d = np.min(dy * dy + dx * dx, axis=1)
        j = int(np.argmax(d))
        if d[j] > best:
            best, bi = d[j], s0 + j
    return x0 + (ex[bi] - 1) * px, body_top - (ey[bi] - 1) * px


# ── 2. nikud from Frank Ruehl ──
def frank_anchors(F):
    """{lookup: {'marks': {glyph: (x, y)}, 'bases': {glyph: (x, y)}}} for Frank's MarkBase lookups."""
    out = {}
    for i, lk in enumerate(F['GPOS'].table.LookupList.Lookup):
        if lk.LookupType != 4:
            continue
        for st in lk.SubTable:
            out.setdefault(i, {'marks': {}, 'bases': {}})
            out[i]['marks'].update({g: (r.MarkAnchor.XCoordinate, r.MarkAnchor.YCoordinate)
                                    for g, r in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord)})
            for g, r in zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord):
                a = r.BaseAnchor[0]
                if a is not None:
                    out[i]['bases'][g] = (a.XCoordinate, a.YCoordinate)
    return out


def add_nikud(T, F):
    fcmap, tcmap = F.getBestCmap(), T.getBestCmap()
    lookups = frank_anchors(F)
    fb, tb = bounds(F, fcmap[0x05D4]), bounds(T, tcmap[0x05D4])
    s = (tb[3] - tb[1]) / (fb[3] - fb[1])           # global scale: STAM ה height / Frank ה height

    # the first MarkBase lookup that positions each of Frank's default mark glyphs
    mark_lookup = {}
    for cp in MARKS:
        g = fcmap.get(cp)
        for i in sorted(lookups):
            if g in lookups[i]['marks'] and lookups[i]['bases']:
                mark_lookup[cp] = i
                break

    fgs = F.getGlyphSet()

    def copy(cp, advance):
        name = tcmap.get(cp) or f'uni{cp:04X}'
        p = pathops.Path()
        fgs[fcmap[cp]].draw(TransformPen(p.getPen(), (s, 0, 0, s, 0, 0)))
        set_glyph(T, name, p, advance)
        return name

    mark_names = {cp: copy(cp, 0) for cp in MARKS}
    spacing = {}
    for cp in SPACING:                               # maqaf, geresh, gershayim, sof pasuq
        name = tcmap.get(cp)
        if name and bounds(T, name):
            continue
        spacing[cp] = copy(cp, F['hmtx'][fcmap[cp]][0] * s)
    for table in T['cmap'].tables:
        if table.isUnicode():
            table.cmap.update({**mark_names, **spacing})

    def map_anchor(x, y, fbox, tbox):
        fx0, fy0, fx1, fy1 = fbox
        tx0, ty0, tx1, ty1 = tbox
        nx = tx0 + (x - fx0) * (tx1 - tx0) / max(1, fx1 - fx0)
        if y > fy1:
            ny = ty1 + (y - fy1) * s
        elif y < fy0:
            ny = ty0 + (y - fy0) * s
        else:
            ny = ty0 + (y - fy0) * (ty1 - ty0) / max(1, fy1 - fy0)
        return round(nx), round(ny)

    tcmap = T.getBestCmap()
    fea = ['languagesystem DFLT dflt;', 'languagesystem hebr dflt;']
    for cp, i in mark_lookup.items():
        if cp == 0x05BC:
            continue
        mx, my = lookups[i]['marks'][fcmap[cp]]
        fea.append(f'markClass [{mark_names[cp]}] <anchor {round(mx * s)} {round(my * s)}> @M{i};')
    # dagesh: anchored at the dot's centre; letters with an open counter get it at the counter's centre,
    # the rest (ו ז י נ …) keep Frank's position shifted to the new mark anchor
    db = bounds(T, mark_names[0x05BC])
    dc = ((db[0] + db[2]) / 2, (db[1] + db[3]) / 2)
    di = mark_lookup.pop(0x05BC)
    dmx, dmy = (v * s for v in lookups[di]['marks'][fcmap[0x05BC]])
    fea.append(f'markClass [{mark_names[0x05BC]}] <anchor {round(dc[0])} {round(dc[1])}> @DAGESH;')
    body_top = bounds(T, tcmap[ord('כ')])[3]
    base_names = set()
    fea.append('feature mark {')
    for i in sorted(set(mark_lookup.values())):
        fea.append(f'  lookup L{i} {{')
        for cp in BASES:
            tname = tcmap.get(cp)
            if not tname:
                continue
            fname = fcmap.get(cp)
            if fname not in lookups[i]['bases']:          # fall back to the undecorated letter
                dec = unicodedata.decomposition(chr(cp)).split()
                fname = fcmap.get(int(dec[0], 16)) if dec else None
            if fname not in lookups[i]['bases']:
                continue
            tbox = bounds(T, tname)
            if tbox is None:
                continue
            x, y = map_anchor(*lookups[i]['bases'][fname], bounds(F, fname), tbox)
            fea.append(f'    pos base [{tname}] <anchor {x} {y}> mark @M{i};')
            base_names.add(tname)
        fea.append(f'  }} L{i};')
    fea.append('  lookup DAGESH {')
    for cp in range(0x05D0, 0x05EB):
        tname = tcmap.get(cp)
        fname = fcmap.get(cp)
        if not tname or not bounds(T, tname):
            continue
        pt = getattr(T, 'dagesh_at', {}).get(tname)
        if pt is None and chr(cp) in COUNTER_LETTERS:
            pt = counter_centre(T, tname, body_top)
        if pt is None:
            if fname not in lookups[di]['bases']:
                continue
            x, y = map_anchor(*lookups[di]['bases'][fname], bounds(F, fname), bounds(T, tname))
            pt = (x + dc[0] - dmx, y + dc[1] - dmy)
        fea.append(f'    pos base [{tname}] <anchor {round(pt[0])} {round(pt[1])}> mark @DAGESH;')
        base_names.add(tname)
    fea.append('  } DAGESH;')
    # Frank draws shin/sin dots through precomposed shin glyphs, so anchor them by hand:
    # above the right (shin) or left (sin) head of ש.
    for cp, side in ((0x05C1, 1), (0x05C2, 0)):
        if cp in mark_lookup:
            continue
        mb = bounds(T, mark_names[cp])
        fea.insert(2, f'markClass [{mark_names[cp]}] <anchor {round((mb[0] + mb[2]) / 2)} {round(mb[1])}> @D{cp:X};')
        fea.append(f'  lookup D{cp:X} {{')
        for base in (0x05E9, 0xFB49):
            tname = tcmap.get(base)
            tbox = tname and bounds(T, tname)
            if not tbox:
                continue
            top = tbox[3]
            w, h = tbox[2] - tbox[0], top - tbox[1]
            x = tbox[2] - 0.12 * w if side else tbox[0] + 0.12 * w
            fea.append(f'    pos base [{tname}] <anchor {round(x)} {round(top + 0.06 * h)}> mark @D{cp:X};')
            base_names.add(tname)
        fea.append(f'  }} D{cp:X};')
    fea.append('} mark;')
    fea.append('table GDEF { GlyphClassDef [%s], , [%s], ; } GDEF;'
               % (' '.join(sorted(base_names)), ' '.join(sorted(set(mark_names.values())))))
    for tag in ('GPOS', 'GDEF', 'FFTM'):
        if tag in T:
            del T[tag]
    addOpenTypeFeaturesFromString(T, '\n'.join(fea))


# ── 3. pieces of ה for the stretched ה of שם הוי"ה ──
def add_he_pieces(T):
    he = T.getBestCmap()[0x05D4]
    g = glyph_path(T, he)
    x0, y0, x1, y1 = g.bounds
    adv = T['hmtx'][he][0]
    leg = min(components(g), key=lambda p: (p.bounds[2] - p.bounds[0]) * (p.bounds[3] - p.bounds[1]))
    cut = leg.bounds[2] + 0.05 * (x1 - x0)           # just right of the left leg: only roof above it
    upm = T['head'].unitsPerEm
    # the roof's band, measured over a stretch right of the cut (a single slice can catch a dip)
    bb, bt = op(g, rect(cut, y0 - 10, cut + 0.25 * (x1 - x0), y1 + 10), pathops.PathOp.INTERSECTION).bounds[1::2]
    ov = 0.02 * upm                                  # the ends overlap the extension: no visible joins
    right = op(op(g, rect(cut, y0 - 10, x1 + 10, y1 + 10), pathops.PathOp.INTERSECTION),
               rect(cut - ov, bb, cut, bt), pathops.PathOp.UNION)
    left = op(op(g, rect(x0 - 10, y0 - 10, cut, y1 + 10), pathops.PathOp.INTERSECTION),
              rect(cut, bb, cut + ov, bt), pathops.PathOp.UNION)
    seg = 3 * upm                                    # one long piece, clipped to width by CSS: no seams
    set_glyph(T, 'he.right', right, adv - cut, dx=-cut)
    set_glyph(T, 'he.left', left, cut)
    set_glyph(T, 'he.roof', rect(0, bb, seg, bt), seg)
    for table in T['cmap'].tables:
        if table.isUnicode():
            table.cmap.update({0xE000: 'he.right', 0xE001: 'he.left', 0xE002: 'he.roof'})


def to_glyf(path):
    """Load a font, converting CFF outlines to glyf so pieces can be added."""
    T = TTFont(path)
    if 'glyf' in T:
        return T
    gs = T.getGlyphSet()
    glyf = newTable('glyf'); glyf.glyphs = {}; glyf.glyphOrder = T.getGlyphOrder()
    for name in T.getGlyphOrder():
        pen = TTGlyphPen(None)
        gs[name].draw(Cu2QuPen(pen, max_err=1, reverse_direction=True))
        glyf[name] = pen.glyph()
    T['glyf'] = glyf
    T['loca'] = newTable('loca')
    del T['CFF ']
    maxp = T['maxp']
    maxp.tableVersion = 0x00010000
    for attr in ('maxZones', 'maxTwilightPoints', 'maxStorage', 'maxFunctionDefs', 'maxInstructionDefs',
                 'maxStackElements', 'maxSizeOfInstructions', 'maxComponentElements', 'maxPoints',
                 'maxContours', 'maxCompositePoints', 'maxCompositeContours', 'maxComponentDepth'):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    T['head'].glyphDataFormat = 0
    T['post'].formatType = 2.0
    T['post'].extraNames = []
    T['post'].mapping = {}
    T.sfntVersion = '\x00\x01\x00\x00'
    for name in T.getGlyphOrder():
        glyf[name].recalcBounds(glyf)
    return T


def save(T, name, family):
    for rec in T['name'].names:
        if rec.nameID in (1, 4, 16):
            rec.string = family
        elif rec.nameID == 6:
            rec.string = family.replace(' ', '')
    T.getReverseGlyphMap(rebuild=True)
    opts = Options()
    opts.layout_features = ['*']
    opts.name_IDs = ['*']
    opts.notdef_outline = True
    opts.drop_tables += ['FFTM']
    sub = Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(T)
    T.flavor = 'woff2'
    T.save(OUT / name)
    print('wrote', name)


if __name__ == '__main__':
    culmus, ari = Path(sys.argv[1]), sys.argv[2]
    F = TTFont(culmus / 'FrankRuehlCLM-Medium.otf')

    T = TTFont(culmus / 'StamAshkenazCLM.ttf')
    straight_tagin(T); add_nikud(T, F); add_he_pieces(T)
    save(T, 'StamSiddur-nikud.woff2', 'Stam Siddur Nikud')

    for src, out, family in ((culmus / 'StamSefaradCLM.ttf', 'StamSefarad-nikud.woff2', 'Stam Sefarad Nikud'),
                             (culmus / 'StamAshkenazCLM.ttf', 'StamAshkenaz-nikud.woff2', 'Stam Ashkenaz Nikud'),
                             (ari, 'SchwarzStamAri-nikud.woff2', 'Schwarz Stam Ari Nikud')):
        T = TTFont(src); add_nikud(T, F); add_he_pieces(T); save(T, out, family)

    for src, out, family in ((culmus / 'KeterYG-Medium.ttf', 'KeterYG-Medium.woff2', 'Keter YG'),
                             (culmus / 'FrankRuehlCLM-Medium.otf', 'FrankRuehlCLM-Medium.woff2', 'Frank Ruehl CLM')):
        T = to_glyf(src); add_he_pieces(T); save(T, out, family)
