"""
Backtest: prüft die Musterregeln auf historischen 15m-Kerzen.

Aufruf: python -m buchbot.backtest

Kein Blick in die Zukunft: Die Signale einer Kerze entstehen nur aus Daten bis
einschließlich dieser Kerze. Simuliert wird ab der Kerze nach dem Signal.
"""

import csv
import logging
import sys
from collections import Counter

import pandas as pd

from buchbot import config as default_config
from buchbot import sltp
from buchbot.data import get_candles, remove_incomplete_candle
from buchbot.detectors import run_detectors
from buchbot.detectors.candles_main import PATTERNS as MAIN_PATTERNS
from buchbot.detectors.candles_single import PATTERNS as SINGLE_PATTERNS
from buchbot.filters import trend
from buchbot.models import format_price
from buchbot.pipeline import BASE_DIR


OUTCOME_TP = "TP"
OUTCOME_SL = "SL"
OUTCOME_TIMEOUT = "Zeitablauf"
OUTCOME_OPEN = "offen"
OUTCOME_NOT_EVALUATED = "nicht bewertet"
EVALUATED_OUTCOMES = (OUTCOME_TP, OUTCOME_SL, OUTCOME_TIMEOUT)
MAIN_PATTERN_NAMES = [p.name for p in MAIN_PATTERNS]
SINGLE_PATTERN_NAMES = [p.name for p in SINGLE_PATTERNS]
TRADED_DIRECTIONS = ("BUY", "SELL")
FUNNEL_STAGES = ("raw", "trend", "sltp")
TRADE_STAGES = ("simuliert", "offen", "uebersprungen")

CSV_FIELDS = [
    "pattern", "direction", "signal_time_utc", "entry", "sl", "tp", "risk_pips", "rr",
    "exit_time_utc", "exit_price", "outcome", "r",
]


def first_position(config):
    """Erste Kerze, ab der ATR und EMA berechenbar sind (Warmlauf)."""
    return max(config.ATR_PERIOD, config.TREND_EMA_PERIOD)


def find_signals(df, config):
    """Liefert (Liste aus (Position, Signal), Trichter-Zähler je Stufe).

    Jede Kerze sieht nur Daten bis einschließlich sich selbst.
    """
    found = []
    funnel = {stage: Counter() for stage in FUNNEL_STAGES}
    # Die letzte Kerze fehlt, weil ihr Ausgang nicht mehr simuliert werden kann
    for pos in range(first_position(config), len(df) - 1):
        view = df.iloc[: pos + 1]
        raw = run_detectors(view, config)
        after_trend = trend.apply(raw, view, config)
        after_sltp = sltp.apply(after_trend, config)
        for stage, signals in (("raw", raw), ("trend", after_trend), ("sltp", after_sltp)):
            funnel[stage].update(s.pattern for s in signals)
        found.extend((pos, signal) for signal in after_sltp)
    return found, funnel


def _trade(signal, df, pos, exit_pos, exit_price, outcome, config):
    trade = {
        "pattern": signal.pattern,
        "source": signal.source,
        "direction": signal.direction,
        "signal_time": signal.time,
        "entry": signal.entry,
        "sl": signal.sl,
        "tp": signal.tp,
        "risk_pips": signal.risk_pips,
        "rr": signal.rr,
        "exit_time": None,
        "exit_price": exit_price,
        "outcome": outcome,
        "r": None,
        "exit_pos": exit_pos,
    }
    if exit_pos is not None and outcome != OUTCOME_OPEN:
        trade["exit_time"] = df.index[exit_pos] + pd.Timedelta(config.INTERVAL)
    if exit_price is not None:
        if signal.direction == "BUY":
            move = exit_price - signal.entry
        else:
            move = signal.entry - exit_price
        net_pips = move / config.PIP_SIZE - config.SPREAD_PIPS
        trade["r"] = net_pips / signal.risk_pips
    return trade


