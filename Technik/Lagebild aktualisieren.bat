@echo off
rem Gemeinsames Lagebild Influenza (Windows): neueste RKI-Daten holen, Lagebild neu rechnen und oeffnen.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\fertig" goto rechnen
echo Erster Start: Python-Umgebung wird eingerichtet (einmalig, einige Minuten) ...
if exist ".venv" rmdir /s /q ".venv"
py -3 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" goto ohnepython
".venv\Scripts\python.exe" --version
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fehler
echo.> ".venv\fertig"
:rechnen
".venv\Scripts\python.exe" 04_Skripte\lagebild_aktualisieren.py
if errorlevel 1 goto fehler
start "" "08_Lagebild\Lagebild.html"
echo.
echo Fertig.
pause
exit /b 0
:ohnepython
echo Python 3 wurde nicht gefunden. Bitte Python 3 von https://www.python.org installieren
echo und dabei "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
pause
exit /b 1
:fehler
echo.
echo Es ist ein Fehler aufgetreten (siehe Meldungen oben).
pause
exit /b 1
