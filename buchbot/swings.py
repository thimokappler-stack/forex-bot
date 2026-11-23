"""
Swing-Punkte (Pivots) für Unterstützung und Widerstand (Buch Kapitel 9).

Ein Swing-Hoch bei Kerze i: High ist größer als die Highs der n vorherigen Kerzen
und mindestens so groß wie die Highs der n folgenden Kerzen. Tiefs spiegelverkehrt.
Ein Pivot gilt erst, wenn n Kerzen danach vorliegen. Übergibt man nur Daten bis zur
Signalkerze, sind damit keine Zukunftsdaten im Spiel.
"""

from dataclasses import dataclass


HIGH = "high"
LOW = "low"


@dataclass(frozen=True)
class Swing:
    pos: int      # Position der Kerze im DataFrame
    price: float  # High bei einem Hoch, Low bei einem Tief
    kind: str     # HIGH oder LOW


def find_swings(df, n):
    """Bestätigte Swing-Punkte in Zeitreihenfolge. Nur Kerzen mit i + n <= letzte Position."""
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    swings = []
    for i in range(n, len(df) - n):
        if highs[i] > highs[i - n:i].max() and highs[i] >= highs[i + 1:i + n + 1].max():
            swings.append(Swing(i, float(highs[i]), HIGH))
        if lows[i] < lows[i - n:i].min() and lows[i] <= lows[i + 1:i + n + 1].min():
            swings.append(Swing(i, float(lows[i]), LOW))
    return swings
