import json
import os

import pandas as pd
import pytest

from buchbot import state
from buchbot.models import Signal


def make_signal(time="2026-05-06 10:00", pattern="Morning Star"):
    return Signal(
        time=pd.Timestamp(time, tz="UTC"), symbol="EURUSD=X", interval="15m",
        source="candles_main", pattern=pattern, direction="BUY",
        entry=1.1, atr=0.001,
    )


def test_signal_key_enthaelt_symbol_muster_und_kerzenzeit():
    key = state.signal_key(make_signal())
    assert key == "EURUSD=X|Morning Star|2026-05-06T10:00:00+00:00"


def test_fehlende_datei_ergibt_leeren_zustand(tmp_path):
    loaded = state.load_state(str(tmp_path / "state_new.json"))
    assert loaded == {"sent": {}}


def test_mark_sent_und_is_sent(tmp_path):
    st = state.empty_state()
    key = state.signal_key(make_signal())
    assert not state.is_sent(st, key)
    state.mark_sent(st, key, pd.Timestamp("2026-05-06 10:00", tz="UTC"))
    assert state.is_sent(st, key)


def test_save_und_load_roundtrip(tmp_path):
    path = str(tmp_path / "state_new.json")
    now = pd.Timestamp("2026-05-06 10:00", tz="UTC")
    st = state.empty_state()
    key = state.signal_key(make_signal())
    state.mark_sent(st, key, now)
    state.save_state(path, st, now, retention_days=7)

    loaded = state.load_state(path)
    assert state.is_sent(loaded, key)


def test_eintraege_aelter_als_sieben_tage_werden_entfernt(tmp_path):
    path = str(tmp_path / "state_new.json")
    now = pd.Timestamp("2026-05-10 10:00", tz="UTC")
    st = state.empty_state()
    old_key = "alt"
    recent_key = "neu"
    st["sent"][old_key] = pd.Timestamp("2026-05-02 10:00", tz="UTC").isoformat()
    st["sent"][recent_key] = pd.Timestamp("2026-05-05 10:00", tz="UTC").isoformat()

    state.save_state(path, st, now, retention_days=7)

    loaded = state.load_state(path)
    assert old_key not in loaded["sent"]
    assert recent_key in loaded["sent"]


def test_atomares_schreiben_hinterlaesst_keine_temp_datei(tmp_path):
    path = str(tmp_path / "state_new.json")
    state.save_state(path, state.empty_state(), pd.Timestamp("2026-05-06 10:00", tz="UTC"), 7)
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"sent": {}}


def test_defekte_datei_wirft_fehler(tmp_path):
    path = tmp_path / "state_new.json"
    path.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        state.load_state(str(path))
