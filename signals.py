"""
Signalberechnung: Muster + Trendfilter → BUY/SELL Signal.
Berechnung von Stop-Loss, Take-Profit, Risiko.
"""

import logging
from config import (
    SL_BUFFER_ATR,
    MIN_SL_PIPS,
    RISK_REWARD,
    PIP_SIZE,
    TREND_EMA_PERIOD,
)
from data import calculate_ema


logger = logging.getLogger(__name__)


def is_uptrend(candles, idx):
    """
    Prüft Aufwärtstrend: Schlusskurs über EMA(50).
    idx ist die Kerze, auf der wir den Trend prüfen.
    """
    if idx < TREND_EMA_PERIOD:
        logger.debug(f"Zu wenige Kerzen für EMA-Berechnung (idx={idx})")
        return False
    
    close = candles["close"].iloc[:idx + 1]
    ema = calculate_ema(close, TREND_EMA_PERIOD)
    
    return bool(candles["close"].iloc[idx] > ema.iloc[idx])


def is_downtrend(candles, idx):
    """
    Prüft Abwärtstrend: Schlusskurs unter EMA(50).
    """
    if idx < TREND_EMA_PERIOD:
        logger.debug(f"Zu wenige Kerzen für EMA-Berechnung (idx={idx})")
        return False
    
    close = candles["close"].iloc[:idx + 1]
    ema = calculate_ema(close, TREND_EMA_PERIOD)
    
    return bool(candles["close"].iloc[idx] < ema.iloc[idx])


def get_pattern_extremes(candles, pattern_name, idx):
    """
    Gibt (min_low, max_high) aller Kerzen des Musters zurück.
    
    Args:
        candles: DataFrame mit high, low
        pattern_name: Name des Musters
        idx: Index der letzten Musterkerze
    
    Returns:
        (min_low, max_high)
    """
    # Bestimme wie viele Kerzen das Muster umfasst
    pattern_bars = {
        "Bullish Engulfing": 2, "Bearish Engulfing": 2,
        "Tweezer Bottom": 2, "Tweezer Top": 2,
        "Morning Star": 3, "Evening Star": 3,
        "Three White Soldiers": 3, "Three Black Crows": 3,
        "Rising Three Method": 5, "Falling Three Method": 5,
    }.get(pattern_name, 1)
    
    start_idx = max(0, idx - pattern_bars + 1)
    pattern_candles = candles.iloc[start_idx:idx + 1]
    
    return pattern_candles["low"].min(), pattern_candles["high"].max()


def calculate_sl_tp(candles, atrs, pattern_name, signal_type, idx):
    """
    Berechnet Stop-Loss und Take-Profit für ein Signal.
    
    Args:
        candles: DataFrame mit open, high, low, close
        atrs: Series mit ATR
        pattern_name: Name des Musters
        signal_type: "BUY" oder "SELL"
        idx: Index der letzten Musterkerze
    
    Returns:
        Dict mit "entry", "sl", "tp", "risk_pips", "crv" oder None wenn zu kleines Signal
    """
    entry = candles["close"].iloc[idx]
    atr = atrs.iloc[idx]
    min_low, max_high = get_pattern_extremes(candles, pattern_name, idx)
    
    if signal_type == "BUY":
        # SL unter dem Tief des Musters
        sl = min_low - SL_BUFFER_ATR * atr
        risk = entry - sl
    else:  # SELL
        # SL über dem Hoch des Musters
        sl = max_high + SL_BUFFER_ATR * atr
        risk = sl - entry
    
    # Risiko in Pips
    risk_pips = risk / PIP_SIZE
    
    # Zu kleines Signal?
    if risk_pips < MIN_SL_PIPS:
        logger.warning(
            f"Signal zu klein: {pattern_name} {signal_type} "
            f"risk={risk_pips:.2f} Pips < MIN_SL_PIPS={MIN_SL_PIPS}"
        )
        return None
    
    # Take-Profit
    if signal_type == "BUY":
        tp = entry + RISK_REWARD * risk
    else:  # SELL
        tp = entry - RISK_REWARD * risk
    
    # Auf 5 Dezimalstellen runden
    entry = round(entry, 5)
    sl = round(sl, 5)
    tp = round(tp, 5)
    
    return {
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "risk_pips": round(risk_pips, 2),
        "crv": round(RISK_REWARD, 1),
    }


def evaluate_pattern(candles, atrs, pattern_name, signal_type, idx):
    """
    Bewertet ein Muster: Trend-Filter + SL/TP-Berechnung.
    
    Returns:
        Dict mit Pattern-Info oder None wenn gefiltert
    """
    # Trend-Filter: auf Kerze VOR dem Muster (idx - 1)
    trend_idx = max(0, idx - 1)
    
    if signal_type == "BUY" and not is_downtrend(candles, trend_idx):
        logger.debug(f"BUY-Signal gefiltert: kein Abwärtstrend bei idx={trend_idx}")
        return None
    
    if signal_type == "SELL" and not is_uptrend(candles, trend_idx):
        logger.debug(f"SELL-Signal gefiltert: kein Aufwärtstrend bei idx={trend_idx}")
        return None
    
    # SL/TP berechnen
    sl_tp = calculate_sl_tp(candles, atrs, pattern_name, signal_type, idx)
    if sl_tp is None:
        return None
    
    return {
        "pattern": pattern_name,
        "signal": signal_type,
        "timestamp": candles.index[idx],
        "candle_idx": idx,
        **sl_tp,
    }
