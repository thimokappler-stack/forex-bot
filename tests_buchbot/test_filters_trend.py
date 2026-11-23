"""
Tests für buchbot/filters/trend.py: Trendfilter auf Basis von Detektor-Signalen.

Der Trend wird auf der Kerze VOR der ersten Musterkerze geprüft.
"""

import logging

import pandas as pd

import buchbot.config as cfg
from buchbot.detectors import candles_main
from buchbot.detectors.candles_main import Candle
from buchbot.filters import trend


FLAT = Candle(1.1000, 1.1005, 1.0995, 1.1000)
ENG_POS = [Candle(1.1010, 1.1015, 1.0990, 1.0995), Candle(1.0990, 1.1030, 1.0985, 1.1025)]
BEAR_ENG = [Candle(1.0990, 1.0995, 1.0988, 1.0995), Candle(1.0998, 1.1000, 1.0983, 1.0985)]
SOLDIERS_POS = [
    Candle(1.1000, 1.1003, 1.0999, 1.1002),
    Candle(1.1001, 1.1007, 1.1000, 1.1007),
    Candle(1.1005, 1.1016, 1.1004, 1.1016),
]


def make_df(candles, start="2026-01-01 00:00"):
    index = pd.date_range(start, periods=len(candles), freq="15min", tz="UTC")
    return pd.DataFrame([c._asdict() for c in candles], index=index)


def ramp(start, step, n=60):
    """Gleichmäßiger Verlauf: Schluss steigt (step > 0) oder fällt (step < 0)."""
    candles = []
    for k in range(n):
        c = round(start + k * step, 5)
        candles.append(Candle(c - 0.0003, c + 0.0005, c - 0.0006, c))
    return candles


UPTREND = ramp(1.0800, 0.0005)
DOWNTREND = ramp(1.1200, -0.0005)
FLAT_PREFIX = [FLAT] * 60


def detect_and_filter(prefix, pattern_candles, pattern_name):
    df = make_df(prefix + pattern_candles)
    signals = [s for s in candles_main.detect(df, cfg) if s.pattern == pattern_name]
    assert len(signals) == 1, f"{pattern_name} muss genau einmal erkannt werden"
    return trend.apply(signals, df, cfg)


class TestTrendFilter:
    def test_bullish_soldiers_after_uptrend_are_discarded(self):
        assert detect_and_filter(UPTREND, SOLDIERS_POS, "Drei bullische Soldaten") == []

    def test_bullish_soldiers_after_downtrend_are_kept(self):
        kept = detect_and_filter(DOWNTREND, SOLDIERS_POS, "Drei bullische Soldaten")
        assert len(kept) == 1

    def test_bearish_engulfing_after_downtrend_is_discarded(self):
        assert detect_and_filter(DOWNTREND, BEAR_ENG, "Bearish Engulfing") == []

    def test_bearish_engulfing_after_uptrend_is_kept(self):
        kept = detect_and_filter(UPTREND, BEAR_ENG, "Bearish Engulfing")
        assert len(kept) == 1

    def test_trend_is_checked_on_candle_before_pattern_not_last_pattern_candle(self):
        # Kerze vor dem Muster liegt knapp unter der EMA (Trend "down"),
        # die letzte Musterkerze (Schluss 1.1025) liegt darüber (Trend "up").
        trend_candle = Candle(1.1000, 1.1002, 1.0988, 1.0990)
        prefix = [FLAT] * 58 + [trend_candle]

        kept = detect_and_filter(prefix, ENG_POS, "Bullish Engulfing")

        assert len(kept) == 1

    def test_no_trend_when_close_equals_ema_discards_reversal_signal(self):
        assert detect_and_filter(FLAT_PREFIX, ENG_POS, "Bullish Engulfing") == []

    def test_no_trend_when_ema_not_computable_discards_reversal_signal(self):
        # 19 Füllkerzen + 2 Musterkerzen: genug für ATR, aber zu wenig für EMA(50)
        prefix = [FLAT] * 19
        assert detect_and_filter(prefix, ENG_POS, "Bullish Engulfing") == []

    def test_discarded_signal_is_logged_with_reason(self, caplog):
        with caplog.at_level(logging.INFO):
            detect_and_filter(UPTREND, SOLDIERS_POS, "Drei bullische Soldaten")

        assert "verworfen" in caplog.text
        assert "Drei bullische Soldaten" in caplog.text

    def test_signal_without_required_trend_is_untouched(self):
        df = make_df(FLAT_PREFIX + ENG_POS)
        signals = candles_main.detect(df, cfg)
        for s in signals:
            s.tags.pop("required_trend")

        assert trend.apply(signals, df, cfg) == signals


