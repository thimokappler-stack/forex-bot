"""
Zentrale Konfiguration für den EUR/USD Candlestick Signal Bot.
Alle Parameter sind hier definiert und leicht änderbar.
"""

# === Datenquelle ===
SYMBOL = "EURUSD=X"          # yfinance Symbol für EUR/USD
INTERVAL = "15m"              # Kerzenlänge
LOOKBACK_CANDLES = 100        # Anzahl geholter Kerzen

# === Trendfilter ===
TREND_EMA_PERIOD = 50         # Schlusskurs über EMA = Aufwärtstrend

# === Volatilitätsmessung (ATR) ===
ATR_PERIOD = 14               # ATR-Periode für Größenvergleiche

# === Kerzengrößen (relativ zu ATR) ===
LONG_BODY_ATR = 0.8           # "Lange Kerze": Körper ≥ 0.8 × ATR
SMALL_BODY_ATR = 0.3          # "Kleiner Körper": Körper ≤ 0.3 × ATR

# === Muster-Toleranzen ===
TWEEZER_TOLERANCE = 0.00015   # ~1.5 Pips Toleranz bei "gleichen" Hochs/Tiefs
MIN_SHADOW_RATIO = 0.25       # "Kleine Schatten": Schatten ≤ 25% der Kerzenspanne

# === Risiko & Stop-Loss ===
SL_BUFFER_ATR = 0.5           # Puffer hinter Muster-Extrem: 0.5 × ATR
MIN_SL_PIPS = 5               # Mindestabstand Einstieg bis SL in Pips
RISK_REWARD = 2.0             # Take-Profit = 2 × (Einstieg - SL) → CRV 1:2
PIP_SIZE = 0.0001             # Pip-Größe bei EUR/USD

# === Backtest ===
MAX_HOLD_CANDLES = 32         # Max Haltedauer: 32 Kerzen = 8 Stunden
SPREAD_PIPS = 1.0             # Angenommener Spread in Pips
