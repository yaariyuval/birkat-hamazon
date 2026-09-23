// Checks every Hebrew string in text.js against the Wikisource source (resolved to נוסח מזרח).
// Usage: node tools/verify-text.mjs   — prints any string not found verbatim, and intentional fixes.
import { readFileSync } from 'node:fs';
import { TEXT } from '../text.js';

let src = readFileSync(new URL('../source.wiki', import.meta.url), 'utf8') + '\n' +
          readFileSync(new URL('../al-hanisim.wiki', import.meta.url), 'utf8');
// resolve al-hanisim templates for נוסח מזרח
src = src.replace(/\{\{נוא\|[^{}]*\}\}/g, '');
for (let i = 0; i < 3; i++) src = src.replace(/\{\{נוסחי תפילה קצרים\|נוסח=\{\{\{נוסח\|\}\}\}((?:\|[^|{}]*(?:\{\{[^{}]*\}\})?[^|{}]*)*)\}\}/g, (_, args) => {
  const kv = Object.fromEntries(args.split('|').slice(1).map(a => { const j = a.indexOf('='); return [a.slice(0, j), a.slice(j + 1)]; }));
  return kv['מזרח'] ?? kv['כל השאר'] ?? '';
});
src = src.replace(/\{\{הוראה למתפללים\|[^{}]*\}\}/g, ' ').replace(/\{\{ש\}\}/g, ' ')
         .replace(/\{\{[^{}|]*\}\}/g, ' ').replace(/\s+/g, ' ').replace(/\( +/g, '(');
// Deliberate fixes of typos in the Wikisource page (applied to the source before comparing).
export const CORRECTIONS = [
  ['לַמְנַצֵּח ', 'לַמְנַצֵּחַ '],                       // missing furtive patach
  ['הֵפַֽֽרְתָּ', 'הֵפַֽרְתָּ'],                          // doubled meteg
  ['ועַל הַכֹּל', 'וְעַל הַכֹּל'],                       // missing sheva
  ['הַשַׁבָּת הַגָּדוֹל וְהַקָדוֹשׂ', 'הַשַּׁבָּת הַגָּדוֹל וְהַקָּדוֹשׁ'], // dagesh + shin dot
  ['וְרַחוּם אָֽתָּה ', 'וְרַחוּם אָֽתָּה. '],
  ['רְפוּאֵת הֵנֶּֽפֶש', 'רְפוּאַת הַנֶּֽפֶשׁ'],
  ['הַרָחֲמָן', 'הָרַחֲמָן'],                            // misplaced kamatz/patach
  ['שֶׁכֻּלוֹ', 'שֶׁכֻּלּוֹ'],
  ['אֶת הָחֹֽדֶשׁ', 'אֶת הַחֹֽדֶשׁ'],
  ['יַגִּיעֵנוּ', 'יַגִּיעֵֽנוּ'],
];
for (const [a, b] of CORRECTIONS) { if (!src.includes(a)) console.log('correction not found in source:', a); src = src.split(a).join(b); }
const norm = s => s.replace(/\s+/g, ' ').trim();

const strings = [];
const walk = (x) => {
  if (typeof x === 'string') { if (/[ְ-ׇ]/.test(x)) strings.push(x); return; }
  if (Array.isArray(x)) return x.forEach(walk);
  if (x && typeof x === 'object') { if (x.t) walk(x.t); if (x.lines) walk(x.lines); if (x.items) walk(x.items); }
};
walk(TEXT);
let bad = 0;
for (const s of strings) {
  // allow sentence-split fragments: check by chunks separated by line breaks in source
  const n = norm(s);
  if (!src.includes(n)) { bad++; console.log('✗', n.slice(0, 200)); }
}
console.log(`${strings.length} strings, ${bad} not verbatim`);
