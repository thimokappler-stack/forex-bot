import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from buchbot import config as default_config
from buchbot import pipeline, sltp
from buchbot.config import read_settings, for_market
from buchbot.models import Signal
from buchbot.outputs.mail import build_body


PROJEKT = Path(__file__).resolve().parent.parent
NEUE_MAERKTE = ["USDJPY", "AUDUSD", "GBPJPY", "USDCAD", "USDCHF", "EURJPY", "GOLD"]

# Markt, Symbol, Pip-Größe, Nachkommastellen, Mindestabstand, Spread, Tweezer absolut, Tweezer ATR-Anteil, Handelszeiten, Einheit
TABELLE = [
    ("USDJPY", "USDJPY=X", 0.01, 3, 5, 1.0, 0.015, None, "forex", "Pips"),
    ("AUDUSD", "AUDUSD=X", 0.0001, 5, 5, 1.0, 0.00015, None, "forex", "Pips"),
    ("GBPJPY", "GBPJPY=X", 0.01, 3, 5, 2.0, 0.015, None, "forex", "Pips"),
    ("USDCAD", "USDCAD=X", 0.0001, 5, 5, 1.5, 0.00015, None, "forex", "Pips"),
    ("USDCHF", "USDCHF=X", 0.0001, 5, 5, 1.5, 0.00015, None, "forex", "Pips"),
    ("EURJPY", "EURJPY=X", 0.01, 3, 5, 1.5, 0.015, None, "forex", "Pips"),
    ("GOLD", "GC=F", 1.0, 2, 2, 0.5, None, 0.15, "futures_gold", "USD"),
]


def _signal(entry, pattern_low, atr, direction="BUY", market="USDJPY"):
    return Signal(
        time=pd.Timestamp("2026-01-14 10:00", tz="UTC"), symbol="USDJPY=X", interval="15m",
        source="candles_main", pattern="Morning Star", direction=direction, entry=entry, atr=atr,
        market=market, tags={"pattern_low": pattern_low},
    )


@pytest.mark.parametrize(
    "name,symbol,pip,decimals,min_sl,spread,tweezer,fraction,hours,unit", TABELLE,
)
def test_neue_maerkte_haben_die_vereinbarten_werte(
    name, symbol, pip, decimals, min_sl, spread, tweezer, fraction, hours, unit,
):
    cfg = for_market(name, read_settings({}))
    assert cfg.SYMBOL == symbol
    assert cfg.PIP_SIZE == pip
    assert cfg.PRICE_DECIMALS == decimals
    assert cfg.MIN_SL_PIPS == min_sl
    assert cfg.SPREAD_PIPS == spread
    assert cfg.TWEEZER_TOLERANCE == tweezer
    assert cfg.TWEEZER_ATR_FRACTION == fraction
    assert cfg.HOURS == hours
    assert cfg.RISK_UNIT == unit
    assert cfg.INTERVAL == "15m"
    assert cfg.OBSERVE_ONLY is True
    assert cfg.DETECTORS == {"candles_main": "log_only", "candles_single": "log_only"}


def test_anzeigenamen_der_neuen_maerkte():
    erwartet = {"USDJPY": "USD/JPY", "AUDUSD": "AUD/USD", "GBPJPY": "GBP/JPY",
                "USDCAD": "USD/CAD", "USDCHF": "USD/CHF", "EURJPY": "EUR/JPY", "GOLD": "Gold"}
    for name, display in erwartet.items():
        assert for_market(name, read_settings({})).DISPLAY_SYMBOL == display


def test_yen_paar_berechnet_sl_tp_und_risiko_in_pips():
    cfg = for_market("USDJPY", read_settings({}))
    signal = _signal(entry=150.000, pattern_low=149.700, atr=0.200)
    kept = sltp.apply([signal], cfg)
    assert len(kept) == 1
    # SL = 149.700 - 0.5 * 0.200 = 149.600, Abstand 0.400 = 40 Pips bei Pip 0.01
    assert signal.sl == pytest.approx(149.600)
    assert signal.risk_pips == pytest.approx(40.0)
    # TP = 150.000 + 2 * 0.400 = 150.800
    assert signal.tp == pytest.approx(150.800)
    assert signal.rr == 2.0


def test_yen_paar_formatiert_drei_nachkommastellen_und_pips():
    cfg = for_market("USDJPY", read_settings({}))
    signal = _signal(entry=150.000, pattern_low=149.700, atr=0.200)
    sltp.apply([signal], cfg)
    text = build_body([signal], cfg)
    assert "Einstieg: 150.000" in text
    assert "Stop-Loss: 149.600" in text
    assert "Take-Profit: 150.800" in text
    assert "Risiko: 40.0 Pips" in text


def test_gold_formatiert_zwei_nachkommastellen_und_usd():
    cfg = for_market("GOLD", read_settings({}))
    signal = _signal(entry=2350.123, pattern_low=2340.0, atr=4.0, market="GOLD")
    kept = sltp.apply([signal], cfg)
    assert len(kept) == 1
    # SL = 2340 - 0.5 * 4 = 2338, Abstand 12.123 USD, TP = 2350.123 + 2 * 12.123
    assert signal.risk_pips == pytest.approx(12.123)
    text = build_body([signal], cfg)
    assert "Einstieg: 2350.12" in text
    assert "Stop-Loss: 2338.00" in text
    assert "Take-Profit: 2374.37" in text
    assert "Risiko: 12.1 USD" in text


