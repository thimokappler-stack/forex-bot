"""
Main-Einstiegspunkt: Holt Daten, erkennt Muster, sendet Signale.
Läuft per Cron alle 15 Minuten.
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime, timedelta
import calendar
from data import get_candles, remove_incomplete_candle, calculate_atr
from patterns import detect_patterns
from signals import evaluate_pattern
from notify import send_signal
from config import TREND_EMA_PERIOD


# Logging setup
LOG_FILE = "bot.log"
logger = logging.getLogger(__name__)
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Auch zur Console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def is_forex_market_open():
    """
    Prüft ob Forex-Markt offen ist (Mo-Fr, 00:00-23:59 UTC).
    Wochenende: Markt geschlossen.
    """
    now = datetime.utcnow()
    weekday = now.weekday()  # 0=Mo, 6=So
    
    if weekday >= 5:  # Sa, So
        return False
    
    return True


def load_state():
    """
    Lädt already_sent_signals aus state.json.
    
    Returns:
        List von (pattern, timestamp_str) Tuples
    """
    if not os.path.exists("state.json"):
        return []
    
    try:
        with open("state.json", "r") as f:
            data = json.load(f)
            return data.get("sent_signals", [])
    except Exception as e:
        logger.warning(f"Fehler beim Laden von state.json: {e}")
        return []


def save_state(sent_signals):
    """
    Speichert sent_signals in state.json.
    """
    try:
        with open("state.json", "w") as f:
            json.dump({"sent_signals": sent_signals}, f, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Speichern von state.json: {e}")


def signal_already_sent(pattern, timestamp, sent_signals):
    """
    Prüft ob Signal (pattern + timestamp) schon versendet wurde.
    """
    signal_key = (pattern, str(timestamp))
    return signal_key in [tuple(s) if isinstance(s, list) else s for s in sent_signals]


def main():
    logger.info("=" * 60)
    logger.info("Bot Start")
    logger.info(f"Uhrzeit UTC: {datetime.utcnow()}")
    
    # Prüfe Markt
    if not is_forex_market_open():
        logger.info("Forex-Markt geschlossen (Wochenende)")
        return
    
    # Daten holen
    candles = get_candles()
    if candles is None or len(candles) == 0:
        logger.error("Konnte Kerzen nicht abrufen")
        return
    
    logger.info(f"Daten erhalten: {len(candles)} Kerzen")
    
    # Letzte Kerze entfernen (nicht geschlossen)
    candles = remove_incomplete_candle(candles)
    logger.info(f"Nach Entfernung unvollständiger Kerze: {len(candles)} Kerzen")
    
    if len(candles) < TREND_EMA_PERIOD + 5:
        logger.warning(f"Zu wenige Kerzen für Analyse ({len(candles)} < {TREND_EMA_PERIOD + 5})")
        return
    
    # ATR berechnen
    atrs = calculate_atr(candles)
    
    # Muster erkennen
    detected = detect_patterns(candles, atrs)
    logger.info(f"Erkannte Muster: {len(detected)}")
    
    # State laden
    sent_signals = load_state()
    
    # Jedes Muster bewerten
    for pattern_info in detected:
        pattern_name = pattern_info["pattern"]
        signal_type = pattern_info["signal"]
        idx = pattern_info["idx"]
        
        logger.info(f"Evaluiere {pattern_name} ({signal_type}) an idx {idx}")
        
        # Signalberechnung (Trend + SL/TP)
        from signals import evaluate_pattern
        signal = evaluate_pattern(candles, atrs, pattern_name, signal_type, idx)
        
        if signal is None:
            logger.info(f"  → Signal gefiltert (Trend oder zu kleines Risiko)")
            continue
        
        # Duplikat-Prüfung
        if signal_already_sent(pattern_name, signal["timestamp"], sent_signals):
            logger.info(f"  → Signal schon versendet, übersprungen")
            continue
        
        # E-Mail senden
        logger.info(f"  → Sende E-Mail!")
        if send_signal(signal, candles):
            # State speichern
            sent_signals.append([pattern_name, str(signal["timestamp"])])
            save_state(sent_signals)
            logger.info(f"  → State aktualisiert")
        else:
            logger.error(f"  → E-Mail-Versand fehlgeschlagen")
    
    logger.info("Bot beendet")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
