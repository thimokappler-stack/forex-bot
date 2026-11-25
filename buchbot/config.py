"""
Zentrale Konfiguration für den EUR/USD Candlestick Signal Bot.
Alle Parameter sind hier definiert und leicht änderbar.

Richtlinien:
- Keine festen Zahlen im Code, alles hier definieren
- Keine Geheimnisse (Passwörter, API-Keys) hier, nur in .env
- Parameter-Namen aussagekräftig, mit Kommentar erklären
"""

from types import SimpleNamespace

# === MÄRKTE ===
# Je Markt: Anzeigename, yfinance-Symbol, Handelszeiten ("forex" = Fr 22:00 bis So 22:00 UTC
# geschlossen, "24_7" ohne Pause), Pip-Größe, Risiko-Einheit, Mindestabstand des SL,
# Spread (Backtest), Tweezer-Toleranz (absolut oder Anteil am ATR), Preisformat.
# "detectors": None = globale DETECTORS, sonst eigene Modi je Detektor.
MARKETS = {
    "EURUSD": {
        "display": "EUR/USD", "symbol": "EURUSD=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.0,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
    },
    "GBPUSD": {
        "display": "GBP/USD", "symbol": "GBPUSD=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.0,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
    },
    "BTC": {
        "display": "Bitcoin", "symbol": "BTC-USD", "hours": "24_7",
        "pip_size": 1.0, "risk_unit": "USD", "min_sl_pips": 10, "spread_pips": 10.0,
        "tweezer_tolerance": None, "tweezer_atr_fraction": 0.15,
        "price_decimals": 2, "detectors": None,
    },
    "ETH": {
        "display": "Ethereum", "symbol": "ETH-USD", "hours": "24_7",
        "pip_size": 1.0, "risk_unit": "USD", "min_sl_pips": 5, "spread_pips": 5.0,
        "tweezer_tolerance": None, "tweezer_atr_fraction": 0.15,
        "price_decimals": 2, "detectors": None,
    },
    # Beobachtungsmarkt: EUR/USD mit 30m-Kerzen. Nur log_only, sendet nie Mails.
    "EURUSD_30M": {
        "display": "EUR/USD (30m)", "symbol": "EURUSD=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.0,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
        "interval": "30m", "observe_only": True,
    },
    # Beobachtungsmärkte (Standard in OBSERVE_ONLY_MARKETS): nur Auswertung und CSV, keine Mail.
    # Mindestabstand und Spread sind Startwerte und in dieser Datei änderbar.
    "USDJPY": {
        "display": "USD/JPY", "symbol": "USDJPY=X", "hours": "forex",
        "pip_size": 0.01, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.0,
        "tweezer_tolerance": 0.015, "tweezer_atr_fraction": None,
        "price_decimals": 3, "detectors": None,
    },
    "AUDUSD": {
        "display": "AUD/USD", "symbol": "AUDUSD=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 3, "spread_pips": 1.0,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
    },
    "GBPJPY": {
        "display": "GBP/JPY", "symbol": "GBPJPY=X", "hours": "forex",
        "pip_size": 0.01, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 2.0,
        "tweezer_tolerance": 0.015, "tweezer_atr_fraction": None,
        "price_decimals": 3, "detectors": None,
    },
    "USDCAD": {
        "display": "USD/CAD", "symbol": "USDCAD=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.5,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
    },
    "USDCHF": {
        "display": "USD/CHF", "symbol": "USDCHF=X", "hours": "forex",
        "pip_size": 0.0001, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.5,
        "tweezer_tolerance": 0.00015, "tweezer_atr_fraction": None,
        "price_decimals": 5, "detectors": None,
    },
    "EURJPY": {
        "display": "EUR/JPY", "symbol": "EURJPY=X", "hours": "forex",
        "pip_size": 0.01, "risk_unit": "Pips", "min_sl_pips": 5, "spread_pips": 1.5,
        "tweezer_tolerance": 0.015, "tweezer_atr_fraction": None,
        "price_decimals": 3, "detectors": None,
    },
    # Gold als Future (GC=F): XAUUSD=X liefert bei yfinance keine Daten.
    "GOLD": {
        "display": "Gold", "symbol": "GC=F", "hours": "futures_gold",
        "pip_size": 1.0, "risk_unit": "USD", "min_sl_pips": 2, "spread_pips": 0.5,
        "tweezer_tolerance": None, "tweezer_atr_fraction": 0.15,
        "price_decimals": 2, "detectors": None,
    },
}
DEFAULT_MARKET = "EURUSD"
# "interval" je Markt in MARKETS, fehlt er, gilt INTERVAL.
# "observe_only" in MARKETS ist fest (EURUSD_30M): nie Mail. Die übrigen Beobachtungsmärkte kommen aus OBSERVE_ONLY_MARKETS.

