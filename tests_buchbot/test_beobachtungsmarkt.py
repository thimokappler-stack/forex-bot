import logging

import pandas as pd
import pytest

from buchbot import detectors
from buchbot import pipeline
from buchbot.config import MARKETS, for_market, read_settings
from buchbot.data import remove_incomplete_candle
from buchbot.models import Signal
from buchbot.outputs import mail
from tests_buchbot.test_outputs_mail import FakeSMTP


NOW = pd.Timestamp("2026-05-06 10:00", tz="UTC")  # letzte Kerze jedes Marktes schließt um 10:00


def candles(freq, periods, start="2026-05-06 00:00"):
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = [1.1000 + i * 0.00001 for i in range(periods)]
    return pd.DataFrame(
        {"open": close, "high": [c + 0.0005 for c in close],
         "low": [c - 0.0005 for c in close], "close": close},
        index=idx,
    )


def fake_fetch(df):
    calls = []

    def fetch(symbol, interval, lookback):
        calls.append((symbol, interval, lookback))
        return df.copy()

    fetch.calls = calls
    return fetch


def make_dummy(fire_at):
    """Feuert nur für (Intervall, Startzeit der letzten Kerze) aus fire_at."""
    def dummy_detector(df, config):
        last_start = pd.Timestamp(df.index[-1])
        if (config.INTERVAL, last_start) not in fire_at:
            return []
        entry = float(df["close"].iloc[-1])
        return [Signal(
            time=last_start + pd.Timedelta(config.INTERVAL),
            symbol=config.SYMBOL, interval=config.INTERVAL, source="dummy",
            pattern="Morning Star", direction="BUY", entry=entry, atr=0.001,
            market=config.MARKET,
            tags={"required_trend": None, "pattern_low": entry - 0.0025},
        )]
    return dummy_detector


@pytest.fixture
def fire_at(monkeypatch):
    fires = set()
    monkeypatch.setattr(detectors, "_REGISTRY", {})
    detectors.register("dummy", make_dummy(fires), "dummy")
    return fires


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("MAIL_USER", "bot@example.com")
    monkeypatch.setenv("MAIL_APP_PASSWORD", "test-passwort")
    monkeypatch.setenv("MAIL_TO", "empfaenger@example.com")
    return FakeSMTP


def market_config(name, mode="log_only", settings=None):
    cfg = for_market(name, read_settings(settings or {}))
    cfg.DETECTORS = {"dummy": mode}
    return cfg


