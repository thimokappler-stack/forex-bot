"""
Mustererkennung: Alle 10 Candlestick-Muster.
Rückgabe: (pattern_name, signal_type) oder (None, None)
"""

import logging
from config import (
    LONG_BODY_ATR,
    SMALL_BODY_ATR,
    TWEEZER_TOLERANCE,
    MIN_SHADOW_RATIO,
)


logger = logging.getLogger(__name__)


def get_body_size(candle):
    """Größe des Kerzenkörpers = abs(close - open)"""
    return abs(candle["close"] - candle["open"])


def get_upper_shadow(candle):
    """Oberer Schatten = high - max(open, close)"""
    return candle["high"] - max(candle["open"], candle["close"])


def get_lower_shadow(candle):
    """Unterer Schatten = min(open, close) - low"""
    return min(candle["open"], candle["close"]) - candle["low"]


def is_bullish(candle):
    """True wenn Kerze grün (close > open)"""
    return candle["close"] > candle["open"]


def is_bearish(candle):
    """True wenn Kerze rot (close < open)"""
    return candle["close"] < candle["open"]


def is_long_body(candle, atr):
    """True wenn Körper ≥ LONG_BODY_ATR × ATR"""
    return get_body_size(candle) >= LONG_BODY_ATR * atr


def is_small_body(candle, atr):
    """True wenn Körper ≤ SMALL_BODY_ATR × ATR"""
    return get_body_size(candle) <= SMALL_BODY_ATR * atr


# ============ ZWEI-KERZEN-MUSTER ============

def bullish_engulfing(candles, atrs, idx):
    """
    Bullish Engulfing: K1 rot, K2 grün, Körper K2 umschließt Körper K1.
    idx ist Index von K2 (neuere Kerze).
    """
    if idx < 1:
        return False
    
    k1 = candles.iloc[idx - 1]
    k2 = candles.iloc[idx]
    
    # K1 rot, K2 grün
    if not (is_bearish(k1) and is_bullish(k2)):
        return False
    
    # K2 Körper umschließt K1 Körper komplett
    # K2 open < K1 open/close (niedrigerer Punkt des K1 Körpers)
    # K2 close > K1 open/close (höherer Punkt des K1 Körpers)
    k1_low_body = min(k1["open"], k1["close"])
    k1_high_body = max(k1["open"], k1["close"])
    
    if k2["open"] >= k1_low_body or k2["close"] <= k1_high_body:
        return False
    
    return True


def bearish_engulfing(candles, atrs, idx):
    """
    Bearish Engulfing: K1 grün, K2 rot, Körper K2 umschließt Körper K1.
    """
    if idx < 1:
        return False
    
    k1 = candles.iloc[idx - 1]
    k2 = candles.iloc[idx]
    
    # K1 grün, K2 rot
    if not (is_bullish(k1) and is_bearish(k2)):
        return False
    
    # K2 Körper umschließt K1 Körper komplett
    k1_low_body = min(k1["open"], k1["close"])
    k1_high_body = max(k1["open"], k1["close"])
    
    if k2["open"] <= k1_high_body or k2["close"] >= k1_low_body:
        return False
    
    return True


def tweezer_bottom(candles, atrs, idx):
    """
    Tweezer Bottom: K1 rot, K2 grün, Tiefs gleich (innerhalb Toleranz).
    """
    if idx < 1:
        return False
    
    k1 = candles.iloc[idx - 1]
    k2 = candles.iloc[idx]
    
    # K1 rot, K2 grün
    if not (is_bearish(k1) and is_bullish(k2)):
        return False
    
    # Tiefs gleich innerhalb Toleranz
    if abs(k1["low"] - k2["low"]) > TWEEZER_TOLERANCE:
        return False
    
    return True


def tweezer_top(candles, atrs, idx):
    """
    Tweezer Top: K1 grün, K2 rot, Hochs gleich (innerhalb Toleranz).
    """
    if idx < 1:
        return False
    
    k1 = candles.iloc[idx - 1]
    k2 = candles.iloc[idx]
    
    # K1 grün, K2 rot
    if not (is_bullish(k1) and is_bearish(k2)):
        return False
    
    # Hochs gleich innerhalb Toleranz
    if abs(k1["high"] - k2["high"]) > TWEEZER_TOLERANCE:
        return False
    
    return True


# ============ DREI-KERZEN-MUSTER ============

