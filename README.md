# EUR/USD Candlestick Signal Bot

> **Hinweis:** Für den neuen Bot (Paket `buchbot/`) haben `docs/ERGAENZUNG.md` und `docs/ERGAENZUNG_2.md` Vorrang vor dieser README. Der Start des neuen Bots lautet `python -m buchbot.main`.

Ein Python-Bot, der den EUR/USD-Chart (15-Minuten-Kerzen) auf klassische Candlestick-Muster prüft und bei Erkennung eines Musters ein **Kauf- oder Verkaufssignal per E-Mail** versendet. Der Bot ist **nur ein Signalgeber** – er platziert keine Orders und führt keinen automatischen Handel durch.

## Features

- **10 Candlestick-Muster** (2-, 3- und 5-Kerzen-Muster)
- **Trendfilter** (EMA-basiert)
- **Stop-Loss & Take-Profit** automatisch berechnet
- **Duplikat-Schutz** (state.json)
- **E-Mail-Versand** via Gmail (mit 2FA App-Passwort)
- **Backtest-Modus** zur Validierung der Regeln
- **Vollständige Test-Suite** (pytest)
- **Raspberry Pi ready** (Cron-Automation)

## Installation

### 1. Repo klonen / Projekt-Folder erstellen

```bash
cd /home/pi  # oder lokal
mkdir forex-bot && cd forex-bot
```

### 2. Virtual Environment & Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. E-Mail-Konfiguration

Kopiere `.env.example` zu `.env` und fülle die Werte:

```bash
cp .env.example .env
# Editiere .env:
# MAIL_USER=deine.adresse@gmail.com
# MAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  (Google App-Passwort!)
# MAIL_TO=empfaenger@example.com
```

**Wichtig:** Für Gmail benötigst du:
1. 2-Faktor-Authentifizierung aktivieren
2. Ein [Google App-Passwort](https://myaccount.google.com/apppasswords) generieren
3. Dieses in `MAIL_APP_PASSWORD` einfügen (nicht dein normales Passwort!)

## Verwendung

### Live-Modus

Der Bot lädt die letzten ~100 Kerzen, prüft alle Muster und versendet ein Signal, wenn ein Muster + Trendfilter passt:

```bash
python main.py
```

Die Ausgabe geht in `bot.log` und zur Console. Jedes Signal wird in `state.json` gespeichert (Duplikat-Schutz).

### Backtest

Lädt maximal verfügbare 15m-Historie (etwa 60 Tage) und simuliert alle Trades:

```bash
python -m buchbot.backtest                      # alle Märkte, je Markt eine Auswertung
python -m buchbot.backtest --market EURUSD      # nur ein Markt
python -m buchbot.backtest --markets ALL        # alle zwölf Märkte, zusätzlich gepoolter Zonen-Vergleich
python -m buchbot.backtest --markets ALL --snapshot backtest_snapshot.csv   # eingefrorener Datenstand
python -m buchbot.backtest --markets EURUSD,GBPUSD
python -m buchbot.backtest --markets ALL --sr-max-zones 3   # nur für den Vergleich: je Seite die 3 stärksten Zonen
python -m buchbot.backtest --markets ALL --interval 1d --no-sr --snapshot backtest_snapshot_1d.csv   # Forschung auf Tagesdaten
python -m buchbot.backtest --markets ALL --interval 1h --no-sr --snapshot backtest_snapshot_1h.csv   # Forschung auf Stundendaten
```

Ausgabe: Tabelle mit für jedes Muster:
- Anzahl Signale
- Anteil TP / SL / Timeout
- Durchschnittliches Ergebnis in R (TP = +2, SL = -1, etc.)

Zusätzlich je Markt (und bei mehreren Märkten gepoolt) ein **Zonen-Vergleich** (Unterstützung und Widerstand, Kapitel 9):
- Gruppen: a) Muster an starker passender Zone, b) keine Zone in der Nähe, c) gegen starke Zone, d) a) und nicht c)
- Trend-Gruppen: in Trendrichtung, gegen den Trend, range
- Je Gruppe: Anzahl, Anteil TP / SL / Timeout, Ø R, Standardfehler des Ø R, Summe R; unter 30 Trades ein Hinweis "zu wenige Fälle"
- Verteilung: Anteil der Gruppe an allen Signalen und Ø starke Zonen je Signalkerze. Liegt eine Gruppe über 80 % oder unter 5 %, erscheint die Warnung "Zonenparameter möglicherweise unpassend" (Schwellen in `config.py`)
- Kopfzeilen: Ø starke Zonen je Kerze und Seite sowie die Anteile der Gruppen a) und c). Liegt der Wert über `SR_WARN_MAX_ZONES` (Standard 4), erscheint "Zonen zu dicht"
- Bei `--markets ALL` zusätzlich getrennt für die erste und zweite Hälfte des Zeitraums (Trennung am Median der Signalzeiten, gepoolt über alle Märkte), jeweils mit Anzahl, Ø R und Standardfehler

