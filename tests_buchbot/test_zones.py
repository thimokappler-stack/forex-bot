from types import SimpleNamespace

import pandas as pd
import pytest

from buchbot.models import Signal
from buchbot.swings import HIGH, LOW, Swing
from buchbot.zones import RESISTANCE, SUPPORT, Zone, annotate, build_zones, limit_per_side, swing_trend


CONFIG = SimpleNamespace(
    SR_ENABLED=True,
    SWING_N=1,
    SR_LOOKBACK_CANDLES=400,
    SR_ZONE_WIDTH_ATR=0.5,
    SR_MIN_ZONE_WIDTH_ATR=0.25,
    SR_MIN_TOUCHES=3,
    SR_PROXIMITY_ATR=0.5,
    SR_MAX_ZONES_PER_SIDE=None,
    INTERVAL="15m",
)


def zigzag_df(points):
    """Kerzen aus (Preis, "H" oder "L") Punkten. Ein H-Punkt setzt das High, ein L-Punkt das Low."""
    rows = []
    for price, kind in points:
        if kind == "H":
            rows.append({"open": price - 0.1, "high": price, "low": price - 0.2, "close": price - 0.1})
        else:
            rows.append({"open": price + 0.1, "high": price + 0.2, "low": price, "close": price + 0.1})
    index = pd.date_range("2024-01-01", periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=index)


def add_signal_candle(df, high, low):
    """Hängt die Signalkerze an. Ihr Zeitstempel ist die Schlusszeit (Index + 15 min)."""
    row = pd.DataFrame(
        [{"open": low, "high": high, "low": low, "close": high}],
        index=[df.index[-1] + pd.Timedelta("15min")],
    )
    return pd.concat([df, row])


def make_signal(df, direction, entry, **tags):
    return Signal(
        time=df.index[-1] + pd.Timedelta("15min"),
        symbol="EURUSD=X",
        interval="15m",
        source="test",
        pattern="Test",
        direction=direction,
        entry=entry,
        atr=1.0,
        tags=dict(tags),
    )


# Ein Pivot-Hoch bei 3.0 (3x) und Pivot-Tiefs bei 1.00, 1.05, 1.10 -> starke Unterstützung 1.00-1.10
def df_support_and_resistance():
    points = [(3.0, "H"), (1.00, "L"), (3.0, "H"), (1.05, "L"), (3.0, "H"), (1.10, "L"), (3.0, "H")]
    return add_signal_candle(zigzag_df(points), high=1.22, low=1.11)


# Pivot-Hochs bei 1.00, 1.05, 1.10 -> starker Widerstand; Pivot-Tiefs 0.20-0.30 liegen weit genug weg, damit sie nicht mitclustern
def df_resistance_band():
    points = [(0.20, "L"), (1.00, "H"), (0.25, "L"), (1.05, "H"), (0.25, "L"), (1.10, "H"), (0.30, "L")]
    return add_signal_candle(zigzag_df(points), high=1.00, low=0.94)


def test_cluster_bildet_zwei_zonen_mit_beruehrungen():
    pivots = [Swing(0, p, HIGH) for p in (1.00, 1.10, 1.20)] + [Swing(1, p, LOW) for p in (2.00, 2.10)]
    zones = build_zones(pivots, atr=1.0, entry=4.0, config=CONFIG)
    assert [(z.touches, z.strong, z.kind) for z in zones] == [(3, True, SUPPORT), (2, False, SUPPORT)]
    # Mindestbreite 0.25 ATR, um die Mitte zentriert
    assert (zones[0].low, zones[0].high) == (pytest.approx(0.975), pytest.approx(1.225))
    assert (zones[1].low, zones[1].high) == (pytest.approx(1.925), pytest.approx(2.175))


def test_zone_wird_auf_mindestbreite_zentriert():
    pivots = [Swing(0, 5.00, HIGH), Swing(1, 5.05, LOW)]
    (zone,) = build_zones(pivots, atr=1.0, entry=4.0, config=CONFIG)
    assert zone.low == pytest.approx(4.90)
    assert zone.high == pytest.approx(5.15)
    assert zone.kind == RESISTANCE


@pytest.mark.parametrize(
    "highs, lows, trend",
    [
        ((1.0, 1.2), (0.9, 1.0), "up"),
        ((1.2, 1.0), (1.0, 0.9), "down"),
        ((1.0, 1.2), (1.0, 0.9), "range"),
    ],
)
def test_swing_trend_aufwaerts_abwaerts_seitwaerts(highs, lows, trend):
    pivots = [Swing(0, highs[0], HIGH), Swing(1, lows[0], LOW), Swing(2, highs[1], HIGH), Swing(3, lows[1], LOW)]
    assert swing_trend(pivots) == trend


def test_swing_trend_ohne_genug_pivots_ist_leer():
    assert swing_trend([Swing(0, 1.0, HIGH), Swing(1, 0.9, LOW)]) is None


def test_buy_an_starker_unterstuetzung_passt():
    df = df_support_and_resistance()
    signal = make_signal(df, "BUY", entry=1.12, pattern_low=1.08)
    (out,) = annotate([signal], df, CONFIG)
    t = out.tags
    assert t["sr_relation"] == "at_support"
    assert t["sr_zone_low"] == pytest.approx(0.925)
    assert t["sr_zone_high"] == pytest.approx(1.175)
    assert t["sr_touches"] == 3
    assert t["sr_aligned"] is True
    assert t["sr_against"] is False
    assert t["sr_room_atr"] == pytest.approx(2.875 - 1.12)
    assert t["swing_trend"] == "range"


