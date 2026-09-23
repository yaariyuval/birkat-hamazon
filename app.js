import { TEXT } from './text.js';
import { dayInfo, flags, halachicCivilDate, formatHebrew, MANUAL_DAYS } from './calendar.js';

// ── persisted settings (per device; the page works without storage) ──
const DEFAULTS = {
  zimun: 'none', ten: false, meal: 'none', guest: false, lshem: true, kavanot: false, names: true,
  font: 'siddur', theme: 'auto', size: 26, showAll: false,
  walled: false, diaspora: false,
  loc: { lat: 31.778, lon: 35.235 },         // Jerusalem until the user shares a location
  override: null,                             // { key: 'YYYY-M-D', mode }
};
const load = () => { try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem('bhm') || '{}') }; } catch { return { ...DEFAULTS }; } };
const S = load();
if (!S.fontV) { S.font = 'siddur'; S.fontV = 3; }            // move everyone to the siddur-style font once
const save = () => { try { localStorage.setItem('bhm', JSON.stringify(S)); } catch {} };

const $ = id => document.getElementById(id);

// ── the day ──
function today() {
  const civil = halachicCivilDate(new Date(), S.loc);
  const key = `${civil.getFullYear()}-${civil.getMonth() + 1}-${civil.getDate()}`;
  const auto = dayInfo(civil, { diaspora: S.diaspora, walledCity: S.walled });
  if (S.override && S.override.key !== key) { S.override = null; save(); }   // overrides last one day
  const m = S.override && MANUAL_DAYS[S.override.mode];
  const info = m ? { h: auto.h, ...m, shabbat: !!(m.shabbat || S.override.shabbat) } : auto;
  return { key, auto, info, manual: !!S.override };
}

function dayChips(info) {
  const out = [];
  if (info.shabbat) out.push('שבת');
  if (info.rc) out.push('ראש חודש');
  const HOL = { rh: 'ראש השנה', sukkot: 'סוכות', shemini: 'שמיני עצרת', pesach: 'פסח', shavuot: 'שבועות' };
  if (info.holiday) out.push(HOL[info.holiday] + (info.cholHamoed ? ' · חול המועד' : ''));
  if (info.chanukah) out.push('חנוכה');
  if (info.purim) out.push('פורים');
  return out.length ? out : ['יום חול'];
}

