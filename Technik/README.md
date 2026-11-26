# Technik

Wie das Lagebild entsteht, wie man es selbst rechnet und woher die Daten kommen. Für die Nutzung reicht die [Online-Seite](https://2708tom.github.io/Lagebild-Influenza/); zurück zur [Übersicht](../README.md).

## Ablauf

Jeden Montag und Donnerstag um 6:17 Uhr (Winterzeit) startet auf GitHub der Workflow „Lagebild aktualisieren“ (`.github/workflows/lagebild.yml`, Reiter „Actions“). Er läuft auf einem Linux-Rechner von GitHub:

1. Abruf der Meldefälle Influenza je Kreis und Woche (RKI SurvStat, laufendes und voriges Jahr, damit Nachmeldungen ankommen) und des Abwassers je Klärwerk (RKI AMELAG).
2. Aufbereitung in den Notebooks 01, 03 und 15: Berliner Bezirke zu Berlin zusammenfassen, Inzidenz je 100.000, Abwasser je Kreis.
3. Rechnung in `lagebild_erzeugen.py`: Erwartung und Prognose (XGBoost), Last nach MEM, Stufe und empfohlene Maßnahme für alle Wochen ab Saison 2023, je Kreis und Land.
4. Die fertige Seite `08_Lagebild/Lagebild.html` und die neuen Daten werden im Repository gespeichert und als Website veröffentlicht.

Von Hand starten: Reiter „Actions“, „Lagebild aktualisieren“, „Run workflow“.

## Selbst rechnen

Einmal vorab **Python 3** installieren, falls noch nicht vorhanden:

- **Mac:** Im Terminal `python3 --version` eingeben. Fehlt Python, bietet macOS die Installation der Entwicklerwerkzeuge an, oder es von [python.org](https://www.python.org/downloads/) installieren.
- **Windows:** Von [python.org](https://www.python.org/downloads/) installieren und dabei „Add python.exe to PATH“ anhaken.

Dann das Repository herunterladen (grüner Knopf „Code“, „Download ZIP“, entpacken) und im Ordner `Technik` starten:

| System | Datei | Start |
|---|---|---|
| Mac | `Lagebild aktualisieren.command` | Doppelklick. Beim ersten Mal Rechtsklick und „Öffnen“, weil macOS Dateien aus dem Internet zunächst blockiert. |
| Windows | `Lagebild aktualisieren.bat` | Doppelklick. Erscheint „Der Computer wurde durch Windows geschützt“: „Weitere Informationen“ und „Trotzdem ausführen“. |

Beim **ersten Start** richtet die Datei eine eigene Python-Umgebung im Ordner `.venv` ein (einmalig einige Minuten, braucht Internet). Danach holt sie bei jedem Start die neuesten Daten, rechnet das Lagebild neu (etwa eine Minute) und öffnet `08_Lagebild/Lagebild.html`.

## Inhalt

| Ordner | Inhalt |
|---|---|
| `02_Daten/SurvStat` | Meldefälle Influenza je Kreis und Woche ab 2015; die letzten zwei Jahre werden bei jedem Lauf neu abgerufen |
| `02_Daten/Bevölkerung` | Einwohner je Kreis |
| `02_Daten/AMELAG` | Abwasser je Klärwerk, wird bei jedem Lauf abgerufen |
| `02_Daten/aufbereitet` | feste Modellergebnisse: Prognosen der Testsaisons, Schwellen, Mischungsgewichte, Kartenumrisse |
| `04_Skripte` | Abruf (`lagebild_aktualisieren.py`), Rechnung (`lagebild.py`, `lagebild_erzeugen.py`, Notebooks 01, 03 und 15), Vorlage der Website |
| `08_Lagebild` | die fertige Website |

## Modell

Das Prognosemodell (XGBoost 2.1.4) wird bei jedem Lauf mit allen bis dahin gemeldeten Wochen neu trainiert. Je nach Rechner (Mac, Windows, Linux) rechnet es dabei minimal anders, weil der Prozessor anders rundet. Das betrifft nur die laufende Saison, vor allem die Prognose (im Mittel 0,5 Fälle je 100.000); maßgeblich ist der Stand der Online-Seite.

Schwellen und Mischungsgewichte stammen aus der Prüfung über frühere Saisons und sind hier fest. Sie werden nach Ende einer Saison im vollständigen Projekt neu bestimmt (Notebooks 16 bis 21, nicht in diesem Repository).

## Datenquellen

- Meldefälle: Robert Koch-Institut, SurvStat@RKI 2.0, [survstat.rki.de](https://survstat.rki.de), Referenzdefinition erfüllt
- Abwasser: Robert Koch-Institut, Abwassersurveillance AMELAG, [GitHub](https://github.com/robert-koch-institut/Abwassersurveillance_AMELAG), Lizenz CC BY 4.0
- Einwohner: Statistische Ämter des Bundes und der Länder, Regionaldatenbank Deutschland, Tabelle 12411-01-01-4, Lizenz dl-de/by-2-0
- Kreisgrenzen: © GeoBasis-DE / BKG (VG250), Lizenz dl-de/by-2-0

Der eigene Code, die Website-Vorlage und die Texte dieses Repositorys stehen unter CC BY 4.0 (siehe [LICENSE](../LICENSE)); für die Daten gelten die oben genannten Lizenzen der Quellen.
