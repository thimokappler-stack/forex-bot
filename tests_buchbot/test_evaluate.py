import csv

import pandas as pd
import pytest

from buchbot import backtest
from buchbot import config as default_config
from buchbot import evaluate
from buchbot.models import Signal
from buchbot.zones import SR_COLUMNS


SIGNAL_FIELDS = ["time", "symbol", "interval", "source", "pattern", "direction",
                 "entry", "atr", "sl", "tp", "risk_pips", "rr", "mode"]


def make_config(**overrides):
    cfg = default_config.for_market(default_config.DEFAULT_MARKET)
    cfg.MAX_HOLD_CANDLES = 1
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def make_df(rows):
    index = pd.date_range("2026-01-05 10:00", periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def candle(high, low, close=None):
    close = (high + low) / 2 if close is None else close
    return [close, high, low, close]


def signal_row(**overrides):
    """Eine CSV-Zeile: Signalkerze 10:00 UTC, Schlusszeit 10:15 UTC, BUY Entry 1.1000, SL 1.0980, TP 1.1040."""
    row = {
        "time": "2026-01-05T10:15:00+00:00", "symbol": "EURUSD=X", "interval": "15m",
        "source": "candles_main", "pattern": "Bullish Engulfing", "direction": "BUY",
        "entry": "1.10000", "atr": "0.00100", "sl": "1.09800", "tp": "1.10400",
        "risk_pips": "20.0", "rr": "2.0", "mode": "log_only",
    }
    row.update(overrides)
    return row


def write_csv(path, rows, fields=SIGNAL_FIELDS):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_read_signal_rows_liest_alte_und_neue_kopfzeile(tmp_path):
    old = tmp_path / "alt.csv"
    new = tmp_path / "neu.csv"
    write_csv(old, [signal_row()])
    write_csv(new, [signal_row(sr_relation="at_support")], fields=SIGNAL_FIELDS + SR_COLUMNS)
    for path in (old, new):
        rows = evaluate.read_signal_rows(str(path))
        assert len(rows) == 1
        assert rows[0]["entry"] == "1.10000"


def evaluate_one(df, config, **overrides):
    trades, _, _ = evaluate.evaluate_rows([signal_row(**overrides)], df, config)
    assert len(trades) == 1
    return trades[0]


def test_tp_hit_in_next_candle():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    trade = evaluate_one(df, make_config())
    assert trade["outcome"] == backtest.OUTCOME_TP
    assert trade["r"] == pytest.approx(1.95)


def test_sl_hit_in_next_candle():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1010, 1.0975), candle(1.1020, 1.1000)])
    trade = evaluate_one(df, make_config())
    assert trade["outcome"] == backtest.OUTCOME_SL
    assert trade["r"] == pytest.approx(-1.05)


def test_sl_wins_when_sl_and_tp_in_same_candle():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.0975)])
    trade = evaluate_one(df, make_config())
    assert trade["outcome"] == backtest.OUTCOME_SL
    assert trade["r"] == pytest.approx(-1.05)


def test_timeout_closes_at_last_hold_candle_close():
    df = make_df([
        candle(1.1005, 1.0995, 1.1000),
        candle(1.1005, 1.0995, 1.1002),
        candle(1.1012, 1.1000, 1.1010),
    ])
    trade = evaluate_one(df, make_config(MAX_HOLD_CANDLES=2))
    assert trade["outcome"] == backtest.OUTCOME_TIMEOUT
    assert trade["exit_price"] == pytest.approx(1.1010)
    assert trade["r"] == pytest.approx(0.45)


def test_open_when_hold_window_extends_past_data():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1010, 1.1000)])
    trade = evaluate_one(df, make_config(MAX_HOLD_CANDLES=2))
    assert trade["outcome"] == backtest.OUTCOME_OPEN
    assert trade["r"] is None
    assert backtest.open_count([trade]) == 1


def test_missing_signal_candle_counts_as_open_and_is_excluded_from_stats():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    trade = evaluate_one(df, make_config(), time="2026-01-06T10:15:00+00:00")
    assert trade["outcome"] == backtest.OUTCOME_OPEN
    rows, total = backtest.summarize([trade], [trade["pattern"]])
    assert total["n"] == 0


def test_neutral_signal_is_counted_but_not_evaluated():
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    trade = evaluate_one(df, make_config(), direction="NEUTRAL", sl="", tp="", risk_pips="",
                         pattern="Doji", source="candles_single")
    assert trade["outcome"] == backtest.OUTCOME_NOT_EVALUATED
    assert trade["r"] is None


def test_empty_csv_yields_no_rows(tmp_path):
    path = tmp_path / "signals_log.csv"
    path.write_bytes(b"")
    assert evaluate.read_signal_rows(path) == []


def test_empty_csv_main_returns_zero_without_fetching(tmp_path, capsys):
    path = tmp_path / "signals_log.csv"
    path.write_bytes(b"")

    def fetch(*args, **kwargs):
        pytest.fail("Kerzen dürfen bei leerer CSV nicht geladen werden")

    assert evaluate.main(fetch=fetch, csv_path=path) == 0
    assert "Keine Signale" in capsys.readouterr().out


