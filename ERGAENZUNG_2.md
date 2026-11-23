# Ergänzung 2: Architektur (ein modularer Bot)

Diese Ergänzung ergänzt `README.md` und `ERGAENZUNG.md`. Bei Widersprüchen gilt die Reihenfolge: **ERGAENZUNG_2.md > ERGAENZUNG.md > README.md**.

## 0. Dauerhafte Arbeitsregeln

(Diese Regeln bitte zusätzlich in `.github/copilot-instructions.md` übernehmen.)

- Der **bestehende Bot läuft live** auf dem Raspberry Pi und darf nicht verändert werden: `main.py`, `main_gbpusd.py`, `main_btc.py`, `main_eth.py`, `config.py`, `data.py`, `patterns.py`, `signals.py`, `notify.py`, `backtest.py`, `state.json`, `tests/test_patterns.py`.
- Alle neue Arbeit passiert auf dem Git-Branch `buchmuster` und im neuen Paket `buchbot/`.
- Nicht raten. Bei unklaren Regeln nachfragen.
- Alle Parameter stehen in `buchbot/config.py`, keine festen Zahlen im Code.
- Keine Zugangsdaten im Code oder Repo, nur über `.env`.
- Zu jeder Änderung gehören Tests. Nach jedem Schritt: Tests ausführen und die echte Terminal-Ausgabe zeigen.
- Kleine Schritte. Nach jedem Schritt auf mein OK warten.

## 1. Ziel

Ein einziger Bot mit austauschbaren Bausteinen. Später kommen weitere Funktionen dazu (Unterstützung/Widerstand, ABC-Muster, weitere), ohne dass bestehende Teile umgebaut werden müssen. Zunächst läuft der neue Bot im **Schattenmodus** (nur Log und CSV, keine Mails) neben dem alten Bot.

## 2. Paketstruktur

Die bisherigen `_new`-Dateien wandern ohne Suffix in das neue Paket:

```
buchbot/
├── __init__.py
├── config.py            (bisher config_new.py)
├── data.py              (bisher data_new.py)
├── models.py            Signal-Datenstruktur
├── detectors/
│   ├── __init__.py      Registry der Detektoren
│   ├── candles_main.py  die zehn Haupt-Muster (bisher patterns_new.py)
│   └── candles_single.py  Einzelkerzen (später)
├── filters/
│   ├── __init__.py
│   └── trend.py         Trendfilter
├── sltp.py              Stop-Loss, Take-Profit, Mindestabstand
├── pipeline.py          verbindet alles
├── outputs/
│   ├── __init__.py
│   ├── log_csv.py       Log und CSV
│   └── mail.py          E-Mail
├── state.py             Duplikat-Schutz (state_new.json)
├── backtest.py
└── main.py              Einstieg: python -m buchbot.main
tests/                   alte Tests bleiben unverändert
tests_buchbot/           Tests für das neue Paket
```

Die Tests aus `tests_patterns_new.py` und `tests_data_new.py` wandern nach `tests_buchbot/`. Alle Tests müssen nach dem Verschieben weiterhin grün sein.

## 3. Signal-Datenstruktur (`models.py`)

Ein `Signal` (dataclass) enthält:

| Feld | Bedeutung |
|---|---|
| `time` | Schlusszeit der Signalkerze (UTC) |
| `symbol` | z. B. `EURUSD=X` |
| `interval` | z. B. `15m` |
| `source` | Herkunft: `candles_main`, `candles_single`, später `support_resistance`, `abc` usw. |
| `pattern` | Name, z. B. `Morning Star` |
| `direction` | `BUY`, `SELL` oder `NEUTRAL` |
| `entry` | Einstiegskurs (Schluss der letzten Musterkerze) |
| `sl`, `tp` | Stop-Loss, Take-Profit (leer bei `NEUTRAL`) |
| `risk_pips` | Abstand Einstieg bis Stop-Loss in Pips |
| `rr` | Chance-Risiko-Verhältnis |
| `atr` | ATR zum Zeitpunkt des Signals |
| `tags` | Dictionary für Zusatzinfos (z. B. Trend, später „am Widerstand“) |

Alle Module tauschen nur diese Struktur aus.

## 4. Detektoren

- Jeder Detektor ist eine Funktion `detect(df, config) -> list[Signal]` (noch ohne SL/TP und Trendfilter) und wird in `detectors/__init__.py` registriert.
- Ein neuer Detektor = neue Datei + Registrierung + Eintrag in der Config. Bestehende Detektoren werden dafür nicht verändert.
- Der Betrieb jedes Detektors wird in der Config gesteuert:

```python
DETECTORS = {
    "candles_main":   "log_only",   # später "notify"
    "candles_single": "off",
}
```

