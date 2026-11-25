import argparse
import io
from contextlib import redirect_stdout
import pandas as pd
import pytest

from buchbot import backtest
from buchbot import config as real_config
from buchbot import evaluate
from buchbot import main as cli_module
from buchbot import pipeline
from buchbot.config import SettingsError, for_market, read_settings
from buchbot.detectors import candles_main
from buchbot.detectors.candles_main import Candle
from buchbot.models import Signal
from buchbot.outputs import mail
from tests_buchbot.test_evaluate import SIGNAL_FIELDS, candle, make_df, signal_row, write_csv
from tests_buchbot.test_outputs_mail import FakeSMTP


def make_signal(direction="BUY", pattern="Morning Star", market="GBPUSD"):
    return Signal(
        time=pd.Timestamp("2026-05-06 10:15", tz="UTC"), symbol="GBPUSD=X", interval="15m",
        source="candles_main", pattern=pattern, direction=direction,
        entry=1.2500, atr=0.001, sl=1.2480, tp=1.2540, risk_pips=20.0, rr=2.0,
        mode="notify", market=market,
    )


def make_candles(periods=40, start="2026-05-06 00:00"):
    idx = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    close = [1.1000 + i * 0.00001 for i in range(periods)]
    return pd.DataFrame(
        {"open": close, "high": [c + 0.0005 for c in close],
         "low": [c - 0.0005 for c in close], "close": close},
        index=idx,
    )


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("MAIL_USER", "bot@example.com")
    monkeypatch.setenv("MAIL_APP_PASSWORD", "test-passwort")
    monkeypatch.setenv("MAIL_TO", "empfaenger@example.com")
    return FakeSMTP


# --- Fünf-Kerzen-Muster: RISEFALL_MIN_COUNTER_CANDLES ---

def rising_three_candles():
    """K1 lang grün, K2-K4 klein (zwei rot, eine grün), K5 lang grün über K1."""
    return [
        Candle(1.0, 2.0, 0.95, 1.9),
        Candle(1.5, 1.55, 1.40, 1.45),
        Candle(1.5, 1.55, 1.45, 1.48),
        Candle(1.46, 1.52, 1.44, 1.50),
        Candle(1.4, 2.30, 1.38, 2.25),
    ]


def test_rising_three_mit_zwei_gegenlaeufigen_nur_bei_n2(monkeypatch):
    candles = rising_three_candles()
    monkeypatch.setattr(real_config, "RISEFALL_MIN_COUNTER_CANDLES", 2)
    assert candles_main.rising_three_methods(candles, atr=1.0) is True
    monkeypatch.setattr(real_config, "RISEFALL_MIN_COUNTER_CANDLES", 3)
    assert candles_main.rising_three_methods(candles, atr=1.0) is False


def test_rising_three_mit_drei_gegenlaeufigen_bei_n2_und_n3(monkeypatch):
    candles = rising_three_candles()
    candles[3] = Candle(1.46, 1.52, 1.44, 1.45)  # K4 jetzt auch rot
    monkeypatch.setattr(real_config, "RISEFALL_MIN_COUNTER_CANDLES", 3)
    assert candles_main.rising_three_methods(candles, atr=1.0) is True


# --- Tweezer-Toleranz je Markt ---

def test_tweezer_toleranz_absolut_fuer_forex():
    assert candles_main.tweezer_tolerance(for_market("EURUSD"), 0.002) == pytest.approx(0.00015)
    assert candles_main.tweezer_tolerance(for_market("GBPUSD"), 0.002) == pytest.approx(0.00015)


def test_tweezer_toleranz_als_atr_anteil_fuer_krypto():
    assert candles_main.tweezer_tolerance(for_market("BTC"), 100.0) == pytest.approx(15.0)
    assert candles_main.tweezer_tolerance(for_market("ETH"), 40.0) == pytest.approx(6.0)


# --- Marktzeiten ---

def test_forex_ist_freitag_nach_22_uhr_bis_sonntag_22_uhr_geschlossen():
    eur = for_market("EURUSD")
    assert pipeline.is_market_open(pd.Timestamp("2026-05-08 21:59", tz="UTC"), eur) is True
    assert pipeline.is_market_open(pd.Timestamp("2026-05-08 22:00", tz="UTC"), eur) is False
    assert pipeline.is_market_open(pd.Timestamp("2026-05-10 21:59", tz="UTC"), eur) is False
    assert pipeline.is_market_open(pd.Timestamp("2026-05-10 22:00", tz="UTC"), eur) is True


