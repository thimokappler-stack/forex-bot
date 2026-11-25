import io
import math
from contextlib import redirect_stdout

import numpy as np
import pandas as pd
import pytest

from buchbot import backtest, nulltest
from buchbot import config as default_config
from buchbot.filters import trend
from tests_buchbot.test_backtest import _walk, make_trade


# Kurze Reihen halten die Läufe schnell; das Mindestmaß für Märkte wird dafür gesenkt (autouse-Fixture)
CANDLES = 120


@pytest.fixture(autouse=True)
def kurze_reihen_erlaubt(monkeypatch):
    monkeypatch.setattr(default_config, "MIN_CANDLES_FOR_BACKTEST", 100)


def ts(text):
    return pd.Timestamp(text, tz="UTC")


# --- Cluster-Standardfehler ---

def test_cluster_se_zahlenbeispiel():
    # Mittelwert 0.5; Abweichungen 0.5, -1.5 | 1.5, -0.5; Clustersummen -1 und +1: sqrt(1 + 1) / 4
    se = backtest.cluster_std_error([1.0, -1.0, 2.0, 0.0], ["A", "A", "B", "B"])
    assert se == pytest.approx(math.sqrt(2) / 4)


def test_cluster_se_ein_cluster_ist_null_und_einzelwert_ist_none():
    assert backtest.cluster_std_error([1.0, 2.0, 3.0], ["A", "A", "A"]) == pytest.approx(0.0)
    assert backtest.cluster_std_error([1.0], ["A"]) is None


def test_cluster_se_ohne_cluster_gleich_wurzel_summe_abweichungsquadrate_durch_n():
    values = [1.0, -1.0, 2.0, 0.0]
    mean = sum(values) / len(values)
    expected = math.sqrt(sum((v - mean) ** 2 for v in values)) / len(values)
    assert backtest.cluster_std_error(values, [1, 2, 3, 4]) == pytest.approx(expected)


def test_stats_cluster_je_kalendermonat_ueber_alle_maerkte():
    trades = (
        [make_trade(r=1.0, market="EURUSD", time=ts("2020-01-05")) for _ in range(20)]
        + [make_trade(r=-1.0, market="GBPUSD", time=ts("2020-01-20")) for _ in range(10)]
        + [make_trade(r=-0.2, market="EURUSD", time=ts("2020-02-10")) for _ in range(30)]
    )
    stats = backtest._stats(trades)
    # Januar (beide Märkte) ist ein Cluster: Mittelwert 0.1167 (7 / 60)
    mean = (20 - 10 - 6) / 60
    january = 20 * (1.0 - mean) + 10 * (-1.0 - mean)
    february = 30 * (-0.2 - mean)
    assert stats["cse"] == pytest.approx(math.sqrt(january ** 2 + february ** 2) / 60)
    assert stats["cse_gross"] == pytest.approx(stats["cse"])


def test_cluster_se_ohne_signalzeit_ist_none():
    assert backtest._stats([make_trade(r=1.0), make_trade(r=2.0)])["cse"] is None


def test_gepoolte_tabelle_zeigt_cluster_se_nur_auf_wunsch():
    trades = [make_trade(r=1.0, time=ts("2020-01-05")), make_trade(r=-1.0, time=ts("2020-02-05"))]
    rows, total = backtest.summarize(trades, ["Test"])
    plain = backtest.render_table(rows, total, default_config, "T", "both", with_se=True)
    pooled = backtest.render_table(rows, total, default_config, "T", "both", with_se=True, cluster_se=True)
    assert "SE Cl." not in plain
    assert "SE Cl. vor K." in pooled and "SE Cl. nach K." in pooled


# --- doppelter Datensatz ---

