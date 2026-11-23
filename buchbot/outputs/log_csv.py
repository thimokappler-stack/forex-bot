"""
Log und signals_log.csv.

CSV: Semikolon als Trennzeichen, utf-8-sig, Kopfzeile nur beim Anlegen der Datei.
"""

import csv
import logging
import os

import pandas as pd

from buchbot.models import format_price, to_utc


logger = logging.getLogger(__name__)

CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"
BASE_COLUMNS = [
    "time", "symbol", "interval", "source", "pattern", "direction",
    "entry", "atr", "sl", "tp", "risk_pips", "rr", "mode",
]
TAG_COLUMNS = ["required_trend", "n_candles", "pattern_low", "pattern_high"]
PRICE_COLUMNS = ["entry", "atr", "sl", "tp"]
PRICE_TAG_COLUMNS = ["pattern_low", "pattern_high"]
OHLC_COLUMNS = ["open", "high", "low", "close"]
COLUMNS = BASE_COLUMNS + TAG_COLUMNS + OHLC_COLUMNS


def signal_row(signal, df, interval):
    """Eine CSV-Zeile: Signal-Felder, Tags und OHLC der Signalkerze. Preise mit 5 Nachkommastellen."""
    candle_start = to_utc(signal.time) - pd.Timedelta(interval)
    candle = df.loc[candle_start]
    row = {column: getattr(signal, column) for column in BASE_COLUMNS}
    row["time"] = to_utc(signal.time).isoformat()
    row["risk_pips"] = None if signal.risk_pips is None else round(signal.risk_pips, 1)
    for column in TAG_COLUMNS:
        row[column] = signal.tags.get(column)
    for column in OHLC_COLUMNS:
        row[column] = candle[column]
    for column in PRICE_COLUMNS + PRICE_TAG_COLUMNS + OHLC_COLUMNS:
        row[column] = format_price(row[column])
    return row


def append_signals(signals, df, interval, path):
    """Hängt die Signale an die CSV-Datei an. Kopfzeile nur, wenn die Datei neu ist."""
    if not signals:
        return
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    rows = [signal_row(signal, df, interval) for signal in signals]
    with open(path, "a", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=CSV_DELIMITER)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    logger.info("CSV geschrieben: %d Zeile(n) in %s", len(rows), path)


def log_signals(signals):
    for signal in signals:
        logger.info(
            "Signal %s %s %s (Kerze %s) Einstieg=%s SL=%s TP=%s Modus=%s",
            signal.direction, signal.pattern, signal.symbol,
            to_utc(signal.time).isoformat(), format_price(signal.entry),
            format_price(signal.sl), format_price(signal.tp), signal.mode,
        )
