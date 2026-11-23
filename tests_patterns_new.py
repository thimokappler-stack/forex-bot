"""
Tests für patterns_new.py (zehn Haupt-Muster).

Jedes Muster hat einen positiven Fall und negative Fälle.
Bärische Muster werden über Spiegelung (mirror) der bullischen Fälle geprüft:
Preise werden an 2 gespiegelt, Farben und Hoch/Tief tauschen dabei.
"""

import pandas as pd
import pytest

import patterns_new as pn
from patterns_new import Candle

ATR = 0.0010


def C(o, h, l, c):
    return Candle(o, h, l, c)


def mirror(candles):
    return [Candle(2 - c.open, 2 - c.low, 2 - c.high, 2 - c.close) for c in candles]


# --- Bullish Engulfing / Bearish Engulfing ---
ENG_POS = [C(1.1010, 1.1015, 1.0990, 1.0995), C(1.0990, 1.1030, 1.0985, 1.1025)]
ENG_NEG_SMALLER_BODY = [C(1.1010, 1.1015, 1.0990, 1.0995), C(1.0996, 1.1012, 1.0994, 1.1008)]
ENG_NEG_NOT_ENCLOSING = [C(1.1010, 1.1015, 1.0990, 1.0995), C(1.0998, 1.1025, 1.0995, 1.1020)]
ENG_NEG_WRONG_COLOR = [C(1.0995, 1.1010, 1.0990, 1.1010), C(1.0990, 1.1030, 1.0985, 1.1025)]

# --- Tweezer Bottom / Tweezer Top ---
TWEEZER_POS = [C(1.1000, 1.1002, 1.0995, 1.0998), C(1.0998, 1.1003, 1.0995, 1.1000)]
TWEEZER_NEG_LOWS_DIFFER = [C(1.1000, 1.1002, 1.0995, 1.0998), C(1.0998, 1.1003, 1.0985, 1.1000)]
TWEEZER_NEG_BODY_DISSIMILAR = [C(1.1000, 1.1002, 1.0995, 1.0998), C(1.0999, 1.1002, 1.0995, 1.1000)]
TWEEZER_NEG_SAME_COLOR = [C(1.1000, 1.1002, 1.0995, 1.0998), C(1.1000, 1.1003, 1.0995, 1.0998)]

# --- Morning Star / Evening Star ---
STAR_POS = [
    C(1.1020, 1.1025, 1.0995, 1.1000),
    C(1.0995, 1.0996, 1.0990, 1.0993),
    C(1.0996, 1.1020, 1.0994, 1.1015),
]
STAR_NEG_MIDDLE_OTHER_COLOR = [
    C(1.1020, 1.1025, 1.0995, 1.1000),
    C(1.0993, 1.0996, 1.0990, 1.0995),
    C(1.0996, 1.1020, 1.0994, 1.1015),
]
STAR_NEG_MIDDLE_TOO_BIG = [
    C(1.1020, 1.1025, 1.0995, 1.1000),
    C(1.1000, 1.1005, 1.0970, 1.0980),
    C(1.0996, 1.1020, 1.0994, 1.1015),
]
STAR_NEG_FIRST_NOT_LONG = [
    C(1.1000, 1.1003, 1.0995, 1.0995),
    C(1.0995, 1.0996, 1.0990, 1.0993),
    C(1.0996, 1.1020, 1.0994, 1.1015),
]
STAR_NEG_FIRST_DOJI = [
    C(1.1010, 1.1110, 1.1000, 1.1000),
    C(1.0998, 1.0999, 1.0996, 1.0997),
    C(1.0997, 1.1010, 1.0995, 1.1008),
]
STAR_NEG_LAST_NOT_LONG = [
    C(1.1020, 1.1025, 1.0995, 1.1000),
    C(1.0995, 1.0996, 1.0990, 1.0993),
    C(1.0996, 1.1005, 1.0994, 1.1003),
]