`--sr-max-zones N` überschreibt `SR_MAX_ZONES_PER_SIDE` nur für den Backtest. Standard ist `None` (alle starken Zonen). Der Live-Bot ist davon nicht betroffen.

`--snapshot DATEI.csv` friert den Datenstand ein: Beim ersten Lauf werden alle abgerufenen Kerzen in der Datei gespeichert (Dateien `*.csv` sind in `.gitignore`). Spätere Läufe mit derselben Option lesen daraus, ohne Abruf. Die Ausgabe nennt Abrufzeitpunkt und Zeitraum je Markt. Fehlt ein Markt in der Datei, wird er nachgeladen und ergänzt. Die Datei kann mehrere Intervalle enthalten (Schlüssel Markt und Intervall). Beispiel: `python -m buchbot.backtest --markets ALL --snapshot backtest_snapshot.csv`. Zwei Läufe mit demselben Snapshot liefern identische Ergebnisse, auch für `--sr-max-zones`.

#### Intervall, Kosten und Zeitaufteilung (Forschung, Schritt 13a)

Zweck: Prüfen, ob die bestehenden Regeln (Muster, EMA-50-Trendfilter, ATR, SL/TP, Mindestabstand, Überlappungsregel) auch auf 1h- und 1d-Daten ein Ergebnis zeigen. Es wird nichts optimiert, alle Parameter bleiben wie in `config.py`. Der Live-Betrieb ist nicht betroffen.

- `--interval {15m,30m,1h,1d}` überschreibt das Intervall aller gewählten Märkte nur für den Backtest. Zeitraum je Intervall (`BACKTEST_PERIOD_BY_INTERVAL` in `config.py`): 15m und 30m "60d", 1h "730d", 1d "max". Märkte mit weniger als `MIN_CANDLES_FOR_BACKTEST` (500) Kerzen werden mit Hinweis übersprungen.
- `--no-sr` ruft die Zonen-Annotation nicht auf. Die `sr_*`-Spalten bleiben leer, die Signale und R-Werte sind unverändert.
- `--spread {both,with,without}` (Standard `both`): Ergebnisse vor Kosten (Spread 0) und/oder nach Kosten. R vor Kosten = R nach Kosten + Spread / Risiko.
- Zusätzlich zu den Zeithälften werden die Haupt-Muster-Tabellen nach Jahrzehnt der Signalzeit ausgegeben (bis 2009, 2010 bis 2019, ab 2020). Unter 30 Trades erscheint der Hinweis "zu wenige Fälle".
- Die Ausgabe beginnt mit Datenstand (Abrufdatum und Zeitraum) und den verwendeten Parametern.
- Beispiele: `python -m buchbot.backtest --markets ALL --interval 1d --no-sr --snapshot backtest_snapshot_1d.csv` und `--interval 1h --no-sr --snapshot backtest_snapshot_1h.csv`. Die Läufe je Intervall werden nacheinander gestartet.
- Märkte, die bei `--interval` denselben Datensatz (Symbol und Intervall) wie ein früherer Markt nutzen (EURUSD_30M bei 1d), werden mit Hinweis übersprungen, damit nichts doppelt gezählt wird.

#### Nullvergleich und Cluster-Standardfehler (Forschung, Schritt 13b)