# === DATENQUELLE ===
INTERVAL = "15m"              # Kerzenlänge (Standard, je Markt überschreibbar)
INTERVAL_MINUTES = {"15m": 15, "30m": 30}
LOOKBACK_CANDLES = 100        # Anzahl geholter Kerzen
MARKET_PAUSE_SECONDS = 1      # Pause zwischen zwei Märkten (schont yfinance bei vielen Abrufen)
FETCH_RETRY_SECONDS = 5       # Wartezeit vor einem einzigen Wiederholungsversuch bei leerer Antwort oder Fehler

# === TRENDFILTER ===
TREND_EMA_PERIOD = 50         # EMA-Periode für Trend-Filter
                              # Schlusskurs über EMA = Aufwärtstrend

# === VOLATILITÄT (ATR) ===
ATR_PERIOD = 14               # ATR-Periode für Größenvergleiche

# === UNTERSTÜTZUNG UND WIDERSTAND (Kapitel 9, nur Zusatzinfo, filtert nichts) ===
SR_ENABLED = True             # False: Bot verhält sich exakt wie ohne Zonen
SWING_N = 3                   # Pivot gilt als bestätigt, wenn n Kerzen danach vorliegen
SR_LOOKBACK_CANDLES = 400     # Kerzen, aus denen Zonen gebildet werden
SR_ZONE_WIDTH_ATR = 0.5       # Pivots mit Abstand > 0.5 × ATR zum Clusteranfang bilden neuen Cluster
SR_MIN_ZONE_WIDTH_ATR = 0.25  # Mindestbreite einer Zone (um die Mitte zentriert)
SR_MIN_TOUCHES = 3            # Ab so vielen Pivots gilt eine Zone als stark
SR_PROXIMITY_ATR = 0.5        # Nähe zur Zone in ATR (beidseitig erweitert, auch für sr_against)
SR_IN_MAIL = True             # Zonen-Zeilen in die Mail; Überschreibung per .env: BUCH_SR_IN_MAIL
SR_MAX_ZONES_PER_SIDE = None  # None = alle starken Zonen; N = je Seite nur die N mit den meisten Berührungen
SR_WARN_MAX_ZONES = 4         # Backtest: Ø starke Zonen je Kerze und Seite über diesem Wert -> Warnung
SR_FETCH_PERIOD = "14d"       # yfinance-Periode, damit SR_LOOKBACK_CANDLES + SWING_N Kerzen reichen

# === KERZENGRÖSSEN (relativ zu ATR) ===
LONG_BODY_ATR = 0.8           # "Lange Kerze": Körper ≥ 0.8 × ATR
SMALL_BODY_ATR = 0.3          # "Kleiner Körper": Körper ≤ 0.3 × ATR

# === MUSTER-TOLERANZEN ===
# Tweezer-Toleranz je Markt in MARKETS (absolut oder Anteil am ATR)
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
RISEFALL_MIN_COUNTER_CANDLES = 3       # Mindestzahl gegenläufiger Mittelkerzen (3 = Buchregel, 2 = altes Verhalten)

