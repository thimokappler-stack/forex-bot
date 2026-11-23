"""
Trendfilter: Reversal-Signale nur zulassen, wenn der Trend passt.

Der Trend wird auf der Kerze VOR der ersten Musterkerze bestimmt:
Schlusskurs über EMA = "up", darunter = "down". Gleich oder EMA nicht
berechenbar = kein Trend.
"""

import logging

import pandas as pd

from buchbot.data import calculate_ema


logger = logging.getLogger(__name__)


def trend_at(df, pos, config):
    """Trend auf der Kerze an Position `pos`: "up", "down" oder None."""
    if pos < 0:
        return None
    ema = calculate_ema(df["close"], period=config.TREND_EMA_PERIOD)
    if ema is None:
        return None
    close = df["close"].iloc[pos]
    ema_value = ema.iloc[pos]
    if pd.isna(close) or pd.isna(ema_value):
        return None
    # Auf 10 Nachkommastellen runden, damit "gleich" nicht an Float-Rauschen scheitert
    close = round(float(close), 10)
    ema_value = round(float(ema_value), 10)
    if close == ema_value:
        return None
    return "up" if close > ema_value else "down"


def apply(signals, df, config):
    """Gibt nur Signale zurück, deren required_trend zum Trend passt."""
    kept = []
    for signal in signals:
        required = signal.tags.get("required_trend")
        if required is None:
            kept.append(signal)
            continue

        last_pattern_pos = df.index.get_loc(signal.time - pd.Timedelta(config.INTERVAL))
        trend_pos = last_pattern_pos - signal.tags["n_candles"]
        trend = trend_at(df, trend_pos, config)

        if trend == required:
            kept.append(signal)
        else:
            logger.info(
                "Signal verworfen: %s (%s), benötigter Trend %s, Trend %s",
                signal.pattern, signal.time, required, trend or "kein Trend",
            )
    return kept
