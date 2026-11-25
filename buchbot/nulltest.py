"""
Nullvergleich für den Backtest (Forschung): Sind die Ergebnisse der Haupt-Muster besser als Zufall?

Als Vergleich dienen Pseudo-Muster aus den letzten Kerzen: Jede Kerze, deren Trendbedingung der Live-Filter erfüllt,
ist ein Kandidat. Einstieg, SL, TP, Mindestabstand, Haltedauer und Spread laufen über dieselben Funktionen wie
im Backtest (trend.apply, sltp.apply, backtest.simulate), nur ohne Überlappungsregel. Je Ziehung werden je Markt und
Richtung so viele Kandidaten ohne Zurücklegen gezogen, wie die echten Haupt-Muster Trades hatten.

Aufruf über python -m buchbot.backtest --null-test
"""

import math
from collections import Counter

import numpy as np
import pandas as pd

from buchbot import backtest, sltp
from buchbot import config as default_config
from buchbot.data import calculate_atr
from buchbot.filters import trend
from buchbot.models import Signal


SOURCE = "null_test"
PSEUDO_PATTERN = "Pseudo-Muster"
# Wie bei den Umkehrmustern: BUY nur nach Abwärtstrend (Schluss unter EMA), SELL nur nach Aufwärtstrend
REQUIRED_TREND = {"BUY": "down", "SELL": "up"}
DIRECTIONS = backtest.TRADED_DIRECTIONS


def candidate_trades(df, config):
    """Alle bewerteten Pseudo-Trades je Richtung: {"BUY": [Trades], "SELL": [Trades]}.

    Je Kerze (wie im Backtest ab dem Warmlauf, ohne die letzte) entsteht ein Pseudo-Muster aus den letzten
    NULL_PATTERN_CANDLES Kerzen. Trendfilter und SL/TP sind die Live-Funktionen; offene Trades fallen heraus.
    """
    n = default_config.NULL_PATTERN_CANDLES
    result = {direction: [] for direction in DIRECTIONS}
    atr = calculate_atr(df, period=config.ATR_PERIOD)
    if atr is None:
        return result
    atr_values = atr.to_numpy(dtype=float)
    close, high, low = (df[column].to_numpy(dtype=float) for column in ("close", "high", "low"))
    step = pd.Timedelta(config.INTERVAL)
    for pos in range(backtest.first_position(config), len(df) - 1):
        if math.isnan(atr_values[pos]):
            continue
        pattern_low = float(low[pos - n + 1:pos + 1].min())
        pattern_high = float(high[pos - n + 1:pos + 1].max())
        signals = [
            Signal(
                time=df.index[pos] + step, symbol=config.SYMBOL, interval=config.INTERVAL, source=SOURCE,
                pattern=PSEUDO_PATTERN, direction=direction, entry=float(close[pos]),
                atr=float(atr_values[pos]), market=getattr(config, "MARKET", None),
                tags={"required_trend": required, "n_candles": n,
                      "pattern_low": pattern_low, "pattern_high": pattern_high},
            )
            for direction, required in REQUIRED_TREND.items()
        ]
        for signal in sltp.apply(trend.apply(signals, df, config), config):
            trade = backtest.simulate(signal, df, pos, config)
            if trade["outcome"] in backtest.EVALUATED_OUTCOMES and trade["r"] is not None:
                trade["market"] = getattr(config, "MARKET", None)
                result[signal.direction].append(trade)
    return result


def real_main_trades(trades):
    """Bewertete BUY/SELL-Trades der Haupt-Muster (candles_main), wie in den Haupt-Muster-Tabellen."""
    return [t for t in trades
            if t["source"] == "candles_main" and t["direction"] in DIRECTIONS
            and t["outcome"] in backtest.EVALUATED_OUTCOMES and t["r"] is not None]


def decade_index(time):
    return backtest.decade_labels().index(backtest.decade_label(time))


def _arrays(trades):
    return {
        "gross": np.array([t["r_gross"] for t in trades], dtype=float),
        "net": np.array([t["r"] for t in trades], dtype=float),
        "dir": np.array([DIRECTIONS.index(t["direction"]) for t in trades], dtype=int),
        "dec": np.array([decade_index(t["signal_time"]) for t in trades], dtype=int),
    }


