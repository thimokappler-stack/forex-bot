# Arbeitsregeln für dieses Repository

- Der **bestehende Bot läuft live** auf dem Raspberry Pi und darf nicht verändert werden: `main.py`, `main_gbpusd.py`, `main_btc.py`, `main_eth.py`, `config.py`, `data.py`, `patterns.py`, `signals.py`, `notify.py`, `backtest.py`, `state.json`, `tests/test_patterns.py`.
- Alle neue Arbeit passiert auf dem Git-Branch `buchmuster` und im neuen Paket `buchbot/`.
- Nicht raten. Bei unklaren Regeln nachfragen.
- Alle Parameter stehen in `buchbot/config.py`, keine festen Zahlen im Code.
- Keine Zugangsdaten im Code oder Repo, nur über `.env`.
- Zu jeder Änderung gehören Tests. Nach jedem Schritt: Tests ausführen und die echte Terminal-Ausgabe zeigen.
- Kleine Schritte. Nach jedem Schritt auf das OK des Nutzers warten.
