import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from buchbot import config as real_config
from buchbot import detectors
from buchbot import pipeline
from buchbot import state as state_store
from buchbot.models import Signal, to_utc
from buchbot.outputs import mail
from tests_buchbot.test_outputs_mail import FakeSMTP


NOW = pd.Timestamp("2026-05-06 10:00", tz="UTC")  # Mittwoch, letzte Kerze 09:45 schließt 10:00


def make_candles(periods=40, start="2026-05-06 00:00"):
    idx = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    close = [1.1000 + i * 0.00001 for i in range(periods)]
    return pd.DataFrame(
        {"open": close, "high": [c + 0.0005 for c in close],
         "low": [c - 0.0005 for c in close], "close": close},
        index=idx,
    )


def make_config(**overrides):
    values = dict(vars(real_config.for_market(real_config.DEFAULT_MARKET)))
    values["DETECTORS"] = {"dummy": "log_only"}
    values.update(overrides)
    return SimpleNamespace(**values)


def run_one(config, now=None, at=None, fetch=None, **paths):
    """Ruft run_market für einen Markt auf, mit derselben Zeit- und Probelauf-Logik wie pipeline.run."""
    dry_run = at is not None
    ts = to_utc(at) if dry_run else to_utc(now)
    return pipeline.run_market(config, ts, dry_run, fetch, paths.get("state_path"), paths.get("csv_path"))


DEFAULT_FIRE = pd.Timestamp("2026-05-06 09:45", tz="UTC")  # Start der letzten geschlossenen Kerze bei NOW


def make_dummy(fire_at):
    def dummy_detector(df, config):
        last_start = pd.Timestamp(df.index[-1])
        if last_start not in fire_at:
            return []
        entry = float(df["close"].iloc[-1])
        return [Signal(
            time=last_start + pd.Timedelta(config.INTERVAL),
            symbol=config.SYMBOL, interval=config.INTERVAL, source="dummy",
            pattern="Morning Star", direction="BUY", entry=entry, atr=0.001,
            tags={"required_trend": None, "pattern_low": entry - 0.0025},
        )]
    return dummy_detector


@pytest.fixture
def fire_at():
    return {DEFAULT_FIRE}


@pytest.fixture
def registry(monkeypatch, fire_at):
    monkeypatch.setattr(detectors, "_REGISTRY", {})
    detectors.register("dummy", make_dummy(fire_at), "dummy")
    return detectors._REGISTRY


@pytest.fixture
def paths(tmp_path):
    return {"state_path": str(tmp_path / "state_new.json"),
            "csv_path": str(tmp_path / "signals_log.csv")}


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("MAIL_USER", "bot@example.com")
    monkeypatch.setenv("MAIL_APP_PASSWORD", "test-passwort")
    monkeypatch.setenv("MAIL_TO", "empfaenger@example.com")
    return FakeSMTP


def fake_fetch(df):
    calls = []

    def fetch(symbol, interval, lookback):
        calls.append((symbol, interval, lookback))
        return df.copy()

    fetch.calls = calls
    return fetch


def test_marktzeiten_grenzen():
    cfg = make_config()
    assert pipeline.is_market_open(pd.Timestamp("2026-05-08 21:59", tz="UTC"), cfg)
    assert not pipeline.is_market_open(pd.Timestamp("2026-05-08 22:00", tz="UTC"), cfg)
    assert not pipeline.is_market_open(pd.Timestamp("2026-05-10 21:59", tz="UTC"), cfg)
    assert pipeline.is_market_open(pd.Timestamp("2026-05-10 22:00", tz="UTC"), cfg)


def test_pipeline_durchlaeuft_alle_stufen_mit_log_only(registry, paths):
    fetch = fake_fetch(make_candles())
    summary = run_one(now=NOW, config=make_config(), fetch=fetch, **paths)

    assert summary["signals"] == 1
    assert summary["new"] == 1
    assert fetch.calls == [("EURUSD=X", "15m", 100)]
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1
    assert rows.iloc[0]["sl"] == pytest.approx(1.1000 + 39 * 0.00001 - 0.0025 - 0.0005)
    assert __import__("os").path.exists(paths["state_path"])


def test_modus_off_erzeugt_nichts(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "off"}, NOTIFY_ENABLED=True)
    summary = run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles()), **paths)
    assert summary["signals"] == 0
    assert not __import__("os").path.exists(paths["csv_path"])
    assert smtp.instances == []


