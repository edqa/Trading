"""
EM Strategy Lab — Novel Strategy Discovery
============================================
Tests 7 fundamentally different strategy archetypes across all 10 instruments
to find edges beyond the ICT/SMC confluence engine.

Strategies:
  1. Opening Range Breakout (ORB)     — trade breakout of first N minutes of session
  2. VWAP Mean Reversion              — fade extremes, target VWAP
  3. Volatility Squeeze Breakout      — BB inside KC → expansion trade
  4. Session Gap Fill                  — trade the fill between session closes/opens
  5. Momentum Ignition                — ride strong bars with trend, trail tight
  6. Time-of-Day Reversal             — specific hours have mean-reversion tendency
  7. Range Compression Breakout       — narrowest N-bar range → directional break

Each strategy is tested with walk-forward (70/30) across all instruments.
"""

import os, glob, re, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── DATA ────────────────────────────────────────────────────────────────────────

DATA_DIRS = [
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_futures_sample",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_ES",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_GC",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_HG",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_J1",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_PA",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_PL",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_RP",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_SI",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_ZW",
]

POINT_VALUE = {
    "NQ": 20.0, "ES": 50.0, "GC": 100.0, "SI": 5000.0, "HG": 25000.0,
    "PL": 50.0, "PA": 100.0, "J1": 125000.0, "RP": 50.0, "ZW": 50.0,
}


def parse_filename(fname):
    base = os.path.basename(fname)
    m = re.match(r"([A-Z0-9]+)_(\w+)_sample\.csv", base)
    return (m.group(1), m.group(2)) if m else (None, None)


def load_csv(fpath):
    sym, tf = parse_filename(fpath)
    if sym is None:
        return None, None, None
    df = pd.read_csv(fpath, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "ts"}).sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("America/New_York", ambiguous="infer",
                                            nonexistent="shift_forward")
    df.set_index("ts", inplace=True)
    return df, sym, tf


def load_all_5min():
    seen = {}
    files = []
    for d in DATA_DIRS:
        if os.path.exists(d):
            files.extend(glob.glob(os.path.join(d, "*.csv")))
    data = {}
    for f in sorted(files):
        sym, tf = parse_filename(f)
        if sym is None or tf != "5min":
            continue
        if sym not in seen:
            seen[sym] = True
            df, _, _ = load_csv(f)
            if df is not None and len(df) > 200:
                data[sym] = df
    return data