def morning_star(candles, atrs, idx):
    """
    Morning Star: K1 lange rot, K2 kleiner Körper, K3 lange grün,
    K3 close über Mitte von K1 Körper.
    idx ist Index von K3.
    """
    if idx < 2:
        return False
    
    k1 = candles.iloc[idx - 2]
    k2 = candles.iloc[idx - 1]
    k3 = candles.iloc[idx]
    atr = atrs.iloc[idx]
    
    # K1 lange rote Kerze
    if not (is_bearish(k1) and is_long_body(k1, atr)):
        return False
    
    # K2 kleiner Körper
    if not is_small_body(k2, atr):
        return False
    
    # K3 lange grüne Kerze
    if not (is_bullish(k3) and is_long_body(k3, atr)):
        return False
    
    # K3 close über der Mitte des K1 Körpers
    k1_mid = (k1["open"] + k1["close"]) / 2.0
    if k3["close"] <= k1_mid:
        return False
    
    return True


def evening_star(candles, atrs, idx):
    """
    Evening Star: K1 lange grün, K2 kleiner Körper, K3 lange rot,
    K3 close unter Mitte von K1 Körper.
    """
    if idx < 2:
        return False
    
    k1 = candles.iloc[idx - 2]
    k2 = candles.iloc[idx - 1]
    k3 = candles.iloc[idx]
    atr = atrs.iloc[idx]
    
    # K1 lange grüne Kerze
    if not (is_bullish(k1) and is_long_body(k1, atr)):
        return False
    
    # K2 kleiner Körper
    if not is_small_body(k2, atr):
        return False
    
    # K3 lange rote Kerze
    if not (is_bearish(k3) and is_long_body(k3, atr)):
        return False
    
    # K3 close unter der Mitte des K1 Körpers
    k1_mid = (k1["open"] + k1["close"]) / 2.0
    if k3["close"] >= k1_mid:
        return False
    
    return True


def three_white_soldiers(candles, atrs, idx):
    """
    Drei bullische Soldaten: 3 grüne Kerzen in Folge, jeder close höher,
    jede eröffnung innerhalb des Körpers der vorherigen, kleine obere Schatten.
    idx ist Index von K3.
    """
    if idx < 2:
        return False
    
    k1 = candles.iloc[idx - 2]
    k2 = candles.iloc[idx - 1]
    k3 = candles.iloc[idx]
    
    # Alle grün
    if not (is_bullish(k1) and is_bullish(k2) and is_bullish(k3)):
        return False
    
    # Jeder close höher
    if not (k2["close"] > k1["close"] and k3["close"] > k2["close"]):
        return False
    
    # Jede eröffnung innerhalb des Körpers der vorherigen
    if not (k1["open"] < k2["open"] < k1["close"]):
        return False
    if not (k2["open"] < k3["open"] < k2["close"]):
        return False
    
    # Kleine obere Schatten (≤ 25% der Kerzenspanne)
    span_k1 = k1["high"] - k1["low"]
    span_k2 = k2["high"] - k2["low"]
    span_k3 = k3["high"] - k3["low"]
    
    if get_upper_shadow(k1) > MIN_SHADOW_RATIO * span_k1:
        return False
    if get_upper_shadow(k2) > MIN_SHADOW_RATIO * span_k2:
        return False
    if get_upper_shadow(k3) > MIN_SHADOW_RATIO * span_k3:
        return False
    
    return True


def three_black_crows(candles, atrs, idx):
    """
    Drei bärische Soldaten: 3 rote Kerzen in Folge, jeder close tiefer,
    jede eröffnung innerhalb des Körpers der vorherigen, kleine untere Schatten.
    """
    if idx < 2:
        return False
    
    k1 = candles.iloc[idx - 2]
    k2 = candles.iloc[idx - 1]
    k3 = candles.iloc[idx]
    
    # Alle rot
    if not (is_bearish(k1) and is_bearish(k2) and is_bearish(k3)):
        return False
    
    # Jeder close tiefer
    if not (k2["close"] < k1["close"] and k3["close"] < k2["close"]):
        return False
    
    # Jede eröffnung innerhalb des Körpers der vorherigen
    if not (k1["close"] < k2["open"] < k1["open"]):
        return False
    if not (k2["close"] < k3["open"] < k2["open"]):
        return False
    
    # Kleine untere Schatten (≤ 25% der Kerzenspanne)
    span_k1 = k1["high"] - k1["low"]
    span_k2 = k2["high"] - k2["low"]
    span_k3 = k3["high"] - k3["low"]
    
    if get_lower_shadow(k1) > MIN_SHADOW_RATIO * span_k1:
        return False
    if get_lower_shadow(k2) > MIN_SHADOW_RATIO * span_k2:
        return False
    if get_lower_shadow(k3) > MIN_SHADOW_RATIO * span_k3:
        return False
    
    return True


