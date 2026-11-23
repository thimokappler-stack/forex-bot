"""
Tests für data.py

Fokus Schritt 1:
- remove_incomplete_candle: letzte Kerze wird entfernt wenn >= 2 Kerzen vorhanden
- Fehlbehandlung: zu wenige Kerzen, None-Input
"""

import pytest
import pandas as pd
from datetime import datetime
from buchbot.data import remove_incomplete_candle, calculate_atr, calculate_ema


class TestRemoveIncompleteCandle:
    """Tests für das Verwerfen der letzten (noch offenen) Kerze"""
    
    def test_remove_incomplete_candle_with_sufficient_candles(self):
        """Wenn >= 2 Kerzen vorhanden: letzte wird entfernt"""
        # Arrange: 3 Kerzen
        df = pd.DataFrame({
            "open": [1.0800, 1.0810, 1.0820],
            "high": [1.0810, 1.0820, 1.0830],
            "low": [1.0790, 1.0800, 1.0810],
            "close": [1.0805, 1.0815, 1.0825],
        }, index=pd.DatetimeIndex([
            datetime(2026, 1, 1, 12, 0),
            datetime(2026, 1, 1, 12, 15),
            datetime(2026, 1, 1, 12, 30),
        ]))
        
        # Act (jetzt 12:40: letzte Kerze 12:30 ist noch offen)
        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 40))
        
        # Assert: 2 Kerzen bleiben, letzte gelöscht
        assert len(result) == 2
        assert result.index[-1] == datetime(2026, 1, 1, 12, 15)
        assert result.iloc[-1]["close"] == 1.0815
    
    def test_remove_incomplete_candle_with_exactly_two_candles(self):
        """Mit genau 2 Kerzen: eine bleibt, eine wird entfernt"""
        df = pd.DataFrame({
            "open": [1.0800, 1.0810],
            "high": [1.0810, 1.0820],
            "low": [1.0790, 1.0800],
            "close": [1.0805, 1.0815],
        }, index=pd.DatetimeIndex([
            datetime(2026, 1, 1, 12, 0),
            datetime(2026, 1, 1, 12, 15),
        ]))
        
        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 20))
        
        assert len(result) == 1
        assert result.iloc[0]["close"] == 1.0805

    def test_closed_last_candle_is_kept(self):
        """Startzeit + 15 Min == jetzt: Kerze gilt als geschlossen und bleibt"""
        df = pd.DataFrame({
            "open": [1.0800, 1.0810],
            "high": [1.0810, 1.0820],
            "low": [1.0790, 1.0800],
            "close": [1.0805, 1.0815],
        }, index=pd.DatetimeIndex([
            datetime(2026, 1, 1, 12, 0),
            datetime(2026, 1, 1, 12, 15),
        ]))

        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 30))

        assert len(result) == 2
        assert result.index[-1] == datetime(2026, 1, 1, 12, 15)

    def test_open_last_candle_is_dropped_one_second_before_close(self):
        """Eine Sekunde vor Ende der Kerze: noch offen, wird verworfen"""
        df = pd.DataFrame({
            "open": [1.0800, 1.0810],
            "high": [1.0810, 1.0820],
            "low": [1.0790, 1.0800],
            "close": [1.0805, 1.0815],
        }, index=pd.DatetimeIndex([
            datetime(2026, 1, 1, 12, 0),
            datetime(2026, 1, 1, 12, 15),
        ]))

        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 29, 59))

        assert len(result) == 1
        assert result.index[-1] == datetime(2026, 1, 1, 12, 0)

    def test_now_is_interpreted_as_utc_when_tz_is_naive_and_index_is_aware(self):
        """Tz-aware Index wird mit naivem 'now' (UTC) korrekt verglichen"""
        df = pd.DataFrame({
            "open": [1.0800], "high": [1.0810], "low": [1.0790], "close": [1.0805],
        }, index=pd.DatetimeIndex([pd.Timestamp("2026-01-01 12:00", tz="UTC")]))

        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 14))

        assert len(result) == 0
    
    def test_remove_incomplete_candle_with_one_candle(self):
        """Mit 1 geschlossener Kerze: unverändert"""
        df = pd.DataFrame({
            "open": [1.0800],
            "high": [1.0810],
            "low": [1.0790],
            "close": [1.0805],
        }, index=pd.DatetimeIndex([datetime(2026, 1, 1, 12, 0)]))
        
        result = remove_incomplete_candle(df, now=datetime(2026, 1, 1, 12, 20))
        
        assert len(result) == 1
    
    def test_remove_incomplete_candle_with_empty_dataframe(self):
        """Mit leerem DataFrame: unverändert"""
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []})
        
        result = remove_incomplete_candle(df)
        
        assert len(result) == 0
    
    def test_remove_incomplete_candle_with_none(self):
        """Mit None-Input: None zurückgeben"""
        result = remove_incomplete_candle(None)
        
        assert result is None