def test_buy_unter_starkem_widerstand_ist_against():
    df = df_support_and_resistance()
    signal = make_signal(df, "BUY", entry=2.80, pattern_low=2.80)
    (out,) = annotate([signal], df, CONFIG)
    assert out.tags["sr_relation"] == "none"
    assert out.tags["sr_aligned"] is False
    assert out.tags["sr_against"] is True
    assert out.tags["sr_against_level"] == pytest.approx(2.875)


def test_sell_an_starkem_widerstand_passt():
    df = df_resistance_band()
    signal = make_signal(df, "SELL", entry=1.04, pattern_high=1.08)
    (out,) = annotate([signal], df, CONFIG)
    assert out.tags["sr_relation"] == "at_resistance"
    assert out.tags["sr_zone_low"] == pytest.approx(0.925)
    assert out.tags["sr_zone_high"] == pytest.approx(1.175)
    assert out.tags["sr_aligned"] is True


def test_sell_ueber_starker_unterstuetzung_ist_against():
    df = df_support_and_resistance()
    signal = make_signal(df, "SELL", entry=1.20, pattern_high=1.15)
    (out,) = annotate([signal], df, CONFIG)
    assert out.tags["sr_relation"] == "none"
    assert out.tags["sr_aligned"] is False
    assert out.tags["sr_against"] is True
    assert out.tags["sr_room_atr"] == pytest.approx(1.20 - 1.175)


def test_neutral_beschreibt_nahe_zone_ohne_aligned_und_against():
    df = df_support_and_resistance()
    signal = make_signal(df, "NEUTRAL", entry=1.12)
    (out,) = annotate([signal], df, CONFIG)
    assert out.tags["sr_relation"] == "at_support"
    assert out.tags["sr_aligned"] is None
    assert out.tags["sr_against"] is None
    assert out.tags["sr_room_atr"] is None


def test_neutral_ohne_nahe_zone_ist_none():
    df = df_support_and_resistance()
    signal = make_signal(df, "NEUTRAL", entry=2.00)
    (out,) = annotate([signal], df, CONFIG)
    assert out.tags["sr_relation"] == "none"
    assert out.tags["sr_zone_low"] is None


def test_kein_look_ahead_spaetere_kerzen_aendern_nichts():
    df = df_support_and_resistance()
    signal_a = make_signal(df, "BUY", entry=1.12, pattern_low=1.08)
    (alone,) = annotate([signal_a], df, CONFIG)

    future = zigzag_df([(0.20, "L"), (5.00, "H"), (0.20, "L"), (5.00, "H")])
    future.index = pd.DatetimeIndex([df.index[-1] + pd.Timedelta("15min") * k for k in range(1, 5)])
    longer = pd.concat([df, future])
    signal_b = make_signal(df, "BUY", entry=1.12, pattern_low=1.08)
    (with_future,) = annotate([signal_b], longer, CONFIG)

    assert with_future.tags == alone.tags


def test_sr_deaktiviert_setzt_keine_tags():
    df = df_support_and_resistance()
    signal = make_signal(df, "BUY", entry=1.12, pattern_low=1.08)
    disabled = SimpleNamespace(**{**vars(CONFIG), "SR_ENABLED": False})
    (out,) = annotate([signal], df, disabled)
    assert "sr_relation" not in out.tags


def zone(mid, touches, kind=SUPPORT, width=0.1):
    return Zone(mid - width / 2, mid + width / 2, touches, kind, touches >= 3)


def test_limit_none_laesst_alle_zonen_unveraendert():
    zones = [zone(1.0, 3), zone(1.3, 4, RESISTANCE)]
    assert limit_per_side(zones, 1.1, None) is zones


def test_limit_behaelt_je_seite_die_meisten_beruehrungen():
    supports = [zone(1.00, 3), zone(0.80, 5), zone(0.50, 4)]
    resistances = [zone(1.30, 3, RESISTANCE), zone(1.50, 4, RESISTANCE)]
    kept = limit_per_side(supports + resistances, 1.1, 2)
    assert sorted(z.touches for z in kept if z.kind == SUPPORT) == [4, 5]
    assert sorted(z.touches for z in kept if z.kind == RESISTANCE) == [3, 4]


def test_limit_gleichstand_nimmt_die_dem_einstieg_naehere_zone():
    near = zone(1.08, 3)
    far = zone(1.00, 3)
    farthest = zone(0.50, 3)
    kept = limit_per_side([far, near, farthest], 1.10, 1)
    assert len(kept) == 1
    assert (kept[0].low + kept[0].high) / 2 == pytest.approx(1.08)


def test_limit_mit_weniger_starken_zonen_als_n_behaelt_alle_starken():
    kept = limit_per_side([zone(1.0, 3), zone(1.2, 2)], 1.1, 3)
    assert [(z.touches, z.strong) for z in kept] == [(3, True)]


def test_annotate_tags_kommen_nur_aus_behaltenen_zonen():
    df = df_support_and_resistance()
    signal = make_signal(df, "BUY", entry=1.12, pattern_low=1.08)
    (with_zones,) = annotate([signal], df, CONFIG)
    assert with_zones.tags["sr_relation"] == "at_support"

    none_kept = SimpleNamespace(**{**vars(CONFIG), "SR_MAX_ZONES_PER_SIDE": 0})
    (without_zones,) = annotate([make_signal(df, "BUY", entry=1.12, pattern_low=1.08)], df, none_kept)
    assert without_zones.tags["sr_relation"] == "none"
    assert without_zones.tags["sr_aligned"] is False
    assert without_zones.tags["sr_zone_low"] is None
