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
        entry=1.1, atr=0.001, market="EURUSD",
    )


def test_signal_key_enthaelt_markt_symbol_muster_und_kerzenzeit():
    key = state.signal_key(make_signal())
    assert key == "EURUSD|EURUSD=X|Morning Star|2026-05-06T10:00:00+00:00"


def test_gleiches_signal_in_verschiedenen_maerkten_hat_verschiedene_schluessel():
    eur = make_signal()
    gbp = make_signal()
    gbp.market = "GBPUSD"
    assert state.signal_key(eur) != state.signal_key(gbp)


def test_fehlende_datei_ergibt_leeren_zustand(tmp_path):
    loaded = state.load_state(str(tmp_path / "state_new.json"))
    assert loaded == {"sent": {}}


def test_mark_logged_und_mark_mailed_sind_getrennt(tmp_path):
    st = state.empty_state()
    key = state.signal_key(make_signal())
    now = pd.Timestamp("2026-05-06 10:00", tz="UTC")
    assert not state.is_logged(st, key)
    assert not state.is_mailed(st, key)
    state.mark_logged(st, key, now)
    assert state.is_logged(st, key)
    assert not state.is_mailed(st, key)
    state.mark_mailed(st, key, now)
    assert state.is_mailed(st, key)


def test_save_und_load_roundtrip(tmp_path):
    path = str(tmp_path / "state_new.json")
    now = pd.Timestamp("2026-05-06 10:00", tz="UTC")
    st = state.empty_state()
    key = state.signal_key(make_signal())
    state.mark_logged(st, key, now)
    state.mark_mailed(st, key, now)
    state.save_state(path, st, now, retention_days=7)

    loaded = state.load_state(path)
    assert state.is_logged(loaded, key)
    assert state.is_mailed(loaded, key)


def test_eintraege_aelter_als_sieben_tage_werden_entfernt(tmp_path):
    path = str(tmp_path / "state_new.json")
    now = pd.Timestamp("2026-05-10 10:00", tz="UTC")
    st = state.empty_state()
    st["sent"]["alt"] = {"logged": pd.Timestamp("2026-05-02 10:00", tz="UTC").isoformat(), "mailed": None}
    st["sent"]["neu"] = {"logged": pd.Timestamp("2026-05-02 10:00", tz="UTC").isoformat(),
                         "mailed": pd.Timestamp("2026-05-09 10:00", tz="UTC").isoformat()}

    state.save_state(path, st, now, retention_days=7)

    loaded = state.load_state(path)
    assert "alt" not in loaded["sent"]
    assert "neu" in loaded["sent"]


def test_altes_format_ohne_markt_wird_als_eurusd_uebernommen(tmp_path):
    path = tmp_path / "state_new.json"
    path.write_text(json.dumps({"sent": {
        "EURUSD=X|Morning Star|2026-05-06T10:00:00+00:00": "2026-05-06T10:00:00+00:00",
    }}), encoding="utf-8")

    loaded = state.load_state(str(path))

    key = "EURUSD|EURUSD=X|Morning Star|2026-05-06T10:00:00+00:00"
    assert loaded["sent"][key] == {"logged": "2026-05-06T10:00:00+00:00",
                                   "mailed": "2026-05-06T10:00:00+00:00"}
    assert state.is_mailed(loaded, key)


def test_altes_format_mit_markt_im_schluessel_bleibt_erhalten(tmp_path):
    path = tmp_path / "state_new.json"
    path.write_text(json.dumps({"sent": {
        "GBPUSD|GBPUSD=X|Morning Star|2026-05-06T10:00:00+00:00": "2026-05-06T10:00:00+00:00",
    }}), encoding="utf-8")

    loaded = state.load_state(str(path))

    assert list(loaded["sent"]) == ["GBPUSD|GBPUSD=X|Morning Star|2026-05-06T10:00:00+00:00"]
    assert state.is_logged(loaded, "GBPUSD|GBPUSD=X|Morning Star|2026-05-06T10:00:00+00:00")


def test_altes_format_wird_beim_start_nicht_zum_fehler_und_altersbereinigt(tmp_path):
    path = tmp_path / "state_new.json"
    path.write_text(json.dumps({"sent": {
        "EURUSD=X|Morning Star|2026-04-01T10:00:00+00:00": "2026-04-01T10:00:00+00:00",
    }}), encoding="utf-8")

    loaded = state.load_state(str(path))
    state.save_state(str(path), loaded, pd.Timestamp("2026-05-06 10:00", tz="UTC"), retention_days=7)

    assert state.load_state(str(path))["sent"] == {}


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
