import numpy as np
import pandas as pd
import pytest

from buchbot import backtest
from buchbot import config as default_config
from buchbot.models import Signal


def make_config(**overrides):
    cfg = default_config.for_market(default_config.DEFAULT_MARKET)
    # Kurze Testreihen: Haltefenster passt in die Daten, sonst gilt der Trade als offen
    cfg.MAX_HOLD_CANDLES = 1
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


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
    rows, total = backtest.summarize([open_trade, tp_trade], backtest.MAIN_PATTERN_NAMES)
    stats = dict(rows)["Morning Star"]
    assert stats["n"] == 1
    assert total["n"] == 1
    assert total["sum_r"] == pytest.approx(1.95)
    assert backtest.open_count([open_trade, tp_trade]) == 1


def test_table_lists_all_patterns_even_without_signals():
    rows, total = backtest.summarize([], backtest.MAIN_PATTERN_NAMES)
    table = backtest.render_table(rows, total, make_config(), "info")
    for name in backtest.MAIN_PATTERN_NAMES:
        assert name in table
    assert len(backtest.MAIN_PATTERN_NAMES) == 10
    line = next(line for line in table.splitlines() if line.startswith("Steigendes Dreier-Pattern"))
    assert line.endswith("-")
    assert "0" in line


def test_neutral_signal_is_not_simulated_and_has_no_r():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1010, 1.1000)])
    trade = backtest.simulate(make_signal("NEUTRAL", None, None), df, 0, make_config())
    assert trade["outcome"] == "nicht bewertet"
    assert trade["r"] is None
    assert trade["exit_time"] is None


def test_neutral_signals_are_counted_with_dashes_for_results():
    neutral = {"pattern": "Doji", "outcome": "nicht bewertet", "r": None}
    rows, total = backtest.summarize([neutral], backtest.SINGLE_PATTERN_NAMES)
    stats = dict(rows)["Doji"]
    assert stats["n"] == 1
    assert stats["avg_r"] is None
    assert stats["sum_r"] is None
    table = backtest.render_table(rows, total, make_config(), "info")
    line = next(line for line in table.splitlines() if line.startswith("Doji"))
    assert line.split()[1:] == ["1", "-", "-", "-", "-", "-"]


def test_summary_groups_are_separate():
    main = {"pattern": "Morning Star", "outcome": "TP", "r": 1.0}
    single = {"pattern": "Doji", "outcome": "nicht bewertet", "r": None}
    _, total = backtest.summarize([main, single], backtest.MAIN_PATTERN_NAMES)
    assert total["n"] == 1
    _, total = backtest.summarize([main, single], backtest.SINGLE_PATTERN_NAMES)
    assert total["n"] == 1


def test_funnel_stages_only_shrink():
    rng = np.random.default_rng(7)
    steps = rng.normal(0, 0.0004, 400)
    close = 1.1 + np.cumsum(steps)
    open_ = np.concatenate([[1.1], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.0003, 400))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.0003, 400))
    full = make_df(np.column_stack([open_, high, low, close]).tolist())

    _, funnel = backtest.find_signals(full, make_config(MAX_HOLD_CANDLES=32))
    for name in backtest.MAIN_PATTERN_NAMES + backtest.SINGLE_PATTERN_NAMES:
        assert funnel["raw"][name] >= funnel["trend"][name] >= funnel["sltp"][name]


def make_trade(direction="BUY", source="candles_main", outcome="TP", r=1.0, aligned=None,
               against=False, relation="none", trend="range", zones=2, market="EURUSD",
               time=None, support=0, resistance=0):
    tags = {"sr_aligned": aligned, "sr_against": against, "sr_relation": relation,
            "swing_trend": trend, "sr_strong_zones": zones,
            "sr_strong_support": support, "sr_strong_resistance": resistance}
    return {"pattern": "Test", "source": source, "direction": direction, "outcome": outcome,
            "r": r, "tags": tags, "market": market, "signal_time": time}


