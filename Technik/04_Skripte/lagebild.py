"""Bausteine für das Lagebild Influenza (Notebooks 16 bis 20, lagebild_erzeugen.py). Erklärungen in den Notebooks.

Ablauf:
1. Paare: aus der Wochentabelle werden Paare aus Stichtag und Zielwoche (Stichtag + h Wochen, h = 1 bis 7).
2. Zwei XGBoost-Modelle sagen die Veränderung der logarithmierten Inzidenz vom Stichtag bis zur Zielwoche vorher:
   Prognosemodell (nur Wissen vom Stichtag) und Einordnungsmodell (kennt zusätzlich das übrige Bundesgebiet in der Zielwoche).
3. Abweichung: Wochen t−2 bis t gegen die Erwartung des Einordnungsmodells vom Stand t−4, als Faktor gemeldet ÷ erwartet.
4. Stufe: leicht / deutlich über der Erwartung ab dem 90- bzw. 98-%-Wert, je Kalendermonat, aus den Saisons ab 2023.
   Ist das Abwasser erhöht, gilt „deutlich“ schon ab dem 95-%-Wert (Abwasser verstärkt, ist aber keine Voraussetzung).
5. Last (wie viel Influenza da ist, Grenzen nach der Moving Epidemic Method) × Stufe → Lagestufe.

Fachliche Annahmen (Notebook 21, seit 19.11.2026): Testsprung seit der Pandemie (Schwellen und Last nur aus Saisons ab 2023),
MEM für die Last. Geprüft und am 22.11.2026 nicht übernommen, weil der Nutzen im Bereich der Zufallsschwankung lag:
Merkmal nach_testsprung im Einordnungsmodell, Nachbarkreise im Prognosemodell. Die Funktionen dafür (nachbarn_*, Spalten
nachbar_* und nach_testsprung) bleiben für Notebook 21 erhalten.
"""
import numpy as np
import pandas as pd
import xgboost as xgb

MAX_H = 7                                   # Vorhersage bis 7 Wochen nach dem Stichtag
BEGINN = "2014-12-29"                       # erster Stichtag
PANDEMIE = [2021, 2022]                     # Saisons ohne Grippewelle: zählen nicht für Schwellen; das Modell lernt aus allen Saisons
TESTSPRUNG = pd.Timestamp("2022-10-03")     # Beginn der Saison 2023: seit der Pandemie wird viel mehr getestet (Notebook 21)

# Vergleichsgröße „bund_…“: Inzidenz im Bundesgebiet ohne den eigenen Kreis. Nachbarkreise und nach_testsprung: geprüft in
# Notebook 21, nicht übernommen (22.11.2026). Die Reihenfolge der Merkmale nicht ändern: XGBoost zieht je Baum zufällig
# Spalten, eine andere Reihenfolge ergibt andere Bäume und einen um bis zu rund 1 % anderen Fehler.
PROGNOSE_MERKMALE = ["lage", "trend", "bund_lage", "bund_trend", "h", "Meldewoche", "Kreis_kat"]
EINORDNUNG_MERKMALE = ["lage", "trend", "bund", "bund_aenderung", "h", "Meldewoche", "Kreis_kat"]
MODELLE = {"erw_prognose": PROGNOSE_MERKMALE, "erw_einordnung": EINORDNUNG_MERKMALE}
XGB_EINSTELLUNGEN = dict(n_estimators=400, learning_rate=0.05, max_depth=4, subsample=0.8, colsample_bytree=0.8,
                         enable_categorical=True, tree_method="hist", random_state=1)


