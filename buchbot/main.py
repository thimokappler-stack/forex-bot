"""
Einstieg: python -m buchbot.main [--at ZEITPUNKT] [--test-mail]

Wertet alle Märkte nacheinander aus. Exit-Code 0 bei normalem Lauf (auch ohne Signal),
1 bei unerwartetem Fehler in einem Markt, bei ungültiger .env oder fehlgeschlagener Testmail.
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from buchbot import config
from buchbot.models import to_utc
from buchbot.outputs import mail
from buchbot.pipeline import run


logger = logging.getLogger("buchbot")


def parse_at(value):
    return to_utc(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Candlestick-Signalbot (Mehrmarkt)")
    parser.add_argument(
        "--at", type=parse_at, default=None,
        help='Auswertung als wäre jetzt dieser UTC-Zeitpunkt, z. B. "2026-11-20T12:30:00Z". '
             "Kein Mailversand, keine Zustandsänderung.",
    )
    parser.add_argument(
        "--test-mail", action="store_true",
        help="Sendet eine Testmail. Ändert weder Zustand noch CSV.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()

    try:
        settings = config.read_settings(os.environ)
    except config.SettingsError as exc:
        print(f"Fehler in der .env: {exc}", file=sys.stderr)
        return 1

    if args.test_mail:
        try:
            mail.send_test_mail(config.for_market(config.DEFAULT_MARKET, settings))
        except Exception as exc:
            print(f"Testmail fehlgeschlagen: {exc}", file=sys.stderr)
            return 1
        print("Testmail gesendet.")
        return 0

    try:
        results = run(at=args.at, settings=settings)
    except Exception:
        logger.exception("Unerwarteter Fehler im Lauf")
        return 1

    failed = [name for name, result in results.items() if "error" in result]
    if failed:
        logger.error("Unerwarteter Fehler in Markt(en): %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
