"""
Haupt-Muster (zehn Muster, die eine E-Mail auslösen).

Jede Musterfunktion prüft nur die Form der Kerzen (Farbe, Körper, Dochte, Lage).
Der Trendfilter steht in PATTERNS als `required_trend` und wird in signals.py angewendet.

Kerzen werden als Liste von Candle(open, high, low, close) übergeben,
in zeitlicher Reihenfolge, die letzte Kerze ist die des Musters.
"""

import math
from collections import namedtuple

import pandas as pd

import buchbot.config as cfg
from buchbot.data import calculate_atr
from buchbot.models import Signal


Candle = namedtuple("Candle", ["open", "high", "low", "close"])

Pattern = namedtuple("Pattern", ["name", "signal", "required_trend", "size", "check"])


def body(c):
    return abs(c.close - c.open)


def body_top(c):
    return max(c.open, c.close)


def body_bottom(c):
    return min(c.open, c.close)


def upper_wick(c):
    return c.high - body_top(c)


def lower_wick(c):
    return body_bottom(c) - c.low


def candle_range(c):
    return c.high - c.low


def is_green(c):
    return c.close > c.open


def is_red(c):
    return c.close < c.open


def is_long(c, atr):
    return body(c) >= cfg.LONG_BODY_ATR * atr


def is_small(c, atr):
    return body(c) <= cfg.SMALL_BODY_ATR * atr


def is_doji(c):
    return body(c) <= cfg.DOJI_BODY_RATIO * candle_range(c)


def _midpoint(c):
    return (c.open + c.close) / 2


def _engulfs(c1, c2):
    return (
        body(c2) > body(c1)
        and body_bottom(c2) <= body_bottom(c1)
        and body_top(c2) >= body_top(c1)
    )


def _similar_bodies(c1, c2):
    big = max(body(c1), body(c2))
    return big > 0 and min(body(c1), body(c2)) / big >= cfg.TWEEZER_BODY_SIMILARITY


def bullish_engulfing(candles, atr):
    c1, c2 = candles
    return is_red(c1) and is_green(c2) and _engulfs(c1, c2)


def bearish_engulfing(candles, atr):
    c1, c2 = candles
    return is_green(c1) and is_red(c2) and _engulfs(c1, c2)


def tweezer_bottom(candles, atr):
    c1, c2 = candles
    return (
        is_red(c1)
        and is_green(c2)
        and is_small(c1, atr)
        and is_small(c2, atr)
        and _similar_bodies(c1, c2)
        and abs(c1.low - c2.low) <= cfg.TWEEZER_TOLERANCE
    )


def tweezer_top(candles, atr):
    c1, c2 = candles
    return (
        is_green(c1)
        and is_red(c2)
        and is_small(c1, atr)
        and is_small(c2, atr)
        and _similar_bodies(c1, c2)
        and abs(c1.high - c2.high) <= cfg.TWEEZER_TOLERANCE
    )


def morning_star(candles, atr):
    c1, c2, c3 = candles
    return (
        is_red(c1)
        and is_red(c2)
        and is_green(c3)
        and is_long(c1, atr)
        and is_long(c3, atr)
        and not is_doji(c1)
        and body(c2) <= cfg.STAR_MIDDLE_MAX_RATIO * body(c1)
        and body(c3) > cfg.STAR_LAST_MIN_RATIO * body(c1)
        and (not cfg.STAR_REQUIRE_CLOSE_BEYOND_MID or c3.close > _midpoint(c1))
    )


def evening_star(candles, atr):
    c1, c2, c3 = candles
    return (
        is_green(c1)
        and is_green(c2)
        and is_red(c3)
        and is_long(c1, atr)
        and is_long(c3, atr)
        and not is_doji(c1)
        and body(c2) <= cfg.STAR_MIDDLE_MAX_RATIO * body(c1)
        and body(c3) > cfg.STAR_LAST_MIN_RATIO * body(c1)
        and (not cfg.STAR_REQUIRE_CLOSE_BEYOND_MID or c3.close < _midpoint(c1))
    )


def _open_in_body(prev, cur):
    return body_bottom(prev) <= cur.open <= body_top(prev)


def _three_soldiers(candles, atr, bullish):
    c1, c2, c3 = candles
    color = is_green if bullish else is_red
    wick = upper_wick if bullish else lower_wick

    if not all(color(c) for c in candles):
        return False
    if bullish and not (c1.close < c2.close < c3.close):
        return False
    if not bullish and not (c1.close > c2.close > c3.close):
        return False
    if not (body(c1) < body(c2) < body(c3)):
        return False
    if body(c1) > cfg.SOLDIERS_K1_MAX_ATR * atr:
        return False
    if not (wick(c2) <= cfg.WICK_SMALL_RATIO * candle_range(c2)):
        return False
    if not (wick(c3) <= cfg.WICK_SMALL_RATIO * candle_range(c3)):
        return False
    if cfg.SOLDIERS_REQUIRE_OPEN_IN_BODY and not (
        _open_in_body(c1, c2) and _open_in_body(c2, c3)
    ):
        return False
    return True


