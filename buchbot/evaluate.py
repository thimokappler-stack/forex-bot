"""
Auswertung der Schattenbetrieb-Signale aus signals_log.csv.

Aufruf: python -m buchbot.evaluate [--csv Pfad] [--out ergebnis.csv]

Jedes Signal wird mit derselben Simulation wie im Backtest (backtest.simulate) ausgewertet:
Einstieg ist der Schluss der Signalkerze, simuliert wird ab der Folgekerze. SL und TP kommen aus der CSV.
Reicht die Historie für das Haltefenster nicht oder fehlt die Signalkerze, gilt das Signal als offen
und geht nicht in die Statistik ein.
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

import pandas as pd

from buchbot import config as default_config
from buchbot.backtest import (
    MAIN_PATTERN_NAMES,
    OUTCOME_NOT_EVALUATED,
    OUTCOME_OPEN,
    SINGLE_PATTERN_NAMES,
    TRADED_DIRECTIONS,
    _trade,
    open_count,
    render_table,
    simulate,
    summarize,
    write_csv,
)
from buchbot.data import get_candles, remove_incomplete_candle
from buchbot.models import Signal, to_utc
from buchbot.outputs.log_csv import CSV_DELIMITER, CSV_ENCODING
from buchbot.pipeline import BASE_DIR


logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["time", "source", "pattern", "direction", "entry", "sl", "tp"]
GROUPS = [
    ("Haupt-Muster", "candles_main", MAIN_PATTERN_NAMES),
    ("Einzelkerzen (Hintergrund, NEUTRAL nur gezählt, nicht bewertet)", "candles_single", SINGLE_PATTERN_NAMES),
]


def read_signal_rows(path):
    """Liest die Signal-CSV. Leere Datei ergibt keine Zeilen, fehlende Pflichtspalten einen ValueError."""
    with open(path, newline="", encoding=CSV_ENCODING) as handle:
        reader = csv.DictReader(handle, delimiter=CSV_DELIMITER)
        if reader.fieldnames is None:
            return []
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"Pflichtspalten fehlen: {', '.join(missing)}")
        return list(reader)


def _optional_float(value):
    return None if value in (None, "") else float(value)


def signal_from_row(row, config):
    """Baut aus einer CSV-Zeile ein Signal. Liefert None für Zeilen, die nicht auswertbar sind."""
    direction = row["direction"]
    entry = _optional_float(row["entry"])
    sl = _optional_float(row["sl"])
    tp = _optional_float(row["tp"])
    if entry is None:
        logger.warning("Signal ohne Einstieg übersprungen: %s %s", row["pattern"], row["time"])
        return None

    risk_pips = None
    if direction in TRADED_DIRECTIONS:
        if sl is None or tp is None:
            logger.warning("Signal ohne SL/TP übersprungen: %s %s", row["pattern"], row["time"])
            return None
        risk_pips = abs(entry - sl) / config.PIP_SIZE
        if risk_pips <= 0:
            logger.warning("Signal mit Risiko 0 übersprungen: %s %s", row["pattern"], row["time"])
            return None
    elif direction != "NEUTRAL":
        logger.warning("Unbekannte Richtung übersprungen: %r (%s)", direction, row["pattern"])
        return None

    return Signal(
        time=to_utc(row["time"]),
        symbol=row.get("symbol") or config.SYMBOL,
        interval=row.get("interval") or config.INTERVAL,
        source=row["source"],
        pattern=row["pattern"],
        direction=direction,
        entry=entry,
        atr=_optional_float(row.get("atr")),
        sl=sl,
        tp=tp,
        risk_pips=risk_pips,
        rr=_optional_float(row.get("rr")),
        mode=row.get("mode") or "",
    )


def evaluate_rows(rows, df, config):
    """Simuliert jedes Signal ab der Kerze nach seiner Signalkerze. Liefert Trades im Format des Backtests."""
    trades = []
    for row in rows:
        signal = signal_from_row(row, config)
        if signal is None:
            continue
        signal_candle = signal.time - pd.Timedelta(config.INTERVAL)
        if signal_candle in df.index:
            trade = simulate(signal, df, df.index.get_loc(signal_candle), config)
        else:
            logger.warning("Signalkerze fehlt in den Kerzen, nicht ausgewertet: %s %s",
                           signal.pattern, signal.time.isoformat())
            outcome = OUTCOME_NOT_EVALUATED if signal.direction not in TRADED_DIRECTIONS else OUTCOME_OPEN
            trade = _trade(signal, df, None, None, None, outcome, config)
        trade["source"] = signal.source
        trades.append(trade)
    return trades


def main(config=default_config, fetch=get_candles, csv_path=None, out_path=None):
    path = Path(csv_path) if csv_path else BASE_DIR / config.SIGNALS_CSV_FILE
    if not path.exists():
        print(f"Signaldatei nicht gefunden: {path}")
        return 1
    try:
        rows = read_signal_rows(path)
    except ValueError as error:
        print(f"Fehler in {path}: {error}")
        return 1
    if not rows:
        print(f"Keine Signale in {path}")
        return 0

    df = fetch(config.SYMBOL, config.INTERVAL, lookback=None, period=config.BACKTEST_PERIOD)
    if df is None or len(df) == 0:
        print("Keine Kerzen erhalten, Auswertung abgebrochen.")
        return 1
    df = remove_incomplete_candle(df, config.INTERVAL)

    trades = evaluate_rows(rows, df, config)
    if not trades:
        print(f"Keine auswertbaren Signale in {path}")
        return 0

    times = [t["signal_time"] for t in trades]
    print(f"Signale in {path}: {len(rows)}, ausgewertet: {len(trades)}")
    print(f"Zeitraum der CSV: {min(times).isoformat()} bis {max(times).isoformat()} (UTC)")
    print(f"Kerzen für die Simulation: {df.index[0].isoformat()} bis {df.index[-1].isoformat()} (UTC)")
    print()
    for title, source, names in GROUPS:
        group = [t for t in trades if t["source"] == source]
        rows_by_pattern, total = summarize(group, names)
        print(render_table(rows_by_pattern, total, config, title))
        print()
    print(f"offen: {open_count(trades)} (Haltefenster oder Signalkerze außerhalb der Kerzen, nicht in der Statistik)")

    if out_path:
        write_csv(trades, out_path)
        print(f"Einzelergebnisse: {out_path}")
    return 0


def cli(argv=None):
    parser = argparse.ArgumentParser(description="Auswertung der Schattenbetrieb-Signale aus signals_log.csv")
    parser.add_argument("--csv", help="Pfad zur Signaldatei (Standard: signals_log.csv im Projektordner)")
    parser.add_argument("--out", help="Einzelergebnisse als CSV schreiben, z. B. ergebnis.csv")
    args = parser.parse_args(argv)
    return main(csv_path=args.csv, out_path=args.out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(cli())
