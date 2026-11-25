"""
Backtest: prüft die Musterregeln auf historischen 15m-Kerzen.

Aufruf: python -m buchbot.backtest

Kein Blick in die Zukunft: Die Signale einer Kerze entstehen nur aus Daten bis
einschließlich dieser Kerze. Simuliert wird ab der Kerze nach dem Signal.
"""

import argparse
import csv
import logging
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import stdev

import pandas as pd

from buchbot import config as default_config
from buchbot import sltp
from buchbot.data import get_candles, remove_incomplete_candle
from buchbot.detectors import run_detectors
from buchbot.detectors.candles_main import PATTERNS as MAIN_PATTERNS
from buchbot.detectors.candles_single import PATTERNS as SINGLE_PATTERNS
from buchbot.filters import trend
from buchbot.models import format_price
from buchbot.outputs.log_csv import sr_fields
from buchbot.pipeline import BASE_DIR
from buchbot.zones import SR_COLUMNS, annotate


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
SE_KEYS = ("se", "se_gross", "cse", "cse_gross")

CSV_FIELDS = [
    "market", "pattern", "direction", "signal_time_utc", "entry", "sl", "tp", "risk_pips", "rr",
    "exit_time_utc", "exit_price", "outcome", "r",
] + SR_COLUMNS


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
        # view endet bei pos, die SR-Zonen sehen also keine späteren Kerzen
        if config.SR_ENABLED:
            after_sltp = annotate(after_sltp, view, config)
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
        "r_gross": None,
        "tags": signal.tags,
        "exit_pos": exit_pos,
    }
    if exit_pos is not None and outcome != OUTCOME_OPEN:
        trade["exit_time"] = df.index[exit_pos] + pd.Timedelta(config.INTERVAL)
    if exit_price is not None:
        if signal.direction == "BUY":
            move = exit_price - signal.entry
        else:
            move = signal.entry - exit_price
        gross_pips = move / config.PIP_SIZE
        trade["r_gross"] = gross_pips / signal.risk_pips
        trade["r"] = (gross_pips - config.SPREAD_PIPS) / signal.risk_pips
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


def _std_error(values):
    """Standardfehler des Mittelwerts: Standardabweichung (n-1) geteilt durch Wurzel aus n."""
    if len(values) < 2:
        return None
    return stdev(values) / math.sqrt(len(values))


def cluster_std_error(values, clusters):
    """Cluster-Standardfehler des Mittelwerts: Wurzel aus der Summe über Cluster von (Summe der Abweichungen
    vom Mittelwert im Cluster)^2, geteilt durch n. clusters: je Wert ein Cluster-Schlüssel. None bei weniger als 2 Werten.
    """
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    deviation_sums = {}
    for value, cluster in zip(values, clusters):
        deviation_sums[cluster] = deviation_sums.get(cluster, 0.0) + (value - mean)
    return math.sqrt(sum(s * s for s in deviation_sums.values())) / n


def month_cluster(time):
    """Cluster für den Cluster-Standardfehler: Kalendermonat der Signalzeit (alle Märkte zusammen)."""
    return (time.year, time.month)


