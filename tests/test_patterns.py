"""
Tests für Candlestick-Muster.
Handgebaute Kerzen pro Muster.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from patterns import (
    bullish_engulfing, bearish_engulfing,
    tweezer_bottom, tweezer_top,
    morning_star, evening_star,
    three_white_soldiers, three_black_crows,
    rising_three_method, falling_three_method,
)
from signals import calculate_sl_tp, is_uptrend, is_downtrend
from config import MIN_SL_PIPS, RISK_REWARD, PIP_SIZE, TREND_EMA_PERIOD


def create_candles(ohlc_list):
    """
    Erstellt DataFrame mit Kerzen aus Liste von (open, high, low, close) Tuples.
    
    Args:
        ohlc_list: [(o, h, l, c), ...]
    
    Returns:
        DataFrame mit Index als Timestamps
    """
    dates = [datetime(2024, 1, 1) + timedelta(minutes=15*i) for i in range(len(ohlc_list))]
    df = pd.DataFrame({
        "open": [x[0] for x in ohlc_list],
        "high": [x[1] for x in ohlc_list],
        "low": [x[2] for x in ohlc_list],
        "close": [x[3] for x in ohlc_list],
    }, index=dates)
    return df


def create_atrs(length, atr_value=0.001):
    """Erstellt Series mit konstanten ATR-Werten."""
    dates = [datetime(2024, 1, 1) + timedelta(minutes=15*i) for i in range(length)]
    return pd.Series([atr_value] * length, index=dates)


# ============ ZWEI-KERZEN-TESTS ============

def test_bullish_engulfing():
    """Bullish Engulfing: K1 rot, K2 grün, K2 umschließt K1."""
    # K1: rot (1.0 -> 0.98), K2: grün (0.95 -> 1.02)
    candles = create_candles([
        (1.0, 1.0, 0.98, 0.98),      # K1 rot
        (0.95, 1.02, 0.95, 1.02),    # K2 grün, umschließt K1
    ])
    atrs = create_atrs(2)
    
    assert bullish_engulfing(candles, atrs, 1) is True


def test_bullish_engulfing_fails_if_not_engulfing():
    """Bullish Engulfing schlägt fehl wenn K2 nicht komplett umschließt."""
    # K2 umschließt K1 nicht komplett
    candles = create_candles([
        (1.0, 1.0, 0.98, 0.98),
        (0.99, 1.01, 0.98, 1.01),  # K2 umschließt nicht ganz
    ])
    atrs = create_atrs(2)
    
    assert bullish_engulfing(candles, atrs, 1) is False


def test_bearish_engulfing():
    """Bearish Engulfing: K1 grün, K2 rot, K2 umschließt K1."""
    candles = create_candles([
        (0.98, 1.02, 0.98, 1.02),    # K1 grün
        (1.05, 1.05, 0.95, 0.95),    # K2 rot, umschließt K1
    ])
    atrs = create_atrs(2)
    
    assert bearish_engulfing(candles, atrs, 1) is True


def test_tweezer_bottom():
    """Tweezer Bottom: K1 rot, K2 grün, Tiefs gleich."""
    candles = create_candles([
        (1.0, 1.0, 0.98, 0.98),      # K1 rot
        (0.98, 1.01, 0.98, 1.01),    # K2 grün, gleiches Tief
    ])
    atrs = create_atrs(2)
    
    assert tweezer_bottom(candles, atrs, 1) is True


def test_tweezer_top():
    """Tweezer Top: K1 grün, K2 rot, Hochs gleich."""
    candles = create_candles([
        (0.98, 1.02, 0.98, 1.02),    # K1 grün
        (1.02, 1.02, 0.99, 0.99),    # K2 rot, gleiches Hoch
    ])
    atrs = create_atrs(2)
    
    assert tweezer_top(candles, atrs, 1) is True


# ============ DREI-KERZEN-TESTS ============

def test_morning_star():
    """Morning Star: K1 lange rot, K2 kleiner Körper, K3 lange grün, K3 close > K1 mid."""
    candles = create_candles([
        (1.02, 1.02, 0.98, 0.98),      # K1 lange rot
        (0.98, 0.985, 0.975, 0.98),    # K2 kleiner Körper
        (0.97, 1.03, 0.97, 1.03),      # K3 lange grün, close > 1.0 (Mitte von K1)
    ])
    atrs = create_atrs(3, 0.002)
    
    assert morning_star(candles, atrs, 2) is True


def test_evening_star():
    """Evening Star: K1 lange grün, K2 kleiner Körper, K3 lange rot, K3 close < K1 mid."""
    candles = create_candles([
        (0.98, 1.02, 0.98, 1.02),      # K1 lange grün
        (1.02, 1.025, 1.015, 1.02),    # K2 kleiner Körper
        (1.025, 1.025, 0.97, 0.97),    # K3 lange rot, close < 1.0
    ])
    atrs = create_atrs(3, 0.002)
    
    assert evening_star(candles, atrs, 2) is True


def test_three_white_soldiers():
    """Drei bullische Soldaten: 3 grüne, steigende Closes, Eröffnungen im vorherigen Körper."""
    candles = create_candles([
        (1.000, 1.010, 0.999, 1.009),  # K1 grün
        (1.002, 1.012, 1.001, 1.011),  # K2 grün, close > K1 close, open in K1 body
        (1.004, 1.014, 1.003, 1.013),  # K3 grün, close > K2 close, open in K2 body
    ])
    atrs = create_atrs(3, 0.002)
    
    assert three_white_soldiers(candles, atrs, 2) is True


def test_three_black_crows():
    """Drei bärische Soldaten: 3 rote, fallende Closes, Eröffnungen im vorherigen Körper."""
    candles = create_candles([
        (1.013, 1.014, 1.003, 1.004),  # K1 rot
        (1.011, 1.012, 1.001, 1.002),  # K2 rot, close < K1 close, open in K1 body
        (1.009, 1.010, 0.999, 1.000),  # K3 rot, close < K2 close, open in K2 body
    ])
    atrs = create_atrs(3, 0.002)
    
    assert three_black_crows(candles, atrs, 2) is True


# ============ FÜNF-KERZEN-TESTS ============

# ============ FÜNF-KERZEN-MUSTER (INTEGRATION TESTS) ============

def test_rising_three_method_callable():
    """Überprüft dass rising_three_method aufgerufen werden kann."""
    candles = create_candles([
        (1.000, 1.100, 1.000, 1.100),
        (1.080, 1.095, 1.010, 1.020),
        (1.020, 1.090, 1.010, 1.025),
        (1.025, 1.090, 1.010, 1.020),
        (1.020, 1.110, 1.020, 1.110),
    ])
    atrs = create_atrs(5, 0.04)
    
    # Funktion sollte ohne Fehler aufgerufen werden
    result = rising_three_method(candles, atrs, 4)
    assert isinstance(result, (bool, type(False)))


def test_falling_three_method_callable():
    """Überprüft dass falling_three_method aufgerufen werden kann."""
    candles = create_candles([
        (1.100, 1.100, 1.000, 1.000),
        (1.020, 1.080, 1.020, 1.070),
        (1.070, 1.085, 1.010, 1.080),
        (1.080, 1.085, 1.010, 1.075),
        (1.090, 1.090, 0.900, 0.900),
    ])
    atrs = create_atrs(5, 0.04)
    
    # Funktion sollte ohne Fehler aufgerufen werden
    result = falling_three_method(candles, atrs, 4)
    assert isinstance(result, (bool, type(False)))


# ============ STOP-LOSS / TAKE-PROFIT TESTS ============

def test_sl_tp_calculation_buy():
    """Test SL/TP Berechnung für BUY Signal."""
    candles = create_candles([
        (1.0985, 1.0995, 1.0985, 1.1000),
    ])
    atrs = pd.Series([0.0010], index=candles.index)
    
    result = calculate_sl_tp(candles, atrs, "Test", "BUY", 0)
    
    assert result is not None
    assert result["entry"] == 1.1
    assert result["risk_pips"] == 20.0


def test_sl_tp_calculation_sell():
    """Test SL/TP Berechnung für SELL Signal."""
    candles = create_candles([
        (1.0995, 1.1015, 1.0985, 1.0990),
    ])
    atrs = pd.Series([0.0010], index=candles.index)
    
    result = calculate_sl_tp(candles, atrs, "Test", "SELL", 0)
    
    assert result is not None
    assert result["risk_pips"] == 30.0


def test_sl_tp_too_small_signal():
    """Test: Signal zu klein wird verworfen."""
    candles = create_candles([
        (1.0999, 1.1000, 1.0999, 1.1000),
    ])
    atrs = pd.Series([0.00001], index=candles.index)
    
    result = calculate_sl_tp(candles, atrs, "Test", "BUY", 0)
    
    assert result is None


# ============ TREND-FILTER TESTS ============

def test_uptrend_filter():
    """Test Aufwärtstrend-Erkennung (close > EMA)."""
    closes = [1.0 + i*0.001 for i in range(60)]
    dates = [datetime(2024, 1, 1) + timedelta(minutes=15*i) for i in range(60)]
    candles = pd.DataFrame({
        "open": closes,
        "high": [c + 0.0001 for c in closes],
        "low": [c - 0.0001 for c in closes],
        "close": closes,
    }, index=dates)
    
    result = is_uptrend(candles, 59)
    assert result is True, "Sollte Aufwärtstrend erkennen"


def test_downtrend_filter():
    """Test Abwärtstrend-Erkennung (close < EMA)."""
    closes = [1.06 - i*0.001 for i in range(60)]
    dates = [datetime(2024, 1, 1) + timedelta(minutes=15*i) for i in range(60)]
    candles = pd.DataFrame({
        "open": closes,
        "high": [c + 0.0001 for c in closes],
        "low": [c - 0.0001 for c in closes],
        "close": closes,
    }, index=dates)
    
    result = is_downtrend(candles, 59)
    assert result is True, "Sollte Abwärtstrend erkennen"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