Zweck: Prüfen, ob die Haupt-Muster besser sind als zufällig gewählte Kerzen mit derselben Trendbedingung. Der Live-Betrieb ist nicht betroffen, es werden keine Parameter variiert.

- **Cluster-SE** (Spalten "SE Cl." in den gepoolten Tabellen, zusätzlich zum SE): Cluster ist der Kalendermonat der Signalzeit (alle Märkte zusammen). SE = Wurzel aus der Summe über Cluster von (Summe der (R − Mittelwert) im Cluster)² geteilt durch n.
- `--null-test`: Pseudo-Muster aus den letzten `NULL_PATTERN_CANDLES` (2) Kerzen. Kandidaten sind alle Kerzen, die die Trendbedingung des Live-Filters erfüllen (BUY nur bei Schluss unter, SELL nur bei Schluss über der EMA, Trend auf der Kerze vor dem Pseudo-Muster). Einstieg, SL/TP, Mindestabstand, Haltedauer und Spread laufen über dieselben Funktionen wie live, ohne Überlappungsregel. Je Ziehung (`NULL_TEST_DRAWS` = 2000, Seed `NULL_TEST_SEED` = 12345) werden je Markt und Richtung so viele Kandidaten ohne Zurücklegen gezogen, wie die echten Haupt-Muster Trades hatten.
- Ausgabe: Nullverteilung (Mittelwert, 5 %-, 95 %-, 99 %-Quantil) gegen das echte Ø R, p-Wert (Anteil der Ziehungen mit Ø R gleich oder größer), gepoolt, getrennt nach BUY und SELL und je Jahrzehnt, dazu die Drift-Baseline (Ø R aller Kandidaten ohne Ziehung), jeweils vor und nach Kosten.
- Kriterien (vorab festgelegt, Werte in `config.py`), ausgegeben als Zahlen und Ja/Nein ohne Deutung: K1 Ø R vor Kosten größer als das 99 %-Quantil der Nullverteilung. K2 Ø R vor Kosten > 0 in mindestens 2 von 3 Jahrzehnten. K3 Ø R vor Kosten > 0 in mindestens 60 % der Märkte mit mindestens 30 Trades. K4 Ø R vor Kosten geteilt durch Cluster-SE größer als 3. K5 Ø R nach Kosten > 0.
- Zusatzzahlen: Ø R je Markt (nur Märkte mit mindestens 30 Trades) für alle Richtungen, BUY und SELL mit Anzahl positiver Märkte, und gepoolt ohne BTC, ETH und GOLD.

```bash
python -m buchbot.backtest --markets ALL --interval 1d --no-sr --snapshot backtest_snapshot_1d.csv --null-test
```

Der Backtest verändert keine Signale. Die Zonen-Auswertung dient nur der Einschätzung.


### Tests

Neuer Bot (`buchbot`):

```bash
pytest tests_buchbot
```

Alter Bot (unverändert):

```bash
pytest tests
# oder einzeln:
pytest tests/test_patterns.py -v
```

Prüft alle Muster, Trend-Filter, SL/TP-Berechnung und Duplikat-Schutz.

## Projektstruktur

```
.
├── config.py           # Zentrale Konfiguration (Startwerte)
├── data.py             # yfinance-Datenabruf, ATR, EMA
├── patterns.py         # 10 Muster-Erkennungsfunktionen
├── signals.py          # Muster + Trend → Signal, SL/TP-Berechnung
├── notify.py           # E-Mail-Versand (Gmail SMTP)
├── main.py             # Live-Einstiegspunkt (Cron)
├── backtest.py         # Backtest-Simulator
├── tests/
│   └── test_patterns.py  # Komplette Test-Suite
├── requirements.txt    # Dependencies
├── .env.example        # E-Mail-Konfiguration Template
├── .gitignore          # .env, state.json, Logs
├── bot.log             # Laufzeit-Log (Rotation)
└── state.json          # Versendete Signale (auto-generiert)
```

## Die 10 Muster

