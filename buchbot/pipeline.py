"""
Pipeline pro Lauf:
Marktzeit -> Kerzen -> veraltete Daten -> Detektoren -> Trendfilter -> SL/TP
-> Duplikat-Schutz -> Ausgabe (Log, CSV, Mail nur für Modus "notify").

Mit `at` läuft ein Probelauf: Kerzen nach `at` werden entfernt, es gibt weder
Mail noch CSV-Eintrag noch Änderung am Duplikat-Schutz.
"""

import logging
import os
from pathlib import Path

import pandas as pd

from buchbot import config as default_config
from buchbot import sltp
from buchbot import state as state_store
from buchbot.config import LOG_ONLY_DETECTORS, MARKETS, read_settings
from buchbot.data import get_candles, remove_incomplete_candle
from buchbot.detectors import run_detectors
from buchbot.filters import trend
from buchbot.models import to_utc
from buchbot.outputs import log_csv, mail


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


def _minute_of_week(day_hour):
    day, hour = day_hour
    return day * 1440 + hour * 60


def is_market_open(now, config):
    """Forex ist von MARKET_CLOSED_FROM bis MARKET_CLOSED_UNTIL (UTC) geschlossen. "24_7" hat keine Pause."""
    if getattr(config, "HOURS", "forex") == "24_7":
        return True
    now = to_utc(now)
    minute_of_week = now.weekday() * 1440 + now.hour * 60 + now.minute
    closed_from = _minute_of_week(config.MARKET_CLOSED_FROM)
    closed_until = _minute_of_week(config.MARKET_CLOSED_UNTIL)
    return not (closed_from <= minute_of_week < closed_until)


def detect_window(df, config):
    """Wertet die letzten EVAL_WINDOW_CANDLES geschlossenen Kerzen aus (0 = letzte Kerze)."""
    signals = []
    for back in range(config.EVAL_WINDOW_CANDLES):
        end = len(df) - back
        if end <= 0:
            break
        found = run_detectors(df.iloc[:end], config)
        for signal in found:
            signal.tags["prior_candle"] = back > 0
        signals.extend(found)
    return signals


def run_market(config, now, dry_run, fetch=get_candles, state_path=None, csv_path=None):
    """Wertet einen Markt aus. `config` ist eine Marktkonfiguration aus config.for_market."""
    state_path = state_path or BASE_DIR / config.STATE_FILE
    csv_path = csv_path or BASE_DIR / config.SIGNALS_CSV_FILE
    summary = {"signals": 0, "new": 0, "mailed": 0, "dry_run": dry_run}

    if not is_market_open(now, config):
        logger.info("Forex-Wochenende, Markt geschlossen. Lauf beendet (%s UTC)", now.isoformat())
        return summary

    df = fetch(config.SYMBOL, config.INTERVAL, config.LOOKBACK_CANDLES)
    if df is None or len(df) == 0:
        logger.error("Keine Kerzen erhalten. Lauf beendet, nächster Lauf versucht es erneut.")
        return summary

    if not dry_run and pd.Timestamp(df.index[-1]) > now + pd.Timedelta(minutes=config.CLOCK_TOLERANCE_MINUTES):
        logger.warning(
            "Systemuhr geht nach: neueste Kerze startet %s UTC, Systemzeit ist %s UTC. Lauf ohne Auswertung beendet.",
            pd.Timestamp(df.index[-1]).isoformat(), now.isoformat(),
        )
        return summary

    if dry_run:
        df = df[df.index <= now]
    df = remove_incomplete_candle(df, config.INTERVAL, now=now)
    if df is None or len(df) == 0:
        logger.warning("Keine geschlossenen Kerzen vorhanden. Lauf beendet.")
        return summary

    last_close = pd.Timestamp(df.index[-1]) + pd.Timedelta(config.INTERVAL)
    age_minutes = (now - last_close).total_seconds() / 60
    if age_minutes > config.STALE_MAX_MINUTES:
        logger.warning(
            "Daten veraltet: letzte geschlossene Kerze endete %s UTC, vor %.0f Minuten (Maximum %s)",
            last_close.isoformat(), age_minutes, config.STALE_MAX_MINUTES,
        )
        return summary

    signals = detect_window(df, config)
    signals = trend.apply(signals, df, config)
    signals = sltp.apply(signals, config)
    summary["signals"] = len(signals)

    state = state_store.load_state(state_path)
    new = [s for s in signals if not state_store.is_sent(state, state_store.signal_key(s))]
    summary["new"] = len(new)
    logger.info("Lauf: %d Signal(e), davon %d neu", len(signals), len(new))
    if not new:
        return summary

    log_csv.log_signals(new, config)
    if dry_run:
        logger.info("Probelauf mit --at: keine Mail, kein CSV-Eintrag, kein Zustandswechsel")
        return summary

    # Signale im Modus notify, die nicht gemailt werden (Schalter aus oder Versand fehlgeschlagen),
    # bleiben ungeloggt und ungemerkt, damit sie in einem späteren Lauf gesendet werden können.
    notify = [s for s in new if s.mode == "notify" and s.source not in LOG_ONLY_DETECTORS]
    deferred_ids = set()
    if notify and not config.NOTIFY_ENABLED:
        logger.info("[%s] Mail deaktiviert: %d Signal(e) werden zurückgestellt", config.MARKET, len(notify))
        deferred_ids = {id(s) for s in notify}
    elif notify:
        sent = mail.send_notifications(notify, config)
        summary["mailed"] = len(sent)
        sent_ids = {id(s) for s in sent}
        deferred_ids = {id(s) for s in notify if id(s) not in sent_ids}

    handled = [s for s in new if id(s) not in deferred_ids]
    log_csv.append_signals(handled, df, config.INTERVAL, csv_path, config)
    for signal in handled:
        state_store.mark_sent(state, state_store.signal_key(signal), now)
    state_store.save_state(state_path, state, now, config.STATE_RETENTION_DAYS)

    logger.info("[%s] Lauf beendet: %d verarbeitet, %d per Mail gesendet, %d zurückgestellt",
                config.MARKET, len(handled), summary["mailed"], len(deferred_ids))
    return summary


def run(at=None, now=None, fetch=get_candles, state_path=None, csv_path=None,
        settings=None, markets=None):
    """Wertet alle Märkte nacheinander aus. Ein Fehler in einem Markt stoppt die anderen nicht.

    Gibt ein Dict {markt: zusammenfassung} zurück. Unerwartete Fehler stehen im Schlüssel "error".
    """
    dry_run = at is not None
    if dry_run:
        now = to_utc(at)
    elif now is None:
        now = pd.Timestamp.now(tz="UTC")
    else:
        now = to_utc(now)

    settings = settings if settings is not None else read_settings(os.environ)
    names = markets or list(MARKETS)
    results = {}
    for name in names:
        config = default_config.for_market(name, settings)
        try:
            results[name] = run_market(config, now, dry_run, fetch, state_path, csv_path)
        except Exception as exc:  # ein Markt darf die anderen nicht stoppen
            logger.exception("[%s] Unerwarteter Fehler: %s", name, exc)
            results[name] = {"error": str(exc)}
    return results