# ---------------------------------------------------------------------------------------------------
# 1. und 2. Paare und Modelle
# ---------------------------------------------------------------------------------------------------
def _wochen(daten, nachbarn=None):
    """Wochentabelle mit logarithmierter Inzidenz, Trend und Bundesgebiet ohne den eigenen Kreis.
    nachbarn (Kreis → Liste der Nachbarkreise): zusätzlich die Inzidenz der Nachbarkreise zusammen und ihr Trend."""
    d = daten.sort_values(["Kreis", "Wochenbeginn"]).reset_index(drop=True).copy()
    d["log_inz"] = np.log1p(d["Inzidenz"])
    k = d.groupby("Wochenbeginn").agg(F=("Faelle", "sum"), E=("Einwohner", "sum")).reset_index()
    d = d.merge(k, on="Wochenbeginn").sort_values(["Kreis", "Wochenbeginn"]).reset_index(drop=True)
    d["bund_roh"] = np.log1p((d["F"] - d["Faelle"]) / (d["E"] - d["Einwohner"]) * 100_000)
    je_kreis = d.groupby("Kreis")
    d["trend_roh"] = d["log_inz"] - je_kreis["log_inz"].shift(2)            # Veränderung in den zwei Wochen davor
    d["bund_trend_roh"] = d["bund_roh"] - je_kreis["bund_roh"].shift(2)
    if nachbarn is not None:
        d = d.merge(_nachbar_inzidenz(d, nachbarn), on=["Kreis", "Wochenbeginn"]).sort_values(["Kreis", "Wochenbeginn"]).reset_index(drop=True)
        d["nachbar_trend_roh"] = d["nachbar_roh"] - d.groupby("Kreis")["nachbar_roh"].shift(2)
    return d


def _nachbar_inzidenz(d, nachbarn):
    """Je Kreis und Woche: Fälle und Einwohner aller Nachbarkreise zusammen → logarithmierte Inzidenz (wie beim Bundesgebiet)."""
    f = d.pivot(index="Wochenbeginn", columns="Kreis", values="Faelle")
    e = d.pivot(index="Wochenbeginn", columns="Kreis", values="Einwohner")
    w = pd.DataFrame(0.0, index=f.columns, columns=f.columns)          # w[k, n] = 1, wenn n Nachbar von k ist
    for k, liste in nachbarn.items():
        w.loc[k, list(liste)] = 1.0
    inz = np.log1p((f.values @ w.values.T) / (e.values @ w.values.T) * 100_000)
    return pd.DataFrame(inz, index=f.index, columns=f.columns).stack().rename("nachbar_roh").reset_index()

def paare_bilden(daten, nachbarn=None):
    """Paare (Stichtag, Zielwoche) mit den Merkmalen beider Modelle und der Zielgröße.
    nachbarn: siehe _wochen; ohne sie fehlen die Spalten nachbar_lage und nachbar_trend."""
    d = _wochen(daten, nachbarn)
    je_kreis = d.groupby("Kreis")
    ziel_spalten = ["Wochenbeginn", "Saison", "Woche_rel", "Meldewoche", "Faelle", "Einwohner", "log_inz", "bund_roh"]
    teile = []
    for h in range(1, MAX_H + 1):
        p = d[["Kreis", "Raum"]].copy()
        p["h"] = h
        p["Anker_Wochenbeginn"] = d["Wochenbeginn"]
        p["lage"], p["trend"] = d["log_inz"], d["trend_roh"]                 # Stand und Trend am Stichtag
        p["bund_lage"], p["bund_trend"] = d["bund_roh"], d["bund_trend_roh"]
        if nachbarn is not None:                                            # Nachbarkreise am Stichtag (nie die Zielwoche)
            p["nachbar_lage"], p["nachbar_trend"] = d["nachbar_roh"], d["nachbar_trend_roh"]
        for s in ziel_spalten:                                              # Werte der Zielwoche, h Wochen später
            p[s] = je_kreis[s].shift(-h)
        p["bund"] = p.pop("bund_roh")                                       # Bundesgebiet in der Zielwoche
        p["bund_aenderung"] = p["bund"] - p["bund_lage"]
        p["ziel"] = p["log_inz"] - p["lage"]                                # Zielgröße: Veränderung seit dem Stichtag
        p["nach_testsprung"] = (p["Wochenbeginn"] >= TESTSPRUNG).astype(int)  # Zielwoche ab Saison 2023
        teile.append(p)
    paare = pd.concat(teile, ignore_index=True).dropna(subset=["ziel", "trend", "bund_trend"])
    paare = paare[paare["Anker_Wochenbeginn"] >= pd.Timestamp(BEGINN)].reset_index(drop=True)
    paare[["Saison", "Woche_rel"]] = paare[["Saison", "Woche_rel"]].astype(int)
    paare["Kreis_kat"] = pd.Categorical(paare["Kreis"], categories=sorted(daten["Kreis"].unique()))
    return paare


