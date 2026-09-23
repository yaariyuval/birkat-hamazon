// Hebrew-calendar day context for ברכת המזון, using the browser's built-in Hebrew calendar.

const HEB = new Intl.DateTimeFormat('en-u-ca-hebrew', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

// Hebrew date of a civil date (Y-M-D taken in UTC so no time-zone drift).
export function hebrewDate(civil) {
  const utc = new Date(Date.UTC(civil.getFullYear(), civil.getMonth(), civil.getDate(), 12));
  const parts = Object.fromEntries(HEB.formatToParts(utc).map(p => [p.type, p.value]));
  return { day: +parts.day, month: parts.month, year: +parts.year, dow: utc.getUTCDay() };
}

const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

// Sunset (NOAA approximation), returned as a local Date on the civil day of `date`.
export function sunset(date, lat, lon) {
  const rad = Math.PI / 180;
  const start = Date.UTC(date.getFullYear(), 0, 0);
  const n = Math.round((Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) - start) / 864e5);
  const g = 2 * Math.PI / 365 * (n - 1 + 0.5);
  const eqt = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  const ha = Math.acos(Math.cos(90.833 * rad) / (Math.cos(lat * rad) * Math.cos(decl)) - Math.tan(lat * rad) * Math.tan(decl)) / rad;
  const minutesUTC = 720 - 4 * (lon - ha) - eqt;
  return new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) + minutesUTC * 6e4);
}

// The civil date whose Hebrew date is "today" halachically (after sunset → tomorrow).
export function halachicCivilDate(now, loc) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return now >= sunset(today, loc.lat, loc.lon) ? addDays(today, 1) : today;
}

function isChanukah(civil) {
  for (let i = 0; i < 8; i++) {
    const h = hebrewDate(addDays(civil, -i));
    if (h.month === 'Kislev' && h.day === 25) return true;
  }
  return false;
}

function isLeap(year) { return (7 * year + 1) % 19 < 7; }

// Day kind: which holiday (if any) the civil date is, plus shabbat/rosh-chodesh flags.
export function dayInfo(civil, { diaspora = false, walledCity = false } = {}) {
  const h = hebrewDate(civil);
  const { day, month } = h;
  const info = { h, shabbat: h.dow === 6, rc: false, holiday: null, yomTov: false, cholHamoed: false, chanukah: false, purim: false };

  info.rc = day === 30 || (day === 1 && month !== 'Tishri');

  const between = (a, b) => day >= a && day <= b;
  if (month === 'Tishri') {
    if (between(1, 2)) { info.holiday = 'rh'; info.yomTov = true; }
    else if (between(15, 21)) {
      info.holiday = 'sukkot';
      info.yomTov = day === 15 || (diaspora && day === 16);
      info.cholHamoed = !info.yomTov;
    } else if (day === 22 || (diaspora && day === 23)) { info.holiday = 'shemini'; info.yomTov = true; }
  } else if (month === 'Nisan' && between(15, diaspora ? 22 : 21)) {
    info.holiday = 'pesach';
    info.yomTov = [15, 21].includes(day) || (diaspora && [16, 22].includes(day));
    info.cholHamoed = !info.yomTov;
  } else if (month === 'Sivan' && (day === 6 || (diaspora && day === 7))) {
    info.holiday = 'shavuot'; info.yomTov = true;
  }

  info.chanukah = isChanukah(civil);
  const purimMonth = isLeap(h.year) ? 'Adar II' : 'Adar';
  info.purim = month === purimMonth && day === (walledCity ? 15 : 14);
  return info;
}

// Manual day kinds offered in the override picker (value → partial dayInfo).
export const MANUAL_DAYS = {
  weekday:        { label: 'יום חול' },
  shabbat:        { label: 'שבת', shabbat: true },
  rc:             { label: 'ראש חודש', rc: true },
  chanukah:       { label: 'חנוכה', chanukah: true },
  purim:          { label: 'פורים', purim: true },
  rh:             { label: 'ראש השנה', holiday: 'rh', yomTov: true },
  sukkotYT:       { label: 'סוכות (יום טוב)', holiday: 'sukkot', yomTov: true },
  sukkotCH:       { label: 'חול המועד סוכות', holiday: 'sukkot', cholHamoed: true },
  shemini:        { label: 'שמיני עצרת', holiday: 'shemini', yomTov: true },
  pesachYT:       { label: 'פסח (יום טוב)', holiday: 'pesach', yomTov: true },
  pesachCH:       { label: 'חול המועד פסח', holiday: 'pesach', cholHamoed: true },
  shavuot:        { label: 'שבועות', holiday: 'shavuot', yomTov: true },
};

// Flags consumed by text.js `w` keys.
export function flags(info, settings) {
  const f = {
    shabbat: !!info.shabbat,
    rc: !!info.rc,
    rh: info.holiday === 'rh',
    sukkot: info.holiday === 'sukkot',
    yomTov: !!info.yomTov,
    cholHamoed: !!info.cholHamoed,
    chanukah: !!info.chanukah,
    purim: !!info.purim,
  };
  f.nisim = f.chanukah || f.purim;
  f.yaaleh = f.rc || f.yomTov || f.cholHamoed;
  const yv = info.holiday || (f.rc ? 'rc' : null);
  for (const k of ['rc', 'pesach', 'shavuot', 'rh', 'sukkot', 'shemini']) f['yv_' + k] = f.yaaleh && yv === k;
  f.musaf = f.shabbat || f.rc || f.yomTov || f.cholHamoed;
  f.moed = f.yomTov || f.cholHamoed;
  f.forgot = f.shabbat || f.rc || f.moed;

  f.lshem = settings.lshem;
  f.zimun = settings.zimun !== 'none';
  f.zimun_main = settings.zimun === 'main';
  f.zimun_alt = settings.zimun === 'alt';
  f.zimun_morocco = settings.zimun === 'morocco';
  f.ten = f.zimun && settings.ten;
  f.guest = settings.guest;
  f.wedding = settings.meal === 'wedding';
  f.brit = settings.meal === 'brit';
  return f;
}

// ── Hebrew numerals ──
const ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט'];
const TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ'];
const HUNDREDS = ['', 'ק', 'ר', 'ש', 'ת', 'תק', 'תר', 'תש', 'תת', 'תתק'];
export function gematria(n) {
  let s = HUNDREDS[Math.floor(n / 100)] + TENS[Math.floor(n % 100 / 10)] + ONES[n % 10];
  s = s.replace('יה', 'טו').replace('יו', 'טז');
  return s.length === 1 ? s + '׳' : s.slice(0, -1) + '״' + s.slice(-1);
}
const MONTHS_HE = {
  Tishri: 'תשרי', Heshvan: 'חשון', Kislev: 'כסלו', Tevet: 'טבת', Shevat: 'שבט', Adar: 'אדר', 'Adar I': 'אדר א׳',
  'Adar II': 'אדר ב׳', Nisan: 'ניסן', Iyar: 'אייר', Sivan: 'סיון', Tamuz: 'תמוז', Av: 'אב', Elul: 'אלול',
};
export const formatHebrew = h => `${gematria(h.day)} ${MONTHS_HE[h.month] ?? h.month} ${gematria(h.year % 1000)}`;
