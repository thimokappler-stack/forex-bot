"""
Backtest: Prüft Muster auf historischen Daten und simuliert Trades.
"""

import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from config import (
    SYMBOL, INTERVAL, MAX_HOLD_CANDLES, SPREAD_PIPS, PIP_SIZE, RISK_REWARD
)
from data import calculate_atr
from patterns import detect_patterns, PATTERNS
from signals import evaluate_pattern


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backtest_signal(candles, atrs, signal, start_idx):
    """
    Simuliert einen Trade nach einem Signal.
    
    Args:
        candles: DataFrame mit OHLC
        atrs: Series mit ATR
        signal: Dict mit entry, sl, tp, signal-type (BUY/SELL)
        start_idx: Index ab dem die Simulation läuft (nächste Kerze nach Signal)
    
    Returns:
        Dict mit "result" (TP/SL/TIMEOUT), "pips" (Ergebnis in Pips)
    """
    entry = signal["entry"]
    sl = signal["sl"]
    tp = signal["tp"]
    signal_type = signal["signal"]
    
    # Spread abziehen (Entry wird schlechter)
    if signal_type == "BUY":
        entry_actual = entry + SPREAD_PIPS * PIP_SIZE
    else:  # SELL
        entry_actual = entry - SPREAD_PIPS * PIP_SIZE
    
    # Simuliere MAX_HOLD_CANDLES Kerzen
    end_idx = min(start_idx + MAX_HOLD_CANDLES, len(candles))
    
    for i in range(start_idx, end_idx):
        candle = candles.iloc[i]
        
        if signal_type == "BUY":
            # Prüfe SL (wird erreicht wenn low <= sl)
            if candle["low"] <= sl:
                pips = (sl - entry_actual) / PIP_SIZE
                return {"result": "SL", "pips": round(pips, 2)}
            
            # Prüfe TP (wird erreicht wenn high >= tp)
            if candle["high"] >= tp:
                pips = (tp - entry_actual) / PIP_SIZE
                return {"result": "TP", "pips": round(pips, 2)}
        
        else:  # SELL
            # Prüfe SL (wird erreicht wenn high >= sl)
            if candle["high"] >= sl:
                pips = (entry_actual - sl) / PIP_SIZE
                return {"result": "SL", "pips": round(pips, 2)}
            
            # Prüfe TP (wird erreicht wenn low <= tp)
            if candle["low"] <= tp:
                pips = (entry_actual - tp) / PIP_SIZE
                return {"result": "TP", "pips": round(pips, 2)}
    
    # Timeout: Schließe zum Close der letzten Kerze
    close = candles["close"].iloc[end_idx - 1]
    if signal_type == "BUY":
        pips = (close - entry_actual) / PIP_SIZE
    else:  # SELL
        pips = (entry_actual - close) / PIP_SIZE
    
    return {"result": "TIMEOUT", "pips": round(pips, 2)}


def run_backtest():
    """
    Führt Backtest auf maximal verfügbaren historischen Daten durch.
    """
    logger.info(f"Lade historische Daten für {SYMBOL} {INTERVAL}...")
    
    # Holt maximal verfügbare 15m-Historie (etwa 60 Tage bei yfinance)
    df = yf.download(
        SYMBOL,
        interval=INTERVAL,
        progress=False,
        prepost=False,
    )
    
    if df.empty:
        logger.error("Keine Daten verfügbar")
        return
    
    # Vorbereiten
    df = df[["Open", "High", "Low", "Close"]].copy()
    df.columns = ["open", "high", "low", "close"]
    
    logger.info(f"Daten geladen: {len(df)} Kerzen ({df.index[0]} bis {df.index[-1]})")
    
    # ATR
    atrs = calculate_atr(df)
    
    # Backtest-Ergebnisse sammeln
    results = {}
    for pattern_name in PATTERNS.keys():
        results[pattern_name] = {
            "total": 0,
            "tp": 0,
            "sl": 0,
            "timeout": 0,
            "pips_all": [],
        }
    
    # Kerze für Kerze durchgehen
    for idx in range(50, len(df)):
        candles_so_far = df.iloc[:idx + 1]
        atrs_so_far = atrs.iloc[:idx + 1]
        
        # Erkenne Muster
        detected = detect_patterns(candles_so_far, atrs_so_far)
        
        for pattern_info in detected:
            pattern_name = pattern_info["pattern"]
            signal_type = pattern_info["signal"]
            pattern_idx = pattern_info["idx"]
            
            # Evaluiere
            signal = evaluate_pattern(candles_so_far, atrs_so_far, pattern_name, signal_type, pattern_idx)
            
            if signal is None:
                continue
            
            # Simuliere
            trade_result = backtest_signal(df, atrs, signal, idx + 1)
            
            results[pattern_name]["total"] += 1
            results[pattern_name][trade_result["result"].lower()] += 1
            results[pattern_name]["pips_all"].append(trade_result["pips"])
    
    # Ausgabe
    logger.info("\n" + "=" * 100)
    logger.info("BACKTEST-ERGEBNISSE")
    logger.info("=" * 100)
    
    # Tabelle
    print(f"\n{'Muster':<25} {'Signale':>8} {'TP':>6} {'SL':>6} {'Timeout':>8} {'Avg Pips':>10} {'R':>8}")
    print("-" * 100)
    
    total_signals = 0
    total_pips = 0
    
    for pattern_name, stats in results.items():
        total = stats["total"]
        if total == 0:
            print(f"{pattern_name:<25} {'0':>8} {'-':>6} {'-':>6} {'-':>8} {'-':>10} {'-':>8}")
            continue
        
        total_signals += total
        pips_avg = sum(stats["pips_all"]) / total if stats["pips_all"] else 0
        total_pips += sum(stats["pips_all"])
        
        # R berechnen (TP=+RISK_REWARD, SL=-1)
        r_sum = (stats["tp"] * RISK_REWARD) - (stats["sl"] * 1) + (stats["timeout"] * (pips_avg / 100))
        r_avg = r_sum / total if total > 0 else 0
        
        tp_pct = (stats["tp"] / total * 100) if total > 0 else 0
        sl_pct = (stats["sl"] / total * 100) if total > 0 else 0
        timeout_pct = (stats["timeout"] / total * 100) if total > 0 else 0
        
        print(f"{pattern_name:<25} {total:>8} {tp_pct:>5.0f}% {sl_pct:>5.0f}% {timeout_pct:>7.0f}% {pips_avg:>10.1f} {r_avg:>8.2f}")
    
    print("-" * 100)
    if total_signals > 0:
        avg_pips = total_pips / total_signals
        print(f"{'GESAMT':<25} {total_signals:>8} {'-':>6} {'-':>6} {'-':>8} {avg_pips:>10.1f}")
    
    logger.info("=" * 100 + "\n")


if __name__ == "__main__":
    run_backtest()