def stichtag_merkmale(daten, stichtage, nachbarn=None):
    """Merkmale des Prognosemodells für Stichtage, deren Zielwochen nach dem Datenstand liegen dürfen
    (für die Zielwoche braucht es nur die Kalenderwoche)."""
    d = _wochen(daten, nachbarn)
    d = d[d["Wochenbeginn"].isin(pd.to_datetime(stichtage))].dropna(subset=["trend_roh", "bund_trend_roh"])
    teile = []
    for h in range(1, MAX_H + 1):
        p = pd.DataFrame({"Kreis": d["Kreis"].values, "h": h, "Anker_Wochenbeginn": d["Wochenbeginn"].values,
                          "lage": d["log_inz"].values, "trend": d["trend_roh"].values,
                          "bund_lage": d["bund_roh"].values, "bund_trend": d["bund_trend_roh"].values})
        if nachbarn is not None:
            p["nachbar_lage"], p["nachbar_trend"] = d["nachbar_roh"].values, d["nachbar_trend_roh"].values
        ziel = p["Anker_Wochenbeginn"] + pd.Timedelta(weeks=h)
        p["Meldewoche"] = ziel.dt.isocalendar().week.astype(int).values
        p["nach_testsprung"] = (ziel >= TESTSPRUNG).astype(int).values
        teile.append(p)
    p = pd.concat(teile, ignore_index=True)
    p["Kreis_kat"] = pd.Categorical(p["Kreis"], categories=sorted(daten["Kreis"].unique()))
    return p