def permutation_null(groups, draws, seed, n_decades):
    """Zieht je Gruppe k Werte ohne Zurücklegen, draws-mal. Summen und Anzahl je Ziehung, Richtung und Jahrzehnt.

    groups: Liste von dicts mit gross, net, dec (Arrays je Kandidat), dir (Richtungsindex), k (Ziehungsgröße).
    Liefert (Summe R vor Kosten, Summe R nach Kosten, Anzahl), je Form (draws, Richtungen, Jahrzehnte).
    """
    rng = np.random.default_rng(seed)
    shape = (draws, len(DIRECTIONS), n_decades)
    gross, net, counts = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    for draw in range(draws):
        for group in groups:
            picked = rng.choice(len(group["gross"]), size=group["k"], replace=False)
            dec = group["dec"][picked]
            counts[draw, group["dir"]] += np.bincount(dec, minlength=n_decades)
            gross[draw, group["dir"]] += np.bincount(dec, weights=group["gross"][picked], minlength=n_decades)
            net[draw, group["dir"]] += np.bincount(dec, weights=group["net"][picked], minlength=n_decades)
    return gross, net, counts


def _scope_mean(sums, counts):
    """Mittelwert je Ziehung (Summe geteilt durch Anzahl); NaN, wenn in dem Bereich nichts gezogen wurde."""
    safe = np.where(counts > 0, counts, 1)
    return np.where(counts > 0, sums / safe, np.nan)


def scope_definitions():
    """Bereiche der Auswertung als (Name, Richtungsindizes, Jahrzehntindizes): gepoolt, BUY, SELL, je Jahrzehnt."""
    labels = backtest.decade_labels()
    all_dirs, all_decs = list(range(len(DIRECTIONS))), list(range(len(labels)))
    scopes = [("Gepoolt", all_dirs, all_decs)]
    scopes += [(direction, [i], all_decs) for i, direction in enumerate(DIRECTIONS)]
    scopes += [(f"Zeit {label}", all_dirs, [i]) for i, label in enumerate(labels)]
    return scopes


def _mean_in_scope(arrays, key, dirs, decs):
    mask = np.isin(arrays["dir"], dirs) & np.isin(arrays["dec"], decs)
    return (float(arrays[key][mask].mean()) if mask.any() else None), int(mask.sum())


def null_comparison(real, pool, groups):
    """Nullverteilung gegen die echten Haupt-Muster je Bereich (Zeilen für Tabelle und Kriterien).

    real: Arrays der echten Trades, pool: Arrays aller Kandidaten (Drift ohne Ziehung), groups: Ziehungsgruppen.
    """
    cfg = default_config
    n_decades = len(backtest.decade_labels())
    gross_sums, net_sums, counts = permutation_null(groups, cfg.NULL_TEST_DRAWS, cfg.NULL_TEST_SEED, n_decades)
    rows = []
    for name, dirs, decs in scope_definitions():
        count = counts[:, dirs][:, :, decs].sum(axis=(1, 2))
        row = {"scope": name}
        for kind, sums in (("gross", gross_sums), ("net", net_sums)):
            null = _scope_mean(sums[:, dirs][:, :, decs].sum(axis=(1, 2)), count)
            valid = null[~np.isnan(null)]
            real_mean, n_real = _mean_in_scope(real, kind, dirs, decs)
            drift, n_candidates = _mean_in_scope(pool, kind, dirs, decs)
            row[kind] = {
                "real": real_mean,
                "null_mean": float(valid.mean()) if len(valid) else None,
                "quantiles": {q: float(np.quantile(valid, q)) for q in cfg.NULL_QUANTILES} if len(valid) else {},
                "p": float((valid >= real_mean).mean()) if len(valid) and real_mean is not None else None,
                "drift": drift,
            }
            row["n_real"], row["n_candidates"] = n_real, n_candidates
        rows.append(row)
    return rows


def _group_stats(trades):
    return backtest._stats(trades)