def simulate(signal, df, pos, config):
    """Simuliert den Trade ab der Kerze nach dem Signal (Signalkerze an Position `pos`)."""
    if signal.direction not in TRADED_DIRECTIONS:
        return _trade(signal, df, pos, None, None, OUTCOME_NOT_EVALUATED, config)

    end = pos + config.MAX_HOLD_CANDLES
    # Haltefenster reicht über das Datenende: nicht bewertbar, geht nicht in die Statistik ein
    if end > len(df) - 1:
        return _trade(signal, df, pos, len(df) - 1, None, OUTCOME_OPEN, config)

    buy = signal.direction == "BUY"
    for j in range(pos + 1, end + 1):
        high = df["high"].iloc[j]
        low = df["low"].iloc[j]
        if buy:
            sl_hit, tp_hit = low <= signal.sl, high >= signal.tp
        else:
            sl_hit, tp_hit = high >= signal.sl, low <= signal.tp
        # Berühren beide Level dieselbe Kerze, zählt der Stop-Loss
        if sl_hit:
            return _trade(signal, df, pos, j, signal.sl, OUTCOME_SL, config)
        if tp_hit:
            return _trade(signal, df, pos, j, signal.tp, OUTCOME_TP, config)
    return _trade(signal, df, pos, end, df["close"].iloc[end], OUTCOME_TIMEOUT, config)


def simulate_sequence(found, df, config, allow_overlap=False):
    """Simuliert (Position, Signal)-Paare in Positionsreihenfolge.

    Solange für ein Muster eine Position offen ist (bis zum Ausstieg), werden dessen weitere Signale
    übersprungen, außer allow_overlap ist True. NEUTRAL-Signale werden nur gezählt und blockieren nichts.
    Liefert (Trades, Zähler der übersprungenen Signale je Muster).
    """
    trades = []
    skipped = Counter()
    busy_until = {}
    for pos, signal in sorted(found, key=lambda item: item[0]):
        if signal.direction not in TRADED_DIRECTIONS:
            trades.append(simulate(signal, df, pos, config))
            continue
        if not allow_overlap and busy_until.get(signal.pattern, -1) >= pos:
            skipped[signal.pattern] += 1
            continue
        trade = simulate(signal, df, pos, config)
        busy_until[signal.pattern] = trade["exit_pos"]
        trades.append(trade)
    return trades, skipped


def run_backtest(df, config):
    """Liefert (Trades, Trichter-Zähler je Stufe inklusive Simulationsstufen)."""
    found, funnel = find_signals(df, config)
    for stage in TRADE_STAGES:
        funnel[stage] = Counter()
    trades, skipped = simulate_sequence(found, df, config)
    funnel["uebersprungen"].update(skipped)
    for trade in trades:
        if trade["direction"] not in TRADED_DIRECTIONS:
            continue
        funnel["simuliert"][trade["pattern"]] += 1
        if trade["outcome"] == OUTCOME_OPEN:
            funnel["offen"][trade["pattern"]] += 1
    return trades, funnel


def _stats(items):
    """Zählt Trades ohne offene; Anteile und R nur aus bewerteten Trades."""
    items = [t for t in items if t["outcome"] != OUTCOME_OPEN]
    rs = [t["r"] for t in items if t["r"] is not None]
    return {
        "n": len(items),
        "tp": sum(1 for t in items if t["outcome"] == OUTCOME_TP),
        "sl": sum(1 for t in items if t["outcome"] == OUTCOME_SL),
        "timeout": sum(1 for t in items if t["outcome"] == OUTCOME_TIMEOUT),
        "avg_r": sum(rs) / len(rs) if rs else None,
        "sum_r": sum(rs) if rs else None,
    }


def summarize(trades, names):
    """Zeilen für alle Muster der Gruppe (auch ohne Signale) plus Gesamtzeile der Gruppe.

    Offene Trades (Haltefenster über das Datenende) fließen nicht in die Statistik ein.
    """
    rows = [(name, _stats([t for t in trades if t["pattern"] == name])) for name in names]
    return rows, _stats([t for t in trades if t["pattern"] in names])


def open_count(trades):
    return sum(1 for t in trades if t["outcome"] == OUTCOME_OPEN)


def _pct(part, total):
    return f"{100 * part / total:.0f}%" if total else "-"


def _fmt_r(value):
    return "-" if value is None else f"{value:+.2f}"


def render_table(rows, total, config, title):
    header = f"{'Muster':<26}{'Anzahl':>8}{'TP':>6}{'SL':>6}{'Zeitabl.':>10}{'Ø R':>8}{'Summe R':>10}"
    lines = [title, "", header, "-" * len(header)]
    notes = []
    for name, s in rows + [("GESAMT", total)]:
        if name == "GESAMT":
            lines.append("-" * len(header))
        evaluated = s["tp"] + s["sl"] + s["timeout"]
        lines.append(
            f"{name:<26}{s['n']:>8}{_pct(s['tp'], evaluated):>6}{_pct(s['sl'], evaluated):>6}"
            f"{_pct(s['timeout'], evaluated):>10}{_fmt_r(s['avg_r']):>8}{_fmt_r(s['sum_r']):>10}"
        )
        if name != "GESAMT" and s["n"] < config.MIN_SIGNALS_FOR_STATS:
            notes.append(f"  {name}: zu wenige Fälle für eine belastbare Aussage "
                         f"({s['n']} < {config.MIN_SIGNALS_FOR_STATS})")
    if notes:
        lines.append("")
        lines.extend(notes)
    return "\n".join(lines)