def test_zone_groups_assign_each_group_with_fixed_examples():
    aligned_buy = make_trade("BUY", aligned=True, relation="at_support")
    against_sell = make_trade("SELL", against=True, relation="at_resistance")
    no_zone = make_trade("BUY", aligned=None, relation="none")

    a, b, c, d = (predicate for _, predicate in backtest.ZONE_GROUPS)
    assert a(aligned_buy) and not c(aligned_buy) and d(aligned_buy) and not b(aligned_buy)
    assert c(against_sell) and not a(against_sell) and not d(against_sell)
    assert b(no_zone) and not a(no_zone) and not c(no_zone) and not d(no_zone)

    aligned_but_against = make_trade("BUY", aligned=True, against=True, relation="at_support")
    assert a(aligned_but_against) and not d(aligned_but_against)


def test_trend_groups_depend_on_direction_and_swing_trend():
    mit, gegen, range_, ohne = (predicate for _, predicate in backtest.TREND_GROUPS)
    assert mit(make_trade("BUY", trend="up")) and mit(make_trade("SELL", trend="down"))
    assert gegen(make_trade("BUY", trend="down")) and gegen(make_trade("SELL", trend="up"))
    assert range_(make_trade("BUY", trend="range"))
    no_pivots = make_trade("BUY", trend=None)
    assert ohne(no_pivots) and ohne(make_trade("SELL", trend=""))
    assert not (mit(no_pivots) or gegen(no_pivots) or range_(no_pivots))


def test_trend_groups_add_up_to_population_with_ohne_swing_trend():
    population = [make_trade(trend=t) for t in ("up", "down", "range", None, "", "up")]
    counts = [sum(1 for t in population if predicate(t)) for _, predicate in backtest.TREND_GROUPS]
    assert counts == [2, 1, 1, 2]
    assert sum(counts) == len(population)


def test_standard_error_is_sample_std_over_root_n():
    trades = [make_trade(r=r) for r in (1.0, -1.0, 2.0, 0.0)]
    stats = backtest._stats(trades)
    # Mittelwert 0.5, Stichprobenstandardabweichung sqrt(5/3) = 1.291, geteilt durch sqrt(4)
    assert stats["se"] == pytest.approx(0.6455, abs=1e-4)


def test_standard_error_is_none_for_single_trade():
    assert backtest._stats([make_trade(r=1.0)])["se"] is None


def test_empty_population_shows_notice_and_no_warning():
    out = backtest.render_zone_compare([], default_config, "Test")
    assert "keine BUY/SELL-Signale" in out
    assert "Warnung" not in out


def test_empty_group_is_listed_with_dashes_and_few_cases_note():
    population = [make_trade("BUY", aligned=True, relation="at_support", trend="up")]
    out = backtest.render_zone_compare(population, default_config, "Test")
    row = next(line for line in out.splitlines() if line.startswith("c) gegen starke Zone"))
    assert row[38:46].strip() == "0"
    assert row[46:52].strip() == "-"
    assert "c) gegen starke Zone: zu wenige Fälle (0 < 30)" in out


def test_warning_when_one_group_takes_over_80_percent():
    population = [make_trade("BUY", aligned=True, relation="at_support", trend="up") for _ in range(10)]
    out = backtest.render_zone_compare(population, default_config, "Test")
    assert "Zonenparameter möglicherweise unpassend" in out
    assert "Haupt-Muster (candles_main)" in out


def test_warning_when_group_is_below_5_percent():
    population = [make_trade("BUY", aligned=True, relation="at_support", trend="up") for _ in range(10)]
    population += [make_trade("BUY", aligned=None, relation="none", trend="up") for _ in range(20)]
    out = backtest.render_zone_compare(population, default_config, "Test")
    warnings = [line for line in out.splitlines() if "Warnung" in line]
    assert any("c) gegen starke Zone" in line for line in warnings)