class TestCalculateATR:
    """Tests für ATR-Berechnung"""
    
    def test_calculate_atr_basic(self):
        """ATR wird berechnet ohne Fehler"""
        df = pd.DataFrame({
            "open": [1.0800 + i*0.001 for i in range(20)],
            "high": [1.0810 + i*0.001 for i in range(20)],
            "low": [1.0790 + i*0.001 for i in range(20)],
            "close": [1.0805 + i*0.001 for i in range(20)],
        })
        
        atr = calculate_atr(df, period=14)
        
        # ATR sollte eine Series sein
        assert isinstance(atr, pd.Series)
        # Erste 13 sind NaN (nicht genug Daten für SMA)
        assert atr.iloc[:13].isna().all()
        # Ab 14 sollten Werte sein
        assert not atr.iloc[13:].isna().all()
        # ATR sollte positiv sein
        assert (atr.iloc[14:] > 0).all()
    
    def test_calculate_atr_insufficient_candles(self):
        """Mit zu wenigen Kerzen: warnen, None zurückgeben"""
        df = pd.DataFrame({
            "open": [1.0800, 1.0810],
            "high": [1.0810, 1.0820],
            "low": [1.0790, 1.0800],
            "close": [1.0805, 1.0815],
        })
        
        # ATR mit 2 Kerzen, aber period=14 → zu wenig
        atr = calculate_atr(df, period=14)
        
        assert atr is None
    
    def test_calculate_atr_with_none(self):
        """Mit None-DataFrame: None zurückgeben"""
        atr = calculate_atr(None, period=14)
        
        assert atr is None


class TestCalculateEMA:
    """Tests für EMA-Berechnung"""
    
    def test_calculate_ema_basic(self):
        """EMA wird berechnet ohne Fehler"""
        close = pd.Series([1.0800 + i*0.001 for i in range(60)])
        
        ema = calculate_ema(close, period=50)
        
        # EMA sollte eine Series sein
        assert isinstance(ema, pd.Series)
        # Länge sollte gleich sein
        assert len(ema) == len(close)
        # Erste Werte sind weniger zuverlässig (exponentielles Warmup)
        # Aber nicht NaN
        assert not ema.isna().any()
    
    def test_calculate_ema_insufficient_candles(self):
        """Mit zu wenigen Kerzen: warnen, None zurückgeben"""
        close = pd.Series([1.0800, 1.0810, 1.0820])
        
        ema = calculate_ema(close, period=50)
        
        assert ema is None
    
    def test_calculate_ema_with_none(self):
        """Mit None-Series: None zurückgeben"""
        ema = calculate_ema(None, period=50)
        
        assert ema is None


class TestGetCandles:
    """get_candles mit gemockter yfinance-Antwort (MultiIndex, Zeitzone)"""

    def _fake_download(self, index):
        cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close"], ["EURUSD=X"]])
        data = [[1.1, 1.2, 1.0, 1.15]] * len(index)
        return pd.DataFrame(data, index=index, columns=cols)

    def test_get_candles_flattens_columns_and_converts_to_utc(self, monkeypatch):
        import buchbot.data as data

        index = pd.date_range("2026-11-20 10:00", periods=5, freq="15min", tz="Europe/Berlin")
        calls = {}

        def fake(symbol, **kwargs):
            calls.update(kwargs)
            return self._fake_download(index)

        monkeypatch.setattr(data.yf, "download", fake)
        df = data.get_candles(lookback=3)

        assert calls["period"] == "5d"
        assert calls["interval"] == "15m"
        assert list(df.columns) == ["open", "high", "low", "close"]
        assert len(df) == 3
        assert str(df.index.tz) == "UTC"
        assert df.index[-1] == index[-1].tz_convert("UTC")

    def test_get_candles_naive_index_is_treated_as_utc(self, monkeypatch):
        import buchbot.data as data

        index = pd.date_range("2026-11-20 10:00", periods=3, freq="15min")
        monkeypatch.setattr(data.yf, "download", lambda symbol, **kw: self._fake_download(index))
        df = data.get_candles(lookback=3)

        assert str(df.index.tz) == "UTC"
        assert df.index[0] == pd.Timestamp("2026-11-20 10:00", tz="UTC")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
