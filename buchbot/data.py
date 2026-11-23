"""
Datenbeschaffung: Kerzen von yfinance holen und bereinigen.

Funktionen:
- get_candles: Holt Kerzen von yfinance
- remove_incomplete_candle: Entfernt letzte Kerze, falls Startzeit + Intervall > jetzt (UTC)
- calculate_atr: Average True Range für Volatilitätsmessung
- calculate_ema: Exponential Moving Average für Trendfilter
"""

import logging
import pandas as pd
import yfinance as yf
from buchbot.config import MARKETS, DEFAULT_MARKET, INTERVAL, LOOKBACK_CANDLES, ATR_PERIOD, TREND_EMA_PERIOD


logger = logging.getLogger(__name__)


def get_candles(symbol=None, interval=INTERVAL, lookback=LOOKBACK_CANDLES, period="5d"):
    """
    Holt Kerzen von yfinance. `interval` ist die Kerzenlänge je Markt (z.B. "15m", "30m"),
    `lookback` die Anzahl der letzten Kerzen (None = alle).
    
    Args:
        symbol: yfinance Symbol (z.B. "EURUSD=X"). None = Symbol des Standardmarktes.
        interval: Kerzenlänge (z.B. "15m", "30m")
        lookback: Anzahl Kerzen zum Abholen
    
    Returns:
        pd.DataFrame mit Columns: open, high, low, close (Index: timestamp UTC)
        None bei Fehler (leere Antwort, Netzwerk etc.)
    
    Wichtig: 
    - Die zuletzt geholte Kerze könnte noch offen sein.
    - Wird später in main.py verworfen via remove_incomplete_candle()
    """
    symbol = symbol or MARKETS[DEFAULT_MARKET]["symbol"]
    try:
        logger.info(f"Hole Kerzen: {symbol} {interval} lookback={lookback}")
        df = yf.download(
            symbol,
            interval=interval,
            period=period,
            progress=False,
            prepost=False,  # Kein Pre/Post-Market für Forex
        )
        
        if df.empty:
            logger.warning("Leere Antwort von yfinance")
            return None
        
        # yfinance liefert bei einem Symbol MultiIndex-Spalten (Price, Ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df[["Open", "High", "Low", "Close"]].copy()
        df.columns = ["open", "high", "low", "close"]
        # yfinance liefert float32-Rauschen, Preise auf 6 Nachkommastellen runden
        df = df.astype(float).round(6)

        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        
        # Letzten N Kerzen
        if lookback is not None:
            df = df.tail(lookback)
        
        logger.info(f"Erhalten {len(df)} Kerzen. Erste: {df.index[0]}, Letzte: {df.index[-1]}")
        return df
    
    except Exception as e:
        logger.error(f"Fehler beim Datenabruf: {e}")
        return None


def remove_incomplete_candle(df, interval=INTERVAL, now=None):
    """
    Entfernt die letzte Kerze, wenn sie noch nicht geschlossen ist.
    
    Eine Kerze gilt als geschlossen, wenn Startzeit + Intervall <= aktuelle UTC-Zeit.
    
    Args:
        df: DataFrame mit Kerzen (Columns: open, high, low, close, Index: Startzeit)
        interval: Kerzenlänge (z.B. "15m")
        now: Aktuelle Zeit (Standard: jetzt in UTC). Naive Zeiten gelten als UTC.
    
    Returns:
        DataFrame mit geschlossenen Kerzen (letzte Kerze ggf. entfernt)
    """
    if df is None or len(df) == 0:
        logger.warning("Keine Kerzen vorhanden")
        return df

    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    last_start = pd.Timestamp(df.index[-1])
    if last_start.tzinfo is None:
        last_start = last_start.tz_localize("UTC")

    if last_start + pd.Timedelta(interval) <= now:
        return df

    logger.debug("Entferne letzte Kerze (noch nicht geschlossen)")
    return df.iloc[:-1]


def calculate_atr(df, period=None):
    """
    Berechnet Average True Range (ATR) zur Messung der Volatilität.
    
    Args:
        df: DataFrame mit high, low, close
        period: ATR-Periode (Standard: aus config.ATR_PERIOD)
    
    Returns:
        Series mit ATR-Werten
    """
    if period is None:
        period = ATR_PERIOD
    
    if df is None or len(df) < period:
        logger.warning(f"Zu wenige Kerzen für ATR-Berechnung ({len(df) if df is not None else 0} < {period})")
        return None
    
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # True Range: Maximum von (high-low, |high-close_prev|, |low-close_prev|)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = SMA(TR)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_ema(close, period=None):
    """
    Berechnet Exponential Moving Average für Trendfilter.
    
    Args:
        close: Series mit Schlusskursen
        period: EMA-Periode (Standard: aus config.TREND_EMA_PERIOD)
    
    Returns:
        Series mit EMA-Werten
    """
    if period is None:
        period = TREND_EMA_PERIOD
    
    if close is None or len(close) < period:
        logger.warning(f"Zu wenige Kerzen für EMA-Berechnung ({len(close) if close is not None else 0} < {period})")
        return None
    
    return close.ewm(span=period, adjust=False).mean()
