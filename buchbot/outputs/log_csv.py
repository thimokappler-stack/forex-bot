"""
Log und signals_log.csv.

CSV: Semikolon als Trennzeichen, utf-8-sig, Kopfzeile nur beim Anlegen der Datei.
"""

import csv
import logging
import os
from datetime import datetime

import pandas as pd

from buchbot.config import DEFAULT_MARKET, for_market
from buchbot.models import format_price, to_utc
from buchbot.zones import SR_COLUMNS


logger = logging.getLogger(__name__)

CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"
BASE_COLUMNS = [
    "market", "time", "symbol", "interval", "source", "pattern", "direction",
    "entry", "atr", "sl", "tp", "risk_pips", "risk_unit", "rr", "mode",
]
TAG_COLUMNS = ["required_trend", "n_candles", "pattern_low", "pattern_high"]
PRICE_COLUMNS = ["entry", "atr", "sl", "tp"]
PRICE_TAG_COLUMNS = ["pattern_low", "pattern_high"]
OHLC_COLUMNS = ["open", "high", "low", "close"]
COLUMNS = BASE_COLUMNS + TAG_COLUMNS + OHLC_COLUMNS + SR_COLUMNS
SIGNAL_ATTRIBUTE_COLUMNS = [c for c in BASE_COLUMNS if c not in ("risk_unit", "risk_pips")]


def _default_config(config):
    return config if config is not None else for_market(DEFAULT_MARKET)


def sr_fields(tags, decimals):
    """Die SR-Spalten eines Signals. Fehlen die Tags (SR aus), bleiben die Felder leer."""
    room = tags.get("sr_room_atr")
    return {
        "sr_relation": tags.get("sr_relation"),
        "sr_zone_low": format_price(tags.get("sr_zone_low"), decimals),
        "sr_zone_high": format_price(tags.get("sr_zone_high"), decimals),
        "sr_touches": tags.get("sr_touches"),
        "sr_aligned": tags.get("sr_aligned"),
        "sr_against": tags.get("sr_against"),
        "sr_room_atr": None if room is None else f"{room:.2f}",
        "swing_trend": tags.get("swing_trend"),
    }


def signal_row(signal, df, interval, config=None):
    """Eine CSV-Zeile: Signal-Felder, Tags, OHLC der Signalkerze und SR-Zusatzinfo. Preise im Format des Marktes."""
    config = _default_config(config)
    decimals = config.PRICE_DECIMALS
    candle_start = to_utc(signal.time) - pd.Timedelta(interval)
    candle = df.loc[candle_start]
    row = {column: getattr(signal, column) for column in SIGNAL_ATTRIBUTE_COLUMNS}
    row["market"] = signal.market or config.MARKET
    row["time"] = to_utc(signal.time).isoformat()
    row["risk_pips"] = None if signal.risk_pips is None else round(signal.risk_pips, 1)
    row["risk_unit"] = config.RISK_UNIT
    for column in TAG_COLUMNS:
        row[column] = signal.tags.get(column)
    for column in OHLC_COLUMNS:
        row[column] = candle[column]
    for column in PRICE_COLUMNS + PRICE_TAG_COLUMNS + OHLC_COLUMNS:
        row[column] = format_price(row[column], decimals)
    row.update(sr_fields(signal.tags, decimals))
    return row


def _read_header(path):
    with open(path, encoding=CSV_ENCODING, newline="") as f:
        return next(csv.reader(f, delimiter=CSV_DELIMITER), None)


def _migrate_header(path):
    """Alte Kopfzeile ist ein Präfix der neuen: Datei mit neuer Kopfzeile neu schreiben, Zeilen bleiben erhalten.

    Die Datei wird über eine temporäre Datei ersetzt, damit sie bei einem Abbruch nicht halb geschrieben ist.
    """
    with open(path, encoding=CSV_ENCODING, newline="") as f:
        rows = list(csv.DictReader(f, delimiter=CSV_DELIMITER))
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=CSV_DELIMITER, restval="")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, path)
    logger.info("CSV-Kopfzeile in %s um neue Spalten erweitert (%d Zeile(n) erhalten)", path, len(rows))


def _archive(path):
    base, ext = os.path.splitext(path)
    target = f"{base}_alt_{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}"
    os.replace(path, target)
    logger.warning("Kopfzeile von %s passt nicht zur aktuellen Version: alte Datei umbenannt nach %s",
                   path, target)


def append_signals(signals, df, interval, path, config=None):
    """Hängt die Signale an die CSV-Datei an. Kopfzeile nur, wenn die Datei neu ist.

    Ist die alte Kopfzeile ein Präfix der aktuellen, wird die Datei in place erweitert.
    Hat sie eine andere Kopfzeile, wird sie umbenannt und neu angelegt.
    """
    if not signals:
        return
    config = _default_config(config)
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    if exists:
        header = _read_header(path)
        if header == COLUMNS:
            pass
        elif header == COLUMNS[:len(header)]:
            _migrate_header(path)
        else:
            _archive(path)
            exists = False
    write_header = not exists
    rows = [signal_row(signal, df, interval, config) for signal in signals]
    with open(path, "a", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=CSV_DELIMITER)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    logger.info("CSV geschrieben: %d Zeile(n) in %s", len(rows), path)


def log_signals(signals, config=None):
    config = _default_config(config)
    for signal in signals:
        decimals = config.PRICE_DECIMALS
        logger.info(
            "Signal %s %s %s %s (Kerze %s) Einstieg=%s SL=%s TP=%s Modus=%s",
            signal.market or config.MARKET, signal.direction, signal.pattern, signal.symbol,
            to_utc(signal.time).isoformat(), format_price(signal.entry, decimals),
            format_price(signal.sl, decimals), format_price(signal.tp, decimals), signal.mode,
        )
