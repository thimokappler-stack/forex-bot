"""
Signal-Datenstruktur. Alle Module tauschen nur diese Struktur aus.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Signal:
    time: Any                      # Schlusszeit der Signalkerze (UTC)
    symbol: str                    # z. B. "EURUSD=X"
    interval: str                  # z. B. "15m"
    source: str                    # z. B. "candles_main"
    pattern: str                   # z. B. "Morning Star"
    direction: str                 # "BUY", "SELL" oder "NEUTRAL"
    entry: float                   # Schluss der letzten Musterkerze
    atr: float                     # ATR zum Signalzeitpunkt
    sl: Optional[float] = None     # Stop-Loss (noch nicht berechnet)
    tp: Optional[float] = None     # Take-Profit (noch nicht berechnet)
    risk_pips: Optional[float] = None
    rr: Optional[float] = None
    mode: str = "log_only"         # "off", "log_only", "notify" (vom Detektor-Betrieb gesetzt)
    tags: dict = field(default_factory=dict)
