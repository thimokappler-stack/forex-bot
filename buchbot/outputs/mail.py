"""
E-Mail-Ausgabe für Signale mit Modus "notify".

Eine Mail pro Kerze, mehrere Signale derselben Kerze werden gebündelt.
Zugangsdaten kommen aus der Umgebung (.env), nie aus dem Code.
"""

import logging
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from buchbot.models import format_price, to_utc


logger = logging.getLogger(__name__)

SUBJECT_PREFIX = "[BUCH]"


def build_subject(signals, config):
    directions = {signal.direction for signal in signals}
    interval = signals[0].interval
    if len(directions) > 1:
        return f"{SUBJECT_PREFIX} {config.DISPLAY_SYMBOL} – widersprüchliche Signale"
    direction = signals[0].direction
    if len(signals) == 1:
        return f"{SUBJECT_PREFIX} {direction} {config.DISPLAY_SYMBOL} – {signals[0].pattern} ({interval})"
    return f"{SUBJECT_PREFIX} {direction} {config.DISPLAY_SYMBOL} – {len(signals)} Muster ({interval})"


def _price(value):
    formatted = format_price(value)
    return "–" if formatted is None else formatted


def _pips(value):
    return "–" if value is None else f"{value:.1f} Pips"


def _ratio(value):
    return "–" if value is None else f"1:{value:g}"


def build_body(signals, config):
    tz = ZoneInfo(config.DISPLAY_TZ)
    blocks = []
    for signal in signals:
        close = to_utc(signal.time)
        lines = [
            f"Richtung: {signal.direction}",
            f"Muster: {signal.pattern}",
            f"Kerzenschluss: {close.strftime('%Y-%m-%d %H:%M')} UTC / "
            f"{close.tz_convert(tz).strftime('%Y-%m-%d %H:%M %Z')}",
            f"Einstieg: {_price(signal.entry)}",
            f"Stop-Loss: {_price(signal.sl)}",
            f"Take-Profit: {_price(signal.tp)}",
            f"Risiko: {_pips(signal.risk_pips)}",
            f"CRV: {_ratio(signal.rr)}",
        ]
        if signal.tags.get("prior_candle"):
            lines.append("Hinweis: Signal der vorherigen Kerze.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + f"\n\n{config.MAIL_DISCLAIMER}\n"


def build_message(signals, config, sender, recipient):
    msg = EmailMessage()
    msg["Subject"] = build_subject(signals, config)
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(build_body(signals, config), charset="utf-8")
    return msg


def send_bundle(signals, config):
    """Sendet eine Mail für die Signale einer Kerze. Wirft Fehler weiter."""
    user = os.environ.get("MAIL_USER")
    password = os.environ.get("MAIL_APP_PASSWORD")
    recipient = os.environ.get("MAIL_TO")
    if not (user and password and recipient):
        raise RuntimeError("MAIL_USER, MAIL_APP_PASSWORD oder MAIL_TO fehlt in der .env")

    msg = build_message(signals, config, sender=user, recipient=recipient)
    with smtplib.SMTP_SSL(config.MAIL_SMTP_HOST, config.MAIL_SMTP_PORT,
                          timeout=config.MAIL_TIMEOUT_SECONDS) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    logger.info("Mail gesendet: %s", msg["Subject"])


def send_notifications(signals, config):
    """
    Eine Mail pro Kerze. Gibt die Signale zurück, deren Mail erfolgreich war.
    Fehler werden geloggt und stürzen den Lauf nicht ab.
    """
    bundles = {}
    for signal in signals:
        bundles.setdefault(to_utc(signal.time), []).append(signal)

    sent = []
    for candle_time, bundle in bundles.items():
        try:
            send_bundle(bundle, config)
            sent.extend(bundle)
        except Exception:
            logger.exception("Mail-Versand fehlgeschlagen für Kerze %s", candle_time.isoformat())
    return sent