def test_modus_notify_mit_deaktiviertem_schalter_loggt_ohne_mail(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=False)
    summary = run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles()), **paths)
    assert summary["mailed"] == 0
    assert smtp.instances == []
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1
    entry = state_store.load_state(paths["state_path"])["sent"]
    (value,) = entry.values()
    assert value["logged"] is not None
    assert value["mailed"] is None


def test_zurueckgestellte_mail_wird_nach_aktivierung_genau_einmal_gesendet(registry, paths, smtp):
    fetch = fake_fetch(make_candles())
    off = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=False)
    run_one(now=NOW, config=off, fetch=fetch, **paths)

    on = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    second = run_one(now=NOW, config=on, fetch=fetch, **paths)
    assert second["mailed"] == 1
    assert len(smtp.instances[0].sent) == 1

    third = run_one(now=NOW, config=on, fetch=fetch, **paths)
    assert third["mailed"] == 0
    assert len(smtp.instances) == 1
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1


def test_modus_notify_mit_aktiviertem_schalter_sendet_genau_eine_mail(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    summary = run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles()), **paths)
    assert summary["mailed"] == 1
    assert len(smtp.instances) == 1
    assert len(smtp.instances[0].sent) == 1


def test_derselbe_lauf_zweimal_erzeugt_nur_ein_signal(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    fetch = fake_fetch(make_candles())
    run_one(now=NOW, config=cfg, fetch=fetch, **paths)
    second = run_one(now=NOW, config=cfg, fetch=fetch, **paths)

    assert second["new"] == 0
    assert len(smtp.instances) == 1
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1


def test_fehlgeschlagener_versand_wird_nicht_als_gesendet_markiert(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    fetch = fake_fetch(make_candles())
    smtp.fail = True
    first = run_one(now=NOW, config=cfg, fetch=fetch, **paths)
    assert first["mailed"] == 0
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1
    (value,) = state_store.load_state(paths["state_path"])["sent"].values()
    assert value["logged"] is not None
    assert value["mailed"] is None

    smtp.fail = False
    second = run_one(now=NOW, config=cfg, fetch=fetch, **paths)
    assert second["new"] == 1
    assert second["mailed"] == 1
    assert len(smtp.instances[-1].sent) == 1
    rows = pd.read_csv(paths["csv_path"], sep=";", encoding="utf-8-sig")
    assert len(rows) == 1


def test_fehlgeschlagener_lauf_wird_einen_lauf_spaeter_genau_einmal_gemailt(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    fetch = fake_fetch(make_candles())
    smtp.fail = True
    run_one(now=NOW, config=cfg, fetch=fetch, **paths)

    smtp.fail = False
    run_one(now=NOW + pd.Timedelta(minutes=15), config=cfg, fetch=fetch, **paths)
    third = run_one(now=NOW + pd.Timedelta(minutes=30), config=cfg, fetch=fetch, **paths)

    assert third["mailed"] == 0
    assert sum(len(i.sent) for i in smtp.instances if i.sent) == 1


def test_signal_ohne_mail_wird_nach_aktivierung_im_fenster_einmal_gemailt(registry, paths, smtp):
    cfg_off = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=False)
    run_one(now=NOW, config=cfg_off, fetch=fake_fetch(make_candles()), **paths)

    one_later = NOW + pd.Timedelta(minutes=15)
    cfg_on = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    second = run_one(now=one_later, config=cfg_on, fetch=fake_fetch(make_candles(periods=41)), **paths)
    assert second["mailed"] == 1
    assert len(smtp.instances[0].sent) == 1

    third = run_one(now=one_later, config=cfg_on, fetch=fake_fetch(make_candles(periods=41)), **paths)
    assert third["mailed"] == 0
    assert len(smtp.instances) == 1


def test_signal_ausserhalb_des_fensters_wird_nicht_nachtraeglich_gemailt(registry, paths, smtp):
    cfg_off = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=False)
    run_one(now=NOW, config=cfg_off, fetch=fake_fetch(make_candles()), **paths)

    cfg_on = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True, EVAL_WINDOW_CANDLES=1)
    summary = run_one(now=NOW + pd.Timedelta(minutes=15), config=cfg_on,
                      fetch=fake_fetch(make_candles(periods=41)), **paths)
    assert summary["mailed"] == 0
    assert smtp.instances == []