def nachbarn_bestimmen(umrisse, ags_zu_kreis, abstand=700, mindestlaenge=1000):
    """Nachbarkreise aus den vereinfachten Umrissen (GeoJSON, Meter). Die Umrisse sind je Kreis einzeln um bis zu 700 m
    vereinfacht, gemeinsame Randpunkte fehlen daher bei kurzen Grenzen. Deshalb: Zwei Kreise sind Nachbarn, wenn mindestens
    `mindestlaenge` Meter Rand des einen höchstens `abstand` Meter vom Rand des anderen entfernt liegen (Kantenabstand).
    Rückgabe: Kreis → sortierte Liste der Nachbarkreise."""
    kanten = {}
    for f in umrisse["features"]:
        if f["properties"]["art"] != "Kreis" or f["properties"]["AGS"] not in ags_zu_kreis:
            continue
        c = f["geometry"]["coordinates"]
        ringe = [np.array(r, float) for p in ([c] if f["geometry"]["type"] == "Polygon" else c) for r in p]
        kanten[ags_zu_kreis[f["properties"]["AGS"]]] = np.concatenate([np.stack([r[:-1], r[1:]], 1) for r in ringe])

    def nah(punkte, k):                                     # Abstand jedes Punkts zur nächsten Kante von k ≤ abstand?
        a, ab = k[:, 0], k[:, 1] - k[:, 0]
        t = np.clip(((punkte[:, None] - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-9), 0, 1)
        return np.sqrt(((punkte[:, None] - (a + t[..., None] * ab)) ** 2).sum(-1)).min(1) <= abstand

    def gemeinsam(k1, k2):                                  # Länge der Kanten von k1, die ganz nahe am Rand von k2 liegen
        mitte = k1.mean(1)
        n = nah(k1[:, 0], k2) & nah(mitte, k2) & nah(k1[:, 1], k2)
        return np.linalg.norm(k1[n, 1] - k1[n, 0], axis=1).sum()

    box = {k: (v.reshape(-1, 2).min(0) - abstand, v.reshape(-1, 2).max(0) + abstand) for k, v in kanten.items()}
    namen, nachbarn = sorted(kanten), {k: [] for k in kanten}
    for i, k1 in enumerate(namen):
        for k2 in namen[i + 1:]:
            if (box[k1][0] > box[k2][1]).any() or (box[k2][0] > box[k1][1]).any():
                continue
            if max(gemeinsam(kanten[k1], kanten[k2]), gemeinsam(kanten[k2], kanten[k1])) >= mindestlaenge:
                nachbarn[k1].append(k2)
                nachbarn[k2].append(k1)
    return nachbarn


def nachbarn_laden(daten, pfad):
    """Nachbarkreise für die Kreise in daten aus umrisse_lagebild.geojson (pfad)."""
    import json
    ags = daten.drop_duplicates("Kreis").set_index(daten.drop_duplicates("Kreis")["AGS"].astype(str).str.zfill(5))["Kreis"]
    return nachbarn_bestimmen(json.loads(open(pfad, encoding="utf-8").read()), ags.to_dict())


def xgb_trainieren(training, merkmale):
    """Trainiert XGBoost auf der Veränderung seit dem Stichtag."""
    modell = xgb.XGBRegressor(**XGB_EINSTELLUNGEN)
    modell.fit(training[merkmale], training["ziel"])
    return modell


def erwartung_ergaenzen(daten, prognosen, nachbarn=None):
    """Erwartungen für die Saisons nach der letzten Testsaison (laufende Saison). Beide Modelle lernen dafür aus allen
    Saisons bis zur letzten Testsaison, wie im Einsatz. Rückgabe: alle Erwartungen und die beiden Modelle."""
    letzte = prognosen["Saison"].max()
    paare = paare_bilden(daten, nachbarn)
    training, neu = paare[paare["Saison"] <= letzte], paare[paare["Saison"] > letzte].copy()
    modelle = {}
    for spalte, merkmale in MODELLE.items():
        modelle[spalte] = xgb_trainieren(training, merkmale)
        neu[spalte] = neu["lage"] + modelle[spalte].predict(neu[merkmale])
    alle = pd.concat([prognosen, neu.reindex(columns=prognosen.columns)], ignore_index=True)   # „prognose“ (Mischung) nur in Testsaisons
    assert not alle.duplicated(["Kreis", "Anker_Wochenbeginn", "h"]).any()
    return alle, modelle


# Prognose für die Anzeige (Notebook 16, Schritt 4b, 22.11.2026): XGBoost gemischt mit „bleibt wie zuletzt“, je
# Vorhersageweite h ein Gewicht, gewählt nur an früheren Saisons. Der Bereich um die Prognose kommt aus den echten
# Fehlern früherer Saisons: 10- und 90-%-Wert, also 8 von 10 Fällen.
BAND = (0.10, 0.90)


def mischgewichte(v, saisons):
    """Gewicht des Prognosemodells je h (Rest: „bleibt wie zuletzt“) mit dem kleinsten MAE in den Saisons `saisons`.
    v: Spalten Saison, h, log_inz, lage, erw_prognose (Erwartung auf der Log-Skala)."""
    gitter = np.linspace(0, 1, 21)
    g = v[v["Saison"].isin(saisons)]
    return pd.Series({h: gitter[np.argmin([(x["log_inz"] - (w * x["erw_prognose"] + (1 - w) * x["lage"])).abs().mean() for w in gitter])]
                      for h, x in g.groupby("h")})


def prognose_rollierend(v):
    """Spalten gewicht und prognose je Testsaison, Gewichte nur aus früheren Testsaisons ohne Pandemie.
    Ohne frühere Saison (erste Testsaison) gilt XGBoost allein."""
    teile = []
    for J, t in v.groupby("Saison"):
        frueher = [s for s in v["Saison"].unique() if s < J and s not in PANDEMIE]
        w = mischgewichte(v, frueher) if frueher else pd.Series(1.0, index=range(1, MAX_H + 1))
        t = t.assign(gewicht=t["h"].map(w))
        teile.append(t.assign(prognose=t["gewicht"] * t["erw_prognose"] + (1 - t["gewicht"]) * t["lage"]))
    return pd.concat(teile).loc[v.index]


# Ungewohnte Lage (Notebook 16, Schritt 4c, 23.11.2026): Liegt der Stand höher als fast je zuvor in dieser Jahreszeit,
# kennt das Prognosemodell so eine Lage nicht. Dort ist die Prognose viel unsicherer; sie bekommt einen Hinweis und
# einen eigenen, breiteren Bereich.
Q_UNGEWOHNT = 0.99


def ungewohnte_lage(daten, q=Q_UNGEWOHNT):
    """Je Einheit und Woche: Liegt die logarithmierte Inzidenz über dem 99-%-Wert aller Wochen früherer Saisons in
    derselben Jahreszeit (Kalenderwoche ±2)? Nur frühere Saisons, also wie im Einsatz.
    Rückgabe: Kreis, Wochenbeginn, ungewohnt (in der ersten Saison immer False)."""
    d = daten[["Kreis", "Wochenbeginn", "Saison", "Inzidenz"]].copy()
    d["l"], d["kw"] = np.log1p(d["Inzidenz"]), d["Wochenbeginn"].dt.isocalendar().week.astype(int)
    teile = []
    for S, t in d.groupby("Saison"):
        fr = d[d["Saison"] < S]
        if fr.empty:
            teile.append(t.assign(ungewohnt=False))
            continue
        abstand = lambda k: np.minimum((fr["kw"] - k).abs(), 53 - (fr["kw"] - k).abs())
        grenze = {k: fr.loc[abstand(k) <= 2, "l"].quantile(q) for k in range(1, 54)}
        teile.append(t.assign(ungewohnt=t["l"] > t["kw"].map(grenze)))
    return pd.concat(teile)[["Kreis", "Wochenbeginn", "ungewohnt"]]


# In ungewohnter Lage folgt die Anzeige nicht dem Modell, sondern zeigt, wie es in ähnlichen Lagen früherer Saisons
# weiterging: Veränderung seit dem Stichtag, getrennt nach der Höhe des Stands (Fälle je 100.000 und Woche).
STAND_STUFEN = (20, 60)                     # unter 20, 20 bis 60, über 60


def ungewohnt_bereich(v, saisons, mindestens=20):
    """10- und 90-%-Wert von log_inz − lage (Zielwoche gegen Stand am Stichtag) in ungewohnten Fällen der Saisons
    `saisons`, je Stufe des Stands und h. Hat eine Stufe weniger als `mindestens` Fälle, gelten alle Stufen zusammen.
    v: Spalten Saison, h, log_inz, lage, ungewohnt. Rückgabe: stufe, h, unten, oben (Log-Skala, relativ zum Stand)."""
    g = v[v["Saison"].isin(saisons) & v["ungewohnt"]].copy()
    g["stufe"], g["aend"] = np.digitize(np.expm1(g["lage"]), STAND_STUFEN), g["log_inz"] - g["lage"]
    alle = g.groupby("h")["aend"].quantile(list(BAND)).unstack()
    zeilen = []
    for s in range(len(STAND_STUFEN) + 1):
        for h in range(1, MAX_H + 1):
            x = g.loc[(g["stufe"] == s) & (g["h"] == h), "aend"]
            q = x.quantile(list(BAND)).values if len(x) >= mindestens else alle.loc[h].values
            zeilen.append({"stufe": s, "h": h, "unten": q[0], "oben": q[1]})
    return pd.DataFrame(zeilen)


def prognose_band(v, saisons):
    """Bereich um die Prognose je h: 10- und 90-%-Wert der Fehler (gemeldet − Prognose, Log-Skala) in den Saisons `saisons`."""
    g = v[v["Saison"].isin(saisons)]
    q = (g["log_inz"] - g["prognose"]).groupby(g["h"]).quantile(list(BAND)).unstack()
    return q.set_axis(["unten", "oben"], axis=1)


# ---------------------------------------------------------------------------------------------------
# 3. bis 5. Abweichung, Stufe, Last, Lagestufe
# ---------------------------------------------------------------------------------------------------
H_BEWERTUNG = [2, 3, 4]                     # am Stichtag t: Wochen t−2 bis t gegen die Erwartung vom Stand t−4
Q_LEICHT, Q_DEUTLICH, Q_DEUTLICH_ABW = 0.90, 0.98, 0.95     # 98 % ist eine Setzung (Konvention), Sensitivität in Notebook 21
SCHWELLEN_AB = 2023                         # Schwellen nur aus Saisons nach dem Testsprung (Notebook 21, Baustein 1)
STUFEN = ["wie erwartet", "leicht darüber", "deutlich darüber"]
ABWASSER_TYP = "Influenza A+B"              # AMELAG, gemessen seit Oktober 2023


def abwasser_wochen(pfad, kreise, typ=ABWASSER_TYP):
    """Influenza A+B im Abwasser: Mittel der logarithmierten, normalisierten Viruslast je Kreis und Woche."""
    a = pd.read_csv(pfad, sep="\t", parse_dates=["datum"])
    a = a[(a["typ"] == typ) & (a["viruslast_normalisiert"] > 0)].copy()

    def kreis_finden(standort):
        name = standort.split(" (")[0].split("-")[0]
        name = "Berlin" if name.startswith("Berlin") else name
        treffer = sorted((k for k in kreise if k.split(" ", 1)[-1] == name), key=lambda k: not k.startswith("SK "))
        return treffer[0] if treffer else None                    # Klärwerk mit Stadtnamen: kreisfreie Stadt vor Landkreis

    a["Kreis"] = a["standort"].map(kreis_finden)
    a = a.dropna(subset=["Kreis"])
    a["Wochenbeginn"] = a["datum"] - pd.to_timedelta(a["datum"].dt.weekday, unit="D")
    a["log_vl"] = np.log(a["viruslast_normalisiert"])
    return a.groupby(["Kreis", "Wochenbeginn"])["log_vl"].mean().reset_index(), a


def bloecke_bilden(p, abw):
    """Ein Block je Kreis und Stichtag t (Wochen t−2 bis t, Erwartung vom Stand t−4).
    abweichung = Mittel von log(gemeldet) − log(erwartet); Faktor = exp(abweichung), also gemeldet ÷ erwartet.
    abw = Anstieg der Viruslast im Abwasser seit dem Stand t−4, gemittelt über dieselben Wochen."""
    q = p[p["h"].isin(H_BEWERTUNG)].copy()
    q["res"] = q["log_inz"] - q["erw_einordnung"]
    q = q.merge(abw.rename(columns={"Wochenbeginn": "Anker_Wochenbeginn", "log_vl": "vl_anker"}), on=["Kreis", "Anker_Wochenbeginn"], how="left")
    q = q.merge(abw.rename(columns={"log_vl": "vl_ziel"}), on=["Kreis", "Wochenbeginn"], how="left")
    q["abw_anstieg"] = q["vl_ziel"] - q["vl_anker"]
    b = q.sort_values("h").groupby(["Kreis", "Anker_Wochenbeginn"]).agg(
        Raum=("Raum", "first"), Woche_t=("Wochenbeginn", "last"), Saison=("Saison", "last"), Woche_rel=("Woche_rel", "last"),
        Wochen=("h", "size"), Faelle=("Faelle", "sum"), log_inz=("log_inz", "mean"), log_erw=("erw_einordnung", "mean"),
        abweichung=("res", "mean"), abw=("abw_anstieg", "mean")).reset_index()
    b = b[b["Wochen"] == len(H_BEWERTUNG)].drop(columns="Wochen").reset_index(drop=True)
    b["Monat"] = b["Woche_t"].dt.month
    b["Gemeldet"] = np.expm1(b["log_inz"])                         # Inzidenz, Mittel der drei Wochen (Log-Skala)
    b["Erwartet"] = np.expm1(b["log_erw"]).clip(lower=0)
    b["Faktor"] = np.exp(b["abweichung"])
    return b


def schwellen_berechnen(b, nach="Monat", ab=SCHWELLEN_AB, q_deutlich=Q_DEUTLICH):
    """Je Kalendermonat: 90-, 95- und 98-%-Wert der Abweichung, 90-%-Wert des Abwasseranstiegs. Nur Saisons ab `ab`
    (Testsprung), ohne Pandemie-Saisons. nach: Spalte, nach der getrennt wird (Notebook 17 vergleicht damit auch ganzjährige
    und halbjährliche Schwellen). ab=0: alle Saisons ohne Pandemie (Fassung bis 18.11.2026). q_deutlich: nur für die
    Sensitivität in Notebook 21."""
    g = b[~b["Saison"].isin(PANDEMIE) & (b["Saison"] >= ab)].groupby(nach)
    return pd.DataFrame({"leicht": g["abweichung"].quantile(Q_LEICHT), "deutlich": g["abweichung"].quantile(q_deutlich),
                         "deutlich_abw": g["abweichung"].quantile(Q_DEUTLICH_ABW), "abwasser": g["abw"].quantile(Q_LEICHT),
                         "Werte": g.size()}).reset_index()


def stufen_vergeben(b, schwellen, nach="Monat"):
    """Abwasser (erhöht ab dem 90-%-Wert) und Stufe gegenüber der Erwartung: wie erwartet / leicht darüber (ab 90 %) /
    deutlich darüber (ab 98 %, bei erhöhtem Abwasser ab 95 %)."""
    b = b.copy()
    s = schwellen.set_index(nach).reindex(b[nach])
    a = b["abweichung"].values
    abw_hoch = b["abw"].values >= s["abwasser"].values                      # fehlt das Abwasser, ist das False
    b["Abwasser"] = np.where(b["abw"].isna(), "nicht verfügbar", np.where(abw_hoch, "erhöht", "unauffällig"))
    deutlich = (a >= s["deutlich"].values) | ((a >= s["deutlich_abw"].values) & abw_hoch)
    b["Stufe"] = np.select([deutlich, a >= s["leicht"].values], STUFEN[2:0:-1], STUFEN[0])
    return b


# Last = wie viel Influenza da ist, gleiche Skala im Sommer und Winter. Grenzen nach der Moving Epidemic Method (MEM; Vega et al.
# 2013, 2015; R-Paket mem, memmodel): je Saison die n höchsten Wochenwerte (n = 30 ÷ Zahl der Saisons, gerundet), zusammen
# logarithmiert; Grenze = exp(Mittel + z · Standardabweichung) mit z für einseitig 40 % („medium“ → mittel) und 90 % („high“ → hoch).
# Hier je Kreis und Saison, alle Kreise zusammen; Wochenwert wie „Gemeldet“: Mittel der letzten drei Wochen (Log-Skala).
# Saisons ab dem Testsprung (2023); die Fassung bis 18.11.2026 nahm den 25-/90-%-Wert der Saisonspitzen 2016–2026.
LAST_SAISONEN = [2023, 2024, 2025, 2026]
MEM_NIVEAU = {"mittel": 0.40, "hoch": 0.90}         # MEM „very high“ (97,5 %) wird nicht genutzt
LAST = ["niedrig", "mittel", "hoch"]
MASSNAHMEN = ["unauffällig", "erhöht", "auffällig", "stark auffällig"]   # Lagestufen: grün, gelb, orange, rot


def last_schwellen(daten, saisons=LAST_SAISONEN, niveau=MEM_NIVEAU):
    """Grenzen der Last-Stufen nach MEM in Fällen je 100.000 und Woche (Mittel der letzten drei Wochen)."""
    from scipy.stats import norm
    d = daten.sort_values(["Kreis", "Wochenbeginn"])
    drei = np.expm1(d.groupby("Kreis")["Inzidenz"].transform(lambda x: np.log1p(x).rolling(3).mean()))
    n = max(1, round(30 / len(saisons)))                                    # wie mem: i.n.max = -1
    werte = drei[d["Saison"].isin(saisons)].groupby([d["Saison"], d["Kreis"]]).apply(lambda x: x.nlargest(n)).values
    null = (werte <= 0).any()                                               # wie mem: bei Nullwerten log(x + 1)
    lw = np.log(werte + null)
    return pd.Series({stufe: float(np.exp(lw.mean() + norm.ppf(q) * lw.std(ddof=1)) - null) for stufe, q in niveau.items()})


def massnahme(last, deutlich):
    """Matrix Last × Erwartung. last: 0 niedrig, 1 mittel, 2 hoch. deutlich: deutlich über der Erwartung.
    niedrig → unauffällig / erhöht; mittel → erhöht / auffällig; hoch → auffällig / stark auffällig.
    Rückgabe 0 bis 3 (Index in MASSNAHMEN)."""
    last, d = np.asarray(last), np.asarray(deutlich, dtype=bool)
    return np.select([(last == 2) & d, (last == 2) | ((last == 1) & d), (last == 1) | d], [3, 2, 1], 0)


def lage_bewerten(alle, abw, schwellen, grenzen):
    """Alle Kreis-Wochen bewerten: Abweichung, Stufe, Abwasser, Last und Lagestufe."""
    b = stufen_vergeben(bloecke_bilden(alle, abw), schwellen)
    g = b["Gemeldet"].values
    b["Last"] = np.select([g >= grenzen["hoch"], g >= grenzen["mittel"]], [2, 1], 0)
    b["Massnahme"] = massnahme(b["Last"], b["Stufe"] == STUFEN[2])
    return b


def spitzenwochen(b, daten):
    """Je Saison die Woche mit der höchsten Inzidenz in Deutschland und der Anteil der Einheiten je Lagestufe (in %)."""
    bund = daten.groupby(["Saison", "Wochenbeginn"])[["Faelle", "Einwohner"]].sum()
    bund = (bund["Faelle"] / bund["Einwohner"]).reset_index(name="bund")
    spitze = bund.loc[bund.groupby("Saison")["bund"].idxmax(), ["Saison", "Wochenbeginn"]].rename(columns={"Wochenbeginn": "Woche_t"})
    s = b.merge(spitze, on=["Saison", "Woche_t"])
    tab = pd.crosstab(s["Saison"].astype(int), s["Massnahme"].map(dict(enumerate(MASSNAHMEN))), normalize="index").mul(100).round(0)
    tab = tab.reindex(columns=MASSNAHMEN, fill_value=0)
    tab.insert(0, "Spitzenwoche", s.groupby("Saison")["Woche_t"].first().dt.strftime("%d.%m.%Y"))
    return tab


# ---------------------------------------------------------------------------------------------------
# Länderebene (Notebook 20): dieselbe Methode, angewandt auf die 16 Länder
# ---------------------------------------------------------------------------------------------------
LAENDER = {"BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
           "HE": "Hessen", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen", "NW": "Nordrhein-Westfalen",
           "RP": "Rheinland-Pfalz", "SL": "Saarland", "SN": "Sachsen", "ST": "Sachsen-Anhalt", "SH": "Schleswig-Holstein",
           "TH": "Thüringen"}


def laender_daten(daten):
    """Fälle und Einwohner der Kreise je Land und Woche summieren. Der Landesname steht in der Spalte „Kreis“,
    damit alle Bausteine oben unverändert laufen (Vergleichsgröße dann: Bundesgebiet ohne das eigene Land)."""
    d = daten.groupby(["Land", "Wochenbeginn"]).agg(
        Faelle=("Faelle", "sum"), Einwohner=("Einwohner", "sum"), Meldejahr=("Meldejahr", "first"),
        Meldewoche=("Meldewoche", "first"), Saison=("Saison", "first"), Woche_rel=("Woche_rel", "first")).reset_index()
    d["Inzidenz"] = d["Faelle"] / d["Einwohner"] * 100_000
    d["Kreis"], d["AGS"], d["Raum"] = d["Land"].map(LAENDER), d["Land"], "Land"
    return d


def abwasser_laender(abw, daten):
    """Abwasser je Land und Woche: Mittel der logarithmierten Viruslast über die Kreise mit Messstelle."""
    land = daten.drop_duplicates("Kreis").set_index("Kreis")["Land"].map(LAENDER)
    return abw.assign(Kreis=abw["Kreis"].map(land)).groupby(["Kreis", "Wochenbeginn"])["log_vl"].mean().reset_index()
