# Ergänzende Anforderungen (zur README)

Diese Ergänzung passt die README an die Muster-Definitionen aus dem Buch an und fügt Einzelkerzen-Muster **als Hintergrund-Analyse** hinzu. **Bei Widersprüchen gilt diese Ergänzung.** Alles, was hier nicht erwähnt wird, bleibt wie in der README (Datenabruf, Trendfilter, SL/TP, E-Mail, Cron, Duplikat-Schutz).

## 1. Änderungen an den zehn Haupt-Mustern

Die Haupt-Muster bleiben die einzigen Muster, die eine **E-Mail** auslösen.

### Bullish / Bearish Engulfing
- Zusätzlich: Der Körper der zweiten Kerze muss **größer** sein als der Körper der ersten und diesen komplett umschließen.
- Trend wie bisher: Bullish nach Abwärtstrend, Bearish nach Aufwärtstrend.

### Tweezer Top / Bottom
- Die zwei Kerzen müssen sich **ähneln**: beide mit kleinem Körper (`<= SMALL_BODY_ATR * ATR`), Körper ähnlich groß, unterschiedliche Farbe.
- Zusätzlich gilt das gleiche Hoch (Top) bzw. Tief (Bottom) innerhalb von `TWEEZER_TOLERANCE`.
- Tweezer Top: erst grün, dann rot, nach Aufwärtstrend → SELL.
- Tweezer Bottom: erst rot, dann grün, nach Abwärtstrend → BUY.
- Die Docht-Beschreibung aus dem Buch wird **nicht wörtlich** geprüft.

### Morning Star / Evening Star
- **Mittlere Kerze hat dieselbe Farbe wie die erste Kerze.**
  - Evening Star: K1 große grüne, K2 kleine grüne, K3 große rote → SELL, nach Aufwärtstrend.
  - Morning Star: K1 große rote, K2 kleine rote, K3 große grüne → BUY, nach Abwärtstrend.
- K2 ist „viel kleiner“: `Körper K2 <= STAR_MIDDLE_MAX_RATIO * Körper K1`.
- K3 ist größer als die Hälfte von K1: `Körper K3 > STAR_LAST_MIN_RATIO * Körper K1`.
- K1 und K3 sind „lang“ (`>= LONG_BODY_ATR * ATR`), K1 ist kein Doji.
- Die bisherige Bedingung „Schluss K3 über/unter der Mitte von K1“ bleibt als **optionale Zusatzbedingung** (`STAR_REQUIRE_CLOSE_BEYOND_MID`, Standard `False`).

### Drei bullische / bärische Soldaten (Umkehrmuster)
- **Trendbedingung (neu):**
  - Drei bullische Soldaten nur nach **Abwärtstrend** → BUY.
  - Drei bärische Soldaten nur nach **Aufwärtstrend** → SELL.
- Drei Kerzen in Signalfarbe, **Körper wachsen**: `Körper K1 < Körper K2 < Körper K3`.
- K1 klein, K2 größer mit winzigem Docht in Signalrichtung, K3 deutlich größer mit winzigem oder keinem Docht in Signalrichtung (`<= WICK_SMALL_RATIO` der Kerzenspanne).
- Jede Kerze schließt höher (bullisch) bzw. tiefer (bärisch) als die vorherige.
- Die frühere Bedingung „Eröffnung innerhalb des Körpers der vorherigen Kerze“ ist **optional** (`SOLDIERS_REQUIRE_OPEN_IN_BODY`, Standard `False`).

### Steigendes / Fallendes Dreier-Pattern (fünf Kerzen)
- **Alle drei** mittleren Kerzen müssen gegenläufig sein (nicht nur „überwiegend“):
  - Steigend: K1 lange grüne, K2 bis K4 kleine **rote**, K5 lange grüne mit Schluss **über** dem Schluss von K1 → BUY, nur im Aufwärtstrend.
  - Fallend: K1 lange rote, K2 bis K4 kleine **grüne**, K5 lange rote mit Schluss **unter** dem Schluss von K1 → SELL, nur im Abwärtstrend.
- „Eingebettet“: K2 bis K4 liegen innerhalb der Spanne `low..high` von K1. Schaltbar über `RISEFALL_REQUIRE_INSIDE_RANGE` (Standard `True`).

## 2. Einzelkerzen-Muster (Hintergrund-Analyse)

Neue Datei `patterns_single.py`. Die Muster werden erkannt und aufgezeichnet, **lösen aber keine E-Mail aus** (Standard).

### Betriebsmodus
- `SINGLE_PATTERNS_MODE` mit drei Werten:
  - `"off"`: Einzelkerzen werden nicht geprüft
  - `"log_only"` (**Standard**): erkannt, in `background_signals.csv` und im Log gespeichert, keine E-Mail
  - `"notify"`: wie die Haupt-Muster mit E-Mail (nur zum späteren Testen)
- `background_signals.csv` Spalten: Zeit (UTC), Muster, Richtung (BUY/SELL/NEUTRAL), Entry, SL, TP, Risiko in Pips. SL/TP wie in der README berechnet. Bei NEUTRAL-Mustern entfallen Entry/SL/TP.
- Duplikat-Schutz wie bei den Haupt-Mustern.