def _stats(items):
    """Zählt Trades ohne offene; Anteile und R nur aus bewerteten Trades.

    R nach Kosten (r) und vor Kosten (r_gross). Der Standardfehler (se, se_gross) und der Cluster-Standardfehler
    (cse, cse_gross) werden je für R nach und vor Kosten berechnet, weil Spread/Risiko je Trade verschieden ist.
    Der Cluster-Standardfehler braucht die Signalzeit aller Trades (sonst None).
    """
    items = [t for t in items if t["outcome"] != OUTCOME_OPEN]
    scored = [t for t in items if t["r"] is not None]
    rs = [t["r"] for t in scored]
    gross = [t["r_gross"] for t in scored]
    times = [t.get("signal_time") for t in scored]
    clusters = [month_cluster(x) for x in times] if all(x is not None for x in times) else None
    return {
        "n": len(items),
        "tp": sum(1 for t in items if t["outcome"] == OUTCOME_TP),
        "sl": sum(1 for t in items if t["outcome"] == OUTCOME_SL),
        "timeout": sum(1 for t in items if t["outcome"] == OUTCOME_TIMEOUT),
        "avg_r": sum(rs) / len(rs) if rs else None,
        "sum_r": sum(rs) if rs else None,
        "avg_r_gross": sum(gross) / len(gross) if gross else None,
        "sum_r_gross": sum(gross) if gross else None,
        "se": _std_error(rs),
        "se_gross": _std_error(gross),
        "cse": cluster_std_error(rs, clusters) if clusters is not None else None,
        "cse_gross": cluster_std_error(gross, clusters) if clusters is not None else None,
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


def _r_columns(spread, with_se, cluster_se=False):
    """R-Spalten als (Titel, Mindestbreite, Schlüssel): vor Kosten (Brutto), nach Kosten (Netto) oder beides.

    Der Standardfehler gehört zu R nach Kosten, im Modus "without" zu R vor Kosten. Der Cluster-Standardfehler
    (Kalendermonat) steht für jede gezeigte Kostenart.
    """
    if spread not in default_config.BACKTEST_SPREAD_MODES:
        raise ValueError(f"unbekannter Spread-Modus: {spread}")
    if spread == "with":
        avg, total = [("Ø R", 8, "avg_r")], [("Summe R", 10, "sum_r")]
        se, cluster = [("SE Ø R", 8, "se")], [("SE Cl.", 9, "cse")]
    elif spread == "without":
        avg, total = [("Ø R vor K.", 11, "avg_r_gross")], [("Summe R vor K.", 15, "sum_r_gross")]
        se, cluster = [("SE Ø R", 8, "se_gross")], [("SE Cl.", 9, "cse_gross")]
    else:
        avg = [("Ø R vor K.", 11, "avg_r_gross"), ("Ø R nach K.", 13, "avg_r")]
        total = [("Summe R vor K.", 15, "sum_r_gross"), ("Summe R nach K.", 17, "sum_r")]
        se = [("SE Ø R", 8, "se")]
        cluster = [("SE Cl. vor K.", 15, "cse_gross"), ("SE Cl. nach K.", 16, "cse")]
    return avg + (se if with_se else []) + (cluster if cluster_se else []) + total


def _column_width(title, width):
    return max(width, len(title) + 1)


def _r_header(columns):
    return "".join(f"{title:>{_column_width(title, width)}}" for title, width, _ in columns)


def _r_values(stats, columns):
    cells = []
    for title, width, key in columns:
        text = _fmt_se(stats[key]) if key in SE_KEYS else _fmt_r(stats[key])
        cells.append(f"{text:>{_column_width(title, width)}}")
    return "".join(cells)


def render_table(rows, total, config, title, spread="with", with_se=False, cluster_se=False):
    columns = _r_columns(spread, with_se, cluster_se)
    header = f"{'Muster':<26}{'Anzahl':>8}{'TP':>6}{'SL':>6}{'Zeitabl.':>10}" + _r_header(columns)
    lines = [title, "", header, "-" * len(header)]
    notes = []
    for name, s in rows + [("GESAMT", total)]:
        if name == "GESAMT":
            lines.append("-" * len(header))
        evaluated = s["tp"] + s["sl"] + s["timeout"]
        lines.append(
            f"{name:<26}{s['n']:>8}{_pct(s['tp'], evaluated):>6}{_pct(s['sl'], evaluated):>6}"
            f"{_pct(s['timeout'], evaluated):>10}" + _r_values(s, columns)
        )
        if s["n"] < config.MIN_SIGNALS_FOR_STATS:
            notes.append(f"  {name}: zu wenige Fälle für eine belastbare Aussage "
                         f"({s['n']} < {config.MIN_SIGNALS_FOR_STATS})")
    if notes:
        lines.append("")
        lines.extend(notes)
    return "\n".join(lines)


ZONE_SCOPES = (
    ("Haupt-Muster (candles_main)", "candles_main"),
    ("Einzelkerzen (Hintergrund)", "candles_single"),
)


def _is_aligned(trade):
    return trade["tags"].get("sr_aligned") is True


def _is_against(trade):
    return trade["tags"].get("sr_against") is True


def _trend_relation(trade):
    """'mit' bei BUY+up bzw. SELL+down, 'gegen' bei BUY+down bzw. SELL+up, sonst 'range' oder None (zu wenige Pivots)."""
    trend = trade["tags"].get("swing_trend")
    if trend not in ("up", "down"):
        return trend
    return "mit" if (trade["direction"] == "BUY") == (trend == "up") else "gegen"


# Gruppen überlappen sich (a und c, d ist Teilmenge von a), die Anteile ergeben daher nicht 100 %
ZONE_GROUPS = (
    ("a) Muster an starker passender Zone", _is_aligned),
    ("b) keine Zone in der Nähe", lambda t: t["tags"].get("sr_relation") == "none"),
    ("c) gegen starke Zone", _is_against),
    ("d) a) und nicht c)", lambda t: _is_aligned(t) and not _is_against(t)),
)
NO_TREND_GROUP = "ohne Swing-Trend"
TREND_GROUPS = (
    ("in Trendrichtung", lambda t: _trend_relation(t) == "mit"),
    ("gegen den Trend", lambda t: _trend_relation(t) == "gegen"),
    ("range", lambda t: _trend_relation(t) == "range"),
    (NO_TREND_GROUP, lambda t: _trend_relation(t) in (None, "")),
)


def _zone_population(trades, source):
    """Alle BUY/SELL-Signale eines Musterbereichs, offene eingeschlossen (Basis der Anteile)."""
    return [t for t in trades if t["source"] == source and t["direction"] in TRADED_DIRECTIONS]


def _fmt_se(value):
    return "-" if value is None else f"{value:.2f}"


def _fmt_mean(value):
    return "-" if value is None else f"{value:.1f}"


def _zone_group_lines(population, groups, config, spread, cluster_se=False):
    columns = _r_columns(spread, with_se=True, cluster_se=cluster_se)
    header = f"{'Gruppe':<38}{'Anzahl':>8}{'TP':>6}{'SL':>6}{'Zeitabl.':>10}" + _r_header(columns)
    lines = [header, "-" * len(header)]
    notes = []
    for name, predicate in groups:
        s = _stats([t for t in population if predicate(t)])
        evaluated = s["tp"] + s["sl"] + s["timeout"]
        lines.append(
            f"{name:<38}{s['n']:>8}{_pct(s['tp'], evaluated):>6}{_pct(s['sl'], evaluated):>6}"
            f"{_pct(s['timeout'], evaluated):>10}" + _r_values(s, columns)
        )
        if s["n"] < config.MIN_SIGNALS_FOR_STATS:
            notes.append(f"  {name}: zu wenige Fälle ({s['n']} < {config.MIN_SIGNALS_FOR_STATS})")
    return lines, notes


def _distribution_lines(population, groups, config, scope_title):
    """Anteil je Gruppe an allen Signalen des Bereichs und Ø starke Zonen je Signalkerze, plus Warnungen."""
    header = f"{'Gruppe':<38}{'Anteil':>8}{'Ø starke Zonen':>16}"
    lines = [header, "-" * len(header)]
    warnings = []
    total = len(population)
    for name, predicate in groups:
        members = [t for t in population if predicate(t)]
        zones = [t["tags"]["sr_strong_zones"] for t in members if "sr_strong_zones" in t["tags"]]
        mean_zones = sum(zones) / len(zones) if zones else None
        lines.append(f"{name:<38}{_pct(len(members), total):>8}{_fmt_mean(mean_zones):>16}")
        if total and name != NO_TREND_GROUP:
            share = len(members) / total
            if share > config.ZONE_WARN_SHARE_HIGH or share < config.ZONE_WARN_SHARE_LOW:
                warnings.append(f"  Warnung: Zonenparameter möglicherweise unpassend "
                                f"({scope_title}, {name}: {_pct(len(members), total)})")
    return lines, warnings


def _mean_zones_per_side(population):
    """Ø starke Zonen je Kerze: (Unterstützung, Widerstand, Mittel beider Seiten); None ohne Tags."""
    tagged = [t["tags"] for t in population if "sr_strong_support" in t["tags"]]
    if not tagged:
        return None
    support = sum(tags["sr_strong_support"] for tags in tagged) / len(tagged)
    resistance = sum(tags["sr_strong_resistance"] for tags in tagged) / len(tagged)
    return support, resistance, (support + resistance) / 2


def _header_lines(population, config, scope_title):
    """Zusatzzeilen im Kopf: Ø Zonen je Seite und Anteil der Gruppen a und c, dazu Warnung bei zu dichten Zonen."""
    lines, warnings = [], []
    means = _mean_zones_per_side(population)
    if means is not None:
        support, resistance, per_side = means
        lines.append(f"Ø starke Zonen je Kerze und Seite: {per_side:.1f} "
                     f"(Unterstützung {support:.1f}, Widerstand {resistance:.1f})")
        if per_side > config.SR_WARN_MAX_ZONES:
            warnings.append(f"  Warnung: Zonen zu dicht ({scope_title}: Ø {per_side:.1f} je Seite, "
                            f"Grenze {config.SR_WARN_MAX_ZONES})")
    total = len(population)
    lines.append(f"Anteil Gruppe a) {_pct(sum(1 for t in population if _is_aligned(t)), total)}, "
                 f"Gruppe c) {_pct(sum(1 for t in population if _is_against(t)), total)}")
    return lines, warnings


def _zone_tables(population, config, spread="with", cluster_se=False):
    zone_lines, zone_notes = _zone_group_lines(population, ZONE_GROUPS, config, spread, cluster_se)
    trend_lines, trend_notes = _zone_group_lines(population, TREND_GROUPS, config, spread, cluster_se)
    return ["Zonen-Gruppen:"] + zone_lines + ["Trend-Gruppen:"] + trend_lines + zone_notes + trend_notes


def signal_time_median(trades):
    """Median der Signalzeiten aller BUY/SELL-Trades (oberer Wert bei gerader Anzahl); None ohne Trades."""
    times = sorted(t["signal_time"] for t in trades if t["direction"] in TRADED_DIRECTIONS)
    return times[len(times) // 2] if times else None


def render_zone_compare(trades, config, title, split_at=None, spread="with", cluster_se=False):
    """Zonen-Vergleich je Musterbereich: Gruppen (Zonen und Trend) mit Statistik und Verteilung.

    split_at: optionaler Zeitpunkt; dann zusätzlich Tabellen für Signale davor und danach.
    """
    out = [title,
           "Offene Trades fließen nicht in die Statistik ein, sind aber in den Anteilen enthalten. "
           "Gruppen überlappen sich."]
    for scope_title, source in ZONE_SCOPES:
        population = _zone_population(trades, source)
        out += ["", f"{scope_title}: {len(population)} BUY/SELL-Signale"]
        if not population:
            out.append("  keine BUY/SELL-Signale")
            continue
        header, header_warnings = _header_lines(population, config, scope_title)
        out += header
        out += _zone_tables(population, config, spread, cluster_se)
        dist_lines, warnings = _distribution_lines(
            population, ZONE_GROUPS + TREND_GROUPS, config, scope_title)
        out += ["Verteilung:"] + dist_lines + header_warnings + warnings
        if split_at is not None:
            early = [t for t in population if t["signal_time"] < split_at]
            late = [t for t in population if t["signal_time"] >= split_at]
            cut = f"{split_at:%Y-%m-%d %H:%M} UTC"
            out += [f"Zeithälfte 1 (Signale vor {cut}): {len(early)} BUY/SELL-Signale"]
            out += _zone_tables(early, config, spread, cluster_se)
            out += [f"Zeithälfte 2 (Signale ab {cut}): {len(late)} BUY/SELL-Signale"]
            out += _zone_tables(late, config, spread, cluster_se)
    return "\n".join(out)


def decade_labels():
    first, second = default_config.DECADE_BOUNDARIES
    return [f"bis {first - 1}", f"{first}-{second - 1}", f"ab {second}"]


def decade_label(time):
    """Jahrzehnt einer Signalzeit; Grenzen aus DECADE_BOUNDARIES, Bezeichnungen wie in decade_labels()."""
    first, second = default_config.DECADE_BOUNDARIES
    labels = decade_labels()
    if time.year < first:
        return labels[0]
    if time.year < second:
        return labels[1]
    return labels[2]


def render_decade_tables(trades, names, config, title, spread, cluster_se=False):
    """Tabellen je Jahrzehnt der Signalzeit für die Muster in names."""
    out = []
    for label in decade_labels():
        part = [t for t in trades if decade_label(t["signal_time"]) == label]
        count = sum(1 for t in part if t["pattern"] in names)
        rows, total = summarize(part, names)
        out.append(render_table(rows, total, config, f"{title}, Zeit {label} ({count} Trades)",
                                spread, with_se=True, cluster_se=cluster_se))
    return "\n\n".join(out)


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
            row = {
                "market": t.get("market"),
                "pattern": t["pattern"],
                "direction": t["direction"],
                "signal_time_utc": t["signal_time"].isoformat(),
                "entry": format_price(t["entry"], t["decimals"]),
                "sl": format_price(t["sl"], t["decimals"]),
                "tp": format_price(t["tp"], t["decimals"]),
                "risk_pips": _fmt(t["risk_pips"], 1),
                "rr": t["rr"],
                "exit_time_utc": t["exit_time"].isoformat() if t["exit_time"] is not None else None,
                "exit_price": format_price(t["exit_price"], t["decimals"]),
                "outcome": t["outcome"],
                "r": _fmt(t["r"], 2),
            }
            row.update(sr_fields(t["tags"], t["decimals"]))
            writer.writerow(row)


def _print_report(df, cfg, trades, funnel, spread, no_sr):
    main_rows, main_total = summarize(trades, MAIN_PATTERN_NAMES)
    single_rows, single_total = summarize(trades, SINGLE_PATTERN_NAMES)
    evaluated_candles = len(range(first_position(cfg), len(df) - 1))
    print(f"=== {cfg.DISPLAY_SYMBOL} ({cfg.MARKET}) ===")
    print(
        f"Zeitraum: {df.index[0].isoformat()} bis {df.index[-1].isoformat()} (UTC)\n"
        f"Kerzen geladen: {len(df)}, davon ausgewertet: {evaluated_candles} "
        f"(Warmlauf {first_position(cfg)})"
    )
    print()
    print(render_table(main_rows, main_total, cfg, "Haupt-Muster", spread, with_se=True))
    print()
    print(render_decade_tables(trades, MAIN_PATTERN_NAMES, cfg, f"Haupt-Muster {cfg.MARKET}", spread))
    print()
    print(render_table(single_rows, single_total, cfg,
                       "Einzelkerzen (Hintergrund, NEUTRAL nur gezählt, nicht bewertet)", spread))
    print(f"\noffen: {open_count(trades)} (Haltefenster reicht über das Datenende, nicht in der Statistik)")
    print()
    print(render_funnel(funnel, MAIN_PATTERN_NAMES, "Trichter Haupt-Muster (Kerzen mit Treffer, nicht Trades)"))
    print()
    print(render_funnel(funnel, SINGLE_PATTERN_NAMES, "Trichter Einzelkerzen (Hintergrund)"))
    print()
    if not no_sr:
        print(render_zone_compare(trades, cfg, f"Zonen-Vergleich {cfg.DISPLAY_SYMBOL} ({cfg.MARKET})", spread=spread))
        print()


SNAPSHOT_COLUMNS = ["market", "interval", "fetched_at", "time_utc", "open", "high", "low", "close"]


def load_snapshot(path):
    """Liest den Datenstand als {(Markt, Intervall): (DataFrame, Abrufzeit)}, Zeiten in UTC, Reihenfolge der Datei."""
    raw = pd.read_csv(path, sep=";",
                      dtype={"market": str, "interval": str, "fetched_at": str, "time_utc": str})
    entries = {}
    for (market, interval), part in raw.groupby(["market", "interval"], sort=False):
        df = part[["open", "high", "low", "close"]].astype(float).reset_index(drop=True)
        df.index = pd.to_datetime(part["time_utc"].to_numpy(), utc=True)
        entries[(market, interval)] = (df, part["fetched_at"].iloc[0])
    return entries


def save_snapshot(path, entries):
    """Schreibt alle Märkte je Intervall in eine Datei; zuerst temporäre Datei, dann ersetzen."""
    frames = []
    for (market, interval), (df, fetched_at) in entries.items():
        part = df[["open", "high", "low", "close"]].reset_index(drop=True)
        part.insert(0, "time_utc", [ts.isoformat() for ts in df.index])
        part.insert(0, "fetched_at", fetched_at)
        part.insert(0, "interval", interval)
        part.insert(0, "market", market)
        frames.append(part)
    combined = pd.concat(frames, ignore_index=True)[SNAPSHOT_COLUMNS]
    tmp = path.with_name(path.name + ".tmp")
    combined.to_csv(tmp, sep=";", index=False)
    os.replace(tmp, path)


def default_csv_path(markets=None, interval=None):
    """Einzelmarkt: backtest_results_<MARKT>.csv, sonst BACKTEST_CSV_FILE; mit --interval je ein Suffix _<Intervall>."""
    suffix = f"_{interval}" if interval else ""
    if markets and len(markets) == 1:
        return BASE_DIR / f"backtest_results_{markets[0]}{suffix}.csv"
    base = Path(default_config.BACKTEST_CSV_FILE)
    return BASE_DIR / f"{base.stem}{suffix}{base.suffix}"


def main(markets=None, fetch=get_candles, csv_path=None, sr_max_zones=None, snapshot=None,
         interval=None, no_sr=False, spread="both", null_test=False):
    """Backtest je Markt, bei mehreren Märkten zusätzlich gepoolte Tabellen. Gibt 1 zurück, wenn ein Markt keine Kerzen hatte.

    sr_max_zones überschreibt SR_MAX_ZONES_PER_SIDE aus config.py (None = Standardwert aus config.py).
    snapshot: CSV-Datei mit eingefrorenen Kerzen je Markt und Intervall. Fehlt ein Eintrag, wird abgerufen und gespeichert.
    interval: überschreibt das Intervall aller Märkte nur für diesen Lauf (Zeitraum aus BACKTEST_PERIOD_BY_INTERVAL).
    no_sr: annotate nicht aufrufen, keine Zonen-Tabellen.
    spread: "both", "with" (nach Kosten) oder "without" (vor Kosten).
    null_test: zusätzlich Nullvergleich per Permutation mit den Kriterien K1 bis K5 (buchbot.nulltest).
    Märkte, die denselben Datensatz (Symbol und Intervall) wie ein früherer Markt nutzen, werden übersprungen.
    """
    names = list(markets) if markets else list(default_config.MARKETS)
    max_zones = default_config.SR_MAX_ZONES_PER_SIDE if sr_max_zones is None else sr_max_zones
    snapshot = Path(snapshot) if snapshot else None
    snapshot_entries = load_snapshot(snapshot) if snapshot and snapshot.exists() else {}
    fetched_any = False
    print(f"Starke Zonen je Seite: {'alle' if max_zones is None else max_zones}"
          f"{' (Zonen aus, --no-sr)' if no_sr else ''}\n")
    status = 0
    all_trades = []
    candidates = {}
    used_datasets = {}
    run_start = time.perf_counter()
    for name in names:
        market_start = time.perf_counter()
        cfg = default_config.for_market(name)
        cfg.SR_MAX_ZONES_PER_SIDE = max_zones
        cfg.SR_ENABLED = cfg.SR_ENABLED and not no_sr
        if interval:
            cfg.INTERVAL = interval
            cfg.BACKTEST_PERIOD = default_config.BACKTEST_PERIOD_BY_INTERVAL[interval]
        dataset = (cfg.SYMBOL, cfg.INTERVAL)
        if dataset in used_datasets:
            print(f"[{cfg.MARKET}] übersprungen: nutzt denselben Datensatz ({cfg.SYMBOL}, {cfg.INTERVAL}) wie "
                  f"{used_datasets[dataset]}, sonst würden dieselben Trades doppelt gezählt.\n")
            continue
        used_datasets[dataset] = cfg.MARKET
        cached = snapshot_entries.get((name, cfg.INTERVAL))
        if cached is not None:
            raw, fetched_at = cached
            origin = "aus Snapshot"
        else:
            raw = fetch(cfg.SYMBOL, cfg.INTERVAL, lookback=None, period=cfg.BACKTEST_PERIOD)
            if raw is None or len(raw) == 0:
                print(f"[{cfg.MARKET}] Keine Kerzen erhalten, Backtest für diesen Markt übersprungen.\n")
                status = 1
                continue
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            origin = "neu abgerufen"
            snapshot_entries[(name, cfg.INTERVAL)] = (raw, fetched_at)
            fetched_any = True
        print(f"Datenstand {cfg.MARKET} ({cfg.INTERVAL}): {origin}, abgerufen {fetched_at} UTC, Kerzen "
              f"{raw.index[0]:%Y-%m-%d %H:%M} bis {raw.index[-1]:%Y-%m-%d %H:%M} UTC ({len(raw)})")
        df = remove_incomplete_candle(raw, cfg.INTERVAL, now=pd.Timestamp(fetched_at))
        if len(df) < default_config.MIN_CANDLES_FOR_BACKTEST:
            print(f"[{cfg.MARKET}] Nur {len(df)} Kerzen (Minimum {default_config.MIN_CANDLES_FOR_BACKTEST}), "
                  f"übersprungen. Zeitraum ggf. zu kurz für {cfg.INTERVAL}.\n")
            continue
        print(f"Parameter {cfg.MARKET}: Intervall {cfg.INTERVAL}, Zeitraum {cfg.BACKTEST_PERIOD}, "
              f"MAX_HOLD_CANDLES {cfg.MAX_HOLD_CANDLES}, Spread {cfg.SPREAD_PIPS} Pips, "
              f"SL_BUFFER_ATR {cfg.SL_BUFFER_ATR}, RISK_REWARD {cfg.RISK_REWARD}, "
              f"TREND_EMA_PERIOD {cfg.TREND_EMA_PERIOD}, ATR_PERIOD {cfg.ATR_PERIOD}")
        trades, funnel = run_backtest(df, cfg)
        if null_test:
            from buchbot import nulltest
            candidates[cfg.MARKET] = nulltest.candidate_trades(df, cfg)
        for trade in trades:
            trade["market"] = cfg.MARKET
            trade["decimals"] = cfg.PRICE_DECIMALS
        all_trades.extend(trades)
        _print_report(df, cfg, trades, funnel, spread, no_sr)
        print(f"Laufzeit {cfg.MARKET}: {time.perf_counter() - market_start:.1f} s\n")

    if snapshot and fetched_any:
        save_snapshot(snapshot, snapshot_entries)
        print(f"Snapshot gespeichert: {snapshot}\n")
    if len(names) > 1:
        split_at = signal_time_median(all_trades)
        pooled_rows, pooled_total = summarize(all_trades, MAIN_PATTERN_NAMES)
        print(render_table(pooled_rows, pooled_total, default_config,
                           "Haupt-Muster GESAMT (alle Märkte gepoolt)", spread, with_se=True, cluster_se=True))
        print()
        print(render_decade_tables(all_trades, MAIN_PATTERN_NAMES, default_config,
                                   "Haupt-Muster GESAMT", spread, cluster_se=True))
        print()
        if not no_sr:
            print(render_zone_compare(all_trades, default_config,
                                      "Zonen-Vergleich GESAMT (alle Märkte gepoolt)",
                                      split_at=split_at, spread=spread, cluster_se=True))
            print()
    if null_test:
        from buchbot import nulltest
        null_start = time.perf_counter()
        print(nulltest.render_report(all_trades, candidates))
        print(f"Laufzeit Nullvergleich: {time.perf_counter() - null_start:.1f} s\n")
    path = csv_path or default_csv_path(markets, interval)
    write_csv(all_trades, path)
    print(f"Einzelsignale: {path}")
    print(f"Laufzeit gesamt ({len(names)} Märkte): {time.perf_counter() - run_start:.1f} s")
    return status


def _parse_markets(value):
    """'ALL' oder kommagetrennte Marktnamen, die in config.MARKETS stehen."""
    if value.strip().upper() == "ALL":
        return list(default_config.MARKETS)
    names = [m.strip() for m in value.split(",") if m.strip()]
    unknown = [m for m in names if m not in default_config.MARKETS]
    if not names or unknown:
        raise argparse.ArgumentTypeError(f"unbekannte Märkte: {', '.join(unknown) or value}")
    return names


def _parse_max_zones(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"keine ganze Zahl: {value}")
    if number < 1:
        raise argparse.ArgumentTypeError("muss mindestens 1 sein")
    return number


def _parse_snapshot(value):
    """Snapshot nur als .csv (durch .gitignore vor dem Committen geschützt); relative Pfade gelten ab Projektordner."""
    path = Path(value)
    if path.suffix.lower() != ".csv":
        raise argparse.ArgumentTypeError(f"Snapshot muss eine .csv-Datei sein: {value}")
    return path if path.is_absolute() else BASE_DIR / path


def cli(argv=None):
    parser = argparse.ArgumentParser(description="Backtest der Muster je Markt")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--market", choices=sorted(default_config.MARKETS),
                       help="Nur ein Markt (Standard: alle)")
    group.add_argument("--markets", type=_parse_markets,
                       help="ALL oder Liste, z. B. EURUSD,GBPUSD (gepoolter Zonen-Vergleich)")
    parser.add_argument("--sr-max-zones", type=_parse_max_zones, default=None,
                        help="Je Seite nur die N starken Zonen mit den meisten Berührungen (überschreibt SR_MAX_ZONES_PER_SIDE)")
    parser.add_argument("--snapshot", type=_parse_snapshot, default=None,
                        help="CSV mit eingefrorenen Kerzen je Markt und Intervall: fehlt ein Eintrag, wird abgerufen und gespeichert, sonst daraus gelesen")
    parser.add_argument("--interval", choices=list(default_config.BACKTEST_PERIOD_BY_INTERVAL), default=None,
                        help="Intervall nur für den Backtest (Zeitraum aus BACKTEST_PERIOD_BY_INTERVAL); Standard: Intervall des Markts")
    parser.add_argument("--no-sr", action="store_true",
                        help="Zonen nicht berechnen (sr-Spalten bleiben leer, keine Zonen-Tabellen)")
    parser.add_argument("--null-test", action="store_true",
                        help="Nullvergleich per Permutation (Pseudo-Muster, Seed und Ziehungen aus config.py) und Kriterien K1 bis K5")
    parser.add_argument("--spread", choices=list(default_config.BACKTEST_SPREAD_MODES), default="both",
                        help="R nach Kosten (with), vor Kosten (without) oder beides (both, Standard)")
    args = parser.parse_args(argv)
    options = dict(sr_max_zones=args.sr_max_zones, snapshot=args.snapshot, interval=args.interval,
                   no_sr=args.no_sr, spread=args.spread, null_test=args.null_test)
    if args.market:
        return main(markets=[args.market], **options)
    return main(markets=args.markets, **options)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(cli())
