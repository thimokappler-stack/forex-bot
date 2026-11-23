"""
Zentrale Konfiguration für den EUR/USD Candlestick Signal Bot.
Alle Parameter sind hier definiert und leicht änderbar.

Richtlinien:
- Keine festen Zahlen im Code, alles hier definieren
- Keine Geheimnisse (Passwörter, API-Keys) hier, nur in .env
- Parameter-Namen aussagekräftig, mit Kommentar erklären
"""

# === DATENQUELLE ===
SYMBOL = "EURUSD=X"           # yfinance Symbol für EUR/USD
INTERVAL = "15m"              # Kerzenlänge
LOOKBACK_CANDLES = 100        # Anzahl geholter Kerzen

# === TRENDFILTER ===
TREND_EMA_PERIOD = 50         # EMA-Periode für Trend-Filter
                              # Schlusskurs über EMA = Aufwärtstrend

# === VOLATILITÄT (ATR) ===
ATR_PERIOD = 14               # ATR-Periode für Größenvergleiche

# === KERZENGRÖSSEN (relativ zu ATR) ===
LONG_BODY_ATR = 0.8           # "Lange Kerze": Körper ≥ 0.8 × ATR
SMALL_BODY_ATR = 0.3          # "Kleiner Körper": Körper ≤ 0.3 × ATR

# === MUSTER-TOLERANZEN ===
TWEEZER_TOLERANCE = 0.00015   # ~1.5 Pips Toleranz bei "gleichen" Hochs/Tiefs
TWEEZER_BODY_SIMILARITY = 0.6 # Kleinerer Körper ≥ 60% des größeren

# === STAR-MUSTER (Morning/Evening Star) ===
STAR_MIDDLE_MAX_RATIO = 0.5   # Körper K2 ≤ 50% von K1
STAR_LAST_MIN_RATIO = 0.5     # Körper K3 > 50% von K1
STAR_REQUIRE_CLOSE_BEYOND_MID = False  # Optional: Schlusskurs K3 über/unter Mitte K1

# === SOLDATEN-MUSTER (Three White/Black) ===
SOLDIERS_REQUIRE_OPEN_IN_BODY = False  # Optional: Eröffnung im Körper der vorherigen Kerze
SOLDIERS_K1_MAX_ATR = 0.5              # K1 "klein": Körper ≤ 0.5 × ATR

# === DREIER-PATTERN (Rising/Falling) ===
RISEFALL_REQUIRE_INSIDE_RANGE = True   # Mittlere Kerzen innerhalb Spanne K1

# === EINZELKERZEN-MUSTER (Background-Analyse) ===
SINGLE_PATTERNS_MODE = "log_only"      # "off", "log_only", "notify"
                                        # "log_only" = keine E-Mail, nur background_signals.csv
DOJI_BODY_RATIO = 0.10                 # Doji: Körper ≤ 10% der Kerzenspanne
WICK_LONG_RATIO = 2.0                  # Langer Docht ≥ 2 × Körper
WICK_SMALL_RATIO = 0.10                # Kleiner Docht ≤ 10% der Kerzenspanne

# === RISIKO & STOP-LOSS ===
SL_BUFFER_ATR = 0.5           # Puffer hinter Muster-Extrem: 0.5 × ATR
MIN_SL_PIPS = 5               # Mindestabstand Einstieg bis SL in Pips
RISK_REWARD = 2.0             # Take-Profit = 2 × Risiko → CRV 1:2
PIP_SIZE = 0.0001             # Pip-Größe bei EUR/USD

# === DETEKTOREN ===
# Betrieb je Detektor: "off", "log_only" (nur Log/CSV), "notify" (E-Mail)
DETECTORS = {
    "candles_main": "log_only",
    "candles_single": "off",
}

# === PIPELINE & MARKTZEITEN ===
# Marktzeiten als (Wochentag, Stunde UTC); Montag = 0, Sonntag = 6
MARKET_CLOSED_FROM = (4, 22)  # Freitag 22:00 UTC: Markt geschlossen
MARKET_CLOSED_UNTIL = (6, 22) # Sonntag 22:00 UTC: Markt wieder offen
STALE_MAX_MINUTES = 45        # Letzte geschlossene Kerze älter als das = "Daten veraltet"
EVAL_WINDOW_CANDLES = 2       # Pro Lauf ausgewertete geschlossene Kerzen (1 = nur die letzte)
STATE_FILE = "state_new.json" # Duplikat-Schutz, relativ zum Projektordner
STATE_RETENTION_DAYS = 7      # Einträge im Duplikat-Schutz werden nach so vielen Tagen entfernt
SIGNALS_CSV_FILE = "signals_log.csv"  # Signal-Protokoll, relativ zum Projektordner

# === E-MAIL ===
NOTIFY_ENABLED = False        # Schalter: solange False, wird keine Mail gesendet
DISPLAY_SYMBOL = "EUR/USD"    # Anzeigename im Betreff und Text
DISPLAY_TZ = "Europe/Berlin"  # Lokale Zeit in der Mail
MAIL_SMTP_HOST = "smtp.gmail.com"
MAIL_SMTP_PORT = 465          # SMTP über SSL
MAIL_TIMEOUT_SECONDS = 30
MAIL_DISCLAIMER = "Kein Anlagerat, nur Mustererkennung."

# === BACKTEST ===
MAX_HOLD_CANDLES = 32         # Max Haltedauer: 32 Kerzen = 8 Stunden
SPREAD_PIPS = 1.0             # Angenommener Spread in Pips
MIN_SIGNALS_FOR_STATS = 30    # Minimum Signale für belastbare Backtest-Aussage
BACKTEST_PERIOD = "60d"       # Historie für den Backtest (yfinance-Maximum für 15m)
BACKTEST_CSV_FILE = "backtest_results.csv"  # Einzelsignale, relativ zum Projektordner
