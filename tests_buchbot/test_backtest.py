from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from buchbot import backtest
from buchbot import config as default_config
from buchbot.models import Signal


def make_config(**overrides):
    values = {k: getattr(default_config, k) for k in dir(default_config) if k.isupper()}
    # Kurze Testreihen: Haltefenster passt in die Daten, sonst gilt der Trade als offen
    values["MAX_HOLD_CANDLES"] = 1
    values.update(overrides)
    return SimpleNamespace(**values)


def make_df(rows):
    index = pd.date_range("2026-01-05 10:00", periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def make_signal(direction, sl, tp, entry=1.1000):
    return Signal(
        time=pd.Timestamp("2026-01-05 10:15", tz="UTC"),
        symbol="EURUSD=X",
        interval="15m",
        source="candles_main",
        pattern="Test",
        direction=direction,
        entry=entry,
        atr=0.0010,
        sl=sl,
        tp=tp,
        risk_pips=20.0,
        rr=2.0,
    )


def candle(high, low, close=None):
    close = (high + low) / 2 if close is None else close
    return [close, high, low, close]


def test_buy_tp_hit_gives_rr_minus_spread():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    trade = backtest.simulate(make_signal("BUY", 1.0980, 1.1040), df, 0, make_config())
    assert trade["outcome"] == "TP"
    assert trade["r"] == pytest.approx(1.95)


def test_buy_sl_hit_gives_minus_one_minus_spread():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1010, 1.0975), candle(1.1020, 1.1000)])
    trade = backtest.simulate(make_signal("BUY", 1.0980, 1.1040), df, 0, make_config())
    assert trade["outcome"] == "SL"
    assert trade["r"] == pytest.approx(-1.05)


def test_sl_and_tp_in_same_candle_counts_as_sl():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.0975)])
    trade = backtest.simulate(make_signal("BUY", 1.0980, 1.1040), df, 0, make_config())
    assert trade["outcome"] == "SL"
    assert trade["r"] == pytest.approx(-1.05)


def test_timeout_closes_at_last_hold_candle_close():
    df = make_df([
        candle(1.1005, 1.0995, 1.1000),
        candle(1.1010, 1.0990),
        candle(1.1010, 1.0990, 1.1005),
        candle(1.1100, 1.0999),  # nach dem Haltefenster, darf nichts bewirken
    ])
    config = make_config(MAX_HOLD_CANDLES=2)
    trade = backtest.simulate(make_signal("BUY", 1.0980, 1.1040), df, 0, config)
    assert trade["outcome"] == "Zeitablauf"
    assert trade["exit_price"] == pytest.approx(1.1005)
    assert trade["r"] == pytest.approx(0.2)


def test_sell_tp_hit():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1005, 1.0955), candle(1.1000, 1.0950)])
    trade = backtest.simulate(make_signal("SELL", 1.1020, 1.0960), df, 0, make_config())
    assert trade["outcome"] == "TP"
    assert trade["r"] == pytest.approx(1.95)


def test_spread_is_subtracted():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    signal = make_signal("BUY", 1.0980, 1.1040)
    with_spread = backtest.simulate(signal, df, 0, make_config(SPREAD_PIPS=1.0))
    without_spread = backtest.simulate(signal, df, 0, make_config(SPREAD_PIPS=0.0))
    assert without_spread["r"] == pytest.approx(2.0)
    assert without_spread["r"] - with_spread["r"] == pytest.approx(0.05)


def test_signals_do_not_change_when_later_candles_are_added():
    rng = np.random.default_rng(7)
    steps = rng.normal(0, 0.0004, 400)
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.0003, 400))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.0003, 400))
    full = make_df(np.column_stack([open_, high, low, close]).tolist())
    config = make_config()

    short = backtest.find_signals(full.iloc[:300], config)[0]
    long_run = [item for item in backtest.find_signals(full, config)[0] if item[0] < 299]

    assert len(short) > 0
    assert short == long_run


def test_trade_whose_hold_window_exceeds_data_is_open_even_if_tp_is_touched():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000), candle(1.1010, 1.1000)])
    trade = backtest.simulate(make_signal("BUY", 1.0980, 1.1040), df, 0, make_config(MAX_HOLD_CANDLES=5))
    assert trade["outcome"] == "offen"
    assert trade["r"] is None
    assert trade["exit_price"] is None


def test_open_trades_are_excluded_from_statistics():
    open_trade = {"pattern": "Morning Star", "outcome": "offen", "r": None}
    tp_trade = {"pattern": "Morning Star", "outcome": "TP", "r": 1.95}
    rows, total = backtest.summarize([open_trade, tp_trade])
    stats = dict(rows)["Morning Star"]
    assert stats["n"] == 1
    assert total["n"] == 1
    assert total["sum_r"] == pytest.approx(1.95)
    assert backtest.open_count([open_trade, tp_trade]) == 1


def test_table_lists_all_patterns_even_without_signals():
    rows, total = backtest.summarize([])
    table = backtest.render_table(rows, total, make_config(), "info")
    for name in backtest.PATTERN_NAMES:
        assert name in table
    assert len(backtest.PATTERN_NAMES) == 10
    line = next(line for line in table.splitlines() if line.startswith("Steigendes Dreier-Pattern"))
    assert line.endswith("-")
    assert "0" in line


def test_funnel_stages_only_shrink():
    rng = np.random.default_rng(7)
    steps = rng.normal(0, 0.0004, 400)
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.0003, 400))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.0003, 400))
    full = make_df(np.column_stack([open_, high, low, close]).tolist())

    _, funnel = backtest.find_signals(full, make_config(MAX_HOLD_CANDLES=32))
    for name in backtest.PATTERN_NAMES:
        assert funnel["raw"][name] >= funnel["trend"][name] >= funnel["sltp"][name]