def test_kerze_12_00_bis_12_30_ist_um_1229_offen_und_um_1230_geschlossen():
    df = pd.DataFrame(
        {"open": [1.1], "high": [1.2], "low": [1.0], "close": [1.1]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-05-06 12:00", tz="UTC")]),
    )
    assert len(remove_incomplete_candle(df, "30m", now=pd.Timestamp("2026-05-06 12:29", tz="UTC"))) == 0
    assert len(remove_incomplete_candle(df, "30m", now=pd.Timestamp("2026-05-06 12:30", tz="UTC"))) == 1


def test_30m_markt_hat_intervall_stale_schwelle_und_haltedauer():
    cfg = for_market("EURUSD_30M")
    assert cfg.INTERVAL == "30m"
    assert cfg.STALE_MAX_MINUTES == 90
    assert cfg.MAX_HOLD_CANDLES == 32
    assert cfg.DISPLAY_SYMBOL == "EUR/USD (30m)"
    assert cfg.SYMBOL == "EURUSD=X"
    assert set(cfg.DETECTORS.values()) == {"log_only"}


def test_haltedauer_ist_in_kerzen_und_je_markt_ueberschreibbar(monkeypatch):
    for name in ("EURUSD", "GBPUSD", "BTC", "ETH", "EURUSD_30M"):
        assert for_market(name).MAX_HOLD_CANDLES == 32, name
    monkeypatch.setitem(MARKETS["BTC"], "max_hold_candles", 96)
    assert for_market("BTC").MAX_HOLD_CANDLES == 96
    assert for_market("EURUSD").MAX_HOLD_CANDLES == 32


def test_bestehende_maerkte_bleiben_bei_15m_und_unveraenderten_werten():
    for name in ("EURUSD", "GBPUSD", "BTC", "ETH"):
        cfg = for_market(name)
        assert cfg.INTERVAL == "15m", name
        assert cfg.STALE_MAX_MINUTES == 45, name
        assert cfg.MAX_HOLD_CANDLES == 32, name
        assert cfg.NOTIFY_IGNORED is False, name


def test_30m_markt_ist_beobachtungsmarkt_ohne_mail_und_erzwingt_log_only():
    assert MARKETS["EURUSD_30M"]["observe_only"] is True
    settings = read_settings({"BUCH_NOTIFY_ENABLED": "1", "BUCH_NOTIFY_MARKETS": "EURUSD,EURUSD_30M",
                              "BUCH_DETECTOR_MODES": "candles_main=notify,candles_single=off"})
    cfg = for_market("EURUSD_30M", settings)
    assert cfg.NOTIFY_ENABLED is False
    assert cfg.NOTIFY_IGNORED is True
    assert cfg.DETECTORS["candles_main"] == "log_only"
    assert cfg.DETECTORS["candles_single"] == "off"

    normal = for_market("EURUSD", settings)
    assert normal.DETECTORS["candles_main"] == "notify"
    assert normal.NOTIFY_ENABLED is True


def test_fetch_bekommt_intervall_30m(fire_at, tmp_path):
    fetch = fake_fetch(candles("30min", 20))
    pipeline.run_market(market_config("EURUSD_30M"), NOW, False, fetch,
                        str(tmp_path / "s.json"), str(tmp_path / "c.csv"))
    assert fetch.calls == [("EURUSD=X", "30m", 403)]  # SR_LOOKBACK_CANDLES + SWING_N


def test_30m_markt_stale_schwelle_90_minuten(fire_at, tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    fire_at.add(("30m", pd.Timestamp("2026-05-06 09:30", tz="UTC")))
    paths = dict(state_path=str(tmp_path / "s.json"), csv_path=str(tmp_path / "c.csv"))

    # letzte Kerze schloss 10:00: nach 80 Minuten noch gültig (15m-Schwelle 45 würde greifen)
    frisch = pipeline.run_market(market_config("EURUSD_30M"), pd.Timestamp("2026-05-06 11:20", tz="UTC"),
                                 False, fake_fetch(candles("30min", 20)), paths["state_path"], paths["csv_path"])
    assert frisch["signals"] == 1
    assert "Daten veraltet" not in caplog.text

    # nach 100 Minuten veraltet
    alt = pipeline.run_market(market_config("EURUSD_30M"), pd.Timestamp("2026-05-06 11:40", tz="UTC"),
                              False, fake_fetch(candles("30min", 20)), str(tmp_path / "s2.json"), str(tmp_path / "c2.csv"))
    assert alt["signals"] == 0
    assert "Daten veraltet" in caplog.text


def test_30m_markt_sendet_nie_mail_auch_wenn_in_notify_markets(fire_at, tmp_path, smtp, caplog):
    caplog.set_level(logging.INFO)
    fire_at.add(("30m", pd.Timestamp("2026-05-06 09:30", tz="UTC")))
    settings = read_settings({"BUCH_NOTIFY_ENABLED": "1", "BUCH_NOTIFY_MARKETS": "EURUSD_30M"})
    cfg = for_market("EURUSD_30M", settings)
    cfg.DETECTORS = {"dummy": "notify"}  # selbst bei notify-Detektor keine Mail

    summary = pipeline.run_market(cfg, NOW, False, fake_fetch(candles("30min", 20)),
                                  str(tmp_path / "s.json"), str(tmp_path / "c.csv"))

    assert summary["signals"] == 1
    assert summary["mailed"] == 0
    assert smtp.instances == []
    assert "Beobachtungsmarkt" in caplog.text
    rows = pd.read_csv(tmp_path / "c.csv", sep=";", encoding="utf-8-sig")
    assert len(rows) == 1
    assert rows.iloc[0]["interval"] == "30m"


def test_15m_und_30m_markt_beeinflussen_zustand_und_csv_nicht(fire_at, tmp_path):
    fire_at.add(("15m", pd.Timestamp("2026-05-06 09:45", tz="UTC")))
    fire_at.add(("30m", pd.Timestamp("2026-05-06 09:30", tz="UTC")))
    state = str(tmp_path / "s.json")
    csv = str(tmp_path / "c.csv")

    # gleiches Muster, gleicher Symbol-Name und gleiche Signalzeit 10:00 in beiden Märkten
    first_15 = pipeline.run_market(market_config("EURUSD"), NOW, False, fake_fetch(candles("15min", 40)), state, csv)
    first_30 = pipeline.run_market(market_config("EURUSD_30M"), NOW, False, fake_fetch(candles("30min", 20)), state, csv)
    assert first_15["new"] == 1
    assert first_30["new"] == 1

    rows = pd.read_csv(csv, sep=";", encoding="utf-8-sig")
    assert list(rows["market"]) == ["EURUSD", "EURUSD_30M"]
    assert list(rows["interval"]) == ["15m", "30m"]

    # zweiter Lauf: beide Märkte kennen ihr eigenes Signal, keiner wird doppelt geschrieben
    again_15 = pipeline.run_market(market_config("EURUSD"), NOW, False, fake_fetch(candles("15min", 40)), state, csv)
    again_30 = pipeline.run_market(market_config("EURUSD_30M"), NOW, False, fake_fetch(candles("30min", 20)), state, csv)
    assert again_15["new"] == 0
    assert again_30["new"] == 0
    assert len(pd.read_csv(csv, sep=";", encoding="utf-8-sig")) == 2