@pytest.mark.parametrize("name", NEUE_MAERKTE)
def test_neue_maerkte_senden_auch_bei_notify_an_keine_mail(name):
    settings = read_settings({"BUCH_NOTIFY_ENABLED": "1"})
    assert for_market(name, settings).NOTIFY_ENABLED is False


@pytest.mark.parametrize("name", NEUE_MAERKTE)
def test_neue_maerkte_ignorieren_mail_auch_wenn_in_notify_markets(name):
    settings = read_settings({"BUCH_NOTIFY_ENABLED": "1", "BUCH_NOTIFY_MARKETS": name})
    cfg = for_market(name, settings)
    assert cfg.NOTIFY_ENABLED is False
    assert cfg.NOTIFY_IGNORED is True


@pytest.mark.parametrize("ortszeit,offen", [
    # Winter (EST, UTC-5)
    ("2026-01-11 17:59", False),   # Sonntag vor 18:00
    ("2026-01-11 18:00", True),    # Sonntag ab 18:00
    ("2026-01-12 17:30", False),   # Montag tägliche Pause
    ("2026-01-16 16:59", True),    # Freitag vor 17:00
    ("2026-01-16 17:01", False),   # Freitag nach 17:00
    # Sommer (EDT, UTC-4)
    ("2026-07-05 17:59", False),   # Sonntag vor 18:00
    ("2026-07-05 18:00", True),    # Sonntag ab 18:00
    ("2026-07-08 17:30", False),   # Mittwoch tägliche Pause
    ("2026-07-10 16:59", True),    # Freitag vor 17:00
    ("2026-07-10 17:01", False),   # Freitag nach 17:00
])
def test_gold_handelszeiten_nach_new_yorker_zeit(ortszeit, offen):
    cfg = for_market("GOLD", read_settings({}))
    now = pd.Timestamp(ortszeit, tz="America/New_York")
    assert pipeline.is_market_open(now, cfg) is offen


def test_gold_ohne_auswertung_und_ohne_veraltet_warnung_in_der_pause(tmp_path, caplog):
    cfg = for_market("GOLD", read_settings({}))
    now = pd.Timestamp("2026-07-08 17:30", tz="America/New_York")
    aufrufe = []

    def fetch(*args, **kwargs):
        aufrufe.append(args)
        return None

    with caplog.at_level("WARNING"):
        summary = pipeline.run_market(cfg, now.tz_convert("UTC"), False, fetch,
                                      tmp_path / "s.json", tmp_path / "c.csv")
    assert aufrufe == []
    assert summary["signals"] == 0
    assert "veraltet" not in caplog.text


def test_wiederholung_nach_leerer_antwort(monkeypatch):
    cfg = for_market("USDJPY", read_settings({}))
    df = pd.DataFrame({"close": [1.0]})
    antworten = [None, df]
    aufrufe, pausen = [], []
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: pausen.append(s))

    def fetch(*args):
        aufrufe.append(args)
        return antworten.pop(0)

    assert pipeline.fetch_candles(fetch, cfg) is df
    assert len(aufrufe) == 2
    assert pausen == [cfg.FETCH_RETRY_SECONDS] == [5]


def test_wiederholung_nach_fehler_und_weitergabe_nach_zweitem_fehler(monkeypatch):
    cfg = for_market("USDJPY", read_settings({}))
    df = pd.DataFrame({"close": [1.0]})
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    versuche = iter([RuntimeError("Netz weg"), df])

    def fetch(*args):
        nächster = next(versuche)
        if isinstance(nächster, Exception):
            raise nächster
        return nächster

    assert pipeline.fetch_candles(fetch, cfg) is df

    def immer_fehler(*args):
        raise RuntimeError("Netz weg")

    with pytest.raises(RuntimeError):
        pipeline.fetch_candles(immer_fehler, cfg)


def test_pause_zwischen_maerkten_und_wiederholung(monkeypatch, tmp_path):
    pausen = []
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: pausen.append(s))
    settings = read_settings({})
    now = pd.Timestamp("2026-01-14 10:00", tz="UTC")

    pipeline.run(now=now, fetch=lambda *args: None, settings=settings,
                 markets=["EURUSD", "GBPUSD", "GOLD"],
                 state_path=tmp_path / "s.json", csv_path=tmp_path / "c.csv")
    # Je Markt eine Wiederholung nach 5 s, zwischen den Märkten 1 s Pause
    assert pausen == [5, 1, 5, 1, 5]


def test_fehler_in_einem_markt_stoppt_die_anderen(tmp_path):
    settings = read_settings({})
    now = pd.Timestamp("2026-01-14 10:00", tz="UTC")

    def fetch(symbol, interval, lookback):
        if symbol == "GC=F":
            raise RuntimeError("Gold-Abruf kaputt")
        return None

    results = pipeline.run(now=now, fetch=fetch, settings=settings, markets=["GOLD", "EURUSD"],
                           state_path=tmp_path / "s.json", csv_path=tmp_path / "c.csv")
    assert "error" in results["GOLD"]
    assert "error" not in results["EURUSD"]


def test_konstanten_fuer_pause_und_wiederholung():
    assert default_config.MARKET_PAUSE_SECONDS == 1
    assert default_config.FETCH_RETRY_SECONDS == 5


@pytest.mark.parametrize("modul", ["buchbot.backtest", "buchbot.evaluate"])
def test_backtest_und_evaluate_akzeptieren_neue_maerkte(modul):
    ergebnis = subprocess.run(
        [sys.executable, "-m", modul, "--help"], cwd=PROJEKT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    for name in NEUE_MAERKTE:
        assert name in ergebnis.stdout
