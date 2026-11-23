"""Lagebild mit aktuellen Daten: lädt die neuesten offenen Daten und rechnet das Lagebild neu.

Aufruf aus dem Projektordner:  .venv/bin/python 04_Skripte/lagebild_aktualisieren.py
  --nur-abruf      nur Daten laden
  --ohne-abruf     nur neu rechnen (Notebooks 01, 03, 15 und lagebild_erzeugen.py; Notebook 15 baut auch das Abwasser je Kreis)

Abgerufen werden:
  1. RKI SurvStat (Webservice): gemeldete Fälle Influenza je Kreis und Meldewoche, laufendes und
     voriges Jahr (damit Nachmeldungen der letzten Wochen ankommen). Format wie die Exporte in 02_Daten/SurvStat.
  2. RKI AMELAG (GitHub): Abwasser je Klärwerk.
Die Notebooks 16 und 17 (Modellprüfung, Schwellen) laufen nicht wöchentlich, sondern nach Ende einer Saison.

Hinweis: Die jüngsten Meldewochen sind vorläufig, Nachmeldungen sind möglich.
"""
import argparse
import datetime as dt
import html
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

BASIS = Path(__file__).resolve().parents[1]
DATEN = BASIS / "02_Daten"
SKRIPTE = BASIS / "04_Skripte"
SURVSTAT = "https://tools.rki.de/SurvStat/SurvStatWebService.svc"
AMELAG = "https://raw.githubusercontent.com/robert-koch-institut/Abwassersurveillance_AMELAG/main/amelag_einzelstandorte.tsv"
KRANKHEIT = {"Influenza": "Influenza, saisonal"}


def laden(url, daten=None, kopf=None):
    anfrage = urllib.request.Request(url, data=daten, headers=kopf or {"User-Agent": "lagebild-skript"})
    for versuch in range(3):                                          # bei Netzwerkfehlern bis zu 3 Versuche
        try:
            return urllib.request.urlopen(anfrage, timeout=300).read()
        except Exception:
            if versuch == 2:
                raise
            time.sleep(10)