def test_wochenende_wertet_nichts_aus_und_loggt(registry, paths, caplog):
    fetch = fake_fetch(make_candles())
    with caplog.at_level(logging.INFO):
        summary = run_one(now=pd.Timestamp("2026-05-09 10:00", tz="UTC"),
                               config=make_config(), fetch=fetch, **paths)
    assert fetch.calls == []
    assert summary["signals"] == 0
    assert "Markt geschlossen" in caplog.text


def test_veraltete_daten_werden_gemeldet_und_nicht_ausgewertet(registry, paths, caplog):
    fetch = fake_fetch(make_candles())
    stale_now = pd.Timestamp("2026-05-06 11:00", tz="UTC")  # letzte Kerze endete 10:00
    with caplog.at_level(logging.WARNING):
        summary = run_one(now=stale_now, config=make_config(), fetch=fetch, **paths)
    assert summary["signals"] == 0
    assert "Daten veraltet" in caplog.text
    assert not __import__("os").path.exists(paths["csv_path"])


def test_systemuhr_geht_nach_bricht_lauf_ab(registry, paths, caplog):
    fetch = fake_fetch(make_candles())  # neueste Kerze startet 09:45 UTC
    behind_now = pd.Timestamp("2026-05-06 09:30", tz="UTC")
    with caplog.at_level(logging.WARNING):
        summary = run_one(now=behind_now, config=make_config(), fetch=fetch, **paths)
    assert summary["signals"] == 0
    assert "Systemuhr geht nach" in caplog.text
    assert not __import__("os").path.exists(paths["csv_path"])


def test_systemuhr_korrekt_keine_warnung(registry, paths, caplog):
    fetch = fake_fetch(make_candles())  # neueste Kerze startet 09:45, Systemzeit 10:00
    with caplog.at_level(logging.WARNING):
        summary = run_one(now=NOW, config=make_config(), fetch=fetch, **paths)
    assert summary["signals"] == 1
    assert "Systemuhr geht nach" not in caplog.text


def test_systemuhr_innerhalb_toleranz_keine_warnung(registry, paths, caplog):
    fetch = fake_fetch(make_candles())  # neueste Kerze startet 09:45, Systemzeit 09:43 -> 2 Minuten Abweichung
    now = pd.Timestamp("2026-05-06 09:43", tz="UTC")
    with caplog.at_level(logging.WARNING):
        run_one(now=now, config=make_config(), fetch=fetch, **paths)
    assert "Systemuhr geht nach" not in caplog.text


def test_systemuhr_ueber_toleranz_warnt(registry, paths, caplog):
    fetch = fake_fetch(make_candles())  # neueste Kerze startet 09:45, Systemzeit 09:42 -> 3 Minuten Abweichung
    now = pd.Timestamp("2026-05-06 09:42", tz="UTC")
    with caplog.at_level(logging.WARNING):
        summary = run_one(now=now, config=make_config(), fetch=fetch, **paths)
    assert summary["signals"] == 0
    assert "Systemuhr geht nach" in caplog.text


def test_probelauf_mit_at_ist_von_uhrpruefung_ausgenommen(registry, paths, caplog):
    fetch = fake_fetch(make_candles())  # Kerzen nach --at werden entfernt, Systemuhr irrelevant
    with caplog.at_level(logging.WARNING):
        run_one(at="2026-05-06 09:30", config=make_config(), fetch=fetch, **paths)
    assert "Systemuhr geht nach" not in caplog.text


def test_fehlende_kerzen_brechen_nicht_ab(registry, paths, caplog):
    summary = run_one(now=NOW, config=make_config(), fetch=lambda *a: None, **paths)
    assert summary["signals"] == 0
    assert "Keine Kerzen" in caplog.text