### Zwei-Kerzen-Muster
| Muster | Signal | Regel |
|---|---|---|
| **Bullish Engulfing** | BUY | Kerze 1 rot, Kerze 2 grün, Kerze 2 umschließt Kerze 1 komplett |
| **Bearish Engulfing** | SELL | Kerze 1 grün, Kerze 2 rot, Kerze 2 umschließt Kerze 1 komplett |
| **Tweezer Bottom** | BUY | Kerze 1 rot, Kerze 2 grün, identisches Tief (innerhalb 1.5 Pips) |
| **Tweezer Top** | SELL | Kerze 1 grün, Kerze 2 rot, identisches Hoch (innerhalb 1.5 Pips) |

### Drei-Kerzen-Muster
| Muster | Signal | Regel |
|---|---|---|
| **Morning Star** | BUY | Kerze 1 lang rot, Kerze 2 small body, Kerze 3 lang grün, K3 close > Mitte K1 |
| **Evening Star** | SELL | Kerze 1 lang grün, Kerze 2 small body, Kerze 3 lang rot, K3 close < Mitte K1 |
| **Drei Weiße Soldaten** | BUY | 3× grün, steigende Closes, Eröffnungen im Körper der Vorgänger, kleine obere Schatten |
| **Drei Schwarze Krähen** | SELL | 3× rot, fallende Closes, Eröffnungen im Körper der Vorgänger, kleine untere Schatten |

### Fünf-Kerzen-Muster
| Muster | Signal | Regel |
|---|---|---|
| **Steigendes Dreier-Pattern** | BUY | K1 lang grün, alle drei mittleren Kerzen (K2–K4) klein und rot innerhalb K1-Spanne, K5 lang grün mit close > K1 close |
| **Fallendes Dreier-Pattern** | SELL | K1 lang rot, alle drei mittleren Kerzen (K2–K4) klein und grün innerhalb K1-Spanne, K5 lang rot mit close < K1 close |

## Konfiguration (`config.py`)

Alle Parameter sind an einer Stelle und einfach änderbar:

| Parameter | Startwert | Bedeutung |
|---|---|---|
| `SYMBOL` | `EURUSD=X` | yfinance Symbol |
| `INTERVAL` | `15m` | Kerzenlänge |
| `LOOKBACK_CANDLES` | `100` | Geholte Kerzen |
| `TREND_EMA_PERIOD` | `50` | EMA-Periode für Trendfilter |
| `ATR_PERIOD` | `14` | ATR-Periode |
| `LONG_BODY_ATR` | `0.8` | "Lange Kerze": Körper ≥ 0.8 × ATR |
| `SMALL_BODY_ATR` | `0.3` | "Kleiner Körper": Körper ≤ 0.3 × ATR |
| `TWEEZER_TOLERANCE` | `0.00015` | 1.5 Pips Toleranz |
| `MIN_SHADOW_RATIO` | `0.25` | Max Schattengröße bei Soldaten (25% der Kerzenspanne) |
| `SL_BUFFER_ATR` | `0.5` | Puffer hinter Muster-Extrem: 0.5 × ATR |
| `MIN_SL_PIPS` | `5` | Min. Risiko in Pips; kleinere Signale verworfen |
| `RISK_REWARD` | `2.0` | Take-Profit = 2 × Risiko → CRV 1:2 |
| `PIP_SIZE` | `0.0001` | Pip-Größe EUR/USD |
| `MAX_HOLD_CANDLES` | `32` | Backtest: max Haltedauer in Kerzen (15m: 8 Stunden, 30m: 16 Stunden), je Markt überschreibbar |
| `SPREAD_PIPS` | `1.0` | Backtest: angenommener Spread |

## Stop-Loss & Take-Profit

Der Bot **berechnet** SL und TP als Vorschlag (platziert sie nicht):

**BUY-Signal:**
- Entry = Schlusskurs der letzten Musterkerze
- SL = tiefstes Low der Musterkerzen − 0.5 × ATR
- Risk = Entry − SL
- TP = Entry + 2 × Risk (CRV 1:2)

**SELL-Signal:**
- Entry = Schlusskurs der letzten Musterkerze
- SL = höchstes High der Musterkerzen + 0.5 × ATR
- Risk = SL − Entry
- TP = Entry − 2 × Risk

