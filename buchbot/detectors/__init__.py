"""
Detektor-Registry.

Ein neuer Detektor = neue Datei + register(...) hier + Eintrag in DETECTORS (config.py).
"""

from buchbot.detectors import candles_main, candles_single

VALID_MODES = ("off", "log_only", "notify")

_REGISTRY = {}


def register(name, func, source):
    if name in _REGISTRY:
        raise ValueError(f"Detektor bereits registriert: {name}")
    _REGISTRY[name] = (func, source)


def run_detectors(df, config):
    """
    Führt alle Detektoren aus, die in config.DETECTORS nicht auf "off" stehen.
    Jedes Signal bekommt die Betriebsart in signal.mode.
    """
    modes = getattr(config, "DETECTORS", {})
    signals = []
    for name, (func, _source) in _REGISTRY.items():
        mode = modes.get(name, "off")
        if mode == "off":
            continue
        if mode not in VALID_MODES:
            raise ValueError(f"Ungültiger Modus für {name}: {mode}")
        for signal in func(df, config):
            signal.mode = mode
            signals.append(signal)
    return signals


register("candles_main", candles_main.detect, candles_main.SOURCE)
register("candles_single", candles_single.detect, candles_single.SOURCE)