def test_missing_columns_give_clear_error(tmp_path, capsys):
    path = tmp_path / "signals_log.csv"
    write_csv(path, [{"time": "2026-01-05T10:15:00+00:00", "direction": "BUY"}],
              fields=["time", "direction"])

    with pytest.raises(ValueError, match="Pflichtspalten fehlen: source, pattern, entry, sl, tp"):
        evaluate.read_signal_rows(path)

    def fetch(*args, **kwargs):
        pytest.fail("Kerzen dürfen bei fehlenden Spalten nicht geladen werden")

    assert evaluate.main(fetch=fetch, csv_path=path) == 1
    assert "Pflichtspalten fehlen" in capsys.readouterr().out


def test_csv_ohne_market_spalte_wird_als_eurusd_gelesen(tmp_path, caplog):
    path = tmp_path / "signals_log.csv"
    write_csv(path, [signal_row()])

    with caplog.at_level("INFO"):
        rows = evaluate.read_signal_rows(path)

    assert len(rows) == 1
    assert rows[0]["market"] == default_config.DEFAULT_MARKET == "EURUSD"
    assert "altes Format" in caplog.text


def test_evaluate_matches_backtest_r_for_same_signal(tmp_path):
    df = make_df([candle(1.1005, 1.0995, 1.1000), candle(1.1045, 1.1000)])
    config = make_config()
    signal = Signal(
        time=pd.Timestamp("2026-01-05 10:15", tz="UTC"), symbol="EURUSD=X", interval="15m",
        source="candles_main", pattern="Bullish Engulfing", direction="BUY",
        entry=1.1000, atr=0.0010, sl=1.0980, tp=1.1040, risk_pips=20.0, rr=2.0,
    )
    backtest_trade = backtest.simulate(signal, df, 0, config)

    path = tmp_path / "signals_log.csv"
    write_csv(path, [signal_row()])
    evaluate_trades, _, _ = evaluate.evaluate_rows(evaluate.read_signal_rows(path), df, config)
    evaluate_trade = evaluate_trades[0]

    assert evaluate_trade["outcome"] == backtest_trade["outcome"]
    assert evaluate_trade["r"] == pytest.approx(backtest_trade["r"])


OVERLAP_CANDLES = [
    candle(1.1005, 1.0995, 1.1000),
    candle(1.1010, 1.0995, 1.1005),
    candle(1.1010, 1.0995, 1.1005),
    candle(1.1045, 1.1000, 1.1040),
    candle(1.1010, 1.0995),
    candle(1.1010, 1.0995),
]


def test_overlapping_signal_of_same_pattern_is_skipped_by_default():
    df = make_df(OVERLAP_CANDLES)
    config = make_config(MAX_HOLD_CANDLES=3)
    rows = [signal_row(), signal_row(time="2026-01-05T10:30:00+00:00")]
    trades, skipped, too_old = evaluate.evaluate_rows(rows, df, config)
    assert len(trades) == 1
    assert trades[0]["outcome"] == backtest.OUTCOME_TP
    assert skipped == 1
    assert too_old == 0


def test_allow_overlap_evaluates_all_signals():
    df = make_df(OVERLAP_CANDLES)
    config = make_config(MAX_HOLD_CANDLES=3)
    rows = [signal_row(), signal_row(time="2026-01-05T10:30:00+00:00")]
    trades, skipped, _ = evaluate.evaluate_rows(rows, df, config, allow_overlap=True)
    assert len(trades) == 2
    assert skipped == 0


def test_backtest_and_evaluate_agree_on_overlapping_signals(tmp_path, monkeypatch):
    df = make_df(OVERLAP_CANDLES)
    config = make_config(MAX_HOLD_CANDLES=3)
    first = evaluate.signal_from_row(signal_row(), config)
    second = evaluate.signal_from_row(signal_row(time="2026-01-05T10:30:00+00:00"), config)
    monkeypatch.setattr(backtest, "find_signals", lambda df, config: ([(0, first), (1, second)], {}))

    bt_trades, bt_funnel = backtest.run_backtest(df, config)

    path = tmp_path / "signals_log.csv"
    write_csv(path, [signal_row(), signal_row(time="2026-01-05T10:30:00+00:00")])
    ev_trades, ev_skipped, _ = evaluate.evaluate_rows(evaluate.read_signal_rows(path), df, config)

    assert [(t["outcome"], t["r"]) for t in ev_trades] == [(t["outcome"], t["r"]) for t in bt_trades]
    assert bt_funnel["uebersprungen"]["Bullish Engulfing"] == 1
    assert ev_skipped == 1


def test_signals_before_first_candle_counted_as_too_old_not_open():
    df = make_df(OVERLAP_CANDLES)
    config = make_config(MAX_HOLD_CANDLES=3)
    rows = [signal_row(time="2026-01-05T10:00:00+00:00")]
    trades, skipped, too_old = evaluate.evaluate_rows(rows, df, config)
    assert trades == []
    assert skipped == 0
    assert too_old == 1


def test_main_prints_too_old_line_with_data_range(tmp_path, capsys):
    df = make_df(OVERLAP_CANDLES)
    path = tmp_path / "signals_log.csv"
    write_csv(path, [signal_row(time="2026-01-05T10:00:00+00:00")])

    exit_code = evaluate.main(fetch=lambda *a, **k: df, csv_path=path)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "zu alt für die Kerzendaten: 1" in out
    assert "decken den Zeitraum von 2026-01-05T10:00:00+00:00 bis" in out