# ============ FÜNF-KERZEN-MUSTER ============

def rising_three_method(candles, atrs, idx):
    """
    Steigendes Dreier-Pattern: K1 lange grün, K2-K4 kleine Kerzen (überwiegend rot)
    innerhalb der Spanne low..high von K1, K5 lange grün mit close > close von K1.
    idx ist Index von K5.
    """
    if idx < 4:
        return False
    
    k1 = candles.iloc[idx - 4]
    k2 = candles.iloc[idx - 3]
    k3 = candles.iloc[idx - 2]
    k4 = candles.iloc[idx - 1]
    k5 = candles.iloc[idx]
    atr = atrs.iloc[idx]
    
    # K1 lange grüne Kerze
    if not (is_bullish(k1) and is_long_body(k1, atr)):
        return False
    
    # K2-K4 kleine Kerzen
    for k in [k2, k3, k4]:
        if not is_small_body(k, atr):
            return False
    
    # K2-K4 innerhalb der Spanne von K1
    for k in [k2, k3, k4]:
        if k["high"] > k1["high"] or k["low"] < k1["low"]:
            return False
    
    # K2-K4 überwiegend rot (mindestens 2 rot)
    bearish_count = sum(1 for k in [k2, k3, k4] if is_bearish(k))
    if bearish_count < 2:
        return False
    
    # K5 lange grüne Kerze
    if not (is_bullish(k5) and is_long_body(k5, atr)):
        return False
    
    # K5 close > close von K1
    if k5["close"] <= k1["close"]:
        return False
    
    return True


def falling_three_method(candles, atrs, idx):
    """
    Fallendes Dreier-Pattern: K1 lange rot, K2-K4 kleine Kerzen (überwiegend grün)
    innerhalb der Spanne von K1, K5 lange rot mit close < close von K1.
    """
    if idx < 4:
        return False
    
    k1 = candles.iloc[idx - 4]
    k2 = candles.iloc[idx - 3]
    k3 = candles.iloc[idx - 2]
    k4 = candles.iloc[idx - 1]
    k5 = candles.iloc[idx]
    atr = atrs.iloc[idx]
    
    # K1 lange rote Kerze
    if not (is_bearish(k1) and is_long_body(k1, atr)):
        return False
    
    # K2-K4 kleine Kerzen
    for k in [k2, k3, k4]:
        if not is_small_body(k, atr):
            return False
    
    # K2-K4 innerhalb der Spanne von K1
    for k in [k2, k3, k4]:
        if k["high"] > k1["high"] or k["low"] < k1["low"]:
            return False
    
    # K2-K4 überwiegend grün (mindestens 2 grün)
    bullish_count = sum(1 for k in [k2, k3, k4] if is_bullish(k))
    if bullish_count < 2:
        return False
    
    # K5 lange rote Kerze
    if not (is_bearish(k5) and is_long_body(k5, atr)):
        return False
    
    # K5 close < close von K1
    if k5["close"] >= k1["close"]:
        return False
    
    return True


# ============ HAUPT-MUSTERERKENNUNG ============

PATTERNS = {
    "Bullish Engulfing": (bullish_engulfing, "BUY", 2),
    "Bearish Engulfing": (bearish_engulfing, "SELL", 2),
    "Tweezer Bottom": (tweezer_bottom, "BUY", 2),
    "Tweezer Top": (tweezer_top, "SELL", 2),
    "Morning Star": (morning_star, "BUY", 3),
    "Evening Star": (evening_star, "SELL", 3),
    "Three White Soldiers": (three_white_soldiers, "BUY", 3),
    "Three Black Crows": (three_black_crows, "SELL", 3),
    "Rising Three Method": (rising_three_method, "BUY", 5),
    "Falling Three Method": (falling_three_method, "SELL", 5),
}


def detect_patterns(candles, atrs):
    """
    Prüft alle Muster auf den letzten Kerzen.
    
    Args:
        candles: DataFrame mit open, high, low, close (Index: timestamp)
        atrs: Series mit ATR-Werten
    
    Returns:
        List von Dicts: [{"pattern": name, "signal": "BUY"|"SELL", "idx": index}, ...]
    """
    signals = []
    
    for pattern_name, (func, signal_type, min_bars) in PATTERNS.items():
        # Prüfe nur die letzte Kerze (und deren vorherigen für das Muster erforderlich)
        idx = len(candles) - 1
        
        if idx >= min_bars - 1:
            if func(candles, atrs, idx):
                signals.append({
                    "pattern": pattern_name,
                    "signal": signal_type,
                    "idx": idx,
                })
    
    return signals