// ── rendering ──
const heb = t => t.replace(/"/g, '״').replace(/'/g, '׳');          // gershayim / geresh
// שם א"ל for the end of ברכה ג׳ by weekday (פרי עץ חיים, שער השבת כד מט)
const EL_BY_DOW = ['א"ל שד"י', 'א"ל הוי"ה', 'א"ל אדנ"י', 'א"ל אדנ"י', 'א"ל הוי"ה', 'א"ל שד"י'];
const DAY_NAMES = ['א׳', 'ב׳', 'ג׳', 'ד׳', 'ה׳', 'ו׳'];

function kavanah(tag, text, src, f, dow) {
  const el = document.createElement(tag);
  el.className = tag === 'p' ? 'kav-block' : 'kav';
  el.append(heb(text));
  if (dow && EL_BY_DOW[f.dow]) {
    const today = document.createElement('b');
    today.className = 'kav-today';
    today.textContent = `היום (יום ${DAY_NAMES[f.dow]}): ${heb(EL_BY_DOW[f.dow])}`;
    el.append(' ', today);
  }
  const cite = document.createElement('cite'); cite.textContent = src; el.append(' ', cite);
  return el;
}

function test(w, f) { return !w || (w[0] === '!' ? !f[w.slice(1)] : !!f[w]); }

// שם הוי"ה as printed in the siddur: יהו + a stretched ה (font pieces U+E000–E002) with אדני inside.
// Matches every vowelling of the Name (יְהֹוָה, and the יהוָה of לַיהוָה / בַּיהוָה); the final ה is unvowelled.
const NAME = /(י[\u0591-\u05C7]*ה[\u0591-\u05C7]*ו[\u0591-\u05C7]*)ה(?![\u0591-\u05C7])/g;
function stretchedHe() {
  const he = document.createElement('span'); he.className = 'nm-he';
  const right = document.createElement('span'); right.textContent = '\uE000';
  const mid = document.createElement('span'); mid.className = 'nm-mid';
  const roof = document.createElement('span'); roof.className = 'nm-roof'; roof.textContent = '\uE002';                 // one 3-em bar, clipped to the width of אדני
  const adni = document.createElement('span'); adni.className = 'nm-adni'; adni.textContent = 'אדני';
  const left = document.createElement('span'); left.textContent = '\uE001';
  mid.append(roof, adni); he.append(right, mid, left);
  return he;
}
// The siddur's notes beside the names (שו״ע או״ח ה): after הוי״ה, and after every form of אלהים.
const NIKUD = /[\u0591-\u05C7]/g;
const ELOHIM = /^(?:[והבלכמש])?אלה(?:ים|ינו|יך|י)$/;
function note(...lines) {
  const a = document.createElement('span'); a.className = 'dn' + (lines.length > 1 ? ' two' : '');
  lines.forEach((t, i) => { if (i) a.append(document.createElement('br')); a.append(t); });
  return a;
}
const nameNotes = () => [note('יאהדונהי'), note('אדון הכל', 'היה הוה ויהיה')];
const elohimNote = () => note('תקיף ובעל היכולת', 'ובעל הכוחות כולם');

function withElohim(str, into) {
  if (!S.names) { into.append(str); return; }
  // split into words, keeping separators; a note follows each form of אלהים
  for (const tok of str.split(/([\s־]+)/)) {
    if (!tok) continue;
    const letters = tok.replace(NIKUD, '').replace(/[^\u05D0-\u05EA]/g, '');
    if (!ELOHIM.test(letters)) { into.append(tok); continue; }
    const word = tok.match(/^[^,.:;!?"]*/)[0];
    into.append(word, ' ', elohimNote(), tok.slice(word.length));
  }
}

function withName(str, into) {
  let at = 0;
  for (const m of str.matchAll(NAME)) {
    if (m.index > at) withElohim(str.slice(at, m.index), into);
    const name = document.createElement('span'); name.className = 'nm';     // kept on one line
    name.append(m[1], stretchedHe()); into.append(name);
    if (S.names) into.append(' ', ...nameNotes().flatMap((n, i) => (i ? [' ', n] : [n])));
    at = m.index + m[0].length;
  }
  if (at < str.length) withElohim(str.slice(at), into);
}

// "⟦פּ⟧וֹתֵֽ⟦חַ⟧" → enlarged letters (each ⟦…⟧ keeps a letter together with its vowels)
function withBigLetters(str) {
  NAME.lastIndex = 0;
  if (!str.includes('⟦') && !NAME.test(str) && !(S.names && /אֱלֹה|אלֹה/.test(str))) return document.createTextNode(str);
  NAME.lastIndex = 0;
  const wrap = document.createElement('span');
  str.split(/(⟦[^⟧]*⟧)/).forEach(piece => {
    if (!piece.startsWith('⟦')) { withName(piece, wrap); return; }
    const b = document.createElement('span'); b.className = 'big'; b.textContent = piece.slice(1, -1); wrap.append(b);
  });
  return wrap;
}

function renderLine(line, f) {
  const span = document.createElement('span');
  const parts = typeof line === 'string' ? [line] : line;
  const bits = [];
  for (const p of parts) {
    if (typeof p === 'string') { bits.push(withBigLetters(p)); continue; }
    if (p.k) {
      if (!f.kav || (!test(p.w, f) && !S.showAll)) continue;
      const el = kavanah('span', p.k, p.src, f, p.dow);
      if (!test(p.w, f)) el.classList.add('off');
      bits.push(el); continue;
    }
    if (p.ann) {                                                     // small note beside a divine name
      const a = document.createElement('span');
      a.className = 'ann' + (p.ann.length > 1 ? ' two' : '') + (p.sup ? ' sup' : '');
      p.ann.forEach((t, i) => { if (i) a.append(document.createElement('br')); a.append(t); });
      if (p.tight) a.dataset.tight = '';
      bits.push(a); continue;
    }
    if (p.lbl) {
      const l = document.createElement('span'); l.className = 'lbl'; l.textContent = p.lbl;
      if (!p.t) { bits.push(l); continue; }
      const g = document.createElement('span');                       // "(בלחש: אָמֵן)"
      g.append('(', l, p.t, ')'); bits.push(g); continue;
    }
    const on = test(p.w, f);
    if (!on && !S.showAll) continue;
    let t = p.t;
    if (p.tov && !S.showAll) t = f.yomTov ? t.replace('(טוֹב)', 'טוֹב') : t.replace(' (טוֹב)', '');
    const el = document.createElement('span');
    if (S.showAll && p.label) {
      const lab = document.createElement('span'); lab.className = 'opt-label'; lab.textContent = `(${p.label}:)`;
      el.append(lab);
    }
    el.append(t);
    if (!on) el.className = 'off';
    bits.push(el);
  }
  bits.forEach((b, i) => {
    const glued = b.dataset?.tight !== undefined || /^[.,:]/.test(b.textContent);
    if (i && !glued) span.append(' ');
    span.append(b);
  });
  return span;
}

function render() {
  const { info, manual } = today();
  const f = flags(info, S);
  const root = $('text');
  root.replaceChildren();

  for (const b of TEXT) {
    const on = test(b.w, f);
    if (!on && !S.showAll) continue;
    if (b.type === 'kav' && !f.kav) continue;
    let el;
    if (b.type === 'kav') {
      el = kavanah('p', b.t, b.src, f);
    } else if (b.type === 'h') {
      el = document.createElement('h2'); el.textContent = b.t;
    } else if (b.type === 'note') {
      el = document.createElement('p'); el.className = 'note'; el.textContent = b.t;
    } else if (b.type === 'forgot') {
      el = document.createElement('details'); el.className = 'forgot';
      const s = document.createElement('summary'); s.textContent = b.t; el.append(s);
      for (const it of b.items) {
        if (!test(it.w, f) && !S.showAll) continue;
        const p = document.createElement('p');
        const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = it.label + ':';
        p.append(tag, it.t); el.append(p);
      }
    } else {
      el = document.createElement('p');
      el.className = [b.cls, b.verse && 'verse'].filter(Boolean).join(' ');
      if (b.label && (b.cls || '').includes('insert')) {
        const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = b.label; el.append(tag);
      } else if (b.label && S.showAll) {
        const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = b.label; el.append(tag);
      }
      for (const line of b.lines) el.append(renderLine(line, f));
    }
    if (!on) el.classList.add('off');
    root.append(el);
  }


  $('hdate').textContent = formatHebrew(info.h);
  $('chips').replaceChildren(...dayChips(info).map(t => {
    const c = document.createElement('span'); c.className = 'chip' + (manual ? ' manual' : ''); c.textContent = t; return c;
  }));
}

// ── appearance ──
function applyLook() {
  const r = document.documentElement;
  r.style.setProperty('--size', S.size + 'px');
  r.dataset.font = S.font;
  if (S.theme === 'auto') delete r.dataset.theme; else r.dataset.theme = S.theme;
}

// ── settings sheet ──
function openSettings() {
  const { auto, manual } = today();
  const sel = $('dayMode');
  sel.replaceChildren(new Option(`אוטומטי — ${dayChips(auto).join(', ')}`, 'auto'),
    ...Object.entries(MANUAL_DAYS).map(([k, v]) => new Option(v.label, k)));
  sel.value = manual ? S.override.mode : 'auto';
  $('alsoShabbat').checked = !!S.override?.shabbat;
  $('alsoShabbatRow').hidden = !manual || S.override.mode === 'shabbat';
  $('autoHint').textContent = 'הבחירה הידנית תקפה עד סוף היום (השקיעה).';
  for (const id of ['zimun', 'meal', 'font', 'theme']) $(id).value = S[id];
  for (const id of ['ten', 'guest', 'lshem', 'kavanot', 'names', 'showAll', 'walled', 'diaspora']) $(id).checked = S[id];
  $('settings').showModal();
}

function bind() {
  $('day').onclick = openSettings;
  $('settingsBtn').onclick = openSettings;
  $('dayMode').onchange = e => {
    S.override = e.target.value === 'auto' ? null : { key: today().key, mode: e.target.value, shabbat: $('alsoShabbat').checked };
    $('alsoShabbatRow').hidden = !S.override || S.override.mode === 'shabbat';
    save(); render();
  };
  $('alsoShabbat').onchange = e => { if (S.override) { S.override.shabbat = e.target.checked; save(); render(); } };
  for (const id of ['zimun', 'meal', 'font', 'theme']) $(id).onchange = e => { S[id] = e.target.value; save(); applyLook(); render(); };
  for (const id of ['ten', 'guest', 'lshem', 'kavanot', 'names', 'showAll', 'walled', 'diaspora']) $(id).onchange = e => { S[id] = e.target.checked; save(); render(); };
  const resize = d => { S.size = Math.min(48, Math.max(16, S.size + d)); save(); applyLook(); };
  $('fontBtn').onclick = () => {
    const opts = [...$('font').options];
    const next = opts[(opts.findIndex(o => o.value === S.font) + 1) % opts.length];
    S.font = next.value; save(); applyLook();
    toast(next.text);
  };
  $('smaller').onclick = () => resize(-2);
  $('larger').onclick = () => resize(2);
  $('locate').onclick = () => navigator.geolocation?.getCurrentPosition(p => {
    S.loc = { lat: p.coords.latitude, lon: p.coords.longitude }; save(); render();
    $('locate').textContent = 'המיקום עודכן ✓';
  }, () => { $('locate').textContent = 'לא התקבלה הרשאת מיקום'; });
  $('installGo').onclick = install;
  $('installBtn').onclick = install;
  $('installX').onclick = () => { try { localStorage.setItem('bhm-install-x', '1'); } catch {} installUI(); };
  $('settings').addEventListener('click', e => { if (e.target === $('settings')) $('settings').close(); });
}

// ── install as an app (Chrome fires beforeinstallprompt when the page is installable) ──
let installEvent = null;
const standalone = () => matchMedia('(display-mode: standalone)').matches;
const dismissed = () => { try { return localStorage.getItem('bhm-install-x') === '1'; } catch { return false; } };
function installUI() {
  $('installBar').hidden = !installEvent || standalone() || dismissed();
  $('installBtn').hidden = !installEvent;
  $('installHint').textContent = standalone()
    ? 'האפליקציה מותקנת ✓'
    : installEvent ? ''
    : 'אם אין כפתור התקנה: פתחו את הקישור בדפדפן כרום עצמו (לא מתוך וואטסאפ, מייל וכו׳ — שם בוחרים ⋮ ← „פתיחה בכרום“), ואז בתפריט ⋮ בוחרים „התקנת אפליקציה“ או „הוספה למסך הבית“.';
}
async function install() {
  if (!installEvent) return;
  installEvent.prompt();
  await installEvent.userChoice;
  installEvent = null; installUI();
}
addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvent = e; installUI(); });
addEventListener('appinstalled', () => { installEvent = null; installUI(); toast('הותקן ✓'); });

let toastTimer;
function toast(text) {
  $('toast').textContent = text; $('toast').classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('show'), 1400);
}

// ── keep the screen on while reading ──
let lock = null;
async function wake() {
  try { if (document.visibilityState === 'visible' && !lock) { lock = await navigator.wakeLock?.request('screen'); lock?.addEventListener('release', () => { lock = null; }); } } catch {}
}

let lastKey = null;
function tick() { const k = today().key; if (k !== lastKey) { lastKey = k; render(); } }
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { tick(); wake(); } });
setInterval(tick, 60_000);

applyLook();
bind();
installUI();
lastKey = today().key;
render();
wake();

if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js');
