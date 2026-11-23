"""
Einstieg: python -m buchbot.main [--at ZEITPUNKT]

Exit-Code 0 bei normalem Lauf (auch ohne Signal), 1 bei unerwartetem Fehler.
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

from buchbot.models import to_utc
from buchbot.pipeline import run


logger = logging.getLogger("buchbot")


def parse_at(value):
    return to_utc(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description="EUR/USD Candlestick-Signalbot")
    parser.add_argument(
        "--at", type=parse_at, default=None,
        help='Auswertung als wäre jetzt dieser UTC-Zeitpunkt, z. B. "2026-11-20T12:30:00Z". '
             "Kein Mailversand, keine Zustandsänderung.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()

    try:
        run(at=args.at)
    except Exception:
        logger.exception("Unerwarteter Fehler im Lauf")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
