"""Build the app's fonts from Culmus (+ the Schwarz Ari font).

1. "Stam Siddur": every letter traced from photos of the user's siddur, tagin included
   (tools/trace/trace.py → tools/trace/glyphs.json), on Stam Ashkenaz CLM's metrics.
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


# תגים: three on שעטנ"ז ג"ץ (and ן), one on בדק חי"ה, none on מלאכת סופר.
TRIPLE_TAGIN = 'שעטנזגצץן'
SINGLE_TAG = 'בדקחיה'
# Proportions measured on the traced letters (letter body = 1000): ball tops 470 (middle) and 320
# (outer; single 300) above the head line, balls 145 across, thin straight parallel stems 150 apart.
TAG = dict(mid=490, outer=380, single=310, ball=165, stem=32, spread=155)


def surface(p, x, bt):
    """Top of the letter's head at x (its printed surface, which may slope, as on ט)."""
    u = bt / 1000
    col = op(p, rect(x - 8 * u, -10000, x + 8 * u, bt + 250 * u), pathops.PathOp.INTERSECTION)
    return col.bounds[3] if col.bounds else bt


def tag(x, height, bt, base_y):
    """One tag: a thin straight stem from inside the head (below `base_y`) up to a round ball."""
    u = bt / 1000
    r = TAG['ball'] * u / 2
    cy = bt + height * u - r
    w = TAG['stem'] * u / 2
    stem = rect(x - w, base_y - 40 * u, x + w, cy)
    return op(stem, circle(x, cy, r), pathops.PathOp.UNION)


def add_tagin(p, ch, bt, x):
    """Crisp tagin on the traced letter: three parallel stems centred on the head block (middle one
    tallest), or one, each standing on the head's own surface."""
    u = bt / 1000
    if ch in SINGLE_TAG:
        return op(p, tag(x, TAG['single'], bt, surface(p, x, bt)), pathops.PathOp.UNION)
    sp = TAG['spread'] * u
    for dx, h in ((-sp, TAG['outer']), (0, TAG['mid']), (sp, TAG['outer'])):
        p = op(p, tag(x + dx, h, bt, surface(p, x + dx, bt)), pathops.PathOp.UNION)
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


def traced_letters(T, glyphs_json):
    """Replace the letters with outlines traced from the siddur (tools/trace/glyphs.json: baseline 0,
    letter body 1000 high), scaled to this font's letter height. Sets T.dagesh_at for the letters whose dagesh sits beside
    the stem (ו, ז), as the siddur prints it."""
    import json
    glyphs = json.loads(Path(glyphs_json).read_text())
    cm = T.getBestCmap()
    k = bounds(T, cm[ord('כ')])[3] / 1000             # this font's letter height / traced letter height
    bt = 1000 * k
    side = 0.055 * bt                                # side bearing (the siddur sets letters close)
    paths = {}
    for ch, g in glyphs.items():
        contours = g['outline']
        p = pathops.Path()
        pen = p.getPen()
        for c in contours:
            for op_, *pts in c:
                pts = [(x * k, y * k) for x, y in pts]
                if op_ == 'M':
                    pen.moveTo(pts[0])
                elif op_ == 'L':
                    pen.lineTo(pts[0])
                else:
                    pen.curveTo(*pts)
            pen.closePath()
        paths[ch] = pathops.simplify(p, fix_winding=True, keep_starting_points=False)

    for ch in TRIPLE_TAGIN + SINGLE_TAG:
        if 'tag_x' in glyphs.get(ch, {}):
            paths[ch] = add_tagin(paths[ch], ch, bt, glyphs[ch]['tag_x'] * k)

    for ch, p in paths.items():
        x0, y0, x1, y1 = p.bounds
        set_glyph(T, cm[ord(ch)], p, x1 - x0 + 2 * side, dx=side - x0)

    # dagesh beside the stem of ו (the shuruk) and ז, at the siddur's height
    T.dagesh_at = {}
    for ch, h, gap in (('ו', 0.5, 0.15), ('ז', 0.6, 0.09)):
        name = cm[ord(ch)]
        row = op(glyph_path(T, name), rect(-10000, h * bt - 2, 10000, h * bt + 2), pathops.PathOp.INTERSECTION)
        T.dagesh_at[name] = (row.bounds[0] - gap * bt, h * bt)
    # holam male (וֹ): the dot right above the ו's head, centred on it (dot centre, used by add_nikud)
    vav = cm[ord('ו')]
    head = op(glyph_path(T, vav), rect(-10000, 0.8 * bt, 10000, bt), pathops.PathOp.INTERSECTION).bounds
    T.holam_at = {vav: ((head[0] + head[2]) / 2, 1.17 * bt)}
    if 'GSUB' in T:                                  # no substitution back to the old letter shapes
        del T['GSUB']


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