def three_white_soldiers(candles, atr):
    return _three_soldiers(candles, atr, bullish=True)


def three_black_crows(candles, atr):
    return _three_soldiers(candles, atr, bullish=False)


def _three_method(candles, atr, bullish):
    c1 = candles[0]
    middle = candles[1:4]
    c5 = candles[4]
    color_outer = is_green if bullish else is_red
    color_middle = is_red if bullish else is_green

    if not (color_outer(c1) and is_long(c1, atr)):
        return False
    if not (color_outer(c5) and is_long(c5, atr)):
        return False
    for m in middle:
        if not (color_middle(m) and is_small(m, atr)):
            return False
        if cfg.RISEFALL_REQUIRE_INSIDE_RANGE and not (
            m.low >= c1.low and m.high <= c1.high
        ):
            return False
    if bullish:
        return c5.close > c1.close
    return c5.close < c1.close


def rising_three_methods(candles, atr):
    return _three_method(candles, atr, bullish=True)


def falling_three_methods(candles, atr):
    return _three_method(candles, atr, bullish=False)


PATTERNS = (
    Pattern("Bullish Engulfing", "BUY", "down", 2, bullish_engulfing),
    Pattern("Bearish Engulfing", "SELL", "up", 2, bearish_engulfing),
    Pattern("Tweezer Bottom", "BUY", "down", 2, tweezer_bottom),
    Pattern("Tweezer Top", "SELL", "up", 2, tweezer_top),
    Pattern("Morning Star", "BUY", "down", 3, morning_star),
    Pattern("Evening Star", "SELL", "up", 3, evening_star),
    Pattern("Drei bullische Soldaten", "BUY", "down", 3, three_white_soldiers),
    Pattern("Drei bärische Soldaten", "SELL", "up", 3, three_black_crows),
    Pattern("Steigendes Dreier-Pattern", "BUY", "up", 5, rising_three_methods),
    Pattern("Fallendes Dreier-Pattern", "SELL", "down", 5, falling_three_methods),
)


def detect_patterns(df, atr, i=None):
    """
    Prüft alle Haupt-Muster, die mit der Kerze i enden.

    Args:
        df: DataFrame mit open, high, low, close (Index: Zeit)
        atr: Series mit ATR-Werten, gleiche Länge wie df
        i: Position der letzten Kerze des Musters (Standard: letzte Zeile)

    Returns:
        Liste von dicts mit name, signal, required_trend, time
    """
    if i is None:
        i = len(df) - 1
    atr_value = float(atr.iloc[i])
    if math.isnan(atr_value):
        return []

    found = []
    for p in PATTERNS:
        start = i - p.size + 1
        if start < 0:
            continue
        candles = [
            Candle(*map(float, df.iloc[k][["open", "high", "low", "close"]]))
            for k in range(start, i + 1)
        ]
        if p.check(candles, atr_value):
            found.append({
                "name": p.name,
                "signal": p.signal,
                "required_trend": p.required_trend,
                "time": df.index[i],
            })
    return found


SOURCE = "candles_main"
PATTERN_SIZES = {p.name: p.size for p in PATTERNS}


def detect(df, config):
    """
    Detektor-Einstieg: liefert Signal-Objekte für die letzte Kerze.

    SL/TP und Trendfilter werden hier noch nicht berechnet.
    """
    atr = calculate_atr(df, period=config.ATR_PERIOD)
    if atr is None:
        return []

    i = len(df) - 1
    last_close = float(df["close"].iloc[i])
    signals = []
    for hit in detect_patterns(df, atr, i):
        n = PATTERN_SIZES[hit["name"]]
        window = df.iloc[i - n + 1:i + 1]
        signals.append(Signal(
            time=hit["time"] + pd.Timedelta(config.INTERVAL),
            symbol=config.SYMBOL,
            interval=config.INTERVAL,
            source=SOURCE,
            pattern=hit["name"],
            direction=hit["signal"],
            entry=last_close,
            atr=float(atr.iloc[i]),
            tags={
                "required_trend": hit["required_trend"],
                "n_candles": n,
                "pattern_low": float(window["low"].min()),
                "pattern_high": float(window["high"].max()),
            },
        ))
    return signals
