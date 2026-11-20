"""
E-Mail-Versand für Signale via Gmail SMTP.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def load_mail_config():
    """
    Lädt E-Mail-Konfiguration aus .env.
    
    Returns:
        Dict mit "user", "password", "to" oder None bei Fehler
    """
    load_dotenv()
    
    user = os.getenv("MAIL_USER")
    password = os.getenv("MAIL_APP_PASSWORD")
    mail_to = os.getenv("MAIL_TO")
    
    if not user or not password or not mail_to:
        logger.error("E-Mail-Konfiguration unvollständig (.env fehlt oder leicht)")
        return None
    
    return {
        "user": user,
        "password": password,
        "to": mail_to,
    }


def send_signal(signal, candles, config=None):
    """
    Sendet ein Signal per E-Mail.
    
    Args:
        signal: Dict mit pattern, signal, timestamp, entry, sl, tp, risk_pips, crv, symbol (optional)
        candles: DataFrame mit Kerzen (für Kontext)
        config: Optional config module
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    mail_config = load_mail_config()
    if mail_config is None:
        return False
    
    # Symbol aus Signal oder Default
    symbol = signal.get("symbol", "EUR/USD")
    
    # E-Mail zusammenstellen
    subject = f"{signal['signal']} {symbol} – {signal['pattern']} (15m)"
    
    timestamp_utc = signal["timestamp"]
    local_tz = os.getenv("TZ", "UTC")
    
    body = f"""
{signal['signal']}-Signal erkannt

Muster: {signal['pattern']}
Kerzenzeit (UTC): {timestamp_utc}

--- Kerzen des Musters ---
Schlusskurs: {signal["entry"]:.5f}

--- Einstieg und Risiko ---
Einstieg: {signal["entry"]:.5f}
Stop-Loss: {signal["sl"]:.5f}
Take-Profit: {signal["tp"]:.5f}
Risiko: {signal["risk_pips"]:.2f} Pips
CRV: 1:{signal["crv"]}

---

HINWEIS: Dies ist kein Anlagerat, sondern nur eine automatische Mustererkennung.
Forex-Handel mit Hebel ist hochriskant.
"""
    
    try:
        msg = MIMEMultipart()
        msg["From"] = mail_config["user"]
        msg["To"] = mail_config["to"]
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        
        # Gmail SMTP
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(mail_config["user"], mail_config["password"])
        server.send_message(msg)
        server.quit()
        
        logger.info(f"E-Mail gesendet: {subject}")
        return True
    
    except Exception as e:
        logger.error(f"E-Mail-Fehler: {e}")
        return False
