# Gemeinsames Lagebild Influenza

Wo in Deutschland ist Influenza gerade ungewöhnlich, und was folgt daraus? Das Lagebild beantwortet das jede Woche für alle 400 Kreise und 16 Länder und empfiehlt je Gebiet eine Maßnahme.

### [→ Lagebild öffnen](https://2708tom.github.io/Lagebild-Influenza/)

Die Seite wird jeden Donnerstag mit den neuesten Meldedaten und Abwasserwerten des Robert Koch-Instituts aktualisiert. Sie läuft im Browser, ohne Anmeldung und ohne Installation.

Projektarbeit von Tom Thum in der Lehrveranstaltung „Epidemiologische Gefahren“ bei Prof. Dr. Dr. Alexander Lechleuthner, Institut für Rettungsingenieurwesen und Gefahrenabwehr, Technische Hochschule Köln.

## So lesen Sie das Lagebild

Jede Farbe ist eine Empfehlung. Sie ergibt sich aus zwei Fragen:

1. **Wie viel ist da? (Last)** Gemeldete Fälle je 100.000 Einwohner und Woche, gemittelt über die letzten drei Wochen. Die Grenzen für niedrig, mittel und hoch folgen dem europäischen Standard der Grippe-Überwachung (Moving Epidemic Method).
2. **Ist das ungewöhnlich? (Erwartung)** Ein Modell schätzt, wie viele Fälle in diesem Kreis zu dieser Jahreszeit normal wären. Verglichen wird gemeldet / erwartet: wie erwartet, leicht darüber oder deutlich darüber. „Deutlich darüber“ heißt ungewöhnlich, nicht Ausbruch.

| Last | wie erwartet | leicht darüber | deutlich darüber |
|---|---|---|---|
| hoch | prüfen | prüfen | prüfen und informieren |
| mittel | beobachten | beobachten | prüfen |
| niedrig | keine Maßnahme | keine Maßnahme | beobachten |

Farben: Grün keine Maßnahme, Gelb beobachten, Orange prüfen, Rot prüfen und informieren.

**Abwasser.** Influenza im Abwasser ist eine zweite Quelle, die nicht davon abhängt, wie viel getestet wird. Ist es erhöht, gilt ein Kreis früher als deutlich darüber.

**Prognose.** Die Grafik zeigt den Verlauf und die Vorhersage für 1 bis 7 Wochen. In der grauen Fläche lag der gemeldete Wert im Test an früheren Saisons in 8 von 10 Fällen. Ein Pfeil (↗ ↘) zeigt einen deutlichen Anstieg oder Rückgang in drei Wochen an.

**Ungewohnte Lage.** Ein oranger Hinweis erscheint, wenn der Stand höher ist als fast je zuvor zu dieser Jahreszeit. Das Modell kennt solche Lagen nicht; statt einer Prognose zeigt die Seite, wie es in ähnlichen Lagen früherer Saisons weiterging.

**Bedienung.** Oben Gebiet (Deutschland oder ein Land) und Woche wählen, mit dem Zeitstrahl zurückblättern, einen Kreis in Karte oder Tabelle anklicken. „CSV ↓“ speichert die Kreistabelle, das Drucksymbol oben rechts erzeugt eine Druckansicht (auch als PDF), ◐ schaltet zwischen hell und dunkel.

## Offline nutzen und weitergeben

Das Lagebild ist eine einzige, vollständige Datei. Sie funktioniert auch ohne Internet und lässt sich per E-Mail weitergeben: [Lagebild.html](Technik/08_Lagebild/Lagebild.html) öffnen und oben rechts auf das Download-Symbol klicken. Die heruntergeladene Datei per Doppelklick im Browser öffnen.

## Grenzen

- Proof of Concept einer Hochschularbeit, kein amtliches Produkt.
- Beobachten, prüfen und informieren sind Empfehlungen. Über Maßnahmen entscheidet die zuständige Behörde.
- Die jüngsten Wochen sind vorläufig, Nachmeldungen sind möglich.
- Ob eine Empfehlung im Einzelfall richtig lag, lässt sich mit offenen Daten nicht prüfen; Ausbruchsmeldungen der Gesundheitsämter sind nicht öffentlich.

Daten: Robert Koch-Institut (SurvStat, AMELAG), Statistische Ämter des Bundes und der Länder, © GeoBasis-DE / BKG. Methode, Installation und Quellen im Ordner [Technik](Technik/).