# === EINZELKERZEN-MUSTER (Hintergrund-Analyse, Betriebsart über DETECTORS) ===
DOJI_BODY_RATIO = 0.10                 # Doji: Körper ≤ 10% der Kerzenspanne
WICK_LONG_RATIO = 2.0                  # Langer Docht ≥ 2 × Körper
WICK_SMALL_RATIO = 0.10                # Kleiner Docht ≤ 10% der Kerzenspanne

# === RISIKO & STOP-LOSS ===
SL_BUFFER_ATR = 0.5           # Puffer hinter Muster-Extrem: 0.5 × ATR
RISK_REWARD = 2.0             # Take-Profit = 2 × Risiko → CRV 1:2
# Mindestabstand (min_sl_pips), Pip-Größe und Einheit stehen je Markt in MARKETS

# === DETEKTOREN ===
# Betrieb je Detektor: "off", "log_only" (nur Log/CSV), "notify" (E-Mail)
DETECTORS = {
    "candles_main": "log_only",
    "candles_single": "log_only",
}
# Überschreibbar per .env: BUCH_DETECTOR_MODES="candles_main=notify,candles_single=log_only"

# === PIPELINE & MARKTZEITEN ===
# Handelszeiten je Markt ("hours"): "forex" (Marktzeiten unten, UTC), "24_7", "futures_gold"
# (Fr 17:00 bis So 18:00 und Mo-Do 17:00-18:00 New Yorker Zeit, Feiertage nicht berücksichtigt).
# Marktzeiten als (Wochentag, Stunde UTC); Montag = 0, Sonntag = 6
MARKET_CLOSED_FROM = (4, 22)  # Freitag 22:00 UTC: Markt geschlossen
MARKET_CLOSED_UNTIL = (6, 22) # Sonntag 22:00 UTC: Markt wieder offen
STALE_CANDLES = 3             # Letzte geschlossene Kerze älter als 3 Kerzenlängen = "Daten veraltet" (je Markt)
CLOCK_TOLERANCE_MINUTES = 2   # Toleranz für die Uhrzeit-Prüfung (Systemuhr geht nach)
EVAL_WINDOW_CANDLES = 2       # Pro Lauf ausgewertete geschlossene Kerzen (1 = nur die letzte)
STATE_FILE = "state_new.json" # Duplikat-Schutz, relativ zum Projektordner
STATE_RETENTION_DAYS = 7      # Einträge im Duplikat-Schutz werden nach so vielen Tagen entfernt
SIGNALS_CSV_FILE = "signals_log.csv"  # Signal-Protokoll, relativ zum Projektordner

# === E-MAIL ===
# Mails nur, wenn NOTIFY_ENABLED an ist UND der Markt in BUCH_NOTIFY_MARKETS steht (.env)
NOTIFY_ENABLED = False        # Standard aus; Überschreibung per .env: BUCH_NOTIFY_ENABLED
DISPLAY_TZ = "Europe/Berlin"  # Lokale Zeit in der Mail
MAIL_SMTP_HOST = "smtp.gmail.com"
MAIL_SMTP_PORT = 465          # SMTP über SSL
MAIL_TIMEOUT_SECONDS = 30
MAIL_DISCLAIMER = "Kein Anlagerat, nur Mustererkennung."

# === BACKTEST ===
MAX_HOLD_CANDLES = 32         # Max Haltedauer in Kerzen (15m: 8 Stunden, 30m: 16 Stunden), je Markt überschreibbar
MIN_SIGNALS_FOR_STATS = 30    # Minimum Signale für belastbare Backtest-Aussage
ZONE_WARN_SHARE_HIGH = 0.80   # Zonen-Verteilung: eine Gruppe über diesem Anteil -> Warnung
ZONE_WARN_SHARE_LOW = 0.05    # Zonen-Verteilung: eine Gruppe unter diesem Anteil -> Warnung
BACKTEST_PERIOD = "60d"       # Historie für den Backtest (yfinance-Maximum für 15m)
BACKTEST_PERIOD_BY_INTERVAL = {"15m": "60d", "30m": "60d", "1h": "730d", "1d": "max"}  # Zeitraum je Intervall (yfinance-Grenzen)
BACKTEST_SPREAD_MODES = ("both", "with", "without")  # Ergebnis vor und nach Kosten (both), nur nach Kosten, nur vor Kosten
MIN_CANDLES_FOR_BACKTEST = 500  # Märkte mit weniger brauchbaren Kerzen werden übersprungen
DECADE_BOUNDARIES = (2010, 2020)  # Jahrzehnt-Aufteilung: bis 2009, 2010 bis 2019, ab 2020
BACKTEST_CSV_FILE = "backtest_results.csv"  # Einzelsignale, relativ zum Projektordner