def test_krypto_ist_am_wochenende_offen():
    saturday = pd.Timestamp("2026-05-09 12:00", tz="UTC")
    assert pipeline.is_market_open(saturday, for_market("BTC")) is True
    assert pipeline.is_market_open(saturday, for_market("ETH")) is True
    assert pipeline.is_market_open(saturday, for_market("EURUSD")) is False


# --- Betreff je Markt ---

def test_betreff_nennt_den_markt():
    subject = mail.build_subject([make_signal()], for_market("GBPUSD"))
    assert subject == "[BUCH] BUY GBP/USD – Morning Star (15m)"


def test_betreff_nutzt_anzeigenamen_bitcoin_und_ethereum():
    btc = mail.build_subject([make_signal()], for_market("BTC"))
    eth = mail.build_subject([make_signal()], for_market("ETH"))
    assert btc.startswith("[BUCH] BUY Bitcoin")
    assert eth.startswith("[BUCH] BUY Ethereum")


# --- Fehler in einem Markt stoppt die anderen nicht ---

def test_fehler_in_einem_markt_beeinflusst_die_anderen_nicht(tmp_path):
    def fetch(symbol, interval, lookback=None, period=None):
        if symbol == "GBPUSD=X":
            raise RuntimeError("Netzwerk weg")
        return make_candles()

    results = pipeline.run(
        at="2026-05-06T10:00:00Z", fetch=fetch,
        state_path=str(tmp_path / "s.json"), csv_path=str(tmp_path / "c.csv"),
        settings=read_settings({}), markets=["EURUSD", "GBPUSD", "BTC"],
    )
    assert "error" in results["GBPUSD"]
    assert "error" not in results["EURUSD"]
    assert "error" not in results["BTC"]


# --- .env-Einstellungen ---

def test_ungueltiger_schalter_in_env_wirft_klare_fehlermeldung():
    with pytest.raises(SettingsError, match="BUCH_NOTIFY_ENABLED"):
        read_settings({"BUCH_NOTIFY_ENABLED": "vielleicht"})


def test_unbekannter_markt_in_env_wirft_fehler():
    with pytest.raises(SettingsError, match="BUCH_NOTIFY_MARKETS"):
        read_settings({"BUCH_NOTIFY_MARKETS": "EURUSD,XYZ"})


def test_candles_single_darf_nicht_notify_sein():
    with pytest.raises(SettingsError, match="candles_single"):
        read_settings({"BUCH_DETECTOR_MODES": "candles_single=notify"})


def test_ungueltiger_modus_in_env_wirft_fehler():
    with pytest.raises(SettingsError, match="BUCH_DETECTOR_MODES"):
        read_settings({"BUCH_DETECTOR_MODES": "candles_main=laut"})


def test_gueltige_env_werte_werden_uebernommen():
    settings = read_settings({
        "BUCH_NOTIFY_ENABLED": "yes",
        "BUCH_NOTIFY_MARKETS": "eurusd, GBPUSD",
        "BUCH_DETECTOR_MODES": "candles_main=notify",
    })
    cfg = for_market("GBPUSD", settings)
    assert cfg.NOTIFY_ENABLED is True
    assert cfg.DETECTORS["candles_main"] == "notify"
    assert for_market("BTC", settings).NOTIFY_ENABLED is False


def test_main_mit_ungueltiger_env_gibt_exitcode_1(monkeypatch, capsys):
    monkeypatch.setenv("BUCH_NOTIFY_ENABLED", "vielleicht")
    assert cli_module.main(["--at", "2026-05-06T10:00:00Z"]) == 1


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("yes", True),
                                             ("0", False), ("false", False), ("no", False)])
def test_sr_in_mail_env_schalter_wird_uebernommen(value, expected):
    settings = read_settings({"BUCH_SR_IN_MAIL": value})
    assert settings["sr_in_mail"] is expected
    assert for_market("EURUSD", settings).SR_IN_MAIL is expected


def test_sr_in_mail_ohne_env_bleibt_an():
    assert read_settings({})["sr_in_mail"] is True


def test_sr_in_mail_ungueltiger_wert_wirft_fehler():
    with pytest.raises(SettingsError, match="BUCH_SR_IN_MAIL"):
        read_settings({"BUCH_SR_IN_MAIL": "vielleicht"})


def test_main_gibt_1_wenn_ein_markt_fehlerhaft_ist(monkeypatch):
    monkeypatch.delenv("BUCH_NOTIFY_ENABLED", raising=False)
    monkeypatch.setattr(cli_module, "run", lambda **kwargs: {"EURUSD": {}, "GBPUSD": {"error": "x"}})
    assert cli_module.main([]) == 1


def test_main_gibt_0_wenn_alle_maerkte_ok(monkeypatch):
    monkeypatch.delenv("BUCH_NOTIFY_ENABLED", raising=False)
    monkeypatch.setattr(cli_module, "run", lambda **kwargs: {"EURUSD": {}, "GBPUSD": {}})
    assert cli_module.main([]) == 0