Ist Risk < `MIN_SL_PIPS`, wird das Signal **nicht versendet**.

**Beispiel (BUY):**
- Entry: 1.1000
- Min Low Muster: 1.0985
- ATR: 0.0010
- SL = 1.0985 − 0.0005 = 1.0980
- Risk = 0.0020 (20 Pips)
- TP = 1.1000 + 2 × 0.0020 = 1.1040

## Mehrmarkt-Betrieb (neuer Bot, `buchbot/`)

Ein Lauf von `python -m buchbot.main` wertet alle Märkte nacheinander aus:

| Markt-Schlüssel | Anzeige | yfinance-Symbol | Handelszeiten |
|---|---|---|---|
| `EURUSD` | EUR/USD | `EURUSD=X` | Forex (Fr 22:00 bis So 22:00 UTC geschlossen) |
| `GBPUSD` | GBP/USD | `GBPUSD=X` | Forex |
| `BTC` | Bitcoin | `BTC-USD` | 24/7 |
| `ETH` | Ethereum | `ETH-USD` | 24/7 |

Ein Fehler in einem Markt (Abruf, Daten) bricht die übrigen Märkte nicht ab. Exit-Code 1 gibt es nur bei unerwarteten Fehlern. Zustand (`state_new.json`, Schlüssel mit Markt), CSV (`signals_log.csv`, Spalte `market`) und Betreff (z. B. `[BUCH] BUY GBP/USD – Morning Star (15m)`) sind je Markt getrennt.

**Standard: alle Märkte und Detektoren laufen im Modus `log_only`, es werden keine Mails versendet.** Mails schaltet man in der `.env` frei:

```bash
BUCH_NOTIFY_ENABLED=1                      # 1/true/yes = an
BUCH_NOTIFY_MARKETS=EURUSD,GBPUSD          # nur diese Märkte senden Mails
BUCH_DETECTOR_MODES=candles_main=notify,candles_single=log_only
```

Ungültige Werte führen beim Start zu einer Fehlermeldung mit Exit-Code 1. Einzelkerzen (`candles_single`) gehen nie per Mail. Mit `python -m buchbot.main --test-mail` prüft man den Versand: Es wird eine Mail `[BUCH] Testmail` gesendet, ohne Zustand oder CSV zu ändern.

Backtest und Auswertung laufen mit `--market` (Standard: alle Märkte):

```bash
python -m buchbot.backtest --market BTC
python -m buchbot.evaluate [--csv signals_log.csv] [--market GBPUSD] [--allow-overlap] [--out ergebnis.csv]
```

Für Krypto ist die Risikoeinheit USD statt Pips, und die Preise werden auf 2 Nachkommastellen gerundet. Der yfinance-Zeitraum bleibt bei `60d`, da 15m-Daten nicht länger verfügbar sind.

### Beobachtungsmärkte

Diese Märkte werden ausgewertet, geloggt und in `signals_log.csv` geschrieben. Sie senden standardmäßig **keine** Mail, auch nicht bei `BUCH_NOTIFY_ENABLED=1` und auch nicht, wenn sie in `BUCH_NOTIFY_MARKETS` stehen. Welche Märkte Beobachtungsmärkte sind, steuert `BUCH_OBSERVE_ONLY_MARKETS` in der `.env`. Der Standard ist die Liste `USDJPY, AUDUSD, GBPJPY, USDCAD, USDCHF, EURJPY, GOLD`. `EURUSD_30M` ist zusätzlich fest stummgeschaltet und sendet nie eine Mail, unabhängig von der Liste.

| Markt-Schlüssel | Anzeige | yfinance-Symbol | Intervall | Handelszeiten |
|---|---|---|---|---|
| `EURUSD_30M` | EUR/USD (30m) | `EURUSD=X` | 30m | Forex |
| `USDJPY` | USD/JPY | `USDJPY=X` | 15m | Forex |
| `AUDUSD` | AUD/USD | `AUDUSD=X` | 15m | Forex |
| `GBPJPY` | GBP/JPY | `GBPJPY=X` | 15m | Forex |
| `USDCAD` | USD/CAD | `USDCAD=X` | 15m | Forex |
| `USDCHF` | USD/CHF | `USDCHF=X` | 15m | Forex |
| `EURJPY` | EUR/JPY | `EURJPY=X` | 15m | Forex |
| `GOLD` | Gold | `GC=F` | 15m | Futures (siehe unten) |