def test_leere_restgruppe_ohne_swing_trend_loest_keine_warnung_aus():
    population = [make_trade("BUY", aligned=True, relation="at_support", trend="up") for _ in range(10)]
    population += [make_trade("BUY", aligned=None, relation="none", trend="down") for _ in range(10)]
    out = backtest.render_zone_compare(population, default_config, "Test")
    assert "ohne Swing-Trend" in out
    assert not [line for line in out.splitlines() if "Warnung" in line and "ohne Swing-Trend" in line]


def test_pooling_adds_trades_of_two_markets():
    eurusd = [make_trade("BUY", aligned=True, relation="at_support", market="EURUSD") for _ in range(2)]
    gbpusd = [make_trade("BUY", aligned=True, relation="at_support", market="GBPUSD") for _ in range(3)]
    pooled = eurusd + gbpusd
    assert len(backtest._zone_population(pooled, "candles_main")) == 5
    assert backtest._stats([t for t in pooled if backtest._is_aligned(t)])["n"] == 5
    out = backtest.render_zone_compare(pooled, default_config, "GESAMT")
    row = next(line for line in out.splitlines() if line.startswith("a) Muster an starker passender Zone"))
    assert row[38:46].strip() == "5"


def test_parse_markets_accepts_all_and_lists_and_rejects_unknown():
    assert backtest._parse_markets("ALL") == list(default_config.MARKETS)
    assert backtest._parse_markets("EURUSD, GBPUSD") == ["EURUSD", "GBPUSD"]
    with pytest.raises(Exception):
        backtest._parse_markets("EURUSD,NOPE")


def test_signal_time_median_takes_upper_middle_and_ignores_neutral():
    times = [pd.Timestamp(f"2026-01-0{d}", tz="UTC") for d in (1, 2, 3, 4)]
    trades = [make_trade(time=t) for t in times]
    assert backtest.signal_time_median(trades) == times[2]
    assert backtest.signal_time_median([make_trade("NEUTRAL", time=times[0]), make_trade(time=times[1])]) == times[1]
    assert backtest.signal_time_median([]) is None


def test_time_halves_split_at_median_with_counts_and_group_rows():
    t1 = pd.Timestamp("2026-01-01 10:00", tz="UTC")
    t2 = pd.Timestamp("2026-01-03 10:00", tz="UTC")
    early = [make_trade("BUY", aligned=True, relation="at_support", time=t1) for _ in range(2)]
    late = [make_trade("BUY", aligned=True, relation="at_support", time=t2)]
    out = backtest.render_zone_compare(early + late, default_config, "GESAMT", split_at=t2)
    assert "Zeithälfte 1 (Signale vor 2026-01-03 10:00 UTC): 2 BUY/SELL-Signale" in out
    assert "Zeithälfte 2 (Signale ab 2026-01-03 10:00 UTC): 1 BUY/SELL-Signale" in out
    first_half = out.split("Zeithälfte 1")[1].split("Zeithälfte 2")[0]
    row = next(line for line in first_half.splitlines() if line.startswith("a) Muster an starker passender Zone"))
    assert row[38:46].strip() == "2"


def test_zone_density_warning_only_above_limit():
    dense = [make_trade("BUY", aligned=True, relation="at_support", support=5, resistance=5) for _ in range(3)]
    sparse = [make_trade("BUY", aligned=True, relation="at_support", support=2, resistance=2) for _ in range(3)]
    assert "Zonen zu dicht" in backtest.render_zone_compare(dense, default_config, "Test")
    assert "Zonen zu dicht" not in backtest.render_zone_compare(sparse, default_config, "Test")


def test_header_shows_mean_zones_per_side_and_group_shares():
    population = [
        make_trade("BUY", aligned=True, relation="at_support", support=2, resistance=4),
        make_trade("SELL", against=True, relation="at_resistance", support=0, resistance=2),
    ]
    lines, warnings = backtest._header_lines(population, default_config, "Test")
    assert lines[0] == "Ø starke Zonen je Kerze und Seite: 2.0 (Unterstützung 1.0, Widerstand 3.0)"
    assert "Gruppe a) 50" in lines[1] and "Gruppe c) 50" in lines[1]
    assert warnings == []