Erlaubte Werte: `"off"`, `"log_only"`, `"notify"`.

- Die Detektoren sind **symbolunabhängig**. Pip-Größe und Toleranzen kommen aus der Config pro Symbol.

## 5. Filter

- Filter stehen in `filters/` und haben die Form `apply(signals, df, config) -> list[Signal]`.
- Der erste Filter ist der Trendfilter aus der README (EMA-Trend, ausgewertet auf der Kerze vor dem Muster). Reversal-Muster brauchen den passenden Trend, Fortsetzungsmuster ebenso.
- Verworfene Signale werden mit Grund geloggt.
- Später kommen weitere Filter dazu (z. B. Nähe zu Unterstützung/Widerstand). Dafür müssen Detektoren nicht geändert werden.

## 6. Stop-Loss und Take-Profit (`sltp.py`)

Wie in der README beschrieben (Puffer hinter dem Extrem des Musters, CRV, Mindestabstand). Signale unter `MIN_SL_PIPS` werden verworfen und geloggt.

## 7. Pipeline (`pipeline.py`)

Ablauf pro Lauf:

1. Wochenende: beenden.
2. Kerzen holen, nicht geschlossene Kerze verwerfen.
3. Alle Detektoren ausführen, die nicht auf `"off"` stehen.
4. Filter anwenden.
5. SL/TP berechnen, Mindestabstand prüfen.
6. Duplikat-Schutz (Schlüssel: Symbol, Muster, Kerzenzeit) über `state_new.json`.
7. Ausgabe:
   - **Alle** übrig gebliebenen Signale gehen ins Log und in `signals_log.csv` (Spalten: alle Signal-Felder plus Betriebsart des Detektors).
   - Nur Signale von Detektoren im Modus `"notify"` gehen an die E-Mail.

## 8. E-Mail (`outputs/mail.py`)

- Schalter `NOTIFY_ENABLED` in der Config, Standard **`False`**. Solange `False`, wird keine Mail gesendet, auch wenn ein Detektor auf `"notify"` steht.
- **Eine Mail pro Kerze:** Treffen mehrere Muster oder Detektoren dieselbe Kerze, werden sie in einer Mail gebündelt (Liste aller Signale). Das macht Übereinstimmungen sichtbar.
- Betreff beginnt mit `[BUCH]`, z. B. `[BUCH] BUY EUR/USD – Morning Star (15m)`, bei mehreren Treffern `[BUCH] BUY EUR/USD – 2 Muster (15m)`. Bei widersprüchlichen Richtungen in derselben Kerze: `[BUCH] EUR/USD – widersprüchliche Signale`.
- Inhalt wie in der README: Signal, Muster, Kerzenzeit, Einstieg, SL, TP, Risiko in Pips, CRV.

## 9. Vorbereitung für spätere Erweiterungen

Noch **nicht** umsetzen, aber die Struktur darf ihnen nicht im Weg stehen:

- **Swing-Punkte** (`swings.py`): Funktion `find_swings(df, n)` liefert Hochs und Tiefs. Grundlage für Unterstützung/Widerstand und ABC-Muster.
- **Unterstützung/Widerstand** als Filter oder Zusatz-Tag (`tags["near_resistance"]`).
- **ABC-Muster** als weiterer Detektor.
- **Mehrere Märkte:** `SYMBOLS` als Liste in der Config. Aktuell nur `["EURUSD=X"]`. Pip-Größe und Parameter pro Symbol in der Config.

## 10. Tests

- Pipeline-Test mit einem Dummy-Detektor: Signal läuft durch Filter, SL/TP, Duplikat-Schutz und Ausgabe.
- Modi: `"off"` erzeugt nichts, `"log_only"` schreibt nur Log und CSV, `"notify"` mit `NOTIFY_ENABLED = False` sendet keine Mail, mit `True` genau eine.
- Mehrere Signale in derselben Kerze ergeben eine gebündelte Mail.
- Duplikat-Schutz: derselbe Lauf zweimal erzeugt nur einmal ein Signal.
- Registry: ein neuer Dummy-Detektor lässt sich registrieren, ohne bestehenden Code zu ändern.
- Alle bisherigen Muster- und Datentests laufen nach dem Verschieben weiter grün.

## 11. Akzeptanzkriterien

- Die alten Dateien und `tests/test_patterns.py` sind unverändert (`git diff` auf `main` zeigt keine Änderungen dort).
- `python -m buchbot.main` läuft durch, schreibt `signals_log.csv` und sendet **keine** Mail (Standard).
- Alle Tests in `tests_buchbot/` sind grün.
- Ein neuer Detektor lässt sich mit einer neuen Datei, einem Registry-Eintrag und einer Config-Zeile hinzufügen.
