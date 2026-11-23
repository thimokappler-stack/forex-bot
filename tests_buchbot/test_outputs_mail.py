import email
from email import policy

import pandas as pd
import pytest

from buchbot import config as real_config
from buchbot.models import Signal
from buchbot.outputs import mail


def make_config(market=None, **overrides):
    cfg = real_config.for_market(market or real_config.DEFAULT_MARKET)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def make_signal(direction="BUY", pattern="Morning Star", time="2026-05-06 10:15"):
    return Signal(
        time=pd.Timestamp(time, tz="UTC"), symbol="EURUSD=X", interval="15m",
        source="candles_main", pattern=pattern, direction=direction,
        entry=1.10100, atr=0.001, sl=1.09950, tp=1.10400, risk_pips=15.0, rr=2.0,
        mode="notify",
    )


class FakeSMTP:
    instances = []
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.logged_in = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise OSError("SMTP nicht erreichbar")
        self.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail = False
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("MAIL_USER", "bot@example.com")
    monkeypatch.setenv("MAIL_APP_PASSWORD", "test-passwort")
    monkeypatch.setenv("MAIL_TO", "empfaenger@example.com")
    return FakeSMTP


def test_betreff_einzelnes_signal():
    subject = mail.build_subject([make_signal()], make_config())
    assert subject == "[BUCH] BUY EUR/USD – Morning Star (15m)"


def test_betreff_mehrere_gleichgerichtete_muster():
    signals = [make_signal(pattern="Morning Star"), make_signal(pattern="Tweezer Bottom")]
    assert mail.build_subject(signals, make_config()) == "[BUCH] BUY EUR/USD – 2 Muster (15m)"


def test_betreff_widerspruechliche_richtungen():
    signals = [make_signal(direction="BUY"), make_signal(direction="SELL", pattern="Evening Star")]
    assert mail.build_subject(signals, make_config()) == "[BUCH] EUR/USD – widersprüchliche Signale"


def test_inhalt_enthaelt_zeiten_werte_und_hinweis():
    body = mail.build_body([make_signal()], make_config())
    assert "Richtung: BUY" in body
    assert "Muster: Morning Star" in body
    assert "2026-05-06 10:15 UTC / 2026-05-06 12:15 CEST" in body
    assert "Einstieg: 1.10100" in body
    assert "Stop-Loss: 1.09950" in body
    assert "Take-Profit: 1.10400" in body
    assert "Risiko: 15.0 Pips" in body
    assert "CRV: 1:2" in body
    assert body.rstrip().endswith("Kein Anlagerat, nur Mustererkennung.")


def test_nachricht_ist_utf8_und_laesst_sich_zuruecklesen():
    signals = [make_signal(direction="SELL", pattern="Drei bärische Soldaten")]
    signals.append(make_signal(direction="BUY", pattern="Morning Star"))
    msg = mail.build_message(signals, make_config(), "bot@example.com", "to@example.com")

    raw = msg.as_bytes()
    parsed = email.message_from_bytes(raw, policy=policy.default)
    assert parsed["Subject"] == "[BUCH] EUR/USD – widersprüchliche Signale"
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    assert "Muster: Drei bärische Soldaten" in body
    assert "Kein Anlagerat, nur Mustererkennung." in body


def test_umlaute_im_muster_bleiben_erhalten():
    msg = mail.build_message([make_signal(pattern="Drei bärische Soldaten")],
                             make_config(), "a@example.com", "b@example.com")
    parsed = email.message_from_bytes(msg.as_bytes(), policy=policy.default)
    body = parsed.get_body(preferencelist=("plain",)).get_content()
    assert "Muster: Drei bärische Soldaten" in body


def test_versand_per_smtp_ssl_mit_login(smtp):
    mail.send_bundle([make_signal()], make_config())
    server = smtp.instances[0]
    assert (server.host, server.port) == ("smtp.gmail.com", 465)
    assert server.logged_in == ("bot@example.com", "test-passwort")
    assert len(server.sent) == 1
    assert server.sent[0]["To"] == "empfaenger@example.com"


def test_fehlende_zugangsdaten_wirft_fehler(monkeypatch):
    monkeypatch.delenv("MAIL_USER", raising=False)
    monkeypatch.delenv("MAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_TO", raising=False)
    with pytest.raises(RuntimeError):
        mail.send_bundle([make_signal()], make_config())


def test_mehrere_signale_einer_kerze_ergeben_eine_mail(smtp):
    signals = [make_signal(pattern="Morning Star"), make_signal(pattern="Tweezer Bottom")]
    sent = mail.send_notifications(signals, make_config())
    assert len(sent) == 2
    assert len(smtp.instances) == 1
    assert len(smtp.instances[0].sent) == 1


def test_signale_verschiedener_kerzen_ergeben_mehrere_mails(smtp):
    signals = [make_signal(time="2026-05-06 10:15"), make_signal(time="2026-05-06 10:30")]
    mail.send_notifications(signals, make_config())
    assert len(smtp.instances) == 2


def test_fehlgeschlagener_versand_wird_geloggt_und_nicht_als_gesendet_gemeldet(smtp, caplog):
    smtp.fail = True
    sent = mail.send_notifications([make_signal()], make_config())
    assert sent == []
    assert "Mail-Versand fehlgeschlagen" in caplog.text


def make_zone_signal(direction="BUY", **tags):
    signal = make_signal(direction=direction)
    signal.tags = {"sr_relation": "at_support", "sr_zone_low": 1.09420, "sr_zone_high": 1.09450,
                   "sr_touches": 4, "sr_aligned": True, "sr_against": False,
                   "sr_room_atr": None, "swing_trend": "up"}
    signal.tags.update(tags)
    return signal


def test_mail_mit_zone_zeigt_zone_und_swing_trend():
    body = mail.build_body([make_zone_signal()], make_config())
    assert "Zone: Unterstützung 1.09420–1.09450 (4 Berührungen), Muster liegt an der Zone" in body
    assert "Swing-Trend: aufwärts" in body


def test_mail_achtung_bei_widerstand_nahe_dem_einstieg():
    signal = make_zone_signal(sr_relation="none", sr_aligned=None, sr_zone_low=None,
                              sr_zone_high=None, sr_touches=None, sr_against=True,
                              sr_against_level=1.10900, sr_against_atr=0.4)
    body = mail.build_body([signal], make_config())
    assert "Achtung: Widerstand 1.10900 nur 0.4 ATR über dem Einstieg" in body


def test_mail_ohne_zone_bleibt_unveraendert():
    signal = make_signal()
    signal.tags = {"sr_relation": "none", "sr_against": False}
    body = mail.build_body([signal], make_config())
    assert "Zone:" not in body
    assert "Swing-Trend" not in body
    assert "Achtung" not in body


def test_mail_sr_in_mail_aus_zeigt_keine_zone():
    body = mail.build_body([make_zone_signal()], make_config(SR_IN_MAIL=False))
    assert "Zone:" not in body
    assert "Swing-Trend" not in body
