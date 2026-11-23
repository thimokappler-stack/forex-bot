"""
Duplikat-Schutz: merkt sich je Signal, ob es in die CSV geschrieben (logged)
und ob eine Mail gesendet wurde (mailed).

Schlüssel: Markt | Symbol | Muster | Kerzenzeit. Gespeichert wird in STATE_FILE als JSON,
je Schlüssel {"logged": ISO-Zeit oder null, "mailed": ISO-Zeit oder null}.
Einträge im alten Format (ohne Markt, Wert nur eine Zeit) werden als EURUSD übernommen.
Schreiben erfolgt atomar (temporäre Datei, dann ersetzen).
"""

import json
import logging
import os

import pandas as pd

from buchbot.models import to_utc


logger = logging.getLogger(__name__)

LEGACY_MARKET = "EURUSD"


def empty_state():
    return {"sent": {}}


def _migrate(key, value):
    if isinstance(value, dict):
        return key, value
    if key.count("|") == 2:
        key = f"{LEGACY_MARKET}|{key}"
    return key, {"logged": value, "mailed": value}


def load_state(path):
    """Lädt den Zustand. Fehlt die Datei, ist der Zustand leer. Defekte Datei: Fehler weiterreichen."""
    if not os.path.exists(path):
        return empty_state()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("sent", {})
    migrated = {}
    legacy = 0
    for key, value in entries.items():
        if not isinstance(value, dict):
            legacy += 1
        new_key, entry = _migrate(key, value)
        migrated[new_key] = entry
    if legacy:
        logger.info("Zustand: %d Eintrag/Einträge im alten Format als %s übernommen", legacy, LEGACY_MARKET)
    data["sent"] = migrated
    return data


def signal_key(signal):
    return f"{signal.market}|{signal.symbol}|{signal.pattern}|{to_utc(signal.time).isoformat()}"


def _entry(state, key):
    return state["sent"].get(key, {})


def is_logged(state, key):
    return _entry(state, key).get("logged") is not None


def is_mailed(state, key):
    return _entry(state, key).get("mailed") is not None


def mark_logged(state, key, now):
    state["sent"].setdefault(key, {"logged": None, "mailed": None})["logged"] = to_utc(now).isoformat()


def mark_mailed(state, key, now):
    state["sent"].setdefault(key, {"logged": None, "mailed": None})["mailed"] = to_utc(now).isoformat()


def prune(state, now, retention_days):
    """Entfernt Einträge, deren letzte Änderung älter als retention_days ist."""
    cutoff = to_utc(now) - pd.Timedelta(days=retention_days)

    def latest(entry):
        times = [pd.Timestamp(t) for t in entry.values() if t is not None]
        return max(times) if times else pd.Timestamp(0, tz="UTC")

    state["sent"] = {key: entry for key, entry in state["sent"].items() if latest(entry) >= cutoff}
    return state


def save_state(path, state, now, retention_days):
    prune(state, now, retention_days)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
    logger.debug("Zustand gespeichert: %d Einträge", len(state["sent"]))