# Nullvergleich (--null-test) und vorab festgelegte Kriterien K1 bis K5
NULL_TEST_SEED = 12345        # Zufallsstartwert der Permutation
NULL_TEST_DRAWS = 2000        # Anzahl Ziehungen
NULL_PATTERN_CANDLES = 2      # Pseudo-Muster aus den letzten N Kerzen
NULL_QUANTILES = (0.05, 0.95, 0.99)  # Quantile der Nullverteilung (K1_QUANTILE muss enthalten sein)
K1_QUANTILE = 0.99            # K1: Ø R vor Kosten über diesem Quantil der Nullverteilung (p < 0.01)
K2_MIN_DECADES = 2            # K2: Ø R vor Kosten > 0 in mindestens so vielen Jahrzehnten
K3_MIN_TRADES = 30            # K3: nur Märkte mit mindestens so vielen Trades zählen
K3_MIN_SHARE = 0.6            # K3: Anteil dieser Märkte mit Ø R vor Kosten > 0
K4_MIN_RATIO = 3              # K4: Ø R vor Kosten geteilt durch Cluster-SE über diesem Wert
NULL_EXCLUDED_MARKETS = ("BTC", "ETH", "GOLD")  # Zusatzzahl: gepoolt ohne diese Märkte

# Detektoren, die nie per Mail laufen dürfen (Hintergrund-Analyse)
LOG_ONLY_DETECTORS = ("candles_single",)
DETECTOR_MODES = ("off", "log_only", "notify")
# Beobachtungsmärkte mit Standard-Liste. Überschreibbar per .env: BUCH_OBSERVE_ONLY_MARKETS (vollständige Liste, leer = keine).
OBSERVE_ONLY_MARKETS = ("USDJPY", "AUDUSD", "GBPJPY", "USDCAD", "USDCHF", "EURJPY", "GOLD")


class SettingsError(ValueError):
    """Ungültiger Wert in den Einstellungen (.env)."""


def _parse_markets(raw, variable):
    names = []
    for name in raw.split(","):
        name = name.strip().upper()
        if not name:
            continue
        if name not in MARKETS:
            raise SettingsError(
                f"{variable}: unbekannter Markt '{name}' "
                f"(erlaubt: {', '.join(MARKETS)})"
            )
        names.append(name)
    return tuple(names)


def _parse_bool(environ, variable, default):
    raw = environ.get(variable, "").strip().lower()
    if raw == "":
        return default
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    raise SettingsError(
        f"{variable}: ungültiger Wert '{raw}' (erlaubt: 1, true, yes, 0, false, no)"
    )


