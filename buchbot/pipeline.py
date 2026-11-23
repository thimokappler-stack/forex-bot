"""
Pipeline pro Lauf:
Marktzeit -> Kerzen -> veraltete Daten -> Detektoren -> Trendfilter -> SL/TP
-> Duplikat-Schutz -> Ausgabe (Log, CSV, Mail nur für Modus "notify").

Mit `at` läuft ein Probelauf: Kerzen nach `at` werden entfernt, es gibt weder
Mail noch CSV-Eintrag noch Änderung am Duplikat-Schutz.
"""

import logging
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

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
    """Forex ist von MARKET_CLOSED_FROM bis MARKET_CLOSED_UNTIL (UTC) geschlossen. "24_7" hat keine Pause.
    "futures_gold" ist nach New Yorker Zeit geschlossen (Sommer- und Winterzeit über zoneinfo)."""
    hours = getattr(config, "HOURS", "forex")
    if hours == "24_7":
        return True
    now = to_utc(now)
    if hours == "futures_gold":
        return _gold_open(now)
    minute_of_week = now.weekday() * 1440 + now.hour * 60 + now.minute
    closed_from = _minute_of_week(config.MARKET_CLOSED_FROM)
    closed_until = _minute_of_week(config.MARKET_CLOSED_UNTIL)
    return not (closed_from <= minute_of_week < closed_until)


def _gold_open(now_utc):
    ny = now_utc.tz_convert(ZoneInfo("America/New_York"))
    minute = ny.hour * 60 + ny.minute
    weekday = ny.weekday()
    if weekday == 5:                       # Samstag
        return False
    if weekday == 6:                       # Sonntag: offen ab 18:00
        return minute >= 18 * 60
    if weekday == 4:                       # Freitag: geschlossen ab 17:00
        return minute < 17 * 60
    return not (17 * 60 <= minute < 18 * 60)  # Montag bis Donnerstag: tägliche Pause 17:00-18:00


def fetch_candles(fetch, config):
    """Holt Kerzen. Bei leerer Antwort oder Fehler genau ein Wiederholungsversuch nach FETCH_RETRY_SECONDS."""
    for attempt in range(2):
        if attempt:
            time.sleep(config.FETCH_RETRY_SECONDS)
        try:
            df = fetch(config.SYMBOL, config.INTERVAL, config.LOOKBACK_CANDLES)
        except Exception as exc:
            if attempt == 1:
                raise
            logger.warning("[%s] Abruf fehlgeschlagen (%s), Wiederholung in %s Sekunden",
                           config.MARKET, exc, config.FETCH_RETRY_SECONDS)
            continue
        if df is not None and len(df) > 0:
            return df
        if attempt == 0:
            logger.warning("[%s] Leere Antwort, Wiederholung in %s Sekunden",
                           config.MARKET, config.FETCH_RETRY_SECONDS)
    return df


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

    if config.NOTIFY_IGNORED:
        logger.info("[%s] Beobachtungsmarkt: in BUCH_NOTIFY_MARKETS genannt, Mails werden ignoriert",
                    config.MARKET)

    if not is_market_open(now, config):
        logger.info("[%s] Markt geschlossen, Lauf beendet (%s UTC)", config.MARKET, now.isoformat())
        return summary

    df = fetch_candles(fetch, config)
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
    to_log = [s for s in signals if not state_store.is_logged(state, state_store.signal_key(s))]
    mail_candidates = [
        s for s in signals
        if s.mode == "notify" and s.source not in LOG_ONLY_DETECTORS
        and not state_store.is_mailed(state, state_store.signal_key(s))
    ]
    to_mail = mail_candidates if config.NOTIFY_ENABLED else []
    if mail_candidates and not to_mail:
        logger.info("[%s] Mail deaktiviert: %d Signal(e) nur im Log und in der CSV",
                    config.MARKET, len(mail_candidates))

    pending_ids = {id(s) for s in to_log} | {id(s) for s in to_mail}
    summary["new"] = len(pending_ids)
    logger.info("Lauf: %d Signal(e), davon %d offen", len(signals), len(pending_ids))
    if not pending_ids:
        return summary

    log_csv.log_signals(to_log, config)
    if dry_run:
        logger.info("Probelauf mit --at: keine Mail, kein CSV-Eintrag, kein Zustandswechsel")
        return summary

    if to_log:
        log_csv.append_signals(to_log, df, config.INTERVAL, csv_path, config)
        for signal in to_log:
            state_store.mark_logged(state, state_store.signal_key(signal), now)

    if to_mail:
        sent = mail.send_notifications(to_mail, config)
        summary["mailed"] = len(sent)
        for signal in sent:
            state_store.mark_mailed(state, state_store.signal_key(signal), now)

    state_store.save_state(state_path, state, now, config.STATE_RETENTION_DAYS)
    logger.info("[%s] Lauf beendet: %d in CSV, %d per Mail gesendet, %d Mail(s) fehlgeschlagen",
                config.MARKET, len(to_log), summary["mailed"], len(to_mail) - summary["mailed"])
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
    for index, name in enumerate(names):
        if index:
            time.sleep(default_config.MARKET_PAUSE_SECONDS)
        config = default_config.for_market(name, settings)
        try:
            results[name] = run_market(config, now, dry_run, fetch, state_path, csv_path)
        except Exception as exc:  # ein Markt darf die anderen nicht stoppen
            logger.exception("[%s] Unerwarteter Fehler: %s", name, exc)
            results[name] = {"error": str(exc)}
    return results