def add_nikud(T, F, cap=False):
    """`cap`: measure letters only up to the head line, so marks ignore the tagin (traced letters)."""
    fcmap, tcmap = F.getBestCmap(), T.getBestCmap()
    lookups = frank_anchors(F)
    body_top = bounds(T, tcmap[ord('כ')])[3]
    fb, tb = bounds(F, fcmap[0x05D4]), bounds(T, tcmap[0x05D4])
    s = ((body_top if cap else tb[3]) - tb[1]) / (fb[3] - fb[1])   # scale: STAM ה height / Frank ה height

    def box(name, cp):
        b = bounds(T, name)
        if b and cap and chr(cp) not in 'ל':
            b = (b[0], b[1], b[2], min(b[3], body_top))
        return b

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
            tbox = box(tname, cp)
            if tbox is None:
                continue
            x, y = map_anchor(*lookups[i]['bases'][fname], bounds(F, fname), tbox)
            if tname in getattr(T, 'holam_at', {}) and i == mark_lookup.get(0x05B9):
                # put the holam dot's centre at the requested point
                hb = bounds(T, mark_names[0x05B9])
                mx, my = (v * s for v in lookups[i]['marks'][fcmap[0x05B9]])
                px, py = T.holam_at[tname]
                x, y = round(px - (hb[0] + hb[2]) / 2 + mx), round(py - (hb[1] + hb[3]) / 2 + my)
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
            x, y = map_anchor(*lookups[di]['bases'][fname], bounds(F, fname), box(tname, cp))
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
            tbox = tname and box(tname, base)
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
    # the roof's band: the ink in a slice through the middle of the roof (clear of the leg and tag)
    xm = (cut + x1) / 2
    bb, bt = op(g, rect(xm - 0.05 * (x1 - x0), y0 - 10, xm + 0.05 * (x1 - x0), y1 + 10),
                pathops.PathOp.INTERSECTION).bounds[1::2]
    bb = max(bb, bt - 0.2 * (y1 - y0))               # (the right stem hangs below the roof there)
    ov = 0.02 * upm                                  # the ends overlap the extension: no visible joins
    # both ends get a straight run of the same roof band, so the joins with the bar are seamless
    run = 0.2 * (x1 - x0)
    right = op(op(g, rect(cut, y0 - 10, x1 + 10, y1 + 10), pathops.PathOp.INTERSECTION),
               rect(cut - ov, bb, cut + run, bt), pathops.PathOp.UNION)
    left = op(op(g, rect(x0 - 10, y0 - 10, cut, y1 + 10), pathops.PathOp.INTERSECTION),
              rect(cut - run, bb, cut + ov, bt), pathops.PathOp.UNION)
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

    T = TTFont(culmus / 'StamAshkenazCLM.ttf')        # metrics donor; every letter is replaced
    traced_letters(T, Path(__file__).parent / 'trace' / 'glyphs.json')
    add_nikud(T, F, cap=True); add_he_pieces(T)
    save(T, 'StamSiddur-nikud.woff2', 'Stam Siddur Nikud')

    for src, out, family in ((culmus / 'StamSefaradCLM.ttf', 'StamSefarad-nikud.woff2', 'Stam Sefarad Nikud'),
                             (culmus / 'StamAshkenazCLM.ttf', 'StamAshkenaz-nikud.woff2', 'Stam Ashkenaz Nikud'),
                             (ari, 'SchwarzStamAri-nikud.woff2', 'Schwarz Stam Ari Nikud')):
        T = TTFont(src); add_nikud(T, F); add_he_pieces(T); save(T, out, family)

    for src, out, family in ((culmus / 'KeterYG-Medium.ttf', 'KeterYG-Medium.woff2', 'Keter YG'),
                             (culmus / 'FrankRuehlCLM-Medium.otf', 'FrankRuehlCLM-Medium.woff2', 'Frank Ruehl CLM')):
        T = to_glyf(src); add_he_pieces(T); save(T, out, family)