def render_funnel(funnel, names, title):
    """Trichter je Muster: Rohtreffer -> nach Trend -> nach Mindestabstand -> simuliert."""
    columns = [("Muster", 26), ("Rohtreffer", 11), ("nach Trend", 11), ("nach Abstand", 13),
               ("simuliert", 11), ("offen", 7), ("übersprung.", 12)]
    header = "".join(f"{title_cell:<{w}}" if i == 0 else f"{title_cell:>{w}}"
                     for i, (title_cell, w) in enumerate(columns))
    lines = [title, "", header, "-" * len(header)]
    totals = Counter()
    for name in names:
        values = [funnel["raw"][name], funnel["trend"][name], funnel["sltp"][name],
                  funnel["simuliert"][name], funnel["offen"][name], funnel["uebersprungen"][name]]
        totals.update(dict(zip(["raw", "trend", "sltp", "sim", "offen", "skip"], values)))
        lines.append(_funnel_line(name, values, columns))
    lines.append("-" * len(header))
    total_values = [totals[k] for k in ["raw", "trend", "sltp", "sim", "offen", "skip"]]
    lines.append(_funnel_line("GESAMT", total_values, columns))
    return "\n".join(lines)


def _funnel_line(name, values, columns):
    widths = [w for _, w in columns]
    cells = [f"{name:<{widths[0]}}"] + [f"{v:>{w}}" for v, w in zip(values, widths[1:])]
    return "".join(cells)


def _fmt(value, digits):
    return None if value is None else f"{value:.{digits}f}"


def write_csv(trades, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        for t in trades:
            writer.writerow({
                "pattern": t["pattern"],
                "direction": t["direction"],
                "signal_time_utc": t["signal_time"].isoformat(),
                "entry": format_price(t["entry"]),
                "sl": format_price(t["sl"]),
                "tp": format_price(t["tp"]),
                "risk_pips": _fmt(t["risk_pips"], 1),
                "rr": t["rr"],
                "exit_time_utc": t["exit_time"].isoformat() if t["exit_time"] is not None else None,
                "exit_price": format_price(t["exit_price"]),
                "outcome": t["outcome"],
                "r": _fmt(t["r"], 2),
            })


def main(config=default_config, fetch=get_candles):
    df = fetch(config.SYMBOL, config.INTERVAL, lookback=None, period=config.BACKTEST_PERIOD)
    if df is None or len(df) == 0:
        print("Keine Kerzen erhalten, Backtest abgebrochen.")
        return 1
    df = remove_incomplete_candle(df, config.INTERVAL)

    trades, funnel = run_backtest(df, config)
    main_rows, main_total = summarize(trades, MAIN_PATTERN_NAMES)
    single_rows, single_total = summarize(trades, SINGLE_PATTERN_NAMES)
    evaluated_candles = len(range(first_position(config), len(df) - 1))
    info = (
        f"Zeitraum: {df.index[0].isoformat()} bis {df.index[-1].isoformat()} (UTC)\n"
        f"Kerzen geladen: {len(df)}, davon ausgewertet: {evaluated_candles} "
        f"(Warmlauf {first_position(config)})"
    )
    print(info)
    print()
    print(render_table(main_rows, main_total, config, "Haupt-Muster"))
    print()
    print(render_table(single_rows, single_total, config,
                       "Einzelkerzen (Hintergrund, NEUTRAL nur gezählt, nicht bewertet)"))
    print(f"\noffen: {open_count(trades)} (Haltefenster reicht über das Datenende, nicht in der Statistik)")
    print()
    print(render_funnel(funnel, MAIN_PATTERN_NAMES, "Trichter Haupt-Muster (Kerzen mit Treffer, nicht Trades)"))
    print()
    print(render_funnel(funnel, SINGLE_PATTERN_NAMES, "Trichter Einzelkerzen (Hintergrund)"))

    path = BASE_DIR / config.BACKTEST_CSV_FILE
    write_csv(trades, path)
    print(f"\nEinzelsignale: {path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
