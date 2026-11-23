"""
Tests für buchbot/models.py (Signal), buchbot/detectors/__init__.py (Registry)
und den Signal-Einstieg buchbot/detectors/candles_main.detect.
"""

import math
from types import SimpleNamespace

import pandas as pd
import pytest

import buchbot.config as real_config
import buchbot.detectors as detectors
import buchbot.detectors.candles_main as candles_main
from buchbot.detectors.candles_main import Candle
from buchbot.models import Signal

ATR = 0.0010
ENG_POS = [Candle(1.1010, 1.1015, 1.0990, 1.0995), Candle(1.0990, 1.1030, 1.0985, 1.1025)]
FILLER = [Candle(1.1000, 1.1005, 1.0995, 1.1000)] * 19


def make_df(candles, start="2026-01-01 00:00"):
    index = pd.date_range(start, periods=len(candles), freq="15min", tz="UTC")
    return pd.DataFrame([c._asdict() for c in candles], index=index)


def make_signal(**overrides):
    values = dict(
        time=pd.Timestamp("2026-01-01 12:00", tz="UTC"),
        symbol="EURUSD=X",
        interval="15m",
        source="dummy",
        pattern="Dummy",
        direction="BUY",
        entry=1.1,
        atr=0.001,
    )
    values.update(overrides)
    return Signal(**values)


class TestSignalModel:
    def test_optional_fields_default_to_none_and_tags_to_dict(self):
        s = make_signal()
        assert s.sl is None
        assert s.tp is None
        assert s.risk_pips is None
        assert s.rr is None
        assert s.tags == {}

    def test_mode_defaults_to_log_only(self):
        assert make_signal().mode == "log_only"

    def test_tags_are_not_shared_between_instances(self):
        a = make_signal()
        b = make_signal()
        a.tags["x"] = 1
        assert b.tags == {}


class TestCandlesMainDetect:
    def test_returns_signal_with_expected_fields(self):
        df = make_df(FILLER + ENG_POS)
        cfg = SimpleNamespace(SYMBOL="EURUSD=X", INTERVAL="15m", ATR_PERIOD=14)

        signals = candles_main.detect(df, cfg)

        hit = next(s for s in signals if s.pattern == "Bullish Engulfing")
        assert isinstance(hit, Signal)
        assert hit.source == "candles_main"
        assert hit.direction == "BUY"
        assert hit.symbol == "EURUSD=X"
        assert hit.interval == "15m"
        assert hit.entry == pytest.approx(ENG_POS[-1].close)
        assert hit.atr > 0
        assert not math.isnan(hit.atr)
        assert hit.time == df.index[-1] + pd.Timedelta("15min")
        assert hit.tags == {"required_trend": "down"}
        assert hit.sl is None and hit.tp is None

    def test_signal_time_is_candle_close_time(self):
        df = make_df(FILLER + ENG_POS, start="2026-01-01 12:15")
        cfg = SimpleNamespace(SYMBOL="EURUSD=X", INTERVAL="15m", ATR_PERIOD=14)

        hit = next(s for s in candles_main.detect(df, cfg) if s.pattern == "Bullish Engulfing")

        assert df.index[-1] == pd.Timestamp("2026-01-01 17:15", tz="UTC")
        assert hit.time == pd.Timestamp("2026-01-01 17:30", tz="UTC")

    def test_no_signals_without_pattern(self):
        df = make_df(FILLER + [Candle(1.1000, 1.1005, 1.0995, 1.1000)] * 2)
        cfg = SimpleNamespace(SYMBOL="EURUSD=X", INTERVAL="15m", ATR_PERIOD=14)

        assert candles_main.detect(df, cfg) == []

    def test_too_few_candles_gives_no_signals(self):
        df = make_df(ENG_POS)
        cfg = SimpleNamespace(SYMBOL="EURUSD=X", INTERVAL="15m", ATR_PERIOD=14)

        assert candles_main.detect(df, cfg) == []

    def test_atr_nan_gives_no_signals(self, monkeypatch):
        df = make_df(FILLER + ENG_POS)
        cfg = SimpleNamespace(SYMBOL="EURUSD=X", INTERVAL="15m", ATR_PERIOD=14)
        nan_atr = pd.Series([float("nan")] * len(df), index=df.index)
        monkeypatch.setattr(candles_main, "calculate_atr", lambda df, period=None: nan_atr)

        assert candles_main.detect(df, cfg) == []


class TestRegistry:
    def _dummy(self, signals):
        calls = []

        def detect(df, config):
            calls.append(config)
            return [make_signal(source="dummy", pattern=f"Dummy {i}") for i in range(signals)]

        return detect, calls

    def test_duplicate_registration_is_rejected(self, monkeypatch):
        monkeypatch.setattr(detectors, "_REGISTRY", {})
        detectors.register("dummy", lambda df, config: [], "dummy")

        with pytest.raises(ValueError):
            detectors.register("dummy", lambda df, config: [], "dummy")

    def test_mode_off_returns_nothing_and_does_not_run_detector(self, monkeypatch):
        detect, calls = self._dummy(2)
        monkeypatch.setattr(detectors, "_REGISTRY", {"dummy": (detect, "dummy")})
        cfg = SimpleNamespace(DETECTORS={"dummy": "off"})

        assert detectors.run_detectors(pd.DataFrame(), cfg) == []
        assert calls == []

    def test_missing_entry_counts_as_off(self, monkeypatch):
        detect, calls = self._dummy(1)
        monkeypatch.setattr(detectors, "_REGISTRY", {"dummy": (detect, "dummy")})
        cfg = SimpleNamespace(DETECTORS={})

        assert detectors.run_detectors(pd.DataFrame(), cfg) == []
        assert calls == []

    def test_mode_log_only_returns_signals_with_mode_field(self, monkeypatch):
        detect, calls = self._dummy(2)
        monkeypatch.setattr(detectors, "_REGISTRY", {"dummy": (detect, "dummy")})
        cfg = SimpleNamespace(DETECTORS={"dummy": "log_only"})

        signals = detectors.run_detectors(pd.DataFrame(), cfg)

        assert len(signals) == 2
        assert all(s.mode == "log_only" for s in signals)
        assert all("mode" not in s.tags for s in signals)
        assert calls == [cfg]

    def test_mode_notify_is_passed_to_signal(self, monkeypatch):
        detect, _ = self._dummy(1)
        monkeypatch.setattr(detectors, "_REGISTRY", {"dummy": (detect, "dummy")})
        cfg = SimpleNamespace(DETECTORS={"dummy": "notify"})

        signals = detectors.run_detectors(pd.DataFrame(), cfg)

        assert [s.mode for s in signals] == ["notify"]

    def test_unknown_mode_raises(self, monkeypatch):
        detect, _ = self._dummy(1)
        monkeypatch.setattr(detectors, "_REGISTRY", {"dummy": (detect, "dummy")})
        cfg = SimpleNamespace(DETECTORS={"dummy": "sometimes"})

        with pytest.raises(ValueError):
            detectors.run_detectors(pd.DataFrame(), cfg)

    def test_real_config_runs_candles_main_in_log_only(self):
        df = make_df(FILLER + ENG_POS)

        signals = detectors.run_detectors(df, real_config)

        assert any(s.pattern == "Bullish Engulfing" for s in signals)
        assert all(s.source == "candles_main" for s in signals)
        assert all(s.mode == "log_only" for s in signals)

    def test_dummy_detectors_do_not_leak_into_real_registry(self):
        assert set(detectors._REGISTRY) == {"candles_main"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