# --- 1. SurvStat --------------------------------------------------------------------------------------------
def survstat_abfrage(erreger, jahr):
    """Fälle je Kreis (Zeilen) und Meldewoche (Spalten) eines Jahres, wie die Exporte in 02_Daten/SurvStat."""
    def filt(dim, hier, werte):
        liste = "".join(f"<m:string>{escape(w)}</m:string>" for w in werte)
        return ("<m:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>"
                f"<m:Key><m:DimensionId>{dim}</m:DimensionId><m:HierarchyId>{hier}</m:HierarchyId></m:Key>"
                f"<m:Value>{liste}</m:Value></m:KeyValueOfFilterCollectionKeyFilterMemberCollectionb2rWaiIW>")
    filter_ = (filt("[PathogenOut].[KategorieNz]", "[PathogenOut].[KategorieNz].[Krankheit DE]",
                    [f"[PathogenOut].[KategorieNz].[Krankheit DE].&[{KRANKHEIT[erreger]}]"])
               + filt("[ReferenzDefinition]", "[ReferenzDefinition].[ID]", ["[ReferenzDefinition].[ID].&[1]"])
               + filt("[ReportingDate]", "[ReportingDate].[WeekYear]", [f"[ReportingDate].[WeekYear].&[{jahr}]"]))
    aktion = "GetOlapData"
    umschlag = (
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:s="http://tools.rki.de/SurvStat/" '
        'xmlns:m="http://schemas.datacontract.org/2004/07/Rki.SurvStat.WebService.Contracts.Mdx">'
        '<soap:Header xmlns:a="http://www.w3.org/2005/08/addressing">'
        f'<a:Action>http://tools.rki.de/SurvStat/SurvStatWebService/{aktion}</a:Action><a:To>{SURVSTAT}</a:To></soap:Header>'
        f"<soap:Body><s:GetOlapData><s:request><m:ColumnHierarchy>[ReportingDate].[Week]</m:ColumnHierarchy><m:Cube>SurvStat</m:Cube>"
        f"<m:HierarchyFilters>{filter_}</m:HierarchyFilters>"
        "<m:IncludeNullColumns>true</m:IncludeNullColumns><m:IncludeNullRows>false</m:IncludeNullRows>"
        "<m:IncludeTotalColumn>false</m:IncludeTotalColumn><m:IncludeTotalRow>false</m:IncludeTotalRow>"
        "<m:Language>German</m:Language><m:Measures>Count</m:Measures>"
        "<m:RowHierarchy>[DeutschlandNodes].[Kreise71Web].[CountyKey71]</m:RowHierarchy></s:request></s:GetOlapData>"
        "</soap:Body></soap:Envelope>")
    antwort = laden(SURVSTAT, umschlag.encode("utf-8"), {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="http://tools.rki.de/SurvStat/SurvStatWebService/{aktion}"'}).decode("utf-8")
    spalten = [html.unescape(c) for c in re.findall(r"<b:QueryResultColumn><b:Caption>([^<]*)</b:Caption>", antwort)]
    zeilen = []
    for name, werte in re.findall(r"<b:QueryResultRow><b:Caption>([^<]*)</b:Caption>.*?<b:Values>(.*?)</b:Values>", antwort, re.S):
        zahlen = re.findall(r"<b:string(?:/>|>([^<]*)</b:string>)", werte)
        zeilen.append([html.unescape(name)] + [int(float(z.replace(".", "").replace(",", "."))) if z else 0 for z in zahlen])
    tabelle = pd.DataFrame(zeilen, columns=["Kreis"] + spalten).drop(columns=["Gesamt"], errors="ignore")
    assert len(tabelle) > 300, f"SurvStat lieferte nur {len(tabelle)} Kreise"
    return tabelle


def survstat_schreiben(tabelle, datei):
    """Im Format der SurvStat-Exporte (UTF-16, Tabulator, Kopfzeile + Wochenzeile), damit Notebook 01 es liest."""
    wochen = [f"{int(c):02d}" for c in tabelle.columns[1:]]
    zeilen = ["Kreis\tMeldewoche", "\t" + "\t".join(wochen)]
    zeilen += ["\t".join([r[0]] + [str(v) for v in r[1:]]) for r in tabelle.itertuples(index=False)]
    datei.write_text("\r\n".join(zeilen) + "\r\n", encoding="utf-16")


def survstat_abrufen():
    heute = dt.date.today()
    jahre = sorted({heute.isocalendar()[0], (heute - dt.timedelta(weeks=8)).isocalendar()[0], heute.isocalendar()[0] - 1})
    for erreger in KRANKHEIT:
        for jahr in jahre:
            datei = DATEN / "SurvStat" / f"{erreger}_{jahr}.csv"
            tabelle = survstat_abfrage(erreger, jahr)
            survstat_schreiben(tabelle, datei)
            faelle = f"{tabelle.iloc[:, 1:].to_numpy().sum():,}".replace(",", ".")
            berlin = tabelle["Kreis"].str.startswith("SK Berlin")             # SurvStat führt Berlin als 12 Bezirke, Notebook 01 fasst sie zusammen
            kreise = (~berlin & tabelle["Kreis"].ne("Unbekannt")).sum() + berlin.any()
            print(f"SurvStat {erreger} {jahr}: {kreise} Kreise (Berlin aus {berlin.sum()} Bezirken), {faelle} Fälle")


# --- 2. AMELAG ----------------------------------------------------------------------------------------------
def amelag_abrufen():
    inhalt = laden(AMELAG)
    datei = DATEN / "AMELAG" / "amelag_einzelstandorte.tsv"
    neu = datei.with_suffix(".neu")
    neu.write_bytes(inhalt)
    test = pd.read_csv(neu, sep="\t", usecols=["standort", "datum", "typ"], parse_dates=["datum"])
    assert {"Influenza A+B"} <= set(test["typ"]), "AMELAG-Datei unerwartet"
    neu.replace(datei)
    print(f"AMELAG: {test['standort'].nunique()} Standorte, Messungen bis {test['datum'].max():%d.%m.%Y}")


# --- 3. Neu rechnen -----------------------------------------------------------------------------------------
def neu_rechnen():
    ablage = BASIS / "08_Lagebild" / "Notebook-Läufe"                        # ausgeführte Kopien, Originale bleiben leer
    ablage.mkdir(parents=True, exist_ok=True)
    for nb in ["01_Meldedaten_einlesen.ipynb", "03_Bevoelkerung_Inzidenz.ipynb", "15_Lagebild_Daten.ipynb"]:
        print("Rechne", nb)
        lauf = subprocess.run([sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute", "--output-dir", str(ablage), nb],
                              cwd=SKRIPTE, capture_output=True, text=True)
        if lauf.returncode:
            sys.exit(f"Fehler in {nb}:\n{lauf.stderr[-3000:]}")
    subprocess.run([sys.executable, str(SKRIPTE / "lagebild_erzeugen.py")], cwd=BASIS, check=True)


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arg.add_argument("--nur-abruf", action="store_true")
    arg.add_argument("--ohne-abruf", action="store_true")
    a = arg.parse_args()
    if not a.ohne_abruf:
        survstat_abrufen()
        amelag_abrufen()
    if not a.nur_abruf:
        neu_rechnen()
