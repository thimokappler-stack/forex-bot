import pandas as pd

from buchbot import main as main_module


def test_parse_at_macht_naive_zeit_zu_utc():
    parsed = main_module.parse_at("2026-11-20T12:30:00")
    assert parsed == pd.Timestamp("2026-11-20 12:30", tz="UTC")


def test_parse_at_mit_z_suffix():
    parsed = main_module.parse_at("2026-11-20T12:30:00Z")
    assert parsed == pd.Timestamp("2026-11-20 12:30", tz="UTC")


def test_main_exit_0_bei_normalem_lauf(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "run", lambda at=None: calls.append(at) or {})
    assert main_module.main([]) == 0
    assert calls == [None]


def test_main_gibt_at_an_run_weiter(monkeypatch):
    calls = []
    monkeypatch.setattr(main_module, "run", lambda at=None: calls.append(at) or {})
    assert main_module.main(["--at", "2026-11-20T12:30:00Z"]) == 0
    assert calls == [pd.Timestamp("2026-11-20 12:30", tz="UTC")]


def test_main_exit_1_bei_unerwartetem_fehler(monkeypatch, caplog):
    def boom(at=None):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(main_module, "run", boom)
    assert main_module.main([]) == 1
    assert "Unerwarteter Fehler" in caplog.text