def test_probelauf_mit_at_sendet_nichts_und_veraendert_keinen_zustand(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    summary = run_one(at="2026-05-06 10:00", config=cfg,
                      fetch=fake_fetch(make_candles()), **paths)
    assert summary["dry_run"] is True
    assert summary["signals"] == 1
    assert smtp.instances == []
    assert not __import__("os").path.exists(paths["csv_path"])
    assert not __import__("os").path.exists(paths["state_path"])


def test_arbeitsverzeichnis_hat_keinen_einfluss_auf_zieldateien(tmp_path, monkeypatch, registry):
    project = tmp_path / "projekt"
    elsewhere = tmp_path / "anderswo"
    project.mkdir()
    elsewhere.mkdir()
    monkeypatch.setattr(pipeline, "BASE_DIR", project)
    monkeypatch.chdir(elsewhere)

    run_one(now=NOW, config=make_config(), fetch=fake_fetch(make_candles()))

    assert (project / "state_new.json").exists()
    assert (project / "signals_log.csv").exists()
    assert not (elsewhere / "state_new.json").exists()
    assert not (elsewhere / "signals_log.csv").exists()


def test_probelauf_ignoriert_kerzen_nach_at(registry, paths):
    df = make_candles(periods=40)
    later = make_candles(periods=8, start="2026-05-06 10:00")
    full = pd.concat([df, later])
    seen = {}

    def detector(d, config):
        seen.setdefault("last", d.index[-1])
        return []

    detectors._REGISTRY["dummy"] = (detector, "dummy")
    run_one(at="2026-05-06 10:00", config=make_config(), fetch=fake_fetch(full), **paths)
    assert seen["last"] == pd.Timestamp("2026-05-06 09:45", tz="UTC")


def sent_messages(smtp):
    return [msg for server in smtp.instances for msg in server.sent]


def test_eval_window_standard_ist_zwei():
    assert real_config.EVAL_WINDOW_CANDLES == 2


def test_vorletzte_kerze_wird_erkannt_und_als_vorherig_markiert(registry, paths, fire_at, smtp):
    fire_at.clear()
    fire_at.add(pd.Timestamp("2026-05-06 09:30", tz="UTC"))
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    summary = run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles()), **paths)

    assert summary["new"] == 1
    body = sent_messages(smtp)[0].get_content()
    assert "Hinweis: Signal der vorherigen Kerze." in body


def test_signal_der_letzten_kerze_hat_keinen_vorherig_hinweis(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles()), **paths)

    assert "Hinweis" not in sent_messages(smtp)[0].get_content()


def test_signal_von_vor_drei_kerzen_wird_nicht_erkannt(registry, paths, fire_at):
    fire_at.clear()
    fire_at.add(pd.Timestamp("2026-05-06 09:15", tz="UTC"))
    summary = run_one(now=NOW, config=make_config(), fetch=fake_fetch(make_candles()), **paths)
    assert summary["signals"] == 0


def test_fehlgeschlagener_versand_wird_im_naechsten_lauf_genau_einmal_gesendet(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    smtp.fail = True
    first = run_one(now=NOW, config=cfg, fetch=fake_fetch(make_candles(periods=40)), **paths)
    assert first["mailed"] == 0

    smtp.fail = False
    later = NOW + pd.Timedelta(minutes=15)
    second = run_one(now=later, config=cfg, fetch=fake_fetch(make_candles(periods=41)), **paths)
    assert second["mailed"] == 1
    assert len(sent_messages(smtp)) == 1
    assert "Hinweis: Signal der vorherigen Kerze." in sent_messages(smtp)[0].get_content()


def test_dasselbe_signal_wird_ueber_fenster_hinweg_nicht_doppelt_gesendet(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    fetch = fake_fetch(make_candles(periods=41))
    run_one(now=NOW + pd.Timedelta(minutes=15), config=cfg, fetch=fetch, **paths)
    again = run_one(now=NOW + pd.Timedelta(minutes=15), config=cfg, fetch=fetch, **paths)

    assert again["new"] == 0
    assert len(sent_messages(smtp)) == 1


def test_spaetere_daten_ohne_muster_aendern_gesendete_signale_nicht(registry, paths, smtp):
    cfg = make_config(DETECTORS={"dummy": "notify"}, NOTIFY_ENABLED=True)
    run_one(now=NOW + pd.Timedelta(minutes=15), config=cfg,
            fetch=fake_fetch(make_candles(periods=41)), **paths)
    before = state_store.load_state(paths["state_path"])

    later = NOW + pd.Timedelta(minutes=45)
    summary = run_one(now=later, config=cfg,
                      fetch=fake_fetch(make_candles(periods=43)), **paths)

    after = state_store.load_state(paths["state_path"])
    assert summary["new"] == 0
    assert len(sent_messages(smtp)) == 1
    assert after["sent"] == before["sent"]
