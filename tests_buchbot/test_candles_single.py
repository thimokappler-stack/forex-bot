"""
Tests für buchbot/detectors/candles_single.py (Einzelkerzen im Hintergrund).

Feste Zahlen mit ATR 0.0010 (Schwellen: kleiner Körper <= 0.0003, Doji-Körper <= 10 % der Spanne).
"""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from buchbot import config as real_config
from buchbot import detectors
from buchbot import pipeline
from buchbot.detectors import candles_single as cs
from buchbot.detectors.candles_main import Candle
from buchbot.filters import trend
from buchbot.outputs import mail

ATR = 0.0010
NOW = pd.Timestamp("2026-05-06 10:00", tz="UTC")


def C(o, h, l, c):
    return Candle(o, h, l, c)


def make_config(**overrides):
    cfg = real_config.for_market(real_config.DEFAULT_MARKET)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def build_df(candles, start):
    index = pd.date_range(start, periods=len(candles), freq="15min", tz="UTC")
    return pd.DataFrame([[c.open, c.high, c.low, c.close] for c in candles],
                        index=index, columns=["open", "high", "low", "close"])


def flat_df(last):
    """30 Kerzen mit Spanne 0.0010 (ATR 0.0010), danach die Testkerze."""
    filler = [C(1.1000, 1.1005, 1.0995, 1.1000)] * 30
    return build_df(filler + [last], "2026-05-06 00:00")


def downtrend_candles(n=79):
    candles = []
    for i in range(n):
        o = 1.2 - 0.0002 * i
        c = o - 0.0002
        candles.append(C(o, o + 0.0001, c - 0.0001, c))
    return candles


def uptrend_candles(n=79):
    candles = []
    for i in range(n):
        o = 1.1 + 0.0002 * i
        c = o + 0.0002
        candles.append(C(o, c + 0.0001, o - 0.0001, c))
    return candles


def hammer_after_downtrend():
    candles = downtrend_candles()
    o = candles[-1].close
    return candles + [C(o, o + 0.0001, o - 0.0003, o + 0.0001)]


@pytest.fixture
def only_single(monkeypatch):
    monkeypatch.setattr(detectors, "_REGISTRY", {})
    detectors.register("candles_single", cs.detect, cs.SOURCE)
    return detectors._REGISTRY


POSITIVE = [
    pytest.param(cs.hammer, C(1.1000, 1.1002, 1.0990, 1.1002), id="hammer"),
    pytest.param(cs.hanging_man, C(1.1002, 1.1002, 1.0990, 1.1000), id="hanging-man"),
    pytest.param(cs.inverted_hammer, C(1.1000, 1.1012, 1.1000, 1.1002), id="umgekehrter-hammer"),
    pytest.param(cs.shooting_star, C(1.1002, 1.1012, 1.1000, 1.1000), id="shooting-star"),
    pytest.param(cs.marubozu_green, C(1.1000, 1.1009, 1.1000, 1.1009), id="marubozu-gruen"),
    pytest.param(cs.marubozu_red, C(1.1009, 1.1009, 1.1000, 1.1000), id="marubozu-rot"),
    pytest.param(cs.doji, C(1.1000, 1.1010, 1.0990, 1.10005), id="doji"),
    pytest.param(cs.spinning_top, C(1.1000, 1.1005, 1.0995, 1.1002), id="spinning-top"),
]

NEGATIVE = [
    pytest.param(cs.hammer, C(1.1002, 1.1002, 1.0990, 1.1000), id="hammer-rot-ist-hanging-man"),
    pytest.param(cs.hammer, C(1.1000, 1.1002, 1.0998, 1.1002), id="hammer-unterer-docht-zu-kurz"),
    pytest.param(cs.hammer, C(1.1000, 1.10005, 1.0900, 1.10005), id="hammer-doji-ist-kein-hammer"),
    pytest.param(cs.inverted_hammer, C(1.1000, 1.1002, 1.0990, 1.1002), id="umgek-hammer-ohne-oberen-docht"),
    pytest.param(cs.hanging_man, C(1.1000, 1.1002, 1.0990, 1.1002), id="hanging-man-gruen"),
    pytest.param(cs.shooting_star, C(1.1000, 1.1012, 1.1000, 1.1002), id="shooting-star-gruen"),
    pytest.param(cs.marubozu_green, C(1.1000, 1.1005, 1.1000, 1.1005), id="marubozu-koerper-zu-klein"),
    pytest.param(cs.marubozu_green, C(1.1000, 1.1012, 1.1000, 1.1009), id="marubozu-docht-zu-lang"),
    pytest.param(cs.marubozu_red, C(1.1000, 1.1009, 1.1000, 1.1009), id="marubozu-rot-gruene-kerze"),
    pytest.param(cs.doji, C(1.1000, 1.1010, 1.0990, 1.1005), id="doji-koerper-zu-gross"),
    pytest.param(cs.spinning_top, C(1.1000, 1.1002, 1.0990, 1.1002), id="spinning-top-ohne-oberen-docht"),
    pytest.param(cs.spinning_top, C(1.1000, 1.1005, 1.0995, 1.10005), id="spinning-top-doji-ausgeschlossen"),
]


