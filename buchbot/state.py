"""
Duplikat-Schutz: merkt sich, welche Signale schon verarbeitet wurden.

Schlüssel: Symbol | Muster | Kerzenzeit. Gespeichert wird in STATE_FILE als JSON.
Schreiben erfolgt atomar (temporäre Datei, dann ersetzen).
"""

import json
import logging
import os

import pandas as pd

from buchbot.models import to_utc


logger = logging.getLogger(__name__)


def empty_state():
    return {"sent": {}}


def load_state(path):
    """Lädt den Zustand. Fehlt die Datei, ist der Zustand leer. Defekte Datei: Fehler weiterreichen."""
    if not os.path.exists(path):
        return empty_state()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("sent", {})
    return data


def signal_key(signal):
    return f"{signal.symbol}|{signal.pattern}|{to_utc(signal.time).isoformat()}"


def is_sent(state, key):
    return key in state["sent"]


def mark_sent(state, key, now):
    state["sent"][key] = to_utc(now).isoformat()


def prune(state, now, retention_days):
    """Entfernt Einträge, die älter als retention_days sind."""
    cutoff = to_utc(now) - pd.Timedelta(days=retention_days)
    state["sent"] = {
        key: sent_at for key, sent_at in state["sent"].items()
        if pd.Timestamp(sent_at) >= cutoff
    }
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
