# ברכת המזון

A small offline web app (PWA) with ברכת המזון in נוסח עדות המזרח. The additions for the day are switched on automatically from the Hebrew date: רצה, יעלה ויבוא (with the right holiday), על הניסים, the holiday הרחמן lines, and מגדיל/מגדול.

- **Text:** from [Wikisource](https://he.wikisource.org/wiki/סידור/נוסח_עדות_המזרח/ברכת_המזון) (CC BY-SA). `node tools/verify-text.mjs` checks every string against `source.wiki` and lists the typo fixes applied on purpose.
- **Calendar:** the browser's built-in Hebrew calendar (`Intl`). After sunset the app moves to the next day. Sunset is computed for Jerusalem, or for your location if you share it. `node tools/test-calendar.mjs` spot-checks known dates.
- **Fonts:** Culmus STAM Sefarad/Ashkenaz, Keter YG and Frank Ruehl (GPL with font exception) and Schwarz STAM Ari. Vowel marks and punctuation are merged in from Frank Ruehl CLM by `tools/build-fonts.py`.
- **Install:** open the site in Chrome on Android, tap ⋮, then **Install app**.
