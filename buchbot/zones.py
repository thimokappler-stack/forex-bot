"""
Unterstützung und Widerstand (Buch Kapitel 9) als Zusatzinfo.

Zonen entstehen aus bestätigten Swing-Punkten, die auf Daten bis zur Signalkerze
berechnet werden. Es wird nichts gefiltert: Die Ergebnisse landen nur als Tags
im Signal (CSV, Mail, Backtest).
"""

from dataclasses import dataclass

import pandas as pd

from buchbot.swings import HIGH, LOW, find_swings


SUPPORT = "support"
RESISTANCE = "resistance"
SR_COLUMNS = [
    "sr_relation", "sr_zone_low", "sr_zone_high", "sr_touches",
    "sr_aligned", "sr_against", "sr_room_atr", "swing_trend",
]


@dataclass(frozen=True)
class Zone:
    low: float
    high: float
    touches: int
    kind: str  # SUPPORT oder RESISTANCE
    strong: bool


def build_zones(pivots, atr, entry, config):
    """Zonen aus Swing-Punkten: sortieren, greedy clustern, Band bilden."""
    prices = sorted(s.price for s in pivots)
    clusters = []
    for price in prices:
        if clusters and price - clusters[-1][0] <= config.SR_ZONE_WIDTH_ATR * atr:
            clusters[-1].append(price)
        else:
            clusters.append([price])

    zones = []
    min_width = config.SR_MIN_ZONE_WIDTH_ATR * atr
    for cluster in clusters:
        low, high = cluster[0], cluster[-1]
        if high - low < min_width:
            mid = (low + high) / 2
            low, high = mid - min_width / 2, mid + min_width / 2
        kind = SUPPORT if (low + high) / 2 < entry else RESISTANCE
        zones.append(Zone(low, high, len(cluster), kind, len(cluster) >= config.SR_MIN_TOUCHES))
    return zones


def swing_trend(pivots):
    """"up", "down", "range" oder None (zu wenige Pivots)."""
    highs = [s.price for s in pivots if s.kind == HIGH]
    lows = [s.price for s in pivots if s.kind == LOW]
    if len(highs) < 2 or len(lows) < 2:
        return None
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "up"
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "down"
    return "range"


def _distance(zone, price):
    """Abstand des Preises zum Band der Zone, 0 wenn er darin liegt."""
    if price < zone.low:
        return zone.low - price
    if price > zone.high:
        return price - zone.high
    return 0.0


def _nearest(zones, key):
    return min(zones, key=key, default=None)


def _tag(signal, zones, trend, config):
    atr = signal.atr
    entry = signal.entry
    prox = config.SR_PROXIMITY_ATR * atr
    strong = [z for z in zones if z.strong]
    tags = signal.tags
    tags["swing_trend"] = trend
    match = None
    aligned = None
    against = None
    room = None

    if signal.direction == "BUY":
        price = tags.get("pattern_low", entry)
        wanted = SUPPORT
        match = _nearest(
            [z for z in strong if z.kind == wanted and _distance(z, price) <= prox],
            key=lambda z: _distance(z, price),
        )
        aligned = match is not None
        against = _nearest(
            [z for z in strong if z.kind == RESISTANCE and 0 < z.low - entry < prox],
            key=lambda z: z.low,
        )
        if against is not None:
            tags["sr_against_level"] = against.low
            tags["sr_against_atr"] = (against.low - entry) / atr
        ahead = [z for z in strong if z.low > entry]
        nearest_ahead = _nearest(ahead, key=lambda z: z.low)
        room = (nearest_ahead.low - entry) / atr if nearest_ahead else None
    elif signal.direction == "SELL":
        price = tags.get("pattern_high", entry)
        wanted = RESISTANCE
        match = _nearest(
            [z for z in strong if z.kind == wanted and _distance(z, price) <= prox],
            key=lambda z: _distance(z, price),
        )
        aligned = match is not None
        against = _nearest(
            [z for z in strong if z.kind == SUPPORT and 0 < entry - z.high < prox],
            key=lambda z: -z.high,
        )
        if against is not None:
            tags["sr_against_level"] = against.high
            tags["sr_against_atr"] = (entry - against.high) / atr
        below = [z for z in strong if z.high < entry]
        nearest_below = _nearest(below, key=lambda z: -z.high)
        room = (entry - nearest_below.high) / atr if nearest_below else None
    else:
        match = _nearest(
            [z for z in strong if _distance(z, entry) <= prox],
            key=lambda z: _distance(z, entry),
        )

    tags["sr_relation"] = "none"
    tags["sr_zone_low"] = tags["sr_zone_high"] = tags["sr_touches"] = None
    tags["sr_zone_kind"] = None
    if match is not None:
        tags["sr_relation"] = "at_support" if match.kind == SUPPORT else "at_resistance"
        tags["sr_zone_low"] = match.low
        tags["sr_zone_high"] = match.high
        tags["sr_touches"] = match.touches
        tags["sr_zone_kind"] = match.kind
    tags["sr_strong_zones"] = len(strong)
    tags["sr_aligned"] = aligned
    tags["sr_against"] = None if signal.direction == "NEUTRAL" else against is not None
    tags["sr_room_atr"] = room


def annotate(signals, df, config):
    """Schreibt die SR-Tags in jedes Signal. Nutzt nur Daten bis zur Signalkerze."""
    if not config.SR_ENABLED:
        return signals
    for signal in signals:
        pos = df.index.get_loc(signal.time - pd.Timedelta(config.INTERVAL))
        window = df.iloc[:pos + 1].iloc[-config.SR_LOOKBACK_CANDLES:]
        pivots = find_swings(window, config.SWING_N)
        zones = build_zones(pivots, signal.atr, signal.entry, config)
        _tag(signal, zones, swing_trend(pivots), config)
    return signals
