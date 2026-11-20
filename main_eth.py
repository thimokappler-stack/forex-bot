"""
Main-Einstiegspunkt für Ethereum: Holt Daten, erkennt Muster, sendet Signale.
Läuft per Cron alle 15 Minuten (24/7, auch Wochenende).
"""

import logging
import logging.handlers
import json
import os
from datetime import datetime
from data import get_candles, remove_incomplete_candle, calculate_atr
from patterns import detect_patterns
from signals import evaluate_pattern
from notify import send_signal
import config_eth as config


# Logging setup (separates Log-File für ETH)
LOG_FILE = "bot_eth.log"
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


def load_state():
    """
    Lädt already_sent_signals aus state_eth.json.
    
    Returns:
        List von (pattern, timestamp_str) Tuples
    """
    state_file = "state_eth.json"
    if not os.path.exists(state_file):
        return []
    
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
            return data.get("sent_signals", [])
    except Exception as e:
        logger.warning(f"Fehler beim Laden von {state_file}: {e}")
        return []


def save_state(sent_signals):
    """
    Speichert sent_signals in state_eth.json.
    """
    state_file = "state_eth.json"
    try:
        with open(state_file, "w") as f:
            json.dump({"sent_signals": sent_signals}, f, indent=2)
    except Exception as e:
        logger.error(f"Fehler beim Speichern von {state_file}: {e}")


def signal_already_sent(pattern, timestamp, sent_signals):
    """
    Prüft ob Signal (pattern + timestamp) schon versendet wurde.
    """
    signal_key = (pattern, str(timestamp))
    return signal_key in [tuple(s) if isinstance(s, list) else s for s in sent_signals]


def main():
    logger.info("=" * 60)
    logger.info("Bot Start (ETH)")
    logger.info(f"Uhrzeit UTC: {datetime.utcnow()}")
    
    # Daten holen (mit config_eth)
    candles = get_candles(config.SYMBOL, config.INTERVAL, config.LOOKBACK_CANDLES)
    if candles is None or len(candles) == 0:
        logger.error("Konnte Kerzen nicht abrufen")
        return
    
    logger.info(f"Daten erhalten: {len(candles)} Kerzen")
    
    # Letzte Kerze entfernen (nicht geschlossen)
    candles = remove_incomplete_candle(candles)
    logger.info(f"Nach Entfernung unvollständiger Kerze: {len(candles)} Kerzen")
    
    if len(candles) < config.TREND_EMA_PERIOD + 5:
        logger.warning(f"Zu wenige Kerzen für Analyse ({len(candles)} < {config.TREND_EMA_PERIOD + 5})")
        return
    
    # ATR berechnen (mit config_eth)
    atrs = calculate_atr(candles, config.ATR_PERIOD)
    
    # Muster erkennen
    detected = detect_patterns(candles, atrs, config)
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
        signal = evaluate_pattern(candles, atrs, pattern_name, signal_type, idx, config)
        
        if signal is None:
            logger.info(f"  → Signal gefiltert (Trend oder zu kleines Risiko)")
            continue
        
        # Duplikat-Prüfung
        if signal_already_sent(pattern_name, signal["timestamp"], sent_signals):
            logger.info(f"  → Signal schon versendet, übersprungen")
            continue
        
        # E-Mail senden (mit Symbol-Info)
        signal["symbol"] = "Ethereum"
        logger.info(f"  → Sende E-Mail!")
        if send_signal(signal, candles, config):
            # State speichern
            sent_signals.append([pattern_name, str(signal["timestamp"])])
            save_state(sent_signals)
            logger.info(f"  → State aktualisiert")
        else:
            logger.error(f"  → E-Mail-Versand fehlgeschlagen")
    
    logger.info("Bot beendet (ETH)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