def test_interval_1d_zaehlt_eurusd_nur_einmal(tmp_path):
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append(symbol)
        return _walk(CANDLES, start="2020-01-01", freq="1D")

    out = io.StringIO()
    with redirect_stdout(out):
        backtest.main(markets=["EURUSD", "EURUSD_30M"], fetch=fetch, csv_path=tmp_path / "bt.csv",
                      interval="1d", no_sr=True)
    text = out.getvalue()
    assert calls == ["EURUSD=X"]
    assert text.count("=== EUR/USD") == 1
    assert "[EURUSD_30M] übersprungen" in text and "wie EURUSD" in text
    rows = (tmp_path / "bt.csv").read_text(encoding="utf-8-sig").splitlines()
    assert not any(row.startswith("EURUSD_30M;") for row in rows)


def test_ohne_interval_laufen_beide_eurusd_maerkte(tmp_path):
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append(interval)
        return _walk(CANDLES)

    with redirect_stdout(io.StringIO()):
        backtest.main(markets=["EURUSD", "EURUSD_30M"], fetch=fetch, csv_path=tmp_path / "bt.csv", no_sr=True)
    assert calls == ["15m", "30m"]


# --- Permutation ---

def make_group(values, k, direction=0, decade=0, net_shift=0.0):
    values = np.array(values, dtype=float)
    return {"gross": values, "net": values + net_shift, "dec": np.full(len(values), decade),
            "dir": direction, "k": k}


def test_permutation_zieht_k_ohne_zuruecklegen_und_summiert():
    group = make_group([1.0, 2.0, 3.0, 4.0], k=4, net_shift=-0.5)
    gross, net, counts = nulltest.permutation_null([group], draws=5, seed=1, n_decades=3)
    assert (counts[:, 0, 0] == 4).all() and counts.sum() == 20
    assert (gross[:, 0, 0] == 10.0).all()
    assert (net[:, 0, 0] == 8.0).all()


def test_permutation_ist_bei_festem_seed_reproduzierbar():
    group = make_group(list(range(10)), k=3)
    first = nulltest.permutation_null([group], draws=20, seed=12345, n_decades=3)
    second = nulltest.permutation_null([group], draws=20, seed=12345, n_decades=3)
    other = nulltest.permutation_null([group], draws=20, seed=99, n_decades=3)
    assert all((a == b).all() for a, b in zip(first, second))
    assert not (first[0] == other[0]).all()


def test_nullvergleich_beispielreihe_mit_festem_seed(monkeypatch):
    monkeypatch.setattr(default_config, "NULL_TEST_DRAWS", 200)
    monkeypatch.setattr(default_config, "NULL_TEST_SEED", 12345)
    # Kandidaten 0 und 1, je Ziehung ein Trade: Nullverteilung besteht nur aus 0 und 1
    group = make_group([0.0, 1.0], k=1, net_shift=-0.1)
    real = {"gross": np.array([1.0]), "net": np.array([0.9]), "dir": np.array([0]), "dec": np.array([0])}
    pool = {"gross": np.array([0.0, 1.0]), "net": np.array([-0.1, 0.9]), "dir": np.array([0, 0]),
            "dec": np.array([0, 0])}
    rows = nulltest.null_comparison(real, pool, [group])

    rng = np.random.default_rng(12345)
    picks = np.array([rng.choice(2, size=1, replace=False)[0] for _ in range(200)], dtype=float)
    pooled = rows[0]["gross"]
    assert pooled["null_mean"] == pytest.approx(picks.mean())
    assert pooled["p"] == pytest.approx((picks >= 1.0).mean())
    assert pooled["quantiles"][0.99] == pytest.approx(1.0)
    assert pooled["quantiles"][0.05] == pytest.approx(0.0)
    assert pooled["drift"] == pytest.approx(0.5)
    assert rows[0]["gross"]["real"] == 1.0 and rows[0]["net"]["real"] == pytest.approx(0.9)
    assert rows[0]["n_real"] == 1 and rows[0]["n_candidates"] == 2


def test_nullvergleich_alle_kandidaten_gleich_gibt_p_eins_und_entartete_verteilung(monkeypatch):
    monkeypatch.setattr(default_config, "NULL_TEST_DRAWS", 50)
    group = make_group([0.5] * 8, k=3)
    real = {"gross": np.array([0.5, 0.5, 0.5]), "net": np.array([0.5] * 3), "dir": np.array([0] * 3),
            "dec": np.array([0] * 3)}
    pool = {key: group[key] for key in ("gross", "net", "dec")}
    pool["dir"] = np.zeros(8, dtype=int)
    row = nulltest.null_comparison(real, pool, [group])[0]["gross"]
    assert row["p"] == 1.0
    assert row["null_mean"] == pytest.approx(0.5)
    assert all(v == pytest.approx(0.5) for v in row["quantiles"].values())


