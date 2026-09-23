"""Give the STAM fonts nikud.

The STAM fonts (Culmus Stam Sefarad/Ashkenaz, Schwarz Stam Ari) have no vowel glyphs. This copies
Frank Ruehl CLM's vowel glyphs into each one and rebuilds GPOS mark positioning: each Frank
anchor is mapped onto the matching STAM letter by that letter's bounding box, so a patach lands
under the STAM letter where Frank puts it under its own letter.

Usage:  python3 tools/build-fonts.py <culmus-dir> <SchwarzStamAri.ttf>
Writes fonts/*-nikud.woff2 next to this script's parent directory.
"""
import sys, unicodedata
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

MARKS = [*range(0x05B0, 0x05BE), 0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7]
SPACING = [0x05BE, 0x05C3, 0x05F3, 0x05F4]
BASES = [*range(0x05D0, 0x05EB), *range(0xFB1D, 0xFB50)]
OUT = Path(__file__).resolve().parent.parent / 'fonts'


def bounds(font, name):
    gs = font.getGlyphSet()
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    return bp.bounds


def frank_anchors(F):
    """{lookup: {'marks': {glyph: (x, y)}, 'bases': {glyph: (x, y)}}} for Frank's MarkBase lookups."""
    out = {}
    for i, lk in enumerate(F['GPOS'].table.LookupList.Lookup):
        if lk.LookupType != 4:
            continue
        for st in lk.SubTable:
            marks = {g: (r.MarkAnchor.XCoordinate, r.MarkAnchor.YCoordinate)
                     for g, r in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord)}
            bases = {}
            for g, r in zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord):
                a = r.BaseAnchor[0]
                if a is not None:
                    bases[g] = (a.XCoordinate, a.YCoordinate)
            out.setdefault(i, {'marks': {}, 'bases': {}})
            out[i]['marks'].update(marks)
            out[i]['bases'].update(bases)
    return out


def build(target_path, frank_path, out_name, family):
    F = TTFont(frank_path)
    T = TTFont(target_path)
    fcmap, tcmap = F.getBestCmap(), T.getBestCmap()
    lookups = frank_anchors(F)

    # global scale: STAM ה height / Frank ה height
    fb, tb = bounds(F, fcmap[0x05D4]), bounds(T, tcmap[0x05D4])
    s = (tb[3] - tb[1]) / (fb[3] - fb[1])

    # the first MarkBase lookup that positions each of Frank's default mark glyphs
    mark_lookup = {}
    for cp in MARKS:
        g = fcmap.get(cp)
        for i in sorted(lookups):
            if g in lookups[i]['marks'] and lookups[i]['bases']:
                mark_lookup[cp] = i
                break

    # copy mark outlines (scaled, cubic→quadratic) into the target
    glyf, hmtx = T['glyf'], T['hmtx']
    order = T.getGlyphOrder()
    fgs = F.getGlyphSet()
    mark_names = {}
    for cp in MARKS:
        name = tcmap.get(cp) or f'uni{cp:04X}'
        pen = TTGlyphPen(None)
        fgs[fcmap[cp]].draw(TransformPen(Cu2QuPen(pen, max_err=1, reverse_direction=True), (s, 0, 0, s, 0, 0)))
        glyf[name] = pen.glyph()
        hmtx[name] = (0, 0)
        if name not in order:
            order.append(name)
        mark_names[cp] = name
    # spacing punctuation (maqaf, geresh, gershayim, sof pasuq) that a STAM font may lack
    spacing = {}
    for cp in SPACING:
        name = tcmap.get(cp)
        if name and bounds(T, name):
            continue
        name = name or f'uni{cp:04X}'
        pen = TTGlyphPen(None)
        fgs[fcmap[cp]].draw(TransformPen(Cu2QuPen(pen, max_err=1, reverse_direction=True), (s, 0, 0, s, 0, 0)))
        glyf[name] = pen.glyph()
        hmtx[name] = (round(F['hmtx'][fcmap[cp]][0] * s), round(F['hmtx'][fcmap[cp]][1] * s))
        if name not in order:
            order.append(name)
        spacing[cp] = name
    T.setGlyphOrder(order)
    for table in T['cmap'].tables:
        if table.isUnicode():
            for cp, name in {**mark_names, **spacing}.items():
                table.cmap[cp] = name
    for name in spacing.values():
        glyf[name].recalcBounds(glyf)
    for name in mark_names.values():
        glyf[name].recalcBounds(glyf)

    # anchors: map each Frank base anchor into the STAM letter's box
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
        mx, my = lookups[i]['marks'][fcmap[cp]]
        fea.append(f'markClass [{mark_names[cp]}] <anchor {round(mx * s)} {round(my * s)}> @M{i};')
    used = sorted(set(mark_lookup.values()))
    base_names = set()
    fea.append('feature mark {')
    for i in used:
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
            w, h = tbox[2] - tbox[0], tbox[3] - tbox[1]
            x = tbox[2] - 0.12 * w if side else tbox[0] + 0.12 * w
            fea.append(f'    pos base [{tname}] <anchor {round(x)} {round(tbox[3] + 0.06 * h)}> mark @D{cp:X};')
            base_names.add(tname)
        fea.append(f'  }} D{cp:X};')
    fea.append('} mark;')
    fea.append('table GDEF { GlyphClassDef [%s], , [%s], ; } GDEF;'
               % (' '.join(sorted(base_names)), ' '.join(sorted(set(mark_names.values())))))
    for tag in ('GPOS', 'GDEF', 'FFTM'):
        if tag in T:
            del T[tag]
    addOpenTypeFeaturesFromString(T, '\n'.join(fea))

    for rec in T['name'].names:
        if rec.nameID in (1, 4, 16):
            rec.string = family
        elif rec.nameID == 6:
            rec.string = family.replace(' ', '')
    T.flavor = 'woff2'
    T.save(OUT / out_name)
    print(f'{out_name}: scale {s:.3f}, {len(base_names)} bases, mark classes {used}, added {[hex(c) for c in spacing]}')


if __name__ == '__main__':
    culmus, ari = Path(sys.argv[1]), sys.argv[2]
    frank = culmus / 'FrankRuehlCLM-Medium.otf'
    build(culmus / 'StamSefaradCLM.ttf', frank, 'StamSefarad-nikud.woff2', 'Stam Sefarad Nikud')
    build(culmus / 'StamAshkenazCLM.ttf', frank, 'StamAshkenaz-nikud.woff2', 'Stam Ashkenaz Nikud')
    build(ari, frank, 'SchwarzStamAri-nikud.woff2', 'Schwarz Stam Ari Nikud')
