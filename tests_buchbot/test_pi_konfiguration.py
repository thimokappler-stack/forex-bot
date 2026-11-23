import pandas as pd
import pytest

from buchbot import detectors
from buchbot import pipeline
from buchbot.config import for_market, read_settings
from buchbot.models import Signal
from tests_buchbot.test_beobachtungsmarkt import candles, fake_fetch, smtp  # noqa: F401


# Einstellungen der .env auf dem Raspberry Pi (ohne BUCH_OBSERVE_ONLY_MARKETS)
PI_ENV = {
    "BUCH_NOTIFY_ENABLED": "1",
    "BUCH_NOTIFY_MARKETS": "EURUSD,GBPUSD,BTC,ETH",
    "BUCH_DETECTOR_MODES": "candles_main=notify,candles_single=log_only",
}

MAIL_AN = ("EURUSD", "GBPUSD", "BTC", "ETH")
STANDARD_BEOBACHTUNG = ("USDJPY", "AUDUSD", "GBPJPY", "USDCAD", "USDCHF", "EURJPY", "GOLD")
NOW = pd.Timestamp("2026-05-06 10:00", tz="UTC")
LETZTE_KERZE = pd.Timestamp("2026-05-06 09:45", tz="UTC")


@pytest.mark.parametrize("name", MAIL_AN)
def test_pi_einstellungen_schalten_mail_fuer_die_vier_bisherigen_maerkte_an(name):
    cfg = for_market(name, read_settings(PI_ENV))
    assert cfg.NOTIFY_ENABLED is True
    assert cfg.OBSERVE_ONLY is False
    assert cfg.DETECTORS["candles_main"] == "notify"
    assert cfg.DETECTORS["candles_single"] == "log_only"


@pytest.mark.parametrize("name", STANDARD_BEOBACHTUNG + ("EURUSD_30M",))
def test_pi_einstellungen_halten_beobachtungsmaerkte_ohne_mail(name):
    cfg = for_market(name, read_settings(PI_ENV))
    assert cfg.NOTIFY_ENABLED is False
    assert cfg.OBSERVE_ONLY is True
    assert cfg.DETECTORS["candles_main"] == "log_only"


def test_pi_einstellungen_ohne_observe_liste_nutzen_den_standard():
    settings = read_settings(PI_ENV)
    assert settings["observe_only_markets"] == STANDARD_BEOBACHTUNG


@pytest.fixture
def pi_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(detectors, "_REGISTRY", {})
    detectors.register("candles_main", pi_detector, "dummy")
    return {"state_path": str(tmp_path / "state_new.json"), "csv_path": str(tmp_path / "signals_log.csv")}


def pi_detector(df, config):
    """Feuert auf die letzte geschlossene Kerze mit 0.30 Abstand zum Einstieg (über allen Mindestabständen)."""
    if pd.Timestamp(df.index[-1]) != LETZTE_KERZE:
        return []
    entry = float(df["close"].iloc[-1])
    return [Signal(
        time=LETZTE_KERZE + pd.Timedelta(config.INTERVAL),
        symbol=config.SYMBOL, interval=config.INTERVAL, source="dummy",
        pattern="Morning Star", direction="BUY", entry=entry, atr=0.05,
        market=config.MARKET,
        tags={"required_trend": None, "pattern_low": entry - 0.30},
    )]


def run_pi_market(name, paths):
    cfg = for_market(name, read_settings(PI_ENV))
    return pipeline.run_market(cfg, NOW, False, fake_fetch(candles("15min", 40)),
                               paths["state_path"], paths["csv_path"])


def test_pi_einstellungen_mail_nur_fuer_eurusd(pi_pipeline, smtp):
    summary = run_pi_market("EURUSD", pi_pipeline)
    assert summary["signals"] == 1
    assert summary["mailed"] == 1
    assert len(smtp.instances) == 1
    assert len(smtp.instances[0].sent) == 1


def test_pi_einstellungen_keine_mail_fuer_usdjpy_signal_aber_csv(pi_pipeline, smtp):
    summary = run_pi_market("USDJPY", pi_pipeline)
    assert summary["signals"] == 1
    assert summary["mailed"] == 0
    assert smtp.instances == []
    rows = pd.read_csv(pi_pipeline["csv_path"], sep=";", encoding="utf-8-sig")
    assert list(rows["market"]) == ["USDJPY"]
