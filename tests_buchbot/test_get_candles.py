import numpy as np
import pandas as pd

from buchbot import data


def fake_download_factory(values):
    def fake_download(*args, **kwargs):
        idx = pd.date_range("2026-05-06 00:00", periods=len(values), freq="15min", tz="UTC")
        return pd.DataFrame(
            {"Open": values, "High": values, "Low": values, "Close": values},
            index=idx,
        ).astype(np.float32)
    return fake_download


def test_get_candles_passes_period_to_yf_download(monkeypatch):
    calls = []

    def recording_download(*args, **kwargs):
        calls.append(kwargs)
        return fake_download_factory([1.1, 1.1001])(*args, **kwargs)

    monkeypatch.setattr(data.yf, "download", recording_download)

    df = data.get_candles("EURUSD=X", "15m", lookback=None, period="60d")

    assert calls[0]["period"] == "60d"
    assert len(df) == 2

    noisy = [1.0984183549880981, 1.1000049999999]
    monkeypatch.setattr(data.yf, "download", fake_download_factory(noisy))

    df = data.get_candles("EURUSD=X", "15m", 10)

    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df["close"].iloc[0] == round(float(np.float32(noisy[0])), 6)
    assert df["close"].iloc[1] == round(float(np.float32(noisy[1])), 6)
    for column in ["open", "high", "low", "close"]:
        assert df[column].round(6).equals(df[column])