# --- Drei bullische / bärische Soldaten ---
SOLDIERS_POS = [
    C(1.1000, 1.1003, 1.0999, 1.1002),
    C(1.1001, 1.1007, 1.1000, 1.1007),
    C(1.1005, 1.1016, 1.1004, 1.1016),
]
SOLDIERS_NEG_BODY_NOT_GROWING = [
    C(1.1000, 1.1003, 1.0999, 1.1002),
    C(1.1001, 1.1007, 1.1000, 1.1007),
    C(1.1005, 1.1010, 1.1004, 1.1010),
]
SOLDIERS_NEG_LAST_WICK_TOO_BIG = [
    C(1.1000, 1.1003, 1.0999, 1.1002),
    C(1.1001, 1.1007, 1.1000, 1.1007),
    C(1.1005, 1.1020, 1.1004, 1.1016),
]
SOLDIERS_NEG_FIRST_TOO_BIG = [
    C(1.1000, 1.1006, 1.0999, 1.1006),
    C(1.1004, 1.1014, 1.1003, 1.1014),
    C(1.1010, 1.1024, 1.1009, 1.1024),
]
SOLDIERS_NEG_NOT_ALL_SAME_COLOR = [
    C(1.1000, 1.1003, 1.0999, 1.1002),
    C(1.1007, 1.1007, 1.1000, 1.1001),
    C(1.1005, 1.1016, 1.1004, 1.1016),
]

# --- Steigendes / Fallendes Dreier-Pattern ---
RISE_POS = [
    C(1.1000, 1.1025, 1.0998, 1.1020),
    C(1.1014, 1.1017, 1.1010, 1.1012),
    C(1.1013, 1.1016, 1.1009, 1.1011),
    C(1.1012, 1.1015, 1.1010, 1.1010),
    C(1.1011, 1.1032, 1.1010, 1.1030),
]
RISE_NEG_MIDDLE_GREEN = [
    RISE_POS[0],
    RISE_POS[1],
    C(1.1011, 1.1016, 1.1009, 1.1013),
    RISE_POS[3],
    RISE_POS[4],
]
RISE_NEG_OUTSIDE_RANGE = [
    RISE_POS[0],
    C(1.1014, 1.1030, 1.1010, 1.1012),
    RISE_POS[2],
    RISE_POS[3],
    RISE_POS[4],
]
RISE_NEG_MIDDLE_TOO_BIG = [
    RISE_POS[0],
    C(1.1020, 1.1022, 1.1005, 1.1005),
    RISE_POS[2],
    RISE_POS[3],
    RISE_POS[4],
]
RISE_NEG_CLOSE_NOT_ABOVE_FIRST = [
    RISE_POS[0],
    RISE_POS[1],
    RISE_POS[2],
    RISE_POS[3],
    C(1.1008, 1.1020, 1.1007, 1.1019),
]


CASES = [
    ("Engulfing", pn.bullish_engulfing, pn.bearish_engulfing, ENG_POS,
     [ENG_NEG_SMALLER_BODY, ENG_NEG_NOT_ENCLOSING, ENG_NEG_WRONG_COLOR]),
    ("Tweezer", pn.tweezer_bottom, pn.tweezer_top, TWEEZER_POS,
     [TWEEZER_NEG_LOWS_DIFFER, TWEEZER_NEG_BODY_DISSIMILAR, TWEEZER_NEG_SAME_COLOR]),
    ("Star", pn.morning_star, pn.evening_star, STAR_POS,
     [STAR_NEG_MIDDLE_OTHER_COLOR, STAR_NEG_MIDDLE_TOO_BIG,
      STAR_NEG_FIRST_NOT_LONG, STAR_NEG_LAST_NOT_LONG, STAR_NEG_FIRST_DOJI]),
    ("Soldiers", pn.three_white_soldiers, pn.three_black_crows, SOLDIERS_POS,
     [SOLDIERS_NEG_BODY_NOT_GROWING, SOLDIERS_NEG_LAST_WICK_TOO_BIG,
      SOLDIERS_NEG_FIRST_TOO_BIG, SOLDIERS_NEG_NOT_ALL_SAME_COLOR]),
    ("Three-Method", pn.rising_three_methods, pn.falling_three_methods, RISE_POS,
     [RISE_NEG_MIDDLE_GREEN, RISE_NEG_OUTSIDE_RANGE,
      RISE_NEG_MIDDLE_TOO_BIG, RISE_NEG_CLOSE_NOT_ABOVE_FIRST]),
]