def test_nullvergleich_bereiche_ohne_gezogene_trades_sind_leer(monkeypatch):
    monkeypatch.setattr(default_config, "NULL_TEST_DRAWS", 20)
    group = make_group([1.0, 2.0], k=1, direction=0, decade=1)
    real = {"gross": np.array([1.0]), "net": np.array([1.0]), "dir": np.array([0]), "dec": np.array([1])}
    rows = {r["scope"]: r for r in nulltest.null_comparison(real, group, [group])}
    assert rows["SELL"]["n_real"] == 0 and rows["SELL"]["gross"]["p"] is None
    assert rows["Zeit bis 2009"]["gross"]["null_mean"] is None
    assert rows["Zeit 2010-2019"]["gross"]["null_mean"] is not None


# --- Kandidaten und Trendregel ---

def _candidate_positions(df, result, direction, config):
    step = pd.Timedelta(config.INTERVAL)
    return sorted(df.index.get_loc(t["signal_time"] - step) for t in result[direction])


def test_kandidaten_nutzen_dieselbe_trendregel_wie_der_live_filter():
    config = default_config.for_market("EURUSD")
    df = _walk(300)
    result = nulltest.candidate_trades(df, config)
    n = default_config.NULL_PATTERN_CANDLES
    first = backtest.first_position(config)
    last_closed = len(df) - 1 - config.MAX_HOLD_CANDLES  # danach wäre der Trade offen
    for direction, required in nulltest.REQUIRED_TREND.items():
        expected = [pos for pos in range(first, last_closed + 1)
                    if trend.trend_at(df, pos - n, config) == required]
        assert _candidate_positions(df, result, direction, config) == expected
    assert result["BUY"] and result["SELL"]
    assert not set(_candidate_positions(df, result, "BUY", config)) & set(_candidate_positions(df, result, "SELL", config))


def test_kandidaten_einstieg_ist_schluss_und_sl_aus_den_letzten_zwei_kerzen():
    config = default_config.for_market("EURUSD")
    df = _walk(300)
    result = nulltest.candidate_trades(df, config)
    step = pd.Timedelta(config.INTERVAL)
    for direction in nulltest.DIRECTIONS:
        trade = result[direction][0]
        pos = df.index.get_loc(trade["signal_time"] - step)
        window = df.iloc[pos - 1:pos + 1]
        assert trade["entry"] == pytest.approx(df["close"].iloc[pos])
        if direction == "BUY":
            assert trade["sl"] < window["low"].min()
        else:
            assert trade["sl"] > window["high"].max()
        assert trade["r_gross"] - trade["r"] == pytest.approx(config.SPREAD_PIPS / trade["risk_pips"])


def test_echte_trades_filter_haupt_muster_bewertet():
    trades = [make_trade(), make_trade(source="candles_single"), make_trade(outcome="offen"),
              make_trade(direction="NEUTRAL"), make_trade(r=None)]
    assert len(nulltest.real_main_trades(trades)) == 1


# --- Kriterien und Zusatzzahlen ---

def criteria_trades():
    return (
        [make_trade(r=1.0, market="A", time=ts("2005-01-10")) for _ in range(20)]
        + [make_trade(r=-1.0, market="A", time=ts("2005-01-10")) for _ in range(10)]
        + [make_trade(r=-0.2, market="B", time=ts("2015-01-10")) for _ in range(30)]
        + [make_trade(r=0.5, market="C", time=ts("2022-01-10")) for _ in range(30)]
    )


def pooled_row(real, q99):
    return {"gross": {"real": real, "quantiles": {0.99: q99}, "p": 0.004}}


def results(trades, row):
    return {name: passed for name, _, _, passed in nulltest.evaluate_criteria(trades, row)}