# Fünf-Kerzen-Muster: Trendkerze direkt vor K1, Kerzen K2-K4 liegen innerhalb
# des Musters und haben den Trend in die Gegenrichtung (Gegentest).
RISE_FIVE = [
    Candle(1.0990, 1.1025, 1.0988, 1.1020),  # K1 lang grün
    Candle(1.0998, 1.1000, 1.0994, 1.0997),  # K2 klein rot
    Candle(1.0997, 1.0999, 1.0993, 1.0996),  # K3 klein rot
    Candle(1.0996, 1.0998, 1.0992, 1.0995),  # K4 klein rot
    Candle(1.0996, 1.1030, 1.0994, 1.1025),  # K5 lang grün, Schluss über K1
]
RISE_TREND_CANDLE = Candle(1.1005, 1.1012, 1.1002, 1.1010)  # Schluss über EMA = up

FALL_FIVE = [
    Candle(1.1020, 1.1025, 1.0988, 1.0990),  # K1 lang rot
    Candle(1.1002, 1.1004, 1.1001, 1.1003),  # K2 klein grün
    Candle(1.1003, 1.1005, 1.1002, 1.1004),  # K3 klein grün
    Candle(1.1004, 1.1006, 1.1003, 1.1005),  # K4 klein grün
    Candle(1.1004, 1.1006, 1.0970, 1.0975),  # K5 lang rot, Schluss unter K1
]
FALL_TREND_CANDLE = Candle(1.0995, 1.0998, 1.0990, 1.0990)  # Schluss unter EMA = down


class TestFiveCandlePatterns:
    def test_rising_three_methods_after_uptrend_is_kept(self):
        prefix = [FLAT] * 58 + [RISE_TREND_CANDLE]
        kept = detect_and_filter(prefix, RISE_FIVE, "Steigendes Dreier-Pattern")
        assert len(kept) == 1
        assert kept[0].tags["n_candles"] == 5

    def test_rising_three_methods_trend_is_checked_before_k1_not_inside_pattern(self):
        prefix = [FLAT] * 58 + [RISE_TREND_CANDLE]
        df = make_df(prefix + RISE_FIVE)
        k2_pos = len(prefix) + 1
        # Innerhalb des Musters wäre der Trend "down" und würde das Signal verwerfen
        assert trend.trend_at(df, k2_pos, cfg) == "down"
        assert trend.trend_at(df, len(prefix) - 1, cfg) == "up"
        kept = detect_and_filter(prefix, RISE_FIVE, "Steigendes Dreier-Pattern")
        assert len(kept) == 1

    def test_rising_three_methods_after_downtrend_is_discarded(self):
        prefix = [FLAT] * 58 + [FALL_TREND_CANDLE]
        assert detect_and_filter(prefix, RISE_FIVE, "Steigendes Dreier-Pattern") == []

    def test_falling_three_methods_after_downtrend_is_kept(self):
        prefix = [FLAT] * 58 + [FALL_TREND_CANDLE]
        kept = detect_and_filter(prefix, FALL_FIVE, "Fallendes Dreier-Pattern")
        assert len(kept) == 1
        assert kept[0].tags["n_candles"] == 5

    def test_falling_three_methods_trend_is_checked_before_k1_not_inside_pattern(self):
        prefix = [FLAT] * 58 + [FALL_TREND_CANDLE]
        df = make_df(prefix + FALL_FIVE)
        k2_pos = len(prefix) + 1
        # Innerhalb des Musters wäre der Trend "up" und würde das Signal verwerfen
        assert trend.trend_at(df, k2_pos, cfg) == "up"
        assert trend.trend_at(df, len(prefix) - 1, cfg) == "down"
        kept = detect_and_filter(prefix, FALL_FIVE, "Fallendes Dreier-Pattern")
        assert len(kept) == 1

    def test_falling_three_methods_after_uptrend_is_discarded(self):
        prefix = [FLAT] * 58 + [RISE_TREND_CANDLE]
        assert detect_and_filter(prefix, FALL_FIVE, "Fallendes Dreier-Pattern") == []
