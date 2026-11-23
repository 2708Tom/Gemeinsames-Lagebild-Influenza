#!/bin/zsh
# Gemeinsames Lagebild Influenza (Mac): neueste RKI-Daten holen, Lagebild neu rechnen und öffnen.
cd "${0:A:h}" || exit 1

einrichten() {
  rm -rf .venv
  python3 -m venv .venv || return 1
  .venv/bin/python -m pip install --upgrade pip || return 1
  .venv/bin/python -m pip install -r requirements.txt || return 1
  # XGBoost braucht auf dem Mac libomp. Fehlt sie, die von scikit-learn neben XGBoost legen und dort suchen lassen.
  if ! .venv/bin/python -c "import xgboost" 2>/dev/null; then
    local xgb=(.venv/lib/python3*/site-packages/xgboost/lib(N)) omp=(.venv/lib/python3*/site-packages/sklearn/.dylibs/libomp.dylib(N))
    cp $omp[1] $xgb[1]/ && install_name_tool -add_rpath @loader_path $xgb[1]/libxgboost.dylib && codesign --force -s - $xgb[1]/libxgboost.dylib
  fi
  .venv/bin/python -c "import xgboost" || return 1
  touch .venv/fertig
}

if [[ ! -f .venv/fertig ]]; then
  echo "Erster Start: Python-Umgebung wird eingerichtet (einmalig, einige Minuten) ..."
  einrichten || { echo; echo "Einrichtung fehlgeschlagen (siehe Meldungen oben)."; read "?Enter schließt das Fenster."; exit 1; }
fi
.venv/bin/python 04_Skripte/lagebild_aktualisieren.py && open 08_Lagebild/Lagebild.html
echo; read "?Fertig. Enter schließt das Fenster."