@pytest.mark.parametrize("check, candle", POSITIVE)
def test_muster_positiv(check, candle):
    assert check(candle, ATR)


@pytest.mark.parametrize("check, candle", NEGATIVE)
def test_muster_negativ(check, candle):
    assert not check(candle, ATR)


@pytest.mark.parametrize("pattern", cs.PATTERNS, ids=lambda p: p.name)
def test_spanne_null_gibt_keinen_treffer(pattern):
    assert not pattern.check(C(1.1, 1.1, 1.1, 1.1), ATR)


def test_hammer_signal_felder():
    df = flat_df(C(1.1000, 1.1002, 1.0990, 1.1002))
    signals = cs.detect(df, make_config())

    assert [s.pattern for s in signals] == ["Hammer"]
    s = signals[0]
    assert s.source == "candles_single"
    assert s.direction == "BUY"
    assert s.entry == pytest.approx(1.1002)
    assert s.time == df.index[-1] + pd.Timedelta("15min")
    assert s.tags["required_trend"] == "down"
    assert s.tags["n_candles"] == 1
    assert s.tags["pattern_low"] == pytest.approx(1.0990)
    assert s.tags["pattern_high"] == pytest.approx(1.1002)


def test_doji_ist_neutral_ohne_trend():
    signals = cs.detect(flat_df(C(1.1000, 1.1010, 1.0990, 1.10005)), make_config())
    assert [s.pattern for s in signals] == ["Doji"]
    assert signals[0].direction == "NEUTRAL"
    assert signals[0].tags["required_trend"] is None


def test_marubozu_gruen_signal_felder():
    signals = cs.detect(flat_df(C(1.1000, 1.1009, 1.1000, 1.1009)), make_config())
    assert [s.pattern for s in signals] == ["Marubozu grün"]
    assert signals[0].direction == "BUY"
    assert signals[0].tags["required_trend"] == "up"


def test_atr_nan_liefert_keine_signale(monkeypatch):
    monkeypatch.setattr(cs, "calculate_atr", lambda df, period=None: pd.Series(np.nan, index=df.index))
    assert cs.detect(flat_df(C(1.1000, 1.1002, 1.0990, 1.1002)), make_config()) == []


def test_modus_off_liefert_nichts(only_single):
    df = flat_df(C(1.1000, 1.1002, 1.0990, 1.1002))
    cfg = make_config(DETECTORS={"candles_single": "off"})
    assert detectors.run_detectors(df, cfg) == []


def test_modus_log_only_liefert_signale_mit_betriebsart(only_single):
    df = flat_df(C(1.1000, 1.1002, 1.0990, 1.1002))
    cfg = make_config(DETECTORS={"candles_single": "log_only"})
    signals = detectors.run_detectors(df, cfg)
    assert [s.pattern for s in signals] == ["Hammer"]
    assert signals[0].mode == "log_only"
    assert signals[0].source == "candles_single"


def test_log_only_schreibt_csv_ohne_mail(only_single, monkeypatch, tmp_path):
    smtp = MagicMock()
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", smtp)
    df = build_df(hammer_after_downtrend(), "2026-05-05 14:00")
    cfg = make_config(DETECTORS={"candles_single": "log_only"}, NOTIFY_ENABLED=True)
    csv_path = tmp_path / "signals_log.csv"

    summary = pipeline.run_market(
        cfg, NOW, False, lambda symbol, interval, lookback: df.copy(),
        str(tmp_path / "state_new.json"), str(csv_path),
    )

    assert summary["signals"] == 1
    assert summary["mailed"] == 0
    assert not smtp.called
    rows = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig")
    assert len(rows) == 1
    assert rows.iloc[0]["pattern"] == "Hammer"
    assert rows.iloc[0]["mode"] == "log_only"


def test_marubozu_gruen_nach_abwaertstrend_wird_verworfen():
    candles = downtrend_candles()
    o = candles[-1].close
    df = build_df(candles + [C(o, o + 0.0009, o, o + 0.0009)], "2026-05-05 14:00")
    cfg = make_config()
    signals = [s for s in cs.detect(df, cfg) if s.pattern == "Marubozu grün"]
    assert len(signals) == 1
    assert trend.apply(signals, df, cfg) == []


def test_marubozu_gruen_nach_aufwaertstrend_bleibt():
    candles = uptrend_candles()
    o = candles[-1].close
    df = build_df(candles + [C(o, o + 0.0009, o, o + 0.0009)], "2026-05-05 14:00")
    cfg = make_config()
    signals = [s for s in cs.detect(df, cfg) if s.pattern == "Marubozu grün"]
    assert len(signals) == 1
    assert trend.apply(signals, df, cfg) == signals