# --- Testmail ---

def test_send_test_mail_betreff_und_zugangsdaten(smtp, monkeypatch):
    mail.send_test_mail(for_market("EURUSD"))
    sent = smtp.instances[0].sent
    assert len(sent) == 1
    assert sent[0]["Subject"] == "[BUCH] Testmail"


def test_test_mail_schlaegt_fehl_gibt_exitcode_1(monkeypatch, capsys):
    def failing(config):
        raise RuntimeError("MAIL_USER, MAIL_APP_PASSWORD oder MAIL_TO fehlt in der .env")

    monkeypatch.setattr(mail, "send_test_mail", failing)
    assert cli_module.main(["--test-mail"]) == 1
    assert "fehlt" in capsys.readouterr().err


def test_test_mail_erfolg_gibt_exitcode_0_ohne_zustand(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(mail, "send_test_mail", lambda config: calls.append(config.MARKET))
    monkeypatch.chdir(tmp_path)
    assert cli_module.main(["--test-mail"]) == 0
    assert calls == [real_config.DEFAULT_MARKET]
    assert list(tmp_path.iterdir()) == []


# --- Zustandsdatei je Markt ---

def test_alle_maerkte_nutzen_neuen_zustand_und_keine_alten_dateien():
    for name in real_config.MARKETS:
        cfg = for_market(name)
        assert cfg.STATE_FILE == "state_new.json"
        assert cfg.STATE_FILE not in ("state.json", "state_gbpusd.json", "state_btc.json", "state_eth.json")


# --- Backtest und Evaluate je Markt ---

def test_backtest_gibt_tabelle_je_markt_und_uebergibt_period(tmp_path):
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append((symbol, period))
        return make_candles(periods=600, start="2026-04-01 00:00")

    out = io.StringIO()
    with redirect_stdout(out):
        backtest.main(markets=["BTC"], fetch=fetch, csv_path=str(tmp_path / "bt.csv"))
    assert "=== Bitcoin (BTC) ===" in out.getvalue()
    assert calls == [("BTC-USD", real_config.BACKTEST_PERIOD)]
    assert real_config.BACKTEST_PERIOD == "60d"


def _no_fetch(*args, **kwargs):
    raise AssertionError("Snapshot vorhanden, es darf nicht abgerufen werden")


def test_snapshot_zweiter_lauf_liest_datei_und_liefert_identische_csv(tmp_path):
    snap = tmp_path / "snap.csv"

    def fetch(symbol, interval, lookback=None, period=None):
        return make_candles(periods=600, start="2026-04-01 00:00")

    first, second = io.StringIO(), io.StringIO()
    with redirect_stdout(first):
        backtest.main(markets=["BTC", "EURUSD"], fetch=fetch, csv_path=str(tmp_path / "a.csv"), snapshot=snap)
    with redirect_stdout(second):
        backtest.main(markets=["BTC", "EURUSD"], fetch=_no_fetch, csv_path=str(tmp_path / "b.csv"), snapshot=snap)
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert "neu abgerufen" in first.getvalue()
    assert second.getvalue().count("Datenstand") == 2
    assert "aus Snapshot" in second.getvalue()


def test_snapshot_signalzahl_bleibt_mit_und_ohne_sr_max_zones_gleich(tmp_path):
    snap = tmp_path / "snap.csv"

    def fetch(symbol, interval, lookback=None, period=None):
        return make_candles(periods=600, start="2026-04-01 00:00")

    with redirect_stdout(io.StringIO()):
        backtest.main(markets=["BTC", "EURUSD"], fetch=fetch, csv_path=str(tmp_path / "a.csv"), snapshot=snap)
        backtest.main(markets=["BTC", "EURUSD"], fetch=_no_fetch, csv_path=str(tmp_path / "b.csv"),
                      sr_max_zones=3, snapshot=snap)
    assert len((tmp_path / "a.csv").read_text(encoding="utf-8-sig").splitlines()) == \
        len((tmp_path / "b.csv").read_text(encoding="utf-8-sig").splitlines())


def test_snapshot_roundtrip_behaelt_preise_und_utc_zeiten(tmp_path):
    snap = tmp_path / "snap.csv"
    df = make_candles(periods=5)
    df["close"] = [1.0987654321 + i * 1e-7 for i in range(5)]
    backtest.save_snapshot(snap, {("EURUSD", "15m"): (df, "2026-05-06T10:00:00+00:00")})
    loaded, fetched_at = backtest.load_snapshot(snap)[("EURUSD", "15m")]
    pd.testing.assert_frame_equal(loaded, df, check_freq=False, check_exact=True)
    assert fetched_at == "2026-05-06T10:00:00+00:00"


def test_snapshot_fehlender_markt_wird_nachgeladen(tmp_path):
    snap = tmp_path / "snap.csv"
    interval = for_market("EURUSD").INTERVAL
    backtest.save_snapshot(snap, {("EURUSD", interval): (make_candles(periods=600, start="2026-04-01 00:00"),
                                                        "2026-05-06T10:00:00+00:00")})
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append(symbol)
        return make_candles(periods=600, start="2026-04-01 00:00")

    with redirect_stdout(io.StringIO()):
        backtest.main(markets=["EURUSD", "BTC"], fetch=fetch, csv_path=str(tmp_path / "bt.csv"), snapshot=snap)
    assert calls == ["BTC-USD"]
    btc_interval = for_market("BTC").INTERVAL
    assert set(backtest.load_snapshot(snap)) == {("EURUSD", interval), ("BTC", btc_interval)}


def test_snapshot_muss_csv_sein():
    with pytest.raises(argparse.ArgumentTypeError):
        backtest._parse_snapshot("daten.parquet")


def test_backtest_csv_pfad_ist_je_einzelmarkt_getrennt():
    assert backtest.default_csv_path(["EURUSD"]).name == "backtest_results_EURUSD.csv"
    assert backtest.default_csv_path(["EURUSD_30M"]).name == "backtest_results_EURUSD_30M.csv"
    assert backtest.default_csv_path(None).name == real_config.BACKTEST_CSV_FILE
    assert backtest.default_csv_path(["EURUSD", "BTC"]).name == real_config.BACKTEST_CSV_FILE


def _ohlc_candles(freq, periods, start="2026-05-06 00:00"):
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = [1.1000 + i * 0.00001 for i in range(periods)]
    return pd.DataFrame({"open": close, "high": [c + 0.0005 for c in close],
                         "low": [c - 0.0005 for c in close], "close": close}, index=idx)


def test_evaluate_ruft_je_markt_das_eigene_intervall_und_zeitraum_ab(tmp_path):
    from tests_buchbot.test_evaluate import signal_row, write_csv, SIGNAL_FIELDS

    csv_path = tmp_path / "signals_log.csv"
    rows = [
        {**signal_row(time="2026-05-06T08:30:00+00:00", interval="30m"), "market": "EURUSD_30M"},
        {**signal_row(time="2026-05-06T10:00:00+00:00", interval="15m"), "market": "EURUSD"},
    ]
    write_csv(csv_path, rows, fields=SIGNAL_FIELDS + ["market"])
    frames = {"30m": _ohlc_candles("30min", 60), "15m": _ohlc_candles("15min", 120)}
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append((symbol, interval, period))
        return frames[interval].copy()

    expected = {"EURUSD_30M": ("EUR/USD (30m)", "30m"), "EURUSD": ("EUR/USD", "15m")}
    for market, (display, interval) in expected.items():
        out = io.StringIO()
        with redirect_stdout(out):
            assert evaluate.main(csv_path=str(csv_path), markets=[market], fetch=fetch) == 0
        text = out.getvalue()
        assert f"=== {display} ({market}) ===" in text
        assert "Signale in der CSV: 1" in text
        assert "offen: 0 " in text, "Signalkerze muss im Kerzenraster des Markts liegen"

    assert calls == [
        ("EURUSD=X", "30m", real_config.BACKTEST_PERIOD),
        ("EURUSD=X", "15m", real_config.BACKTEST_PERIOD),
    ]
    assert real_config.BACKTEST_PERIOD == "60d"


def test_evaluate_waehlt_markt_per_spalte(tmp_path):
    csv_path = tmp_path / "signals_log.csv"
    rows = [
        {**signal_row(), "market": "EURUSD"},
        {**signal_row(symbol="GBPUSD=X", entry="1.25000", sl="1.24800", tp="1.25400"), "market": "GBPUSD"},
    ]
    write_csv(csv_path, rows, fields=SIGNAL_FIELDS + ["market"])
    calls = []

    def fetch(symbol, interval, lookback=None, period=None):
        calls.append(symbol)
        return make_df([candle(1.1005, 1.0995)] * 6)

    out = io.StringIO()
    with redirect_stdout(out):
        status = evaluate.main(csv_path=str(csv_path), markets=["GBPUSD"], fetch=fetch)
    assert status == 0
    assert calls == ["GBPUSD=X"]
    assert "=== GBP/USD (GBPUSD) ===" in out.getvalue()
    assert "=== EUR/USD (EURUSD) ===" not in out.getvalue()