def evaluate_criteria(real_trades, pooled_row):
    """Kriterien K1 bis K5 als Liste (Name, Beschreibung, Zahlen, erfüllt), erfüllt: True, False oder None (nicht bewertbar)."""
    cfg = default_config
    pooled = _group_stats(real_trades)
    gross = pooled_row["gross"]
    q = gross["quantiles"].get(cfg.K1_QUANTILE)
    k1 = None if q is None or gross["real"] is None else gross["real"] > q
    k1_text = (f"Ø R vor K. {_num(gross['real'])}, {cfg.K1_QUANTILE:.0%}-Quantil Null {_num(q)}, "
               f"p = {_p(gross['p'])}")

    decade_means = []
    for label in backtest.decade_labels():
        part = [t for t in real_trades if backtest.decade_label(t["signal_time"]) == label]
        decade_means.append((label, _group_stats(part)["avg_r_gross"]))
    positive_decades = sum(1 for _, mean in decade_means if mean is not None and mean > 0)
    k2 = positive_decades >= cfg.K2_MIN_DECADES
    k2_text = (f"Ø R vor K. > 0 in {positive_decades} von {len(decade_means)} Jahrzehnten ("
               + ", ".join(f"{label}: {_num(mean)}" for label, mean in decade_means) + ")")

    market_rows = _market_rows(real_trades, cfg.K3_MIN_TRADES)
    positive = sum(1 for row in market_rows if row["avg_r_gross"] > 0)
    k3 = positive / len(market_rows) >= cfg.K3_MIN_SHARE if market_rows else None
    k3_text = (f"{positive} von {len(market_rows)} Märkten mit mindestens {cfg.K3_MIN_TRADES} Trades haben "
               f"Ø R vor K. > 0" + (f" ({positive / len(market_rows):.0%})" if market_rows else ""))

    cse = pooled["cse_gross"]
    ratio = pooled["avg_r_gross"] / cse if cse else None
    k4 = None if ratio is None else ratio > cfg.K4_MIN_RATIO
    k4_text = (f"Ø R vor K. {_num(pooled['avg_r_gross'])} / Cluster-SE {_num(cse, 4)} = "
               f"{'-' if ratio is None else f'{ratio:.2f}'}")

    k5 = None if pooled["avg_r"] is None else pooled["avg_r"] > 0
    k5_text = f"Ø R nach K. {_num(pooled['avg_r'])}"
    return [
        ("K1", f"Ø R vor Kosten größer als das {cfg.K1_QUANTILE:.0%}-Quantil der Nullverteilung", k1_text, k1),
        ("K2", f"Ø R vor Kosten > 0 in mindestens {cfg.K2_MIN_DECADES} von {len(decade_means)} Jahrzehnten", k2_text, k2),
        ("K3", f"Ø R vor Kosten > 0 in mindestens {cfg.K3_MIN_SHARE:.0%} der Märkte mit mindestens "
               f"{cfg.K3_MIN_TRADES} Trades", k3_text, k3),
        ("K4", f"Ø R vor Kosten geteilt durch Cluster-SE größer als {cfg.K4_MIN_RATIO}", k4_text, k4),
        ("K5", "Ø R nach Kosten größer 0", k5_text, k5),
    ]


def _market_rows(real_trades, min_trades, direction=None):
    """Je Markt mit mindestens min_trades Trades (optional nur eine Richtung): market, n, avg_r_gross, avg_r."""
    markets = list(dict.fromkeys(t["market"] for t in real_trades))
    rows = []
    for market in markets:
        part = [t for t in real_trades
                if t["market"] == market and (direction is None or t["direction"] == direction)]
        stats = _group_stats(part)
        if stats["n"] >= min_trades:
            rows.append({"market": market, **stats})
    return rows


def _num(value, digits=3):
    return "-" if value is None else f"{value:+.{digits}f}"


def _p(value):
    return "-" if value is None else f"{value:.4f}"


def _yes_no(value):
    return "nicht bewertbar" if value is None else ("Ja" if value else "Nein")


def _comparison_lines(rows, cfg):
    quantile_titles = [f"Null {q:.0%}" for q in cfg.NULL_QUANTILES]
    header = (f"{'Bereich':<22}{'Kosten':<13}{'n echt':>8}{'Ø R echt':>10}{'Null Ø':>9}"
              + "".join(f"{title:>10}" for title in quantile_titles)
              + f"{'p-Wert':>9}{'Drift Ø R':>11}{'Kandidaten':>12}")
    lines = [header, "-" * len(header)]
    for row in rows:
        for kind, label in (("gross", "vor Kosten"), ("net", "nach Kosten")):
            cell = row[kind]
            first = kind == "gross"
            lines.append(
                f"{row['scope'] if first else '':<22}{label:<13}{row['n_real'] if first else '':>8}"
                f"{_num(cell['real']):>10}{_num(cell['null_mean']):>9}"
                + "".join(f"{_num(cell['quantiles'].get(q)):>10}" for q in cfg.NULL_QUANTILES)
                + f"{_p(cell['p']):>9}{_num(cell['drift']):>11}{row['n_candidates'] if first else '':>12}"
            )
    return lines


def _market_table(real_trades, cfg, direction=None):
    rows = _market_rows(real_trades, cfg.K3_MIN_TRADES, direction)
    title = "Alle Richtungen" if direction is None else direction
    lines = [f"{title} (Märkte mit mindestens {cfg.K3_MIN_TRADES} Trades):"]
    if not rows:
        return lines + ["  keine Märkte mit genug Trades"]
    header = f"{'Markt':<14}{'Trades':>8}{'Ø R vor K.':>12}{'Ø R nach K.':>13}"
    lines += [header, "-" * len(header)]
    for row in rows:
        lines.append(f"{row['market']:<14}{row['n']:>8}{_num(row['avg_r_gross'], 2):>12}{_num(row['avg_r'], 2):>13}")
    positive_gross = sum(1 for row in rows if row["avg_r_gross"] > 0)
    positive_net = sum(1 for row in rows if row["avg_r"] is not None and row["avg_r"] > 0)
    lines.append(f"Positive Märkte: vor Kosten {positive_gross} von {len(rows)}, nach Kosten {positive_net} von {len(rows)}")
    return lines


