# Quick start

## 1. Start the app

**The Windows app:** unzip `FTIR-Contamination-Analyzer-2.0.0-windows.zip`, open the folder and double-click
**FTIR Contamination Analyzer.exe**. It needs no Python. Keep the files in the folder together.

The app is not signed yet, so Windows may say *Windows protected your PC*. Click **More info → Run anyway**.

**From the source folder:** double-click `run_analyzer.bat`. The first start installs what the app needs, once.

## 2. Try it with the demo

Click the flask button at the top. The app analyses 20 demo spectra. Click one in the list to see its result.

**☰ → Help → Take the tour** shows every part of the app with real data, and keeps nothing.

## 3. Open your own spectra

Click **Open spectra**, or drop files on the window. It reads `.csv`, `.txt`, `.dpt`, JCAMP-DX (`.jdx`, `.dx`) and Bruker
OPUS (`.0`, `.1` ...). Your files are only read, never changed.

Say how each file was measured, ATR or transmission. The app remembers it for that exact file.

## 4. Read the result

| You see | It means | What to do |
|---|---|---|
| **Probable** | A high score, clearly ahead of the next material | Look at the raw spectrum, then sign |
| **Weak** | Similar, but not shown to be the same | Read the bands, shown under the result |
| **No reliable match** | Nothing in the library is similar enough | Read the bands by hand, or add a reference |
| **Measure again** (red) | The spectrum is too poor to rely on | Follow the reason given, and measure again |

The verdict is a suggestion. A person checks the raw spectrum and decides.

## 5. Write the report

Click the export button or press `Ctrl+E`. Choose a folder, enter your name and the tool or area, and sign if you like. You get a PDF, a web
page and an Excel table, and the run is added to the audit log.

## 6. Keep the results trustworthy

- **Check the instrument.** Measure a polystyrene film in transmission, then use **Quality → Check a film…**
- **Have a second person review.** Each exported report waits under **Quality**. A different person reads it and records
  a decision.
- **Add your own references.** A reference measured on your instrument works better than one from elsewhere. Use
  **Add to library…** on a result. The app checks that it can still tell your materials apart before it saves anything.
- **Watch for repeats.** **Trends** shows a material that keeps coming back on one tool. Enter the tool or area at export.

## Where things are kept

Records are in the `records` folder next to the app, or in `FTIR Analyzer records` in your home folder for an installed
copy. To share them across a lab, set the environment variable `FTIR_ANALYZER_RECORDS` to a shared folder. Rows are only
added to these files, so do not edit them by hand.
