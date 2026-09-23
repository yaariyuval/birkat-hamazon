# ברכת המזון

A small offline web app (PWA) with ברכת המזון in נוסח עדות המזרח. The additions for the day are switched on automatically from the Hebrew date: רצה, יעלה ויבוא (with the right holiday), על הניסים, the holiday הרחמן lines, and מגדיל/מגדול.

- **Text:** from [Wikisource](https://he.wikisource.org/wiki/סידור/נוסח_עדות_המזרח/ברכת_המזון) (CC BY-SA). `node tools/verify-text.mjs` checks every string against `source.wiki` and lists the typo fixes applied on purpose.
- **Calendar:** the browser's built-in Hebrew calendar (`Intl`). After sunset the app moves to the next day. Sunset is computed for Jerusalem, or for your location if you share it. `node tools/test-calendar.mjs` spot-checks known dates.
- **Fonts:** Culmus STAM Sefarad/Ashkenaz, Keter YG and Frank Ruehl (GPL with font exception), and Schwarz STAM Ari. `tools/build-fonts.py` builds them: it merges in vowels and punctuation from Frank Ruehl CLM, and it makes "סת״ם סידור" (Stam Ashkenaz with straight, ball-topped תגים like the user's siddur). Every font also gets pieces of ה so the Name can be drawn with its ה stretched and אדני inside. The script needs `pip install -r tools/requirements.txt`.
- **כוונות האר״י** (optional, in settings): verbatim quotes from Pri Etz Chaim (Gate of the Sabbath 24), Sha'ar HaMitzvot (Eikev) and Sha'ar HaKavanot (Morning Prayers 14–17). All three are public-domain texts from Sefaria and are saved in `sources/`. The quotes follow the date: הוי"ה on Shabbat, ל"ה letters on Rosh Chodesh, and the weekday א"ל name at the end of ברכה ג׳.
- **Install:** open the site in Chrome on Android, tap ⋮, then **Install app**.
