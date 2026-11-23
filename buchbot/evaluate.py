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
from buchbot import backtest
from buchbot.backtest import (
    MAIN_PATTERN_NAMES,
    OUTCOME_NOT_EVALUATED,
    OUTCOME_OPEN,
    SINGLE_PATTERN_NAMES,
    TRADED_DIRECTIONS,
    _trade,
    open_count,
    render_table,
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
        market=row.get("market") or config.MARKET,
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


def evaluate_rows(rows, df, config, allow_overlap=False):
    """Simuliert die Signale ab der Kerze nach ihrer Signalkerze, mit derselben Überlappungsregel wie im Backtest.

    Liefert (Trades, Anzahl übersprungener Signale, Anzahl zu alter Signale vor dem ersten Kerzenzeitpunkt).
    """
    found = []
    missing = []
    too_old = 0
    for row in rows:
        signal = signal_from_row(row, config)
        if signal is None:
            continue
        signal_candle = signal.time - pd.Timedelta(config.INTERVAL)
        if signal_candle < df.index[0]:
            too_old += 1
        elif signal_candle in df.index:
            found.append((df.index.get_loc(signal_candle), signal))
        else:
            missing.append(signal)

    trades, skipped = backtest.simulate_sequence(found, df, config, allow_overlap)
    for signal in missing:
        logger.warning("Signalkerze fehlt in den Kerzen, nicht ausgewertet: %s %s",
                       signal.pattern, signal.time.isoformat())
        outcome = OUTCOME_NOT_EVALUATED if signal.direction not in TRADED_DIRECTIONS else OUTCOME_OPEN
        trades.append(_trade(signal, df, None, None, None, outcome, config))
    return trades, sum(skipped.values()), too_old


def _evaluate_market(name, rows, fetch, allow_overlap, trades_out):
    """Wertet die Zeilen eines Marktes aus, druckt den Bericht und hängt die Trades an trades_out an."""
    config = default_config.for_market(name)
    df = fetch(config.SYMBOL, config.INTERVAL, lookback=None, period=config.BACKTEST_PERIOD)
    if df is None or len(df) == 0:
        print(f"[{config.MARKET}] Keine Kerzen erhalten, Auswertung dieses Marktes übersprungen.\n")
        return False
    df = remove_incomplete_candle(df, config.INTERVAL)

    trades, skipped, too_old = evaluate_rows(rows, df, config, allow_overlap)
    for trade in trades:
        trade["market"] = config.MARKET
        trade["decimals"] = config.PRICE_DECIMALS
    trades_out.extend(trades)

    print(f"=== {config.DISPLAY_SYMBOL} ({config.MARKET}) ===")
    print(f"Signale in der CSV: {len(rows)}")
    if trades:
        times = [t["signal_time"] for t in trades]
        print(f"Zeitraum der CSV: {min(times).isoformat()} bis {max(times).isoformat()} (UTC)")
    print(f"Kerzendaten decken den Zeitraum von {df.index[0].isoformat()} bis {df.index[-1].isoformat()} (UTC) ab")
    print(f"Überlappung: {'erlaubt (--allow-overlap)' if allow_overlap else 'ein Trade je Muster gleichzeitig'}")
    print()
    for title, source, names in GROUPS:
        group = [t for t in trades if t["source"] == source]
        rows_by_pattern, total = summarize(group, names)
        print(render_table(rows_by_pattern, total, config, title))
        print()
    print(f"offen: {open_count(trades)} (Haltefenster oder Signalkerze außerhalb der Kerzen, nicht in der Statistik)")
    print(f"übersprungen: {skipped} (Muster hatte noch einen offenen Trade, nicht in der Statistik)")
    print(f"zu alt für die Kerzendaten: {too_old} (Signalkerze vor dem ersten geladenen Kerzenzeitpunkt)")
    print()
    return True


def main(csv_path=None, out_path=None, allow_overlap=False, markets=None, fetch=get_candles):
    path = Path(csv_path) if csv_path else BASE_DIR / default_config.SIGNALS_CSV_FILE
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

    by_market = {}
    for row in rows:
        market = row.get("market") or default_config.DEFAULT_MARKET
        by_market.setdefault(market, []).append(row)
    selected = list(markets) if markets else list(by_market)

    status = 0
    all_trades = []
    for name in selected:
        if name not in default_config.MARKETS:
            print(f"Unbekannter Markt: {name}")
            status = 1
            continue
        market_rows = by_market.get(name, [])
        if not market_rows:
            print(f"[{name}] Keine Signale in {path}\n")
            continue
        if not _evaluate_market(name, market_rows, fetch, allow_overlap, all_trades):
            status = 1

    if out_path:
        write_csv(all_trades, out_path)
        print(f"Einzelergebnisse: {out_path}")
    return status


def cli(argv=None):
    parser = argparse.ArgumentParser(description="Auswertung der Schattenbetrieb-Signale aus signals_log.csv")
    parser.add_argument("--csv", help="Pfad zur Signaldatei (Standard: signals_log.csv im Projektordner)")
    parser.add_argument("--out", help="Einzelergebnisse als CSV schreiben, z. B. ergebnis.csv")
    parser.add_argument("--market", choices=sorted(default_config.MARKETS),
                        help="Nur ein Markt (Standard: alle Märkte in der CSV)")
    parser.add_argument("--allow-overlap", action="store_true",
                        help="alle Signale auswerten, auch wenn für dasselbe Muster ein Trade offen ist")
    args = parser.parse_args(argv)
    return main(csv_path=args.csv, out_path=args.out, allow_overlap=args.allow_overlap,
                markets=[args.market] if args.market else None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(cli())
