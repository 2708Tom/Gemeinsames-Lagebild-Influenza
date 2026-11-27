"""Lagebild Influenza erzeugen: rechnet Lage und Prognose für alle Stichtage bis zum Datenstand und schreibt
08_Lagebild/Lagebild.html, eine Seite zum Öffnen im Browser (ohne Internet, ohne Server).

Aufruf aus dem Projektordner:  .venv/bin/python 04_Skripte/lagebild_erzeugen.py
Eingang: Ergebnisse der Notebooks 15 bis 18 und 20 (Länder) und umrisse_lagebild.geojson (Kreis- und Ländergrenzen, aus dem Archiv lagekarte_qgis.py).
Mit neuen Daten (lagebild_daten.csv, abwasser_kreis_woche.csv aus Notebook 15) einfach erneut ausführen.

Lage: dieselben Funktionen wie Notebook 18 (erwartung_ergaenzen, lage_bewerten).
Prognose: Prognosemodell, 1 bis 7 Wochen ab dem Stichtag, mit dem im Benchmark (Notebook 16) gemessenen Fehler.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from lagebild import (erwartung_ergaenzen, stichtag_merkmale, lage_bewerten, last_schwellen, laender_daten, ungewohnte_lage, abwasser_laender, LAENDER, STUFEN, STAND_STUFEN,
                      PROGNOSE_MERKMALE, MAX_H)

BASIS = Path(__file__).resolve().parents[1]
ORDNER = BASIS / "02_Daten" / "aufbereitet"
AUSGABE = BASIS / "08_Lagebild"
ERREGER = {"Influenza": "Influenza"}                # Schlüssel der Website-Daten (seit 16.11.2026 nur Influenza)
AB = pd.Timestamp("2022-10-03")                     # Website ab Saison 2023 (hält die Seite klein)
ABWASSER = {"nicht gemessen": 0, "normal": 1, "erhöht": 2}


def laden():
    lies = lambda name, **kw: pd.read_csv(ORDNER / name, **kw)
    daten = lies("lagebild_daten.csv", parse_dates=["Wochenbeginn"])
    return dict(
        daten=daten,
        prognosen=lies("prognosen.csv.gz", parse_dates=["Anker_Wochenbeginn", "Wochenbeginn"]),
        schwellen=lies("schwellen.csv"),
        abw=lies("abwasser_kreis_woche.csv", parse_dates=["Wochenbeginn"]),
        usp=lies("vergleich_feste_ampel.csv"),                                 # aus Notebook 18, Schritt 6
        benchmark=lies("benchmark_ergebnis.csv"),
        mischung=lies("prognose_mischung.csv", index_col="h"),                 # Notebook 16, Schritt 4b
        ungewohnt=lies("prognose_ungewohnt.csv"),                              # Notebook 16, Schritt 4c
        umrisse=json.loads((ORDNER / "umrisse_lagebild.geojson").read_text(encoding="utf-8")),
    )


def laden_land(e):
    """Dieselben Eingänge für die 16 Länder (Notebook 20)."""
    lies = lambda name, **kw: pd.read_csv(ORDNER / name, **kw)
    return dict(daten=laender_daten(e["daten"]),
                prognosen=lies("land_prognosen.csv.gz", parse_dates=["Anker_Wochenbeginn", "Wochenbeginn"]),
                schwellen=lies("land_schwellen.csv"), abw=abwasser_laender(e["abw"], e["daten"]),   # wöchentlich neu, wie Notebook 20
                benchmark=lies("land_benchmark.csv"), mischung=lies("land_prognose_mischung.csv", index_col="h"),
                ungewohnt=lies("land_prognose_ungewohnt.csv"))


def rechnen(e):
    """Erwartung für die laufende Saison, Bewertung aller Stichtage, Prognose ab jedem Stichtag (Kreise oder Länder)."""
    daten, prognosen = e["daten"], e["prognosen"]
    stand = daten["Wochenbeginn"].max()
    saison = int(daten.loc[daten["Wochenbeginn"] == stand, "Saison"].iloc[0])
    letzte_test = int(prognosen["Saison"].max())
    alle, modelle = erwartung_ergaenzen(daten, prognosen)

    # Prognose: in den Testsaisons aus der rollierenden Prüfung, danach vom aktuellen Modell (Zielwochen auch nach dem Datenstand)
    erste = alle.loc[alle["Saison"] > letzte_test, "Anker_Wochenbeginn"].min()
    m = stichtag_merkmale(daten, pd.date_range(erste - pd.Timedelta(weeks=MAX_H), stand, freq="7D"))
    # Mischung mit „bleibt wie zuletzt“: Gewicht je h aus den Testsaisons (Notebook 16, Schritt 4b)
    m["prog"] = m["lage"] + m["h"].map(e["mischung"]["gewicht"]) * modelle["erw_prognose"].predict(m[PROGNOSE_MERKMALE])
    alt = alle[alle["Saison"] <= letzte_test][["Kreis", "Anker_Wochenbeginn", "h", "prognose"]].rename(columns={"prognose": "prog"})
    neu = m[["Kreis", "Anker_Wochenbeginn", "h", "prog"]].merge(alt[["Kreis", "Anker_Wochenbeginn", "h"]], how="left", indicator=True)
    prog = pd.concat([alt, neu[neu["_merge"] == "left_only"].drop(columns="_merge")], ignore_index=True)

    grenzen = last_schwellen(daten)
    bloecke = lage_bewerten(alle, e["abw"], e["schwellen"], grenzen)
    assert bloecke["Woche_t"].max() == stand, "Bewertung reicht nicht bis zum Datenstand"
    assert prog.groupby("Kreis")["Anker_Wochenbeginn"].max().eq(stand).all(), "Prognose fehlt am Datenstand"
    return dict(stand=stand, saison=saison, bloecke=bloecke, prog=prog, grenzen=grenzen)


def hinweis_bits(b, stand):
    """1 vorläufig (Nachmeldungen möglich), 4 wenige Fälle, 8 ungewohnte Lage (Prognose unsicher, Notebook 16, Schritt 4c)."""
    bits = np.where(b["Woche_t"] > stand - pd.Timedelta(weeks=3), 1, 0)
    bits |= np.where(b["Faelle"] < 20, 4, 0)
    bits |= np.where(b["ungewohnt"].fillna(False).astype(bool), 8, 0)
    return bits


def umrisse_svg(umrisse, ags_zu_index, breite=560):
    """GeoJSON (EPSG:25832) in SVG-Pfade umrechnen."""
    kreise = [f for f in umrisse["features"] if f["properties"]["art"] == "Kreis"]
    punkte = np.array([p for f in kreise for poly in _polygone(f) for ring in poly for p in ring])
    x0, y0 = punkte.min(axis=0) - 15000
    x1, y1 = punkte.max(axis=0) + 15000
    s = breite / (x1 - x0)
    hoehe = round((y1 - y0) * s)

    def pfad(f):
        teile = []
        for poly in _polygone(f):
            for ring in poly:
                xy = [f"{(x - x0) * s:.1f} {(y1 - y) * s:.1f}" for x, y in ring]
                teile.append("M" + "L".join(xy) + "Z")
        return "".join(teile)

    return dict(breite=breite, hoehe=hoehe,
                kreise=[{"i": ags_zu_index[f["properties"]["AGS"]], "d": pfad(f)} for f in kreise if f["properties"]["AGS"] in ags_zu_index],
                laender=[pfad(f) for f in umrisse["features"] if f["properties"]["art"] == "Land"])


def _polygone(f):
    g = f["geometry"]
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]


def reihen(daten, r, einheiten, widx, benchmark):
    """Inzidenz, Lage, Prognose und Prognosefehler je Einheit (Kreis oder Land) und Woche für die Website."""
    stand = r["stand"]
    kidx = {k: i for i, k in enumerate(einheiten)}
    n_w, n_k = len(widx), len(einheiten)

    def leer():
        return [[None] * n_w for _ in range(n_k)]

    b = r["bloecke"][r["bloecke"]["Woche_t"].between(AB, stand)].copy()
    b = b.merge(ungewohnte_lage(daten).rename(columns={"Wochenbeginn": "Woche_t"}), on=["Kreis", "Woche_t"], how="left")
    b["bits"] = hinweis_bits(b, stand)
    d = daten[daten["Wochenbeginn"].isin(widx)]
    inz = leer()
    for k, w, v in zip(d["Kreis"], d["Wochenbeginn"], d["Inzidenz"]):
        inz[kidx[k]][widx[w]] = round(float(v), 1)

    felder = {f: leer() for f in ["f", "s", "a", "g", "e", "h", "l", "o"]}
    for x in b.itertuples():
        i, j = kidx[x.Kreis], widx[x.Woche_t]
        felder["f"][i][j] = round(float(x.Faktor), 2)
        felder["s"][i][j] = STUFEN.index(x.Stufe)
        felder["a"][i][j] = ABWASSER[x.Abwasser]
        felder["g"][i][j] = round(float(x.Gemeldet), 1)
        felder["e"][i][j] = round(float(x.Erwartet), 1)
        felder["h"][i][j] = int(x.bits)
        felder["l"][i][j] = int(x.Last)
        felder["o"][i][j] = int(x.Massnahme)

    p = r["prog"][r["prog"]["Anker_Wochenbeginn"].between(AB, stand)]
    prog = leer()
    for (k, a), g in p.groupby(["Kreis", "Anker_Wochenbeginn"]):
        werte = g.set_index("h")["prog"].reindex(range(1, MAX_H + 1))
        prog[kidx[k]][widx[a]] = [None if pd.isna(v) else round(float(v), 2) for v in werte]

    bm = benchmark.pivot_table(index="h", columns="Verfahren", values="MAE")
    return dict(inz=inz, lage=felder, prog=prog, mae=[round(float(v), 2) for v in bm["Prognose gemischt"]],
                mae_pers=[round(float(v), 2) for v in bm["Persistenz"]])


def band(mischung):
    """80-%-Bereich um die Prognose je h (Log-Skala, Notebook 16, Schritt 4b)."""
    return {sp: [round(float(v), 3) for v in mischung[sp]] for sp in ["unten", "oben"]}


def bereich_ungewohnt(u):
    """Ungewohnte Lage: Bereich um den Stand je Stufe des Stands und h (Log-Skala, Notebook 16, Schritt 4c)."""
    u = u.sort_values(["stufe", "h"])
    return {"grenzen": list(STAND_STUFEN), **{sp: [[round(float(v), 3) for v in g[sp]] for _, g in u.groupby("stufe")] for sp in ["unten", "oben"]}}


def faktor_grenzen(schwellen):
    """Grenzen der Stufen je Kalendermonat als Faktor gemeldet ÷ erwartet (für die Grafik in der Detailansicht)."""
    s = schwellen.set_index("Monat").reindex(range(1, 13))
    return {sp: [round(float(np.exp(v)), 2) for v in s[sp]] for sp in ["leicht", "deutlich", "deutlich_abw"]}


def daten_fuer_seite(e, r, e_land=None, r_land=None):
    daten, stand = e["daten"], r["stand"]
    wochen = pd.date_range(AB - pd.Timedelta(weeks=26), stand, freq="7D")
    widx = {w: i for i, w in enumerate(wochen)}
    raum_folge = {"Karnevalsstadt": 0, "Kontrollstadt": 1, "Nachbarkreis": 2, "Übernächster Kreis": 3, "Übriger Kreis": 4}
    kreise = daten[daten["Wochenbeginn"] == stand][["Kreis", "AGS", "Raum", "Einwohner", "Land"]].drop_duplicates("Kreis").copy()
    kreise["AGS"] = kreise["AGS"].astype(str).str.zfill(5)
    praefix = ("SK", "LK", "Region", "StädteRegion")
    kreise["kurz"] = [k.split(" ", 1)[1] if k.split(" ", 1)[0] in praefix else k for k in kreise["Kreis"]]
    doppelt = kreise["kurz"].duplicated(keep=False)                     # z. B. SK und LK München: voller Name
    kreise.loc[doppelt, "kurz"] = kreise.loc[doppelt, "Kreis"]
    kreise = kreise.sort_values(["Raum", "Kreis"], key=lambda s: s.map(raum_folge) if s.name == "Raum" else s).reset_index(drop=True)
    n_w = len(wochen)

    seite = {"stand": stand.strftime("%Y-%m-%d"), "wochen": [w.strftime("%Y-%m-%d") for w in wochen],
             "ab": widx[AB], "kreise": [{"name": k, "kurz": ku, "raum": r_, "ew": int(ew)}
                                        for k, ku, r_, ew in zip(kreise["Kreis"], kreise["kurz"], kreise["Raum"], kreise["Einwohner"])],
             "erreger": ERREGER, "inz": {}, "lage": {}, "bund": {}, "prog": {}, "mae": {}, "mae_pers": {}, "band": {}}

    x = reihen(daten, r, list(kreise["Kreis"]), widx, e["benchmark"])
    for feld in ["inz", "lage", "prog", "mae", "mae_pers"]:
        seite[feld]["Influenza"] = x[feld]
    seite["band"]["Influenza"] = band(e["mischung"])
    seite["ungewohnt"] = bereich_ungewohnt(e["ungewohnt"])

    # Deutschland: gemeldete Fälle je 100.000 in der Woche
    bund = daten[daten["Wochenbeginn"].isin(widx)].groupby("Wochenbeginn")[["Faelle", "Einwohner"]].sum()
    seite["bund"]["Influenza"] = [None] * n_w
    for wb, (f, ew) in bund.iterrows():
        seite["bund"]["Influenza"][widx[wb]] = round(float(f / ew * 100_000), 1)

    # Länder (Notebook 20): eigene Lage, Last und Prognose je Land
    if r_land is not None:
        laender = sorted(LAENDER.values())
        ew = e_land["daten"][e_land["daten"]["Wochenbeginn"] == stand].set_index("Kreis")["Einwohner"]
        seite["land"] = {"einheiten": [{"name": n, "ew": int(ew[n])} for n in laender], "inz": {}, "lage": {}, "prog": {}, "mae": {},
                         "mae_pers": {}, "band": {"Influenza": band(e_land["mischung"])}, "ungewohnt": bereich_ungewohnt(e_land["ungewohnt"]), "last_grenzen": {k: round(float(v), 1) for k, v in r_land["grenzen"].items()},
                         "faktor_grenzen": faktor_grenzen(e_land["schwellen"])}
        x = reihen(e_land["daten"], r_land, laender, widx, e_land["benchmark"])
        for feld in ["inz", "lage", "prog", "mae", "mae_pers"]:
            seite["land"][feld]["Influenza"] = x[feld]
        land_nr = {LAENDER[c]: laender.index(LAENDER[c]) for c in LAENDER}
        for kr, code in zip(seite["kreise"], kreise["Land"]):
            kr["land"] = land_nr[LAENDER[code]]

    seite["last_grenzen"] = {k: round(float(v), 1) for k, v in r["grenzen"].items()}
    seite["faktor_grenzen"] = faktor_grenzen(e["schwellen"])
    seite["karte"] = umrisse_svg(e["umrisse"], {a: i for i, a in enumerate(kreise["AGS"])})

    # Mehrwert gegenüber einer festen Ampel: Anteil der Kreise mit Alarm je Monat (Notebook 18, Schritt 6)
    u = e["usp"].set_index("Monat").reindex(range(1, 13))
    seite["usp"] = {"Influenza": {art: [None if pd.isna(v) else round(float(v), 1) for v in u[art]] for art in ["fest", "lagebild"]}}
    return seite


def main():
    e = laden()
    r = rechnen(e)
    e_land = laden_land(e)
    r_land = rechnen(e_land)
    assert r_land["stand"] == r["stand"]
    seite = daten_fuer_seite(e, r, e_land, r_land)
    AUSGABE.mkdir(exist_ok=True)
    vorlage = (Path(__file__).parent / "lagebild_vorlage.html").read_text(encoding="utf-8")
    inhalt = json.dumps(seite, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    datei = AUSGABE / "Lagebild.html"
    datei.write_text(vorlage.replace("/*__DATEN__*/null", inhalt), encoding="utf-8")
    print(f"Datenstand: Woche ab {r['stand']:%d.%m.%Y} | Saison {r['saison']} | {len(seite['wochen']) - seite['ab']} Stichtage")
    print(f"Geschrieben: {datei} ({datei.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
