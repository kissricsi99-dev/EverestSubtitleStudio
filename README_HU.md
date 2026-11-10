# Everest Subtitle Studio – első fejlesztői változat

Windowsos, offline használatra tervezett magyar/angol feliratkészítő és szerkesztő.

## Funkciók az első változatban
- MP3/MP4/WAV/M4A/MKV/MOV és további médiafájlok megnyitása
- Faster-Whisper beszédfelismerés CPU INT8 módban
- Magyar, angol vagy automatikus nyelvfelismerés
- Large v3 / Medium / Small modellválasztás
- Szóidőbélyegek és automatikus felirattagolás
- 10 szó, 42 karakter/sor, maximum 2 sor alapérték
- Feliratszöveg és időzítés szerkesztése
- Felirat kettévágása a kurzornál vagy a kiválasztott szó előtt
- Szomszédos feliratok összevonása
- Idővonalon a blokkok húzása és széleinek állítása
- Projekt mentése .evss formátumban
- SRT export UTF-8 kódolással

## Fontos megjegyzések
1. Az alkalmazás első indításakor a kiválasztott Whisper modell letöltéséhez internet szükséges. A modell letöltése után az átírás offline működik.
2. A Large v3 a Ryzen 3 3200G processzoron lassú lehet. A CPU INT8 beállítás a 2 GB-os GT 1030 helyett a processzort használja.
3. Ez egy korai MVP/prototípus. A szó szerinti szövegvágás jelenleg az eredeti felirategység időtartamán belül arányos időpontot becsül; a következő fejlesztési körben meg kell őrizni a szó-időbélyeg adatokat a szerkesztőben is, hogy a vágások tényleges szóhatárokra kerüljenek.
4. A projektfájl mentése és az SRT export működik; projektfájl visszatöltése, témaváltás, részletes undo/redo, és teljesen pontos szóhatár-vágás még fejlesztendő.

## GitHub Actions build
1. Töltsd fel a teljes mappatartalmat egy GitHub repository-ba.
2. A `.github/workflows/build-windows.yml` fájl útvonala pontosan ez legyen.
3. GitHub → Actions → Build Windows EXE → Run workflow.
4. Sikeres futás után az Artifacts részből töltsd le az `EverestSubtitleStudio-Windows` csomagot.

## Helyi build (Python 3.11 szükséges)
Futtasd a `build_windows.bat` fájlt.