@pytest.mark.parametrize("name, bull, bear, positive, negatives", CASES, ids=[c[0] for c in CASES])
class TestPatternPairs:
    def test_bullish_positive_detected(self, name, bull, bear, positive, negatives):
        assert bull(positive, ATR)

    def test_bearish_positive_detected_via_mirror(self, name, bull, bear, positive, negatives):
        assert bear(mirror(positive), ATR)

    def test_bullish_positive_is_not_bearish(self, name, bull, bear, positive, negatives):
        assert not bear(positive, ATR)

    def test_negatives_not_detected(self, name, bull, bear, positive, negatives):
        for neg in negatives:
            assert not bull(neg, ATR)
            assert not bear(mirror(neg), ATR)


class TestSingleRules:
    def test_morning_star_fails_on_short_third_candle(self):
        candles = [STAR_POS[0], STAR_POS[1], C(1.0996, 1.1005, 1.0994, 1.1003)]
        assert not pn.morning_star(candles, ATR)

    def test_tweezer_bottom_fails_on_red_second_candle(self):
        candles = [TWEEZER_POS[0], C(1.1000, 1.1003, 1.0995, 1.0998)]
        assert not pn.tweezer_bottom(candles, ATR)

    def test_soldiers_open_in_body_optional_off_by_default(self):
        # K2 öffnet unterhalb des Körpers von K1, Regel ist per Default aus
        candles = [
            C(1.1000, 1.1003, 1.0999, 1.1002),
            C(1.1003, 1.1009, 1.1002, 1.1009),
            C(1.1007, 1.1018, 1.1006, 1.1018),
        ]
        assert pn.three_white_soldiers(candles, ATR)


class TestDetectPatterns:
    def test_registry_has_ten_patterns_with_signal_and_trend(self):
        assert len(pn.PATTERNS) == 10
        mapping = {p.name: (p.signal, p.required_trend) for p in pn.PATTERNS}
        assert mapping["Bullish Engulfing"] == ("BUY", "down")
        assert mapping["Bearish Engulfing"] == ("SELL", "up")
        assert mapping["Drei bullische Soldaten"] == ("BUY", "down")
        assert mapping["Steigendes Dreier-Pattern"] == ("BUY", "up")
        assert mapping["Fallendes Dreier-Pattern"] == ("SELL", "down")

    def test_detects_engulfing_at_last_candle(self):
        filler = C(1.1000, 1.1000, 1.1000, 1.1000)
        candles = [filler] + ENG_POS
        index = pd.date_range("2026-01-01 12:00", periods=3, freq="15min")
        df = pd.DataFrame([c._asdict() for c in candles], index=index)
        atr = pd.Series([ATR] * 3, index=index)

        found = pn.detect_patterns(df, atr)

        names = [f["name"] for f in found]
        assert "Bullish Engulfing" in names
        hit = next(f for f in found if f["name"] == "Bullish Engulfing")
        assert hit["signal"] == "BUY"
        assert hit["required_trend"] == "down"
        assert hit["time"] == index[-1]

    def test_no_detection_when_atr_is_nan(self):
        index = pd.date_range("2026-01-01 12:00", periods=2, freq="15min")
        df = pd.DataFrame([c._asdict() for c in ENG_POS], index=index)
        atr = pd.Series([float("nan"), float("nan")], index=index)

        assert pn.detect_patterns(df, atr) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
