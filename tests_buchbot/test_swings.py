import pandas as pd

from buchbot.swings import HIGH, LOW, find_swings


def make_df(highs, lows=None):
    highs = list(highs)
    lows = list(lows) if lows is not None else [h - 1.0 for h in highs]
    return pd.DataFrame({"high": highs, "low": lows})


def test_swing_hoch_in_der_mitte_wird_erkannt():
    df = make_df([1, 2, 3, 10, 3, 2, 1])
    highs = [s for s in find_swings(df, 2) if s.kind == HIGH]
    assert [(s.pos, s.price) for s in highs] == [(3, 10.0)]


def test_gleichstand_ergibt_nur_das_erste_hoch():
    df = make_df([1, 2, 5, 5, 2, 1])
    highs = [s.pos for s in find_swings(df, 2) if s.kind == HIGH]
    assert highs == [2]


def test_pivot_wird_erst_nach_n_kerzen_bestaetigt():
    df = make_df([1, 2, 3, 10, 3, 2, 1])
    assert [s.pos for s in find_swings(df[:5], 2) if s.kind == HIGH] == []
    assert [s.pos for s in find_swings(df[:6], 2) if s.kind == HIGH] == [3]


def test_swing_tief_ist_spiegelverkehrt():
    lows = [5, 4, 3, 0, 3, 4, 5]
    df = make_df([low + 1 for low in lows], lows)
    tiefs = [s for s in find_swings(df, 2) if s.kind == LOW]
    assert [(s.pos, s.price) for s in tiefs] == [(3, 0.0)]


def test_kein_blick_in_die_zukunft():
    df = make_df([1, 2, 3, 10, 3, 2, 1, 1, 1, 1])
    voll = {(s.pos, s.kind) for s in find_swings(df, 3)}
    for t in range(3, len(df)):
        bis_t = {(s.pos, s.kind) for s in find_swings(df.iloc[:t + 1], 3) if s.pos <= t - 3}
        assert bis_t <= voll
        assert all(pos <= t - 3 for pos, _ in bis_t)