def read_settings(environ):
    """Liest BUCH_NOTIFY_ENABLED, BUCH_SR_IN_MAIL, BUCH_NOTIFY_MARKETS, BUCH_OBSERVE_ONLY_MARKETS und BUCH_DETECTOR_MODES."""
    notify_enabled = _parse_bool(environ, "BUCH_NOTIFY_ENABLED", NOTIFY_ENABLED)
    sr_in_mail = _parse_bool(environ, "BUCH_SR_IN_MAIL", SR_IN_MAIL)

    notify_markets = _parse_markets(environ.get("BUCH_NOTIFY_MARKETS", ""), "BUCH_NOTIFY_MARKETS")
    if "BUCH_OBSERVE_ONLY_MARKETS" in environ:
        observe_markets = _parse_markets(environ["BUCH_OBSERVE_ONLY_MARKETS"], "BUCH_OBSERVE_ONLY_MARKETS")
    else:
        observe_markets = OBSERVE_ONLY_MARKETS

    detector_modes = {}
    for item in environ.get("BUCH_DETECTOR_MODES", "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SettingsError(
                f"BUCH_DETECTOR_MODES: '{item}' hat kein Format name=modus"
            )
        name, mode = (part.strip() for part in item.split("=", 1))
        if name not in DETECTORS:
            raise SettingsError(
                f"BUCH_DETECTOR_MODES: unbekannter Detektor '{name}' "
                f"(erlaubt: {', '.join(DETECTORS)})"
            )
        if mode not in DETECTOR_MODES:
            raise SettingsError(
                f"BUCH_DETECTOR_MODES: unbekannter Modus '{mode}' "
                f"(erlaubt: {', '.join(DETECTOR_MODES)})"
            )
        if name in LOG_ONLY_DETECTORS and mode == "notify":
            raise SettingsError(
                f"BUCH_DETECTOR_MODES: '{name}' darf nicht im Modus notify laufen"
            )
        detector_modes[name] = mode

    return {
        "notify_enabled": notify_enabled,
        "sr_in_mail": sr_in_mail,
        "notify_markets": notify_markets,
        "observe_only_markets": observe_markets,
        "detector_modes": detector_modes,
    }


def for_market(name, settings=None):
    """
    Liefert eine Konfiguration für einen Markt: gemeinsame Werte aus diesem Modul,
    überschrieben durch die Marktwerte aus MARKETS und die Einstellungen aus .env.
    """
    if name not in MARKETS:
        raise SettingsError(f"Unbekannter Markt '{name}' (erlaubt: {', '.join(MARKETS)})")
    settings = settings if settings is not None else read_settings({})
    market = MARKETS[name]

    cfg = SimpleNamespace(**{key: value for key, value in globals().items() if key.isupper()})
    cfg.MARKET = name
    cfg.HOURS = market["hours"]
    cfg.SYMBOL = market["symbol"]
    cfg.DISPLAY_SYMBOL = market["display"]
    cfg.PIP_SIZE = market["pip_size"]
    cfg.RISK_UNIT = market["risk_unit"]
    cfg.MIN_SL_PIPS = market["min_sl_pips"]
    cfg.SPREAD_PIPS = market["spread_pips"]
    cfg.TWEEZER_TOLERANCE = market["tweezer_tolerance"]
    cfg.TWEEZER_ATR_FRACTION = market["tweezer_atr_fraction"]
    cfg.PRICE_DECIMALS = market["price_decimals"]
    cfg.INTERVAL = market.get("interval", INTERVAL)
    if cfg.INTERVAL not in INTERVAL_MINUTES:
        raise SettingsError(f"Markt '{name}': ungültiges Intervall '{cfg.INTERVAL}' "
                            f"(erlaubt: {', '.join(INTERVAL_MINUTES)})")
    minutes = INTERVAL_MINUTES[cfg.INTERVAL]
    cfg.STALE_MAX_MINUTES = STALE_CANDLES * minutes
    cfg.MAX_HOLD_CANDLES = market.get("max_hold_candles", MAX_HOLD_CANDLES)
    cfg.OBSERVE_ONLY = (market.get("observe_only", False)
                        or name in settings.get("observe_only_markets", OBSERVE_ONLY_MARKETS))
    cfg.DETECTORS = {**DETECTORS, **(market["detectors"] or {}), **settings["detector_modes"]}
    if cfg.OBSERVE_ONLY:
        cfg.DETECTORS = {key: ("off" if mode == "off" else "log_only") for key, mode in cfg.DETECTORS.items()}
    cfg.SR_IN_MAIL = settings["sr_in_mail"]
    cfg.NOTIFY_IGNORED = cfg.OBSERVE_ONLY and name in settings["notify_markets"]
    cfg.NOTIFY_ENABLED = (settings["notify_enabled"] and name in settings["notify_markets"]
                          and not cfg.OBSERVE_ONLY)
    return cfg