def test_kriterien_mit_festen_zahlen():
    trades = criteria_trades()
    stats = backtest._stats(trades)
    assert stats["avg_r_gross"] == pytest.approx(19 / 90)
    # Clustersummen der Abweichungen: 3.6667, -12.3333, 8.6667
    assert stats["cse_gross"] == pytest.approx(math.sqrt(240.6667) / 90, rel=1e-4)
    res = results(trades, pooled_row(19 / 90, 0.1))
    assert res == {"K1": True, "K2": True, "K3": True, "K4": False, "K5": True}


def test_kriterium_k1_nein_wenn_unter_dem_quantil():
    assert results(criteria_trades(), pooled_row(19 / 90, 0.3))["K1"] is False


def test_kriterium_k2_braucht_zwei_von_drei_jahrzehnten():
    trades = [t for t in criteria_trades() if t["market"] != "C"]
    assert results(trades, pooled_row(0.1, 0.0))["K2"] is False


def test_kriterium_k3_zaehlt_nur_maerkte_mit_30_trades_und_k5_nach_kosten():
    trades = criteria_trades() + [make_trade(r=-5.0, market="KLEIN", time=ts("2022-03-01")) for _ in range(29)]
    assert [row["market"] for row in nulltest._market_rows(trades, 30)] == ["A", "B", "C"]
    negative = [make_trade(r=-0.1, market="A", time=ts("2005-01-10")) for _ in range(30)]
    assert results(negative, pooled_row(-0.1, 0.0))["K5"] is False
    assert results(negative, pooled_row(-0.1, 0.0))["K3"] is False


def test_zusatzzahlen_gepoolt_ohne_btc_eth_gold_und_marktrichtung():
    trades = [make_trade(r=1.0, market="EURUSD", time=ts("2020-01-10")) for _ in range(30)]
    trades += [make_trade(r=-3.0, market="BTC", time=ts("2020-01-10"), direction="SELL") for _ in range(30)]
    text = "\n".join(nulltest._pooled_without_lines(trades, default_config))
    assert "ohne BTC, ETH, GOLD" in text
    all_line = next(line for line in text.splitlines() if line.startswith("Alle"))
    assert all_line.split()[1] == "30" and "+1.000" in all_line
    sell_line = next(line for line in text.splitlines() if line.startswith("SELL"))
    assert sell_line.split()[1] == "0"
    market_text = "\n".join(nulltest._market_table(trades, default_config, "SELL"))
    assert "BTC" in market_text and "EURUSD" not in market_text


# --- Gesamtlauf ---

def test_null_test_im_backtest_gibt_neue_abschnitte_aus(tmp_path, monkeypatch):
    monkeypatch.setattr(default_config, "NULL_TEST_DRAWS", 30)
    out = io.StringIO()
    with redirect_stdout(out):
        backtest.main(markets=["EURUSD"], fetch=lambda *a, **k: _walk(CANDLES), csv_path=tmp_path / "bt.csv",
                      no_sr=True, null_test=True)
    text = out.getvalue()
    assert "=== Nullvergleich (Permutation) ===" in text and "30 Ziehungen" in text
    assert all(f"K{i}:" in text for i in range(1, 6))
    assert "=== Zusatzzahlen ===" in text and "Laufzeit Nullvergleich" in text


def test_ohne_null_test_gibt_es_keine_neuen_abschnitte(tmp_path):
    out = io.StringIO()
    with redirect_stdout(out):
        backtest.main(markets=["EURUSD"], fetch=lambda *a, **k: _walk(CANDLES), csv_path=tmp_path / "bt.csv",
                      no_sr=True)
    assert "Nullvergleich" not in out.getvalue()


def test_cli_kennt_null_test(monkeypatch):
    seen = {}
    monkeypatch.setattr(backtest, "main", lambda markets=None, **options: seen.update(options) or 0)
    backtest.cli(["--markets", "ALL", "--null-test"])
    assert seen["null_test"] is True
    backtest.cli(["--markets", "ALL"])
    assert seen["null_test"] is False
