"""
Tests für buchbot/sltp.py: Stop-Loss und Take-Profit mit festen Zahlen.
"""

import logging

import pandas as pd
import pytest

from buchbot import config as base_config
from buchbot import sltp
from buchbot.models import Signal

cfg = base_config.for_market("EURUSD")


def make_signal(direction, entry, atr, **tags):
    return Signal(
        time=pd.Timestamp("2026-01-01 12:30", tz="UTC"),
        symbol="EURUSD=X",
        interval="15m",
        source="candles_main",
        pattern="Dummy",
        direction=direction,
        entry=entry,
        atr=atr,
        tags=tags,
        market="EURUSD",
    )


def test_buy_sl_tp_and_risk_values():
    s = make_signal("BUY", 1.1000, 0.0010, pattern_low=1.0985, pattern_high=1.1000)

    result = sltp.apply([s], cfg)

    assert result == [s]
    assert s.sl == pytest.approx(1.0980)
    assert s.risk_pips == pytest.approx(20)
    assert s.tp == pytest.approx(1.1040)
    assert s.rr == cfg.RISK_REWARD


def test_sell_sl_and_tp_values():
    s = make_signal("SELL", 1.1000, 0.0010, pattern_low=1.0990, pattern_high=1.1015)

    sltp.apply([s], cfg)

    assert s.sl == pytest.approx(1.1020)
    assert s.tp == pytest.approx(1.0960)
    assert s.risk_pips == pytest.approx(20)


def test_values_are_rounded_to_five_decimals():
    s = make_signal("BUY", 1.10004, 0.00033, pattern_low=1.09851, pattern_high=1.1000)

    sltp.apply([s], cfg)

    assert s.sl == round(s.sl, 5)
    assert s.tp == round(s.tp, 5)
    assert s.risk_pips == round(s.risk_pips, 5)


def test_signal_below_min_risk_is_discarded_and_logged(caplog):
    # SL-Abstand: 1.0997 - 0.5 * 0.0001 = 1.09965, Risiko 3.5 Pips < MIN_SL_PIPS (5)
    s = make_signal("BUY", 1.1000, 0.0001, pattern_low=1.0997, pattern_high=1.1000)

    with caplog.at_level(logging.INFO):
        result = sltp.apply([s], cfg)

    assert result == []
    assert s.sl is None
    assert "verworfen" in caplog.text


def test_neutral_signal_gets_no_sl_tp_and_is_kept():
    s = make_signal("NEUTRAL", 1.1000, 0.0010, pattern_low=1.0999, pattern_high=1.1001)

    result = sltp.apply([s], cfg)

    assert result == [s]
    assert s.sl is None
    assert s.tp is None
    assert s.risk_pips is None


def test_unknown_direction_raises():
    s = make_signal("HOLD", 1.1000, 0.0010, pattern_low=1.0985, pattern_high=1.1000)

    with pytest.raises(ValueError):
        sltp.apply([s], cfg)
