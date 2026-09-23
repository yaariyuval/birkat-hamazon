import { TEXT } from './text.js';
import { dayInfo, flags, halachicCivilDate, formatHebrew, MANUAL_DAYS } from './calendar.js';

// ── persisted settings (per device; the page works without storage) ──
const DEFAULTS = {
  zimun: 'none', ten: false, meal: 'none', guest: false, lshem: true,
  font: 'sefarad', theme: 'auto', size: 26, showAll: false,
  walled: false, diaspora: false,
  loc: { lat: 31.778, lon: 35.235 },         // Jerusalem until the user shares a location
  override: null,                             // { key: 'YYYY-M-D', mode }
};
const load = () => { try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem('bhm') || '{}') }; } catch { return { ...DEFAULTS }; } };
const S = load();
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
function test(w, f) { return !w || (w[0] === '!' ? !f[w.slice(1)] : !!f[w]); }

function renderLine(line, f) {
  const span = document.createElement('span');
  const parts = typeof line === 'string' ? [line] : line;
  const bits = [];
  for (const p of parts) {
    if (typeof p === 'string') { bits.push(document.createTextNode(p)); continue; }
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
  bits.forEach((b, i) => { if (i && !(b.nodeType === 3 && /^[.,:]/.test(b.data))) span.append(' '); span.append(b); });
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
    let el;
    if (b.type === 'h') {
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
  for (const id of ['ten', 'guest', 'lshem', 'showAll', 'walled', 'diaspora']) $(id).checked = S[id];
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
  for (const id of ['ten', 'guest', 'lshem', 'showAll', 'walled', 'diaspora']) $(id).onchange = e => { S[id] = e.target.checked; save(); render(); };
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
  $('settings').addEventListener('click', e => { if (e.target === $('settings')) $('settings').close(); });
}

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
lastKey = today().key;
render();
wake();

if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js');
