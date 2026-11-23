import csv

import pandas as pd

from buchbot.models import Signal
from buchbot.outputs import log_csv


def make_df():
    idx = pd.to_datetime(["2026-05-06 09:45", "2026-05-06 10:00"], utc=True)
    return pd.DataFrame(
        {
            "open": [1.1000, 1.1005],
            "high": [1.1020, 1.1030],
            "low": [1.0990, 1.0995],
            "close": [1.1005, 1.1010],
        },
        index=idx,
    )


def make_signal(pattern="Morning Star", time="2026-05-06 10:15"):
    return Signal(
        time=pd.Timestamp(time, tz="UTC"), symbol="EURUSD=X", interval="15m",
        source="candles_main", pattern=pattern, direction="BUY",
        entry=1.1010, atr=0.001, sl=1.0995, tp=1.1040, risk_pips=15.0, rr=2.0,
        mode="log_only",
        tags={"required_trend": "down", "n_candles": 3,
              "pattern_low": 1.0990, "pattern_high": 1.1030},
    )


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def test_kopfzeile_nur_einmal_beim_anlegen(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    df = make_df()
    log_csv.append_signals([make_signal()], df, "15m", path)
    log_csv.append_signals([make_signal(pattern="Evening Star")], df, "15m", path)

    rows = read_rows(path)
    assert rows[0] == log_csv.COLUMNS
    assert sum(1 for row in rows if row and row[0] == "time") == 1
    assert len(rows) == 3


def test_datei_ist_utf8_sig_mit_bom(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    log_csv.append_signals([make_signal()], make_df(), "15m", path)
    with open(path, "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"


def test_umlaute_werden_korrekt_geschrieben(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    log_csv.append_signals([make_signal(pattern="Drei bärische Soldaten")], make_df(), "15m", path)
    rows = read_rows(path)
    pattern_index = log_csv.COLUMNS.index("pattern")
    assert rows[1][pattern_index] == "Drei bärische Soldaten"


def test_ohlc_der_signalkerze_ist_gefuellt(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    log_csv.append_signals([make_signal()], make_df(), "15m", path)
    rows = read_rows(path)
    record = dict(zip(rows[0], rows[1]))
    # Signalkerze 10:15 Schluss = Startzeit 10:00 -> OHLC der Kerze 10:00
    assert float(record["open"]) == 1.1005
    assert float(record["high"]) == 1.1030
    assert float(record["low"]) == 1.0995
    assert float(record["close"]) == 1.1010


def test_tags_stehen_als_eigene_spalten(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    log_csv.append_signals([make_signal()], make_df(), "15m", path)
    record = dict(zip(*read_rows(path)[:2]))
    assert record["required_trend"] == "down"
    assert record["n_candles"] == "3"
    assert record["pattern_low"] == "1.09900"
    assert record["pattern_high"] == "1.10300"
    assert "tags" not in record


def test_csv_mit_einem_signal_hat_kopf_und_eine_datenzeile(tmp_path):
    path = tmp_path / "signals_log.csv"
    signal = make_signal()
    signal.risk_pips = 6.2075
    log_csv.append_signals([signal], make_df(), "15m", str(path))

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("time;symbol;")
    columns = lines[0].split(";")
    values = lines[1].split(";")
    assert values[columns.index("risk_pips")] == "6.2"


def test_leere_signalliste_legt_keine_datei_an(tmp_path):
    path = tmp_path / "signals_log.csv"
    log_csv.append_signals([], make_df(), "15m", str(path))
    assert not path.exists()


def test_preise_werden_mit_fuenf_nachkommastellen_geschrieben(tmp_path):
    path = str(tmp_path / "signals_log.csv")
    signal = make_signal()
    signal.entry = 1.10098765
    log_csv.append_signals([signal], make_df(), "15m", path)
    record = dict(zip(*read_rows(path)[:2]))
    assert record["entry"] == "1.10099"


def test_log_zeigt_preise_mit_fuenf_nachkommastellen(caplog):
    signal = make_signal()
    signal.entry = 1.10098765
    with caplog.at_level("INFO"):
        log_csv.log_signals([signal])
    assert "Einstieg=1.10099" in caplog.text
