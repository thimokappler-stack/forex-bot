"""
Stop-Loss und Take-Profit als Vorschlag für die E-Mail.

BUY: SL unter dem Mustertief, SELL: SL über dem Musterhoch, jeweils mit Puffer.
Signale mit zu kleinem Abstand werden verworfen und geloggt.
"""

import logging


logger = logging.getLogger(__name__)


def apply(signals, config):
    """Berechnet SL/TP und gibt die Signale zurück, die den Mindestabstand erfüllen."""
    kept = []
    for signal in signals:
        if signal.direction == "NEUTRAL":
            kept.append(signal)
            continue

        if signal.direction == "BUY":
            sl = signal.tags["pattern_low"] - config.SL_BUFFER_ATR * signal.atr
            side = 1
        elif signal.direction == "SELL":
            sl = signal.tags["pattern_high"] + config.SL_BUFFER_ATR * signal.atr
            side = -1
        else:
            raise ValueError(f"Unbekannte Richtung: {signal.direction!r}")

        risk = abs(signal.entry - sl)
        if risk < config.MIN_SL_PIPS * config.PIP_SIZE:
            logger.info(
                "Signal verworfen: %s (%s), Risiko %.1f Pips unter Minimum %s Pips",
                signal.pattern, signal.time, risk / config.PIP_SIZE, config.MIN_SL_PIPS,
            )
            continue

        signal.sl = round(sl, 5)
        signal.tp = round(signal.entry + side * config.RISK_REWARD * risk, 5)
        signal.risk_pips = round(risk / config.PIP_SIZE, 5)
        signal.rr = config.RISK_REWARD
        kept.append(signal)
    return kept
