// Spot-checks calendar.js against known 5787 dates.  Usage: node tools/test-calendar.mjs
import { dayInfo, flags, formatHebrew, sunset } from '../calendar.js';
const S = { lshem: true, zimun: 'none', ten: false, guest: false, meal: 'none' };
const cases = [
  ['2026-09-12', 'rh', f => f.rh && f.yomTov && f.yv_rh && !f.rc],       // א תשרי, Shabbat
  ['2026-09-26', 'sukkot YT', f => f.sukkot && f.yomTov && f.yv_sukkot],  // ט״ו תשרי
  ['2026-09-28', 'chol hamoed', f => f.cholHamoed && f.sukkot && f.musaf],
  ['2026-10-03', 'shemini', f => f.yv_shemini && f.yomTov && !f.sukkot],  // כ״ב תשרי
  ['2026-10-11', 'RC 30 Tishri', f => f.rc && f.yv_rc],
  ['2026-12-05', 'chanukah d1', f => f.chanukah && f.nisim],             // כ״ה כסלו
  ['2026-12-12', 'chanukah d8', f => f.chanukah],
  ['2026-12-13', 'after chanukah', f => !f.chanukah],
  ['2027-03-23', 'purim (Adar II)', f => f.purim && f.nisim],
  ['2027-02-21', 'purim katan', f => !f.purim],
  ['2027-04-22', 'pesach d1', f => f.yomTov && f.yv_pesach],
  ['2027-04-24', 'chol hamoed pesach (shabbat)', f => f.cholHamoed && f.shabbat && f.yv_pesach],
  ['2027-06-11', 'shavuot', f => f.yv_shavuot && f.yomTov],
  ['2026-09-23', 'weekday', f => !f.musaf && !f.yaaleh && !f.nisim],
];
let fail = 0;
for (const [d, name, ok] of cases) {
  const [y, m, dd] = d.split('-').map(Number);
  const info = dayInfo(new Date(y, m - 1, dd));
  const pass = ok(flags(info, S));
  if (!pass) fail++;
  console.log(pass ? '✓' : '✗', d, formatHebrew(info.h), name);
}
const ss = sunset(new Date(2026, 8, 23), 31.778, 35.235);
console.log('Jerusalem sunset 2026-09-23 UTC:', ss.toISOString().slice(11, 16), '(expected ≈15:40)');
process.exit(fail ? 1 : 0);