- Gold nutzt `GC=F` (Future). Das Spot-Symbol `XAUUSD=X` liefert bei yfinance keine Daten.
- Gold ist Freitag 17:00 bis Sonntag 18:00 New Yorker Zeit geschlossen, außerdem täglich Montag bis Donnerstag 17:00 bis 18:00 New Yorker Zeit. Feiertage sind nicht berücksichtigt.
- Yen-Paare haben Pip 0.01, die übrigen Forex-Paare 0.0001. Gold rechnet in USD.
- Mindestabstand und Spread stehen je Markt in `config.py` und sind Startwerte. AUDUSD hat 3 Pips Mindestabstand, weil der Median-ATR dort nur etwa 3.1 Pips beträgt.
- **Mail für einen Beobachtungsmarkt einschalten** braucht zwei Schritte in der `.env`:
  1. Den Markt aus `BUCH_OBSERVE_ONLY_MARKETS` entfernen. Die Liste ist vollständig und ersetzt den Standard. Eine leere Liste hebt alle Beobachtungsmärkte außer `EURUSD_30M` auf.
  2. Den Markt in `BUCH_NOTIFY_MARKETS` eintragen und `BUCH_NOTIFY_ENABLED=1` setzen.

  Beispiel: USDJPY soll Mails senden, die übrigen Beobachtungsmärkte bleiben wie bisher:
  ```bash
  BUCH_OBSERVE_ONLY_MARKETS=AUDUSD,GBPJPY,USDCAD,USDCHF,EURJPY,GOLD
  BUCH_NOTIFY_MARKETS=USDJPY
  BUCH_NOTIFY_ENABLED=1
  ```
  Ohne Schritt 1 bleibt der Markt Beobachtungsmarkt, und `BUCH_NOTIFY_MARKETS` allein hat keine Wirkung. `EURUSD_30M` lässt sich nicht freischalten.

Abrufe laufen mit einer Pause von `MARKET_PAUSE_SECONDS` (1 s) zwischen den Märkten. Schlägt ein Abruf fehl oder liefert er eine leere Antwort, wird nach `FETCH_RETRY_SECONDS` (5 s) einmal wiederholt. mit einer Pause von `MARKET_PAUSE_SECONDS` (1 s) zwischen den Märkten. Schlägt ein Abruf fehl oder liefert er eine leere Antwort, wird nach `FETCH_RETRY_SECONDS` (5 s) einmal wiederholt.

### Umstellung vom alten auf den neuen Bot

Der alte Bot (`main.py`, `main_gbpusd.py`, `main_btc.py`, `main_eth.py`) bleibt im Repository unverändert und läuft weiter, bis man umstellt. Empfohlene Reihenfolge:

1. Neuen Bot per Cron im Modus `log_only` parallel laufen lassen (keine Mails, nur CSV).
2. Mit `python -m buchbot.evaluate` prüfen, ob die Signale plausibel sind.
3. Eine Testmail mit `--test-mail` senden lassen.
4. Für einen Markt `BUCH_NOTIFY_MARKETS` setzen und `BUCH_NOTIFY_ENABLED=1`. Solange der alte Bot für denselben Markt ebenfalls Mails sendet, kommen Signale doppelt an. Deshalb den alten Cron-Eintrag für diesen Markt vorher entfernen.
5. Schrittweise alle Märkte umstellen, dann den alten Cron-Eintrag entfernen.

Der neue Bot liest und schreibt die Zustandsdateien des alten Bots (`state.json`, `state_gbpusd.json`, `state_btc.json`, `state_eth.json`) nie.

## Betrieb auf Raspberry Pi

### Cron-Eintrag

Öffne `crontab -e` und füge ein (Mo–Fr, kurz nach jeder Viertelstunde):

```cron
1,16,31,46 * * * 1-5 cd /home/pi/forex-bot && /home/pi/forex-bot/.venv/bin/python main.py >> bot.log 2>&1
```