### Definitionen
Alle Richtungsmuster gelten nur im passenden Trend (Trendfilter wie bisher).

| Muster | Trend davor | Regel | Richtung |
|---|---|---|---|
| Hammer | Abwärts | grüne Kerze, kleiner Körper, langer unterer Docht (`>= WICK_LONG_RATIO * Körper`), oberer Docht klein (`<= WICK_SMALL_RATIO * Spanne`) | BUY |
| Umgekehrter Hammer | Abwärts | grüne Kerze, kleiner Körper, langer oberer Docht, unterer Docht klein | BUY |
| Hanging Man | Aufwärts | rote Kerze, Form wie Hammer | SELL |
| Shooting Star | Aufwärts | rote Kerze, kleiner Körper, langer oberer Docht, unterer Docht klein | SELL |
| Marubozu | beliebig | Körper `>= LONG_BODY_ATR * ATR`, beide Dochte `<= WICK_SMALL_RATIO * Spanne`. Fortsetzungsmuster: grün im Aufwärtstrend → BUY, rot im Abwärtstrend → SELL | BUY/SELL |
| Doji | beliebig | Körper `<= DOJI_BODY_RATIO * Spanne` | NEUTRAL |
| Spinning Top | beliebig | kleiner Körper, beide Dochte länger als der Körper | NEUTRAL |

Doji und Spinning Top zeigen Unentschlossenheit und haben **keine Richtung**. Sie werden nur markiert.

## 3. Neue Parameter (`config.py`)

| Parameter | Startwert | Bedeutung |
|---|---|---|
| `STAR_MIDDLE_MAX_RATIO` | `0.5` | Körper der mittleren Star-Kerze höchstens halb so groß wie K1 |
| `STAR_LAST_MIN_RATIO` | `0.5` | Körper von K3 größer als die Hälfte von K1 |
| `STAR_REQUIRE_CLOSE_BEYOND_MID` | `False` | Zusatzbedingung: Schluss K3 jenseits der Mitte von K1 |
| `SOLDIERS_REQUIRE_OPEN_IN_BODY` | `False` | Zusatzbedingung: Eröffnung im Körper der vorherigen Kerze |
| `RISEFALL_REQUIRE_INSIDE_RANGE` | `True` | mittlere Kerzen innerhalb der Spanne von K1 |
| `TWEEZER_BODY_SIMILARITY` | `0.6` | kleinerer Körper mindestens 60 % des größeren |
| `SINGLE_PATTERNS_MODE` | `"log_only"` | `"off"`, `"log_only"` oder `"notify"` |
| `DOJI_BODY_RATIO` | `0.10` | Doji: Körper höchstens 10 % der Kerzenspanne |
| `WICK_LONG_RATIO` | `2.0` | langer Docht mindestens 2 × Körper |
| `WICK_SMALL_RATIO` | `0.10` | kleiner Docht höchstens 10 % der Kerzenspanne |

Hinweis: `MIN_SHADOW_RATIO` aus der README wird durch `WICK_SMALL_RATIO` ersetzt. Bitte nur einen der beiden Namen behalten.

## 4. Backtest

- Ausgabe in **zwei getrennten Tabellen**: „Haupt-Muster“ und „Einzelkerzen (Hintergrund)“.
- Gleiche Auswertung wie in der README (TP/SL/Zeitablauf, Ergebnis in R, Spread).
- Bei weniger als 30 Signalen pro Muster steht in der Ausgabe der Hinweis „zu wenige Fälle für eine belastbare Aussage“.
- NEUTRAL-Muster (Doji, Spinning Top) werden nur gezählt, nicht auf Gewinn/Verlust bewertet.

## 5. Zusätzliche Tests

- Soldaten: bullische Soldaten **nach Aufwärtstrend** lösen **nicht** aus. Nicht wachsende Körper lösen nicht aus.
- Stars: mittlere Kerze mit anderer Farbe als K1 löst **nicht** aus.
- Dreier-Pattern: nur zwei von drei mittleren Kerzen gegenläufig löst **nicht** aus.
- Tweezer: gleiches Hoch, aber unterschiedlich große Körper (unter `TWEEZER_BODY_SIMILARITY`) löst nicht aus.
- Engulfing: zweiter Körper kleiner als der erste löst nicht aus.
- Einzelkerzen: je Muster ein positiver und ein negativer Test.
- Im Modus `log_only` wird bei einem Einzelkerzen-Treffer **keine** E-Mail gesendet, aber eine Zeile in `background_signals.csv` geschrieben.

## 6. Akzeptanzkriterien (zusätzlich)

- Alle zehn Haupt-Muster entsprechen den Definitionen in Abschnitt 1.
- Mit `SINGLE_PATTERNS_MODE = "log_only"` kommen E-Mails nur von Haupt-Mustern.
- `background_signals.csv` wird gefüllt, ohne Duplikate.
- Der Backtest zeigt Haupt-Muster und Einzelkerzen getrennt.
- Alle neuen Parameter stehen in `config.py` mit Kommentar.