def compute_atr(df, length=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()


def simulate(df, trades, max_bars=48):
    """Generic forward-walk simulator. Trades need: ts, direction, entry, sl, tp."""
    if trades.empty:
        return trades
    c_arr = df["close"].values
    h_arr = df["high"].values
    l_arr = df["low"].values
    bar_pos = {ts: i for i, ts in enumerate(df.index)}
    results = []
    for _, tr in trades.iterrows():
        si = bar_pos.get(tr["ts"])
        if si is None or si >= len(c_arr) - 1:
            continue
        d, entry, sl, tp = tr["direction"], tr["entry"], tr["sl"], tr["tp"]
        risk = abs(entry - sl)
        if risk < 1e-12:
            continue
        mb = min(max_bars, len(c_arr) - si - 1)
        hit_tp = hit_sl = False
        for j in range(si + 1, si + 1 + mb):
            if d == 1:
                if l_arr[j] <= sl:
                    hit_sl = True; break
                if h_arr[j] >= tp:
                    hit_tp = True; break
            else:
                if h_arr[j] >= sl:
                    hit_sl = True; break
                if l_arr[j] <= tp:
                    hit_tp = True; break
        if hit_tp:
            R = abs(tp - entry) / risk
        elif hit_sl:
            R = -1.0
        else:
            last = c_arr[min(si + mb, len(c_arr) - 1)]
            R = d * (last - entry) / risk
        results.append({**tr.to_dict(), "R": R, "win": R > 0})
    return pd.DataFrame(results) if results else pd.DataFrame()


def metrics(res):
    if res is None or res.empty or "R" not in res.columns:
        return {"n": 0, "wr": 0, "exp": 0, "pf": 0, "dd": 0}
    r = res["R"].values
    n = len(r)
    w = r[r > 0]
    l = r[r < 0]
    wr = len(w) / n if n else 0
    exp = r.mean()
    pf = w.sum() / abs(l.sum()) if l.size > 0 and l.sum() != 0 else (999 if w.size > 0 else 0)
    cum = np.cumsum(r)
    dd = (cum - np.maximum.accumulate(cum)).min() if len(cum) else 0
    return {"n": n, "wr": wr, "exp": exp, "pf": pf, "dd": dd}


def fmt(v, pct=False, dec=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if pct:
        return f"{v*100:.1f}%"
    return f"{v:.{dec}f}"


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 1: OPENING RANGE BREAKOUT (ORB)
# ══════════════════════════════════════════════════════════════════════════════

def strategy_orb(df, session_start_hour=2, orb_minutes=15, rr=3.0):
    """
    Classic ORB: define range of first N minutes of session.
    Trade breakout with SL at opposite side, TP at RR multiple.
    """
    atr = compute_atr(df)
    hour = df.index.hour
    minute = df.index.minute
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]

    orb_bars = orb_minutes // 5  # on 5min chart

    records = []
    i = 0
    idx = df.index
    while i < len(df) - orb_bars - 1:
        # Find session start
        if hour[i] == session_start_hour and minute[i] == 0:
            # Compute ORB range
            orb_high = h.iloc[i:i+orb_bars].max()
            orb_low  = l.iloc[i:i+orb_bars].min()
            orb_range = orb_high - orb_low

            if orb_range < 1e-9:
                i += orb_bars
                continue

            # Scan for breakout in remaining session (next 36 bars = 3hrs)
            scan_end = min(i + orb_bars + 36, len(df))
            for j in range(i + orb_bars, scan_end):
                if h.iloc[j] > orb_high:
                    # Long breakout
                    entry = orb_high
                    sl = orb_low
                    tp = entry + rr * (entry - sl)
                    records.append(dict(ts=idx[j], direction=1, entry=entry,
                                       sl=sl, tp=tp, session="ORB"))
                    break
                elif l.iloc[j] < orb_low:
                    # Short breakout
                    entry = orb_low
                    sl = orb_high
                    tp = entry - rr * (sl - entry)
                    records.append(dict(ts=idx[j], direction=-1, entry=entry,
                                       sl=sl, tp=tp, session="ORB"))
                    break

            i = scan_end  # skip to next session
        else:
            i += 1

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 2: VWAP MEAN REVERSION
# ══════════════════════════════════════════════════════════════════════════════

def strategy_vwap_reversion(df, band_mult=2.0, rr=2.0):
    """
    When price touches VWAP ± N stddev band, fade back to VWAP.
    SL beyond the band, TP at VWAP.
    """
    h, l, c, v = df["high"].values, df["low"].values, df["close"].values, df["volume"].values
    tp_ = (df["high"] + df["low"] + df["close"]) / 3
    # Session VWAP (rolling 78 bars ≈ 6.5hrs)
    cum_tpv = (tp_ * df["volume"]).rolling(78).sum()
    cum_v   = df["volume"].rolling(78).sum().replace(0, np.nan)
    vwap = (cum_tpv / cum_v).values

    # VWAP stddev bands
    sq_diff = ((df["close"] - pd.Series(vwap, index=df.index)) ** 2).rolling(78).mean()
    std = np.sqrt(sq_diff).values
    upper = vwap + band_mult * std
    lower = vwap - band_mult * std

    atr = compute_atr(df).values
    hour = df.index.hour

    records = []
    cooldown = 0
    for i in range(78, len(df)):
        if cooldown > 0:
            cooldown -= 1
            continue
        hr = hour[i]
        if not ((2 <= hr < 5) or (9 <= hr < 16)):
            continue
        if np.isnan(vwap[i]) or np.isnan(upper[i]):
            continue

        a = atr[i]
        if a < 1e-9:
            continue

        # Short when touching upper band
        if h[i] >= upper[i] and c[i] < upper[i]:
            entry = c[i]
            sl = entry + 0.75 * a
            tp = vwap[i]
            if abs(entry - tp) > 0.5 * a:
                records.append(dict(ts=df.index[i], direction=-1,
                                   entry=entry, sl=sl, tp=tp, session="VWAP_REV"))
                cooldown = 6

        # Long when touching lower band
        elif l[i] <= lower[i] and c[i] > lower[i]:
            entry = c[i]
            sl = entry - 0.75 * a
            tp = vwap[i]
            if abs(tp - entry) > 0.5 * a:
                records.append(dict(ts=df.index[i], direction=1,
                                   entry=entry, sl=sl, tp=tp, session="VWAP_REV"))
                cooldown = 6

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 3: VOLATILITY SQUEEZE BREAKOUT
# ══════════════════════════════════════════════════════════════════════════════

def strategy_squeeze(df, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5, rr=3.0):
    """
    Bollinger Bands inside Keltner Channels = squeeze.
    When squeeze releases, trade the breakout direction.
    """
    c_s = df["close"]

    # Bollinger Bands
    bb_mid = c_s.rolling(bb_len).mean()
    bb_std = c_s.rolling(bb_len).std()
    bb_upper = bb_mid + bb_mult * bb_std
    bb_lower = bb_mid - bb_mult * bb_std

    # Keltner Channels
    atr_s = compute_atr(df, kc_len)
    kc_mid = c_s.ewm(span=kc_len, adjust=False).mean()
    kc_upper = kc_mid + kc_mult * atr_s
    kc_lower = kc_mid - kc_mult * atr_s

    # Squeeze = BB inside KC
    squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
    squeeze_off = (squeeze.shift(1).fillna(False) & ~squeeze).values

    mom_bull = (c_s > bb_mid).values
    c = c_s.values
    atr = atr_s.values
    hour = df.index.hour

    records = []
    cooldown = 0
    for i in range(bb_len + 1, len(df)):
        if cooldown > 0:
            cooldown -= 1
            continue
        hr = hour[i]
        if not squeeze_off[i] or not ((2 <= hr < 5) or (9 <= hr < 16)):
            continue
        a = atr[i]
        if np.isnan(a) or a < 1e-9:
            continue

        if mom_bull[i]:
            entry = c[i]
            sl = entry - 1.0 * a
            tp = entry + rr * a
            records.append(dict(ts=df.index[i], direction=1, entry=entry,
                               sl=sl, tp=tp, session="SQUEEZE"))
            cooldown = 6
        else:
            entry = c[i]
            sl = entry + 1.0 * a
            tp = entry - rr * a
            records.append(dict(ts=df.index[i], direction=-1, entry=entry,
                               sl=sl, tp=tp, session="SQUEEZE"))
            cooldown = 6

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 4: SESSION GAP FILL
# ══════════════════════════════════════════════════════════════════════════════

def strategy_gap_fill(df, min_gap_atr=0.5, rr=2.0):
    """
    At session open, if price gaps from prior session close,
    trade the gap fill back to the close level.
    """
    c, o, h, l = df["close"], df["open"], df["high"], df["low"]
    atr = compute_atr(df)
    hour = df.index.hour
    minute = df.index.minute

    # Session boundaries (London open = 2:00, NY open = 9:30)
    session_opens = [(2, 0), (9, 30)]

    records = []
    for i in range(1, len(df)):
        hr, mn = hour[i], minute[i]
        if not any(hr == sh and mn == sm for sh, sm in session_opens):
            continue

        a = atr.iloc[i]
        if pd.isna(a) or a < 1e-9:
            continue

        prev_close = c.iloc[i - 1]
        curr_open = o.iloc[i]
        gap = curr_open - prev_close

        if abs(gap) < min_gap_atr * a:
            continue

        if gap > 0:
            # Gapped up → short to fill
            entry = curr_open
            sl = entry + 1.0 * a
            tp = prev_close
            records.append(dict(ts=df.index[i], direction=-1, entry=entry,
                               sl=sl, tp=tp, session="GAP_FILL"))
        else:
            # Gapped down → long to fill
            entry = curr_open
            sl = entry - 1.0 * a
            tp = prev_close
            records.append(dict(ts=df.index[i], direction=1, entry=entry,
                               sl=sl, tp=tp, session="GAP_FILL"))

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 5: MOMENTUM IGNITION
# ══════════════════════════════════════════════════════════════════════════════

def strategy_momentum(df, body_atr_mult=1.5, vol_mult=2.0, rr=3.0):
    """
    Big body candle + high volume = momentum ignition.
    Enter in direction of the candle, tight trail.
    """
    o_a, c_a = df["open"].values, df["close"].values
    v_a = df["volume"].values
    atr_a = compute_atr(df).values
    body = np.abs(c_a - o_a)
    avg_vol = df["volume"].rolling(20).mean().values

    big_bull = (c_a > o_a) & (body > body_atr_mult * atr_a) & (v_a > vol_mult * avg_vol)
    big_bear = (c_a < o_a) & (body > body_atr_mult * atr_a) & (v_a > vol_mult * avg_vol)

    # Deduplicate
    big_bull[1:] = big_bull[1:] & ~big_bull[:-1]
    big_bear[1:] = big_bear[1:] & ~big_bear[:-1]

    hour = df.index.hour

    records = []
    for i in range(21, len(df)):
        hr = hour[i]
        if not ((2 <= hr < 5) or (9 <= hr < 16)):
            continue
        a = atr_a[i]
        if np.isnan(a) or a < 1e-9:
            continue

        if big_bull[i]:
            entry = c_a[i]
            sl = entry - 0.75 * a
            tp = entry + rr * 0.75 * a
            records.append(dict(ts=df.index[i], direction=1, entry=entry,
                               sl=sl, tp=tp, session="MOMENTUM"))
        elif big_bear[i]:
            entry = c_a[i]
            sl = entry + 0.75 * a
            tp = entry - rr * 0.75 * a
            records.append(dict(ts=df.index[i], direction=-1, entry=entry,
                               sl=sl, tp=tp, session="MOMENTUM"))

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 6: TIME-OF-DAY REVERSAL
# ══════════════════════════════════════════════════════════════════════════════

def strategy_tod_reversal(df, reversal_hours=(3, 10, 14), lookback=6, rr=2.0):
    """
    At specific hours known for reversals (mid-London, mid-NY AM, mid-NY PM),
    if price has trended in one direction for N bars, fade it.
    """
    c_a = df["close"].values
    atr_a = compute_atr(df).values
    hour = df.index.hour
    minute = df.index.minute

    records = []
    cooldown = 0
    for i in range(lookback + 1, len(df)):
        if cooldown > 0:
            cooldown -= 1
            continue
        if hour[i] not in reversal_hours or minute[i] != 0:
            continue
        a = atr_a[i]
        if np.isnan(a) or a < 1e-9:
            continue

        recent_move = c_a[i] - c_a[i - lookback]

        if recent_move > 0.75 * a:
            entry = c_a[i]
            sl = entry + 1.0 * a
            tp = entry - rr * a
            records.append(dict(ts=df.index[i], direction=-1, entry=entry,
                               sl=sl, tp=tp, session="TOD_REV"))
            cooldown = 6
        elif recent_move < -0.75 * a:
            entry = c_a[i]
            sl = entry - 1.0 * a
            tp = entry + rr * a
            records.append(dict(ts=df.index[i], direction=1, entry=entry,
                               sl=sl, tp=tp, session="TOD_REV"))
            cooldown = 6

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 7: RANGE COMPRESSION BREAKOUT (NR4/NR7 adapted to intraday)
# ══════════════════════════════════════════════════════════════════════════════

def strategy_narrow_range(df, lookback=7, rr=3.0):
    """
    NR7 concept on 5-min: when current bar has the narrowest range
    of the last N bars, next breakout tends to be directional.
    """
    h_a, l_a, c_a = df["high"].values, df["low"].values, df["close"].values
    bar_range = df["high"] - df["low"]
    atr_a = compute_atr(df).values

    min_range = bar_range.rolling(lookback).min().values
    br_a = bar_range.values
    is_nr = br_a == min_range

    hour = df.index.hour

    ema9 = df["close"].ewm(span=9, adjust=False).mean().values
    ema21 = df["close"].ewm(span=21, adjust=False).mean().values

    records = []
    cooldown = 0
    for i in range(lookback + 1, len(df)):
        if cooldown > 0:
            cooldown -= 1
            continue
        hr = hour[i]
        if not is_nr[i] or not ((2 <= hr < 5) or (9 <= hr < 16)):
            continue
        a = atr_a[i]
        if np.isnan(a) or a < 1e-9:
            continue

        if ema9[i] > ema21[i]:
            entry = h_a[i]
            sl = l_a[i]
            risk = entry - sl
            if risk < 0.1 * a:
                continue
            tp = entry + rr * risk
            records.append(dict(ts=df.index[i], direction=1, entry=entry,
                               sl=sl, tp=tp, session="NR_BREAK"))
            cooldown = 6
        else:
            entry = l_a[i]
            sl = h_a[i]
            risk = sl - entry
            if risk < 0.1 * a:
                continue
            tp = entry - rr * risk
            records.append(dict(ts=df.index[i], direction=-1, entry=entry,
                               sl=sl, tp=tp, session="NR_BREAK"))
            cooldown = 6

    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  RUN ALL STRATEGIES ACROSS ALL MARKETS
# ══════════════════════════════════════════════════════════════════════════════

STRATEGIES = {
    "ORB (London)":    lambda df: strategy_orb(df, session_start_hour=2, orb_minutes=15, rr=3.0),
    "ORB (NY AM)":     lambda df: strategy_orb(df, session_start_hour=9, orb_minutes=15, rr=3.0),
    "VWAP Reversion":  lambda df: strategy_vwap_reversion(df, band_mult=2.0),
    "Squeeze Breakout": lambda df: strategy_squeeze(df, rr=3.0),
    "Gap Fill":        lambda df: strategy_gap_fill(df, min_gap_atr=0.5),
    "Momentum Ignite": lambda df: strategy_momentum(df, body_atr_mult=1.5, vol_mult=2.0, rr=3.0),
    "TOD Reversal":    lambda df: strategy_tod_reversal(df, reversal_hours=(3, 10, 14)),
    "Narrow Range":    lambda df: strategy_narrow_range(df, lookback=7, rr=3.0),
}

# Also test parameter variations for the top strategies
ORB_VARIANTS = {
    "ORB Ldn 10min RR2": lambda df: strategy_orb(df, 2, 10, 2.0),
    "ORB Ldn 15min RR2": lambda df: strategy_orb(df, 2, 15, 2.0),
    "ORB Ldn 15min RR4": lambda df: strategy_orb(df, 2, 15, 4.0),
    "ORB Ldn 20min RR3": lambda df: strategy_orb(df, 2, 20, 3.0),
    "ORB Ldn 30min RR2": lambda df: strategy_orb(df, 2, 30, 2.0),
    "ORB Ldn 30min RR3": lambda df: strategy_orb(df, 2, 30, 3.0),
}

VWAP_VARIANTS = {
    "VWAP 1.5σ":  lambda df: strategy_vwap_reversion(df, band_mult=1.5),
    "VWAP 2.0σ":  lambda df: strategy_vwap_reversion(df, band_mult=2.0),
    "VWAP 2.5σ":  lambda df: strategy_vwap_reversion(df, band_mult=2.5),
    "VWAP 3.0σ":  lambda df: strategy_vwap_reversion(df, band_mult=3.0),
}

MOMENTUM_VARIANTS = {
    "Mom 1.25x body, 1.5x vol": lambda df: strategy_momentum(df, 1.25, 1.5, 3.0),
    "Mom 1.5x body, 2.0x vol":  lambda df: strategy_momentum(df, 1.5, 2.0, 3.0),
    "Mom 2.0x body, 2.0x vol":  lambda df: strategy_momentum(df, 2.0, 2.0, 3.0),
    "Mom 1.5x body, 2.5x vol":  lambda df: strategy_momentum(df, 1.5, 2.5, 3.0),
    "Mom 1.5x RR4":             lambda df: strategy_momentum(df, 1.5, 2.0, 4.0),
    "Mom 1.5x RR2":             lambda df: strategy_momentum(df, 1.5, 2.0, 2.0),
}


if __name__ == "__main__":
    print("=" * 75)
    print("EM STRATEGY LAB — NOVEL STRATEGY DISCOVERY")
    print("=" * 75)

    data = load_all_5min()
    symbols = sorted(data.keys())
    print(f"\nLoaded {len(symbols)} instruments: {', '.join(symbols)}")

    # ── PHASE 1: Run all strategies on all markets ───────────────────────────

    print("\n" + "=" * 75)
    print("PHASE 1: ALL STRATEGIES × ALL MARKETS (full dataset)")
    print("=" * 75)

    all_results = []

    for strat_name, strat_fn in STRATEGIES.items():
        print(f"\n  📊 {strat_name}")
        for sym in symbols:
            df = data[sym]
            try:
                trades = strat_fn(df)
                sim = simulate(df, trades)
                m = metrics(sim)
                pv = POINT_VALUE.get(sym, 1)
                atr_avg = compute_atr(df).mean()
                dollar = m["exp"] * atr_avg * pv if m["n"] > 0 else 0

                all_results.append({
                    "strategy": strat_name, "symbol": sym,
                    "trades": m["n"], "wr": m["wr"], "exp": m["exp"],
                    "pf": m["pf"], "dd": m["dd"], "dollar_per_trade": dollar,
                })

                if m["n"] > 0:
                    print(f"    {sym:>3s}: {m['n']:>3d} trades, {m['wr']*100:.1f}% WR, "
                          f"{m['exp']:+.3f}R, PF={m['pf']:.2f}, ~${dollar:.0f}/trade")
            except Exception as e:
                print(f"    {sym:>3s}: ERROR — {e}")

    results_df = pd.DataFrame(all_results)

    # ── PHASE 2: Walk-forward validation for promising combos ────────────────

    print("\n\n" + "=" * 75)
    print("PHASE 2: WALK-FORWARD VALIDATION (top combos)")
    print("=" * 75)

    # Filter: positive expectancy and >= 3 trades
    promising = results_df[(results_df["exp"] > 0) & (results_df["trades"] >= 3)]
    promising = promising.sort_values("exp", ascending=False)

    wf_results = []
    for _, row in promising.iterrows():
        strat_name = row["strategy"]
        sym = row["symbol"]
        df = data[sym]
        strat_fn = STRATEGIES[strat_name]

        split = int(len(df) * 0.70)
        train_df = df.iloc[:split]
        test_df  = df.iloc[split:]

        try:
            # In-sample
            tr_trades = strat_fn(train_df)
            tr_sim = simulate(train_df, tr_trades)
            tr_m = metrics(tr_sim)

            # Out-of-sample
            te_trades = strat_fn(test_df)
            te_sim = simulate(test_df, te_trades)
            te_m = metrics(te_sim)

            overfit = (tr_m["exp"] > 0 and te_m["exp"] < tr_m["exp"] * 0.5)

            wf_results.append({
                "strategy": strat_name, "symbol": sym,
                "is_n": tr_m["n"], "is_exp": tr_m["exp"], "is_wr": tr_m["wr"],
                "oos_n": te_m["n"], "oos_exp": te_m["exp"], "oos_wr": te_m["wr"],
                "oos_pf": te_m["pf"], "oos_dd": te_m["dd"],
                "overfit": overfit,
            })
        except Exception:
            pass

    wf_df = pd.DataFrame(wf_results)
    if not wf_df.empty:
        wf_df = wf_df.sort_values("oos_exp", ascending=False)
        print("\nTop Walk-Forward Results (OOS):")
        for _, r in wf_df.head(20).iterrows():
            of = " ⚠️OVERFIT" if r["overfit"] else ""
            print(f"  {r['strategy']:>20s} × {r['symbol']:>3s}: "
                  f"IS={r['is_exp']:+.2f}R ({r['is_n']}tr) → "
                  f"OOS={r['oos_exp']:+.2f}R ({r['oos_n']}tr) PF={r['oos_pf']:.2f}{of}")

    # ── PHASE 3: Parameter sweep for best strategies ─────────────────────────

    print("\n\n" + "=" * 75)
    print("PHASE 3: PARAMETER VARIANTS FOR TOP STRATEGIES")
    print("=" * 75)

    # Find which strategies+markets had positive OOS
    if not wf_df.empty:
        top_strats = wf_df[wf_df["oos_exp"] > 0]["strategy"].unique()
    else:
        top_strats = []

    variant_results = []

    # ORB variants (always test — it's a classic)
    print("\n  ORB Variants on all markets:")
    for vname, vfn in ORB_VARIANTS.items():
        for sym in symbols:
            df = data[sym]
            split = int(len(df) * 0.70)
            try:
                te_trades = vfn(df.iloc[split:])
                te_sim = simulate(df.iloc[split:], te_trades)
                te_m = metrics(te_sim)
                if te_m["n"] >= 2:
                    variant_results.append({
                        "variant": vname, "symbol": sym,
                        "oos_n": te_m["n"], "oos_exp": te_m["exp"],
                        "oos_wr": te_m["wr"], "oos_pf": te_m["pf"],
                    })
                    if te_m["exp"] > 0:
                        print(f"    {vname:>25s} × {sym:>3s}: "
                              f"{te_m['n']}tr, {te_m['exp']:+.2f}R, PF={te_m['pf']:.2f}")
            except Exception:
                pass

    # VWAP variants
    print("\n  VWAP Variants on all markets:")
    for vname, vfn in VWAP_VARIANTS.items():
        for sym in symbols:
            df = data[sym]
            split = int(len(df) * 0.70)
            try:
                te_trades = vfn(df.iloc[split:])
                te_sim = simulate(df.iloc[split:], te_trades)
                te_m = metrics(te_sim)
                if te_m["n"] >= 2:
                    variant_results.append({
                        "variant": vname, "symbol": sym,
                        "oos_n": te_m["n"], "oos_exp": te_m["exp"],
                        "oos_wr": te_m["wr"], "oos_pf": te_m["pf"],
                    })
                    if te_m["exp"] > 0:
                        print(f"    {vname:>25s} × {sym:>3s}: "
                              f"{te_m['n']}tr, {te_m['exp']:+.2f}R, PF={te_m['pf']:.2f}")
            except Exception:
                pass

    # Momentum variants
    print("\n  Momentum Variants on all markets:")
    for vname, vfn in MOMENTUM_VARIANTS.items():
        for sym in symbols:
            df = data[sym]
            split = int(len(df) * 0.70)
            try:
                te_trades = vfn(df.iloc[split:])
                te_sim = simulate(df.iloc[split:], te_trades)
                te_m = metrics(te_sim)
                if te_m["n"] >= 2:
                    variant_results.append({
                        "variant": vname, "symbol": sym,
                        "oos_n": te_m["n"], "oos_exp": te_m["exp"],
                        "oos_wr": te_m["wr"], "oos_pf": te_m["pf"],
                    })
                    if te_m["exp"] > 0:
                        print(f"    {vname:>25s} × {sym:>3s}: "
                              f"{te_m['n']}tr, {te_m['exp']:+.2f}R, PF={te_m['pf']:.2f}")
            except Exception:
                pass

    var_df = pd.DataFrame(variant_results)

    # ── GENERATE REPORT ──────────────────────────────────────────────────────

    print("\n\n📝 Generating Strategy_Lab_Report.md ...")

    lines = []
    lines.append("# EM Strategy Lab — Novel Strategy Discovery Report\n")
    lines.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ET  ")
    lines.append(f"**Instruments:** {', '.join(symbols)}  ")
    lines.append(f"**Strategies tested:** {len(STRATEGIES)}  ")
    lines.append(f"**Walk-forward:** 70/30 split\n")

    # Phase 1: Full heatmap
    lines.append("## Phase 1: Strategy × Market Heatmap (Expectancy R, full data)\n")

    # Build pivot
    if not results_df.empty:
        pivot = results_df.pivot_table(index="strategy", columns="symbol",
                                        values="exp", aggfunc="first")
        pivot = pivot.reindex(columns=symbols)

        header = "| Strategy |"
        for s in symbols:
            header += f" {s} |"
        lines.append(header)
        sep = "|----------|"
        for _ in symbols:
            sep += "------|"
        lines.append(sep)

        for strat in pivot.index:
            row = f"| {strat} |"
            for sym in symbols:
                v = pivot.loc[strat, sym] if sym in pivot.columns else np.nan
                if pd.isna(v):
                    row += " — |"
                else:
                    marker = "**" if v > 0.5 else ""
                    row += f" {marker}{v:+.2f}R{marker} |"
            lines.append(row)
        lines.append("")

    # Phase 2: Walk-forward top results
    lines.append("\n## Phase 2: Walk-Forward Validated Results\n")
    lines.append("Only showing combos with positive OOS expectancy.\n")
    lines.append("| Rank | Strategy | Market | IS Trades | IS Exp | OOS Trades | OOS Exp | OOS WR | OOS PF | Overfit |")
    lines.append("|------|----------|--------|-----------|--------|------------|---------|--------|--------|---------|")

    if not wf_df.empty:
        for rank, (_, r) in enumerate(wf_df[wf_df["oos_exp"] > 0].head(25).iterrows(), 1):
            of = "Yes" if r["overfit"] else "No"
            lines.append(
                f"| {rank} | {r['strategy']} | {r['symbol']} "
                f"| {r['is_n']} | {fmt(r['is_exp'])} "
                f"| {r['oos_n']} | {fmt(r['oos_exp'])} "
                f"| {fmt(r['oos_wr'], pct=True)} | {fmt(r['oos_pf'])} | {of} |"
            )
    lines.append("")

    # Phase 3: Variant results
    lines.append("\n## Phase 3: Parameter Variant Results (OOS only)\n")
    if not var_df.empty:
        pos_var = var_df[var_df["oos_exp"] > 0].sort_values("oos_exp", ascending=False)
        if not pos_var.empty:
            lines.append("| Variant | Market | OOS Trades | OOS Exp | OOS WR | OOS PF |")
            lines.append("|---------|--------|------------|---------|--------|--------|")
            for _, r in pos_var.head(20).iterrows():
                lines.append(f"| {r['variant']} | {r['symbol']} | {r['oos_n']} "
                            f"| {fmt(r['oos_exp'])} | {fmt(r['oos_wr'], pct=True)} "
                            f"| {fmt(r['oos_pf'])} |")
            lines.append("")

    # Recommendations
    lines.append("\n## Key Findings & Recommendations\n")

    # Best new strategy
    if not wf_df.empty:
        best_new = wf_df[wf_df["oos_exp"] > 0].head(1)
        if not best_new.empty:
            b = best_new.iloc[0]
            lines.append(f"### Best New Strategy: **{b['strategy']}** on **{b['symbol']}**\n")
            lines.append(f"- OOS Expectancy: {fmt(b['oos_exp'])}R")
            lines.append(f"- OOS Win Rate: {fmt(b['oos_wr'], pct=True)}")
            lines.append(f"- OOS Profit Factor: {fmt(b['oos_pf'])}")
            lines.append(f"- Overfit: {'Yes' if b['overfit'] else 'No'}\n")

    # Strategy archetypes summary
    lines.append("### Strategy Archetype Summary\n")
    if not results_df.empty:
        for strat in STRATEGIES.keys():
            sub = results_df[results_df["strategy"] == strat]
            pos = sub[sub["exp"] > 0]
            lines.append(f"- **{strat}**: Positive on {len(pos)}/{len(sub)} markets. "
                        f"Avg exp: {sub['exp'].mean():+.3f}R")
    lines.append("")

    # Complementary strategies
    lines.append("### Strategies That Complement Your Existing ICT Engine\n")
    lines.append("Your current strategy is a **trend-following confluence** system. "
                 "These archetypes use *different* market mechanics and can diversify:\n")
    lines.append("1. **VWAP Mean Reversion** — profits when your trend strategy would stop out (mean-reverting sessions)")
    lines.append("2. **ORB** — time-based entry removes subjectivity, purely mechanical")
    lines.append("3. **Squeeze Breakout** — volatility regime detection, fires at compression → expansion transitions")
    lines.append("")

    lines.append("\n---\n")
    lines.append("*Report auto-generated by strategy_lab.py — EM Strategy Lab*")

    report_path = "/Users/edwinmaina/Documents/Space/Trading/Strategy_Lab_Report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\n✅ Report saved to: {report_path}")
    print("Done!")
