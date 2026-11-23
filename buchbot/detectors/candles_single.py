"""
Einzelkerzen-Muster (Hintergrund-Analyse, Detektor "candles_single").

Nur die letzte Kerze wird geprüft. Die Muster laufen mit Betriebsart "log_only"
standardmäßig nur ins Log und in signals_log.csv, nicht in die E-Mail.
Doji und Spinning Top sind NEUTRAL: sie zählen, werden aber nicht bewertet.
"""

import math
from collections import namedtuple

import pandas as pd

import buchbot.config as cfg
from buchbot.data import calculate_atr
from buchbot.detectors.candles_main import (
    Candle,
    body,
    candle_range,
    is_doji,
    is_green,
    is_long,
    is_red,
    is_small,
    lower_wick,
    upper_wick,
)
from buchbot.models import Signal


SingleCandlePattern = namedtuple("SingleCandlePattern", ["name", "signal", "required_trend", "check"])

NEUTRAL = "NEUTRAL"


def _hammer_shape(c, atr):
    # Körper > 0: ein Doji ist kein Hammer
    return (
        candle_range(c) > 0
        and body(c) > 0
        and is_small(c, atr)
        and not is_doji(c)
        and lower_wick(c) >= cfg.WICK_LONG_RATIO * body(c)
        and upper_wick(c) <= cfg.WICK_SMALL_RATIO * candle_range(c)
    )


def _inverted_hammer_shape(c, atr):
    return (
        candle_range(c) > 0
        and body(c) > 0
        and is_small(c, atr)
        and not is_doji(c)
        and upper_wick(c) >= cfg.WICK_LONG_RATIO * body(c)
        and lower_wick(c) <= cfg.WICK_SMALL_RATIO * candle_range(c)
    )


def hammer(c, atr):
    return is_green(c) and _hammer_shape(c, atr)


def inverted_hammer(c, atr):
    return is_green(c) and _inverted_hammer_shape(c, atr)


def hanging_man(c, atr):
    return is_red(c) and _hammer_shape(c, atr)


def shooting_star(c, atr):
    return is_red(c) and _inverted_hammer_shape(c, atr)


def _marubozu(c, atr):
    return (
        candle_range(c) > 0
        and is_long(c, atr)
        and upper_wick(c) <= cfg.WICK_SMALL_RATIO * candle_range(c)
        and lower_wick(c) <= cfg.WICK_SMALL_RATIO * candle_range(c)
    )


def marubozu_green(c, atr):
    return is_green(c) and _marubozu(c, atr)


def marubozu_red(c, atr):
    return is_red(c) and _marubozu(c, atr)


def doji(c, atr):
    return candle_range(c) > 0 and is_doji(c)


def spinning_top(c, atr):
    return (
        candle_range(c) > 0
        and body(c) > 0
        and is_small(c, atr)
        and not is_doji(c)
        and upper_wick(c) > body(c)
        and lower_wick(c) > body(c)
    )


PATTERNS = (
    SingleCandlePattern("Hammer", "BUY", "down", hammer),
    SingleCandlePattern("Umgekehrter Hammer", "BUY", "down", inverted_hammer),
    SingleCandlePattern("Hanging Man", "SELL", "up", hanging_man),
    SingleCandlePattern("Shooting Star", "SELL", "up", shooting_star),
    SingleCandlePattern("Marubozu grün", "BUY", "up", marubozu_green),
    SingleCandlePattern("Marubozu rot", "SELL", "down", marubozu_red),
    SingleCandlePattern("Doji", NEUTRAL, None, doji),
    SingleCandlePattern("Spinning Top", NEUTRAL, None, spinning_top),
)

PATTERN_NAMES = [p.name for p in PATTERNS]
SOURCE = "candles_single"


def detect(df, config):
    """
    Detektor-Einstieg: liefert Signal-Objekte für die letzte Kerze.

    SL/TP und Trendfilter werden hier nicht berechnet.
    """
    atr = calculate_atr(df, period=config.ATR_PERIOD)
    if atr is None:
        return []

    i = len(df) - 1
    atr_value = float(atr.iloc[i])
    if math.isnan(atr_value):
        return []

    c = Candle(*map(float, df.iloc[i][["open", "high", "low", "close"]]))
    signals = []
    for p in PATTERNS:
        if not p.check(c, atr_value):
            continue
        signals.append(Signal(
            time=df.index[i] + pd.Timedelta(config.INTERVAL),
            symbol=config.SYMBOL,
            market=getattr(config, "MARKET", None),
            interval=config.INTERVAL,
            source=SOURCE,
            pattern=p.name,
            direction=p.signal,
            entry=c.close,
            atr=atr_value,
            tags={
                "required_trend": p.required_trend,
                "n_candles": 1,
                "pattern_low": c.low,
                "pattern_high": c.high,
            },
        ))
    return signals
