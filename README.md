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
python -m buchbot.backtest
```

Ausgabe: Tabelle mit für jedes Muster:
- Anzahl Signale
- Anteil TP / SL / Timeout
- Durchschnittliches Ergebnis in R (TP = +2, SL = -1, etc.)

### Tests

```bash
pytest tests/
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