def _pooled_without_lines(real_trades, cfg):
    excluded = cfg.NULL_EXCLUDED_MARKETS
    kept = [t for t in real_trades if t["market"] not in excluded]
    header = (f"{'Bereich':<10}{'Trades':>8}{'Ø R vor K.':>12}{'Ø R nach K.':>13}"
              f"{'SE Cl. vor K.':>15}{'SE Cl. nach K.':>16}")
    lines = [f"Gepoolt ohne {', '.join(excluded)}:", header, "-" * len(header)]
    for title, direction in (("Alle", None), ("BUY", "BUY"), ("SELL", "SELL")):
        part = [t for t in kept if direction is None or t["direction"] == direction]
        s = _group_stats(part)
        lines.append(f"{title:<10}{s['n']:>8}{_num(s['avg_r_gross'], 3):>12}{_num(s['avg_r'], 3):>13}"
                     f"{_num(s['cse_gross'], 4):>15}{_num(s['cse'], 4):>16}")
    return lines


def render_report(all_trades, candidates):
    """Text der neuen Abschnitte: Nullvergleich, Kriterien K1 bis K5, Zusatzzahlen.

    all_trades: Trades aller Märkte (mit "market"), candidates: {Markt: {Richtung: [Pseudo-Trades]}}.
    """
    cfg = default_config
    real_trades = real_main_trades(all_trades)
    real_counts = Counter((t["market"], t["direction"]) for t in real_trades)

    groups, shortfalls, pool_trades = [], [], []
    for market, by_direction in candidates.items():
        for direction in DIRECTIONS:
            trades = by_direction.get(direction, [])
            pool_trades.extend(trades)
            wanted = real_counts.get((market, direction), 0)
            if not trades or not wanted:
                if wanted:
                    shortfalls.append(f"{market} {direction}: 0 Kandidaten für {wanted} echte Trades")
                continue
            if wanted > len(trades):
                shortfalls.append(f"{market} {direction}: nur {len(trades)} Kandidaten für {wanted} echte Trades")
            group = _arrays(trades)
            group["dir"] = DIRECTIONS.index(direction)
            group["k"] = min(wanted, len(trades))
            groups.append(group)

    lines = [
        "=== Nullvergleich (Permutation) ===",
        f"Pseudo-Muster aus den letzten {cfg.NULL_PATTERN_CANDLES} Kerzen; Kandidaten: alle Kerzen mit der Trendbedingung "
        "des Live-Filters (BUY nach Schluss unter EMA, SELL nach Schluss über EMA, Trend auf der Kerze vor dem Pseudo-Muster).",
        "Einstieg = Schluss, SL/TP, Mindestabstand, Haltedauer und Spread wie live, ohne Überlappungsregel.",
        f"Je Ziehung je Markt und Richtung so viele Kandidaten ohne Zurücklegen wie echte Haupt-Muster-Trades; "
        f"Seed {cfg.NULL_TEST_SEED}, {cfg.NULL_TEST_DRAWS} Ziehungen.",
        "p-Wert = Anteil der Ziehungen mit Ø R gleich oder größer als der echte Wert. Drift = Ø R aller Kandidaten ohne Ziehung.",
        "Bereiche nach Jahrzehnt: Null-Ø R aus den gezogenen Trades dieses Jahrzehnts (Ziehungen ohne Trade im Bereich zählen nicht).",
        "",
    ]
    for shortfall in shortfalls:
        lines.append(f"Hinweis: {shortfall}")
    if not groups:
        return "\n".join(lines + ["Keine Kandidaten oder keine echten Trades, kein Vergleich möglich."])
    rows = null_comparison(_arrays(real_trades), _arrays(pool_trades), groups)
    lines += _comparison_lines(rows, cfg)
    lines += ["", "=== Kriterien (vorab festgelegt) ==="]
    for name, description, numbers, passed in evaluate_criteria(real_trades, rows[0]):
        lines.append(f"{name}: {description}: {_yes_no(passed)}")
        lines.append(f"    {numbers}")
    lines += ["", "=== Zusatzzahlen ==="]
    for direction in (None, "BUY", "SELL"):
        lines += _market_table(real_trades, cfg, direction) + [""]
    lines += _pooled_without_lines(real_trades, cfg)
    return "\n".join(lines)
