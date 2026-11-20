"""
Datenbeschaffung: Kerzen von yfinance holen und bereinigen.
"""

import logging
import pandas as pd
import yfinance as yf
from config import SYMBOL, INTERVAL, LOOKBACK_CANDLES


logger = logging.getLogger(__name__)


def get_candles(symbol=SYMBOL, interval=INTERVAL, lookback=LOOKBACK_CANDLES):
    """
    Holt die letzten `lookback` geschlossenen 15m-Kerzen von yfinance.
    
    Args:
        symbol: yfinance Symbol (z.B. "EURUSD=X", "GBPUSD=X")
        interval: Kerzenlänge (z.B. "15m")
        lookback: Anzahl Kerzen zum Abholen
    
    Returns:
        pd.DataFrame mit Columns: open, high, low, close (Index: timestamp UTC)
        None bei Fehler (leere Antwort, Netzwerk etc.)
    
    Wichtig: 
    - Die zuletzt geholte Kerze könnte noch offen sein.
    - Wird später in main.py verworfen, wenn sie nicht geschlossen ist.
    """
    try:
        logger.info(f"Holen Kerzen: {symbol} {interval} lookback={lookback}")
        df = yf.download(
            symbol,
            interval=interval,
            period=None,  # Unlimited history
            progress=False,
            prepost=False,  # Kein Pre/Post-Market für Forex
        )
        
        if df.empty:
            logger.warning("Leere Antwort von yfinance")
            return None
        
        # Nur die Spalten, die wir brauchen
        df = df[["Open", "High", "Low", "Close"]].copy()
        df.columns = ["open", "high", "low", "close"]
        
        # Letzten N Kerzen
        df = df.tail(lookback)
        
        logger.info(f"Erhalten {len(df)} Kerzen. Erste: {df.index[0]}, Letzte: {df.index[-1]}")
        return df
    
    except Exception as e:
        logger.error(f"Fehler beim Datenabruf: {e}")
        return None


def remove_incomplete_candle(df):
    """
    Entfernt die letzte Kerze, wenn sie noch offen ist (sehr junge Kerze).
    
    Da wir nahe nach der Viertelstunde-Grenze ausführen, ist die letzte Kerze
    normalerweise gerade offen worden. Wir prüfen: Wenn der Close gleich dem Open
    ist UND der Index (Timestamp) sehr nah an jetzt liegt, ist sie wahrscheinlich
    noch offen. Sicherheitshalber verwerfen wir sie einfach immer.
    
    Args:
        df: DataFrame mit Kerzen
    
    Returns:
        DataFrame ohne die letzte Kerze (oder original, wenn < 2 Kerzen)
    """
    if len(df) > 1:
        logger.debug(f"Entferne letzte Kerze (Möglichkeit: noch offen)")
        return df.iloc[:-1]
    return df


def calculate_atr(df, period=None):
    """
    Berechnet Average True Range (ATR) zur Messung der Volatilität.
    
    Args:
        df: DataFrame mit high, low, close
        period: ATR-Periode (Standard: 14, oder aus config)
    
    Returns:
        Series mit ATR-Werten
    """
    if period is None:
        from config import ATR_PERIOD
        period = ATR_PERIOD
    
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = SMA(TR)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_ema(close, period):
    """
    Berechnet Exponential Moving Average für Trendfilter.
    
    Args:
        close: Series mit Schlusskursen
        period: EMA-Periode
    
    Returns:
        Series mit EMA-Werten
    """
    return close.ewm(span=period, adjust=False).mean()