Das läuft um **01, 16, 31, 46 Minuten** jeder Stunde, Mo–Fr.

### Logrotation

Damit `bot.log` nicht endlos wächst, erstelle `/etc/logrotate.d/forex-bot`:

```
/home/pi/forex-bot/bot.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

### Prüfung

```bash
# Test live
python main.py

# Log ansehen
tail -f bot.log

# Cron-Test: eine Stunde voraus, dann warten
```

## Signal-E-Mail

Bei Mustererkennung erhält der Empfänger eine E-Mail wie:

```
Subject: BUY EUR/USD – Bullish Engulfing (15m)

BUY-Signal erkannt

Muster: Bullish Engulfing
Kerzenzeit (UTC): 2024-01-15 10:00:00+00:00

--- Einstieg und Risiko ---
Einstieg: 1.10000
Stop-Loss: 1.09800
Take-Profit: 1.10400
Risiko: 20.00 Pips
CRV: 1:2

HINWEIS: Dies ist kein Anlagerat, sondern nur eine automatische Mustererkennung.
Forex-Handel mit Hebel ist hochriskant.
```

## Unterstützung und Widerstand (Kapitel 9)

Zusatzinfos zu jedem Signal aus dem Buchkapitel "Unterstützung und Widerstand". **Es filtert nichts:** Auslöser, Signale und Mail-Empfänger bleiben unverändert.

Regeln:
- **Swing-Punkte** (`buchbot/swings.py`): Ein Hoch ist ein Swing-Hoch, wenn sein High größer ist als die `SWING_N` Highs davor und mindestens so groß wie die `SWING_N` Highs danach (Tiefs spiegelverkehrt). Ein Pivot gilt erst als bestätigt, wenn `SWING_N` Kerzen danach vorliegen. Für eine Kerze werden nur Pivots mit Index `<= t - SWING_N` genutzt, also keine Zukunftsdaten.
- **Zonen** (`buchbot/zones.py`): Alle Pivot-Preise der letzten `SR_LOOKBACK_CANDLES` Kerzen werden sortiert und gierig geclustert. Ein neuer Cluster beginnt, wenn ein Preis mehr als `SR_ZONE_WIDTH_ATR` × ATR über dem tiefsten Preis des Clusters liegt. Die Zone reicht vom tiefsten bis zum höchsten Preis, mindestens 0,25 × ATR breit. `touches` ist die Anzahl der Pivots. Stark ist eine Zone mit `touches >= SR_MIN_TOUCHES`. Liegt ihre Mitte unter dem Einstieg, ist sie Unterstützung, sonst Widerstand.
- **Annotation**: Jedes Signal (auch NEUTRAL) bekommt in `tags` die Felder `sr_relation`, `sr_zone_low`, `sr_zone_high`, `sr_touches`, `sr_aligned`, `sr_against`, `sr_room_atr` und `swing_trend`. Gerechnet wird nur mit Kerzen bis zur Signalkerze.
  - BUY passt an starker Unterstützung, SELL an starkem Widerstand. Dabei zählt das Muster innerhalb der Zone, erweitert um `SR_PROXIMITY_ATR` × ATR.
  - `sr_against`: BUY mit starkem Widerstand knapp über dem Einstieg, SELL mit starker Unterstützung knapp unter dem Einstieg.
  - `swing_trend`: `up` / `down` bei zwei höheren bzw. tieferen Swing-Hochs und -Tiefs, sonst `range`. Der EMA-Trendfilter bleibt unverändert.
- **CSV**: Die acht SR-Spalten stehen am Ende der Kopfzeile. Eine alte Kopfzeile wird in place erweitert, Zeilen bleiben erhalten. Eine fremde Kopfzeile wird weiterhin umbenannt.
- **Mail**: Bei einer Zone stehen unter den Zahlen Zeilen wie `Zone: Unterstützung 1.09420–1.09450 (4 Berührungen), Muster liegt an der Zone`, `Achtung: Widerstand ... nur 0.4 ATR über dem Einstieg` und `Swing-Trend: aufwärts`.

Parameter in `buchbot/config.py` (marktunabhängig, ATR-relativ):

| Parameter | Wert | Bedeutung |
|---|---|---|
| `SR_ENABLED` | `True` | `False`: Verhalten wie vor Schritt 12a |
| `SWING_N` | `3` | Kerzen links/rechts für einen Pivot |
| `SR_LOOKBACK_CANDLES` | `400` | Kerzen für Pivots und Zonen |
| `SR_ZONE_WIDTH_ATR` | `0.5` | Clustergrenze in ATR |
| `SR_MIN_ZONE_WIDTH_ATR` | `0.25` | Mindestbreite einer Zone in ATR |
| `SR_MIN_TOUCHES` | `3` | Berührungen für eine starke Zone |
| `SR_PROXIMITY_ATR` | `0.5` | Nähe in ATR für Zonenbezug und `sr_against` |
| `SR_IN_MAIL` | `True` | Zeilen zur Zone in die Mail; per `.env` überschreibbar mit `BUCH_SR_IN_MAIL` (1/true/yes = an, 0/false/no = aus) |
| `SR_MAX_ZONES_PER_SIDE` | `None` | `None`: alle starken Zonen. Zahl N: je Seite nur die N mit den meisten Berührungen (Gleichstand: dem Einstieg nähere). Wirkt auf alle `sr_*`-Tags |
| `SR_WARN_MAX_ZONES` | `4` | Backtest-Warnung "Zonen zu dicht", wenn Ø starke Zonen je Kerze und Seite darüber liegen |
| `SR_FETCH_PERIOD` | `"14d"` | yfinance-Zeitraum, wenn mehr Kerzen nötig sind |

Die Pipeline holt für Zonen mindestens `SR_LOOKBACK_CANDLES + SWING_N` Kerzen. Fehlen Kerzen, wird eine Zeile ins Log geschrieben. Detektoren, Trendfilter, ATR und SL/TP arbeiten weiter mit den letzten `LOOKBACK_CANDLES`.

## Backtest-Output

```
Muster                    Signale     TP    SL  Timeout  Avg Pips        R
---
Bullish Engulfing              23  52% 39%    9%     12.5    0.84
Bearish Engulfing              19  47% 42%   11%      8.3    0.61
...
GESAMT                        215                       10.1
```

- **Signale:** Anzahl gefundener Muster in der Historie
- **TP/SL/Timeout:** Wie oft TP erreicht, SL erreicht, oder Zeitlimit überschritten
- **Avg Pips:** Durchschnittliches Ergebnis in Pips
- **R:** Ergebnis in Risikoeinheiten (TP = +2, SL = −1, Timeout = proportional)

## Tests

Neuer Bot (`buchbot`):

```bash
pytest tests_buchbot -v
```

Alter Bot (unverändert):

```bash
pytest tests/ -v
```

Dekkt ab:
- ✅ Alle 10 Muster (jeweils 1 Pass + 1 Fail-Variante)
- ✅ SL/TP-Berechnung für BUY und SELL
- ✅ Zu kleine Signale werden verworfen
- ✅ Trend-Filter (Aufwärts- & Abwärtstrend)
- ✅ Duplikat-Schutz

## Wichtige Hinweise

1. **Kein Anlagerat!** Dieser Bot ist nur Mustererkennung. Forex mit Hebel ist hochriskant.
2. **Paper-Trading empfohlen** – teste zuerst mit echtem Backtest & Demokonto.
3. **Abhängigkeiten:** yfinance ist kostenlos, aber nicht 100% zuverlässig. Netzwerkfehler werden geloggt.
4. **Gmail App-Passwort** – unbedingt genau befolgen, sonst Fehler beim E-Mail-Versand.
5. **Zeitzone:** Der Bot arbeitet intern mit UTC. Lokale Zeit für E-Mail aus `.env`.
6. **Raspberry Pi:** CPU-Last minimal, braucht Internetverbindung.

## Lizenz

MIT (oder nach Belieben)

## Credits

Inspiriert durch klassische Forex-Technische-Analyse. Implementierung mit pandas/numpy (kein TA-Lib nötig).
