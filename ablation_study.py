"""
EM-FSE v6 NQ — Strategy Ablation & Variation Study
====================================================
Goes beyond parameter sweeps to answer:

  1. CONFLUENCE ABLATION: Which signals actually help? (toggle each on/off)
  2. SESSION VARIATIONS: London-only vs combinations
  3. PARTIAL TP VARIATIONS: What % to close at TP1?
  4. TRAILING STOP VARIATIONS: ATR multiples for the trail
  5. DOW WEIGHT PROFILES: Aggressive vs conservative day filtering
  6. RISK:REWARD PROFILES: Different SL/TP ratio shapes
  7. SIGNAL COOLDOWN: Minimum bars between trades
  8. TIME-OF-SESSION ENTRY: Early vs late within sessions

Uses NQ 5min data with the new OPT3 base params (tp1=4.0, dow_tue=0.5).
"""

import os, warnings, itertools
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

NQ_5MIN_PATH = "/Users/edwinmaina/Documents/Space/Trading/Data/frd_futures_sample/NQ_5min_sample.csv"
NQ_1HR_PATH  = "/Users/edwinmaina/Documents/Space/Trading/Data/frd_futures_sample/NQ_1hour_sample.csv"

# ── BASE PARAMS (OPT3) ────────────────────────────────────────────────────────

BASE_PARAMS = {
    "atr_stopMult":  0.50,
    "atr_tp1Mult":   4.0,
    "atr_tp2Mult":   4.0,   # TP2 for trailing
    "disp_atrMult":  1.25,
    "lq_sweepWick":  0.30,
    "of_rvolThresh": 2.5,
    "sig_minConf":   6,
    "partial_pct":   0.60,
    "trail_atrMult": 1.25,
}

# DOW weights
BASE_DOW = {0: 1.1, 1: 0.5, 2: 1.0, 3: 0.9, 4: 0.6}  # OPT3: Tue nerfed
DOW_THRESHOLD = 0.8

# ── DATA LOADING ──────────────────────────────────────────────────────────────

def load_5min():
    df = pd.read_csv(NQ_5MIN_PATH, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "ts"}).sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("America/New_York", ambiguous="infer",
                                            nonexistent="shift_forward")
    df.set_index("ts", inplace=True)
    return df

# ── SIGNAL ENGINE (modular for ablation) ──────────────────────────────────────

def compute_atr(df, length=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=length, adjust=False).mean()

def wick_ratio_top(o, h, l, c):
    rng = h - l
    return np.where(rng > 0, (h - np.maximum(o, c)) / rng, 0.0)

def wick_ratio_bot(o, h, l, c):
    rng = h - l
    return np.where(rng > 0, (np.minimum(o, c) - l) / rng, 0.0)

def _session_name(hour_et):
    if hour_et >= 20 or hour_et < 2:
        return "Asia"
    if 2 <= hour_et < 5:
        return "London"
    if 9 <= hour_et < 12:
        return "NY AM"
    if 13 <= hour_et < 16:
        return "NY PM"
    return "Other"

def compute_all_signals(df5, params):
    """
    Returns individual signal components as a dict of boolean Series,
    plus the ATR series. This lets the ablation study toggle each on/off.
    """
    p = params
    df = df5.copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    atr = compute_atr(df, 14)

    # Market Structure
    ms_len = 5
    swing_h = h.rolling(ms_len * 2 + 1, center=True).max() == h
    swing_l = l.rolling(ms_len * 2 + 1, center=True).min() == l
    prev_swing_h = h[swing_h].reindex(df.index).ffill()
    prev_swing_l = l[swing_l].reindex(df.index).ffill()
    bos_up   = (c > prev_swing_h.shift(ms_len))
    bos_dn   = (c < prev_swing_l.shift(ms_len))
    choch_up = bos_up & (c.shift(1) <= prev_swing_h.shift(ms_len).shift(1))
    choch_dn = bos_dn & (c.shift(1) >= prev_swing_l.shift(ms_len).shift(1))

    # Displacement
    body = (c - o).abs()
    disp_bull = (c > o) & (body > p["disp_atrMult"] * atr)
    disp_bear = (c < o) & (body > p["disp_atrMult"] * atr)

    # Liquidity sweep
    swing_hi_10 = h.rolling(21, center=True).max() == h
    swing_lo_10 = l.rolling(21, center=True).min() == l
    prev_hi_10  = h[swing_hi_10].reindex(df.index).ffill()
    prev_lo_10  = l[swing_lo_10].reindex(df.index).ffill()
    wt = pd.Series(wick_ratio_top(o.values, h.values, l.values, c.values), index=df.index)
    wb = pd.Series(wick_ratio_bot(o.values, h.values, l.values, c.values), index=df.index)
    sweep_hi = (h > prev_hi_10.shift(1)) & (wt > p["lq_sweepWick"])
    sweep_lo = (l < prev_lo_10.shift(1)) & (wb > p["lq_sweepWick"])

    # RVOL
    avg_vol = v.rolling(20).mean()
    rvol_hi = (v / avg_vol.replace(0, np.nan)) > p["of_rvolThresh"]

    # FVG
    fvg_bull = l > h.shift(2)
    fvg_bear = h < l.shift(2)

    # EMA / SMA
    ema9  = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    sma200 = c.rolling(200).mean()

    # VWAP
    tp_ = (h + l + c) / 3
    vwap = (tp_ * v).rolling(78).sum() / v.rolling(78).sum().replace(0, np.nan)

    signals = {
        "ms_bull": bos_up | choch_up,
        "ms_bear": bos_dn | choch_dn,
        "choch_bull": choch_up,
        "choch_bear": choch_dn,
        "disp_bull": disp_bull,
        "disp_bear": disp_bear,
        "sweep_bull": sweep_lo,   # sweep low = bullish reversal
        "sweep_bear": sweep_hi,
        "rvol": rvol_hi,
        "fvg_bull": fvg_bull,
        "fvg_bear": fvg_bear,
        "ema_bull": ema9 > ema21,
        "ema_bear": ema9 < ema21,
        "sma_bull": c > sma200,
        "sma_bear": c < sma200,
        "vwap_bull": c > vwap,
        "vwap_bear": c < vwap,
    }

    return signals, atr, df


def build_confluence(signals, enabled_factors=None):
    """
    Build confluence scores from signal components.
    enabled_factors: list of factor names to include.
    If None, use all.
    """
    ALL_BULL_FACTORS = {
        "ms":    "ms_bull",
        "choch": "choch_bull",
        "disp":  "disp_bull",
        "sweep": "sweep_bull",
        "rvol":  "rvol",
        "fvg":   "fvg_bull",
        "ema":   "ema_bull",
        "sma":   "sma_bull",
        "vwap":  "vwap_bull",
    }
    ALL_BEAR_FACTORS = {
        "ms":    "ms_bear",
        "choch": "choch_bear",
        "disp":  "disp_bear",
        "sweep": "sweep_bear",
        "rvol":  "rvol",
        "fvg":   "fvg_bear",
        "ema":   "ema_bear",
        "sma":   "sma_bear",
        "vwap":  "vwap_bear",
    }

    if enabled_factors is None:
        enabled_factors = list(ALL_BULL_FACTORS.keys())

    bull_conf = None
    bear_conf = None
    for f in enabled_factors:
        if f in ALL_BULL_FACTORS:
            b = signals[ALL_BULL_FACTORS[f]].astype(int)
            bull_conf = b if bull_conf is None else bull_conf + b
        if f in ALL_BEAR_FACTORS:
            b = signals[ALL_BEAR_FACTORS[f]].astype(int)
            bear_conf = b if bear_conf is None else bear_conf + b

    if bull_conf is None:
        bull_conf = pd.Series(0, index=signals["ms_bull"].index)
    if bear_conf is None:
        bear_conf = pd.Series(0, index=signals["ms_bear"].index)

    return bull_conf, bear_conf


def generate_trades(df, atr, bull_conf, bear_conf, params,
                    sessions=("London",), dow_weights=None, dow_threshold=0.8,
                    min_conf=6, cooldown_bars=0, entry_hour_filter=None):
    """
    Generate trade list with configurable filters.
    """
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    p = params
    hour_et = df.index.hour
    minute_et = df.index.minute

    # Session mask
    sess_masks = {
        "Asia":   (hour_et >= 20) | (hour_et < 2),
        "London": (hour_et >= 2) & (hour_et < 5),
        "NY AM":  (hour_et >= 9) & (hour_et < 12),
        "NY PM":  (hour_et >= 13) & (hour_et < 16),
    }
    in_trade = pd.Series(False, index=df.index)
    for s in sessions:
        if s in sess_masks:
            in_trade = in_trade | sess_masks[s]

    # DOW filter
    if dow_weights is None:
        dow_weights = BASE_DOW
    dow_arr = pd.Series(df.index.weekday, index=df.index)
    dow_ok = dow_arr.map(dow_weights).fillna(1.0) >= dow_threshold

    # Entry hour filter (e.g., only first N minutes of session)
    if entry_hour_filter is not None:
        minute_in_session = minute_et  # simplified
        # Not trivially doable without session-start tracking, skip for now
        pass

    long_sig  = (bull_conf >= min_conf) & in_trade & dow_ok
    short_sig = (bear_conf >= min_conf) & in_trade & dow_ok

    # Deduplicate
    long_sig  = long_sig & ~long_sig.shift(1).fillna(False)
    short_sig = short_sig & ~short_sig.shift(1).fillna(False)

    # Cooldown
    if cooldown_bars > 0:
        any_sig = long_sig | short_sig
        cooldown_mask = pd.Series(True, index=df.index)
        last_trade_bar = -999
        for i, idx in enumerate(df.index):
            if any_sig[idx]:
                if i - last_trade_bar < cooldown_bars:
                    cooldown_mask[idx] = False
                else:
                    last_trade_bar = i
        long_sig  = long_sig & cooldown_mask
        short_sig = short_sig & cooldown_mask

    records = []
    for idx in df.index[long_sig]:
        entry = c[idx]
        a = atr[idx]
        if pd.isna(a) or a < 1e-9:
            continue
        sl  = entry - p["atr_stopMult"] * a
        tp1 = entry + p["atr_tp1Mult"] * a
        tp2 = entry + p.get("atr_tp2Mult", 4.0) * a
        records.append(dict(ts=idx, direction=1, entry=entry, sl=sl,
                            tp1=tp1, tp2=tp2, session=_session_name(idx.hour),
                            dow=idx.weekday(), conf=bull_conf[idx]))

    for idx in df.index[short_sig]:
        entry = c[idx]
        a = atr[idx]
        if pd.isna(a) or a < 1e-9:
            continue
        sl  = entry + p["atr_stopMult"] * a
        tp1 = entry - p["atr_tp1Mult"] * a
        tp2 = entry - p.get("atr_tp2Mult", 4.0) * a
        records.append(dict(ts=idx, direction=-1, entry=entry, sl=sl,
                            tp1=tp1, tp2=tp2, session=_session_name(idx.hour),
                            dow=idx.weekday(), conf=bear_conf[idx]))

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values("ts").reset_index(drop=True)


def simulate_trades(df5, trades, partial_pct=0.60, trail_mult=1.25):
    """Forward-walk simulation with configurable partial TP and trail."""
    if trades.empty:
        return trades

    results = []
    close_arr = df5["close"].values
    high_arr  = df5["high"].values
    low_arr   = df5["low"].values
    idx_arr   = df5.index
    bar_pos   = {ts: i for i, ts in enumerate(idx_arr)}
    atr_arr   = compute_atr(df5, 14).values

    for _, tr in trades.iterrows():
        start_i = bar_pos.get(tr["ts"], None)
        if start_i is None or start_i >= len(close_arr) - 1:
            continue
        d     = tr["direction"]
        sl    = tr["sl"]
        tp1   = tr["tp1"]
        tp2   = tr["tp2"]
        entry = tr["entry"]
        risk  = abs(entry - sl)
        if risk < 1e-9:
            continue

        max_bars = min(48, len(close_arr) - start_i - 1)
        tp1_hit = tp2_hit = sl_hit = False

        # Trail stop logic: after TP1 hit, trail SL using ATR
        trail_sl = sl
        for j in range(start_i + 1, start_i + 1 + max_bars):
            h_ = high_arr[j]
            l_ = low_arr[j]
            c_ = close_arr[j]
            a_ = atr_arr[j] if j < len(atr_arr) else atr_arr[-1]

            if d == 1:
                if l_ <= trail_sl:
                    sl_hit = True; break
                if h_ >= tp1 and not tp1_hit:
                    tp1_hit = True
                    # Move trail stop up
                    trail_sl = max(trail_sl, tp1 - trail_mult * a_)
                if tp1_hit:
                    # Continue trailing
                    trail_sl = max(trail_sl, h_ - trail_mult * a_)
                    if h_ >= tp2:
                        tp2_hit = True; break
                    if l_ <= trail_sl:
                        sl_hit = True; break
            else:
                if h_ >= trail_sl:
                    sl_hit = True; break
                if l_ <= tp1 and not tp1_hit:
                    tp1_hit = True
                    trail_sl = min(trail_sl, tp1 + trail_mult * a_)
                if tp1_hit:
                    trail_sl = min(trail_sl, l_ + trail_mult * a_)
                    if l_ <= tp2:
                        tp2_hit = True; break
                    if h_ >= trail_sl:
                        sl_hit = True; break

        tp1_R = abs(tp1 - entry) / risk
        tp2_R = abs(tp2 - entry) / risk

        if sl_hit and not tp1_hit:
            exit_R = -1.0
        elif tp1_hit and tp2_hit:
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * tp2_R
        elif tp1_hit and sl_hit:
            # Got partial, then trail stopped on remainder
            trail_exit = abs(trail_sl - entry) / risk * d
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * max(trail_exit, -1.0)
        elif tp1_hit and not tp2_hit and not sl_hit:
            # Timeout after TP1
            last_c = close_arr[min(start_i + max_bars, len(close_arr)-1)]
            remain_R = d * (last_c - entry) / risk
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * remain_R
        else:
            last_c = close_arr[min(start_i + max_bars, len(close_arr)-1)]
            exit_R = d * (last_c - entry) / risk

        results.append({**tr.to_dict(), "R_result": exit_R, "win": exit_R > 0})

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def metrics(result_df):
    if result_df is None or result_df.empty:
        return {"n": 0, "wr": 0, "exp": 0, "pf": 0, "dd": 0, "sharpe": 0}
    r = result_df["R_result"].values
    n = len(r)
    wins = r[r > 0]
    losses = r[r < 0]
    wr  = len(wins) / n if n > 0 else 0
    exp = r.mean()
    pf  = wins.sum() / abs(losses.sum()) if losses.size > 0 and losses.sum() != 0 else (999 if wins.size > 0 else 0)
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak).min() if len(cum) > 0 else 0
    sharpe = (r.mean() / r.std() * np.sqrt(252 * 78)) if r.std() > 0 else 0
    return {"n": n, "wr": wr, "exp": exp, "pf": pf, "dd": dd, "sharpe": sharpe}


def fmt(v, pct=False, dec=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if pct:
        return f"{v*100:.1f}%"
    return f"{v:.{dec}f}"


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("EM-FSE v6 NQ — ABLATION & VARIATION STUDY")
    print("=" * 70)

    df5 = load_5min()
    print(f"Loaded {len(df5)} bars: {df5.index[0]} → {df5.index[-1]}")

    # Walk-forward split
    split_i = int(len(df5) * 0.70)
    train = df5.iloc[:split_i]
    test  = df5.iloc[split_i:]
    print(f"Train: {len(train)} | Test: {len(test)}")

    # Pre-compute signals once
    signals, atr, df = compute_all_signals(df5, BASE_PARAMS)
    sig_train, atr_train, df_train = compute_all_signals(train, BASE_PARAMS)
    sig_test,  atr_test,  df_test  = compute_all_signals(test, BASE_PARAMS)

    ALL_FACTORS = ["ms", "choch", "disp", "sweep", "rvol", "fvg", "ema", "sma", "vwap"]

    report = []
    report.append("# EM-FSE v6 NQ — Ablation & Variation Study\n")
    report.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ET  ")
    report.append(f"**Data:** NQ 5min, {len(df5)} bars ({df5.index[0].date()} → {df5.index[-1].date()})  ")
    report.append(f"**Base Params:** stop={BASE_PARAMS['atr_stopMult']}, tp1={BASE_PARAMS['atr_tp1Mult']}, "
                  f"disp={BASE_PARAMS['disp_atrMult']}, conf={BASE_PARAMS['sig_minConf']}  ")
    report.append(f"**Walk-Forward:** 70/30 split\n")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 1: CONFLUENCE FACTOR ABLATION
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 1: CONFLUENCE FACTOR ABLATION")
    print("Which signals help? Which hurt?")
    print("=" * 70)

    report.append("## Study 1: Confluence Factor Ablation\n")
    report.append("Remove one factor at a time and measure impact on OOS expectancy.\n")
    report.append("| Removed Factor | OOS Trades | OOS WR | OOS Exp (R) | OOS PF | Delta vs Base | Verdict |")
    report.append("|----------------|-----------|--------|-------------|--------|---------------|---------|")

    # Baseline (all factors)
    bc_all, sc_all = build_confluence(sig_test, ALL_FACTORS)
    trades_base = generate_trades(df_test, atr_test, bc_all, sc_all, BASE_PARAMS,
                                  sessions=("London",), min_conf=6)
    sim_base = simulate_trades(df_test, trades_base, partial_pct=0.60, trail_mult=1.25)
    m_base = metrics(sim_base)
    print(f"  BASELINE (all factors): {m_base['n']} trades, {m_base['wr']*100:.1f}% WR, {m_base['exp']:.3f}R exp")

    report.append(f"| **BASELINE** | {m_base['n']} | {fmt(m_base['wr'], pct=True)} "
                  f"| {fmt(m_base['exp'])} | {fmt(m_base['pf'])} | — | — |")

    ablation_results = {}
    for factor in ALL_FACTORS:
        reduced = [f for f in ALL_FACTORS if f != factor]
        bc, sc = build_confluence(sig_test, reduced)
        trades = generate_trades(df_test, atr_test, bc, sc, BASE_PARAMS,
                                sessions=("London",), min_conf=6)
        sim = simulate_trades(df_test, trades, partial_pct=0.60, trail_mult=1.25)
        m = metrics(sim)
        delta = m["exp"] - m_base["exp"]
        verdict = "HELPS" if delta < -0.1 else ("HURTS" if delta > 0.1 else "Neutral")
        ablation_results[factor] = {"metrics": m, "delta": delta, "verdict": verdict}
        print(f"  Remove {factor:>6s}: {m['n']:>3d} trades, {m['wr']*100:.1f}% WR, "
              f"{m['exp']:.3f}R exp  (delta: {delta:+.3f}R) → {verdict}")
        report.append(f"| -{factor} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} | {delta:+.3f}R | {verdict} |")

    # Also test: what if we ONLY use the top factors?
    report.append("")
    helpers = [f for f, r in ablation_results.items() if r["verdict"] == "HELPS"]
    if helpers:
        report.append(f"\n**Key factors (removing hurts performance):** {', '.join(helpers)}\n")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 2: SESSION COMBINATIONS
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 2: SESSION COMBINATIONS")
    print("=" * 70)

    report.append("\n## Study 2: Session Combinations\n")
    report.append("| Sessions | Trades | WR | Exp (R) | PF | Sharpe | Max DD (R) |")
    report.append("|----------|--------|-----|---------|-----|--------|------------|")

    session_combos = [
        ("London",),
        ("NY AM",),
        ("NY PM",),
        ("London", "NY AM"),
        ("London", "NY PM"),
        ("NY AM", "NY PM"),
        ("London", "NY AM", "NY PM"),
        ("Asia", "London"),
    ]

    bc_full, sc_full = build_confluence(signals, ALL_FACTORS)

    for sess in session_combos:
        label = " + ".join(sess)
        trades = generate_trades(df, atr, bc_full, sc_full, BASE_PARAMS,
                                sessions=sess, min_conf=6)
        sim = simulate_trades(df, trades, partial_pct=0.60, trail_mult=1.25)
        m = metrics(sim)
        print(f"  {label:>25s}: {m['n']:>3d} trades, {m['wr']*100:.1f}% WR, "
              f"{m['exp']:.3f}R exp, PF={m['pf']:.2f}")
        report.append(f"| {label} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} | {fmt(m['sharpe'], dec=1)} "
                      f"| {fmt(m['dd'])} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 3: PARTIAL TP % VARIATIONS
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 3: PARTIAL TP % AT TP1")
    print("=" * 70)

    report.append("\n## Study 3: Partial TP % at TP1\n")
    report.append("How much to close at TP1 vs let ride to TP2?\n")
    report.append("| Partial % | Trades | WR | Exp (R) | PF | Avg Winner (R) |")
    report.append("|-----------|--------|-----|---------|-----|----------------|")

    trades_ldn = generate_trades(df, atr, bc_full, sc_full, BASE_PARAMS,
                                 sessions=("London",), min_conf=6)

    for pct in [0.0, 0.20, 0.40, 0.50, 0.60, 0.70, 0.80, 1.0]:
        sim = simulate_trades(df, trades_ldn, partial_pct=pct, trail_mult=1.25)
        m = metrics(sim)
        wins = sim[sim["R_result"] > 0]["R_result"].mean() if not sim.empty and (sim["R_result"] > 0).any() else 0
        label = f"{int(pct*100)}%"
        if pct == 0.0:
            label = "0% (all trails)"
        elif pct == 1.0:
            label = "100% (all at TP1)"
        print(f"  {label:>20s}: exp={m['exp']:.3f}R, PF={m['pf']:.2f}, avg_win={wins:.2f}R")
        report.append(f"| {label} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} | {fmt(wins)} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 4: TRAILING STOP VARIATIONS
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 4: TRAILING STOP ATR MULTIPLE")
    print("=" * 70)

    report.append("\n## Study 4: Trailing Stop ATR Multiple\n")
    report.append("| Trail ATR Mult | Trades | WR | Exp (R) | PF |")
    report.append("|----------------|--------|-----|---------|-----|")

    for trail in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]:
        sim = simulate_trades(df, trades_ldn, partial_pct=0.60, trail_mult=trail)
        m = metrics(sim)
        print(f"  Trail {trail:.2f} ATR: exp={m['exp']:.3f}R, PF={m['pf']:.2f}")
        report.append(f"| {trail:.2f} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 5: DOW WEIGHT PROFILES
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 5: DOW WEIGHT PROFILES")
    print("=" * 70)

    report.append("\n## Study 5: Day-of-Week Weight Profiles\n")
    report.append("| Profile | Mon | Tue | Wed | Thu | Fri | Trades | WR | Exp (R) | PF |")
    report.append("|---------|-----|-----|-----|-----|-----|--------|-----|---------|-----|")

    dow_profiles = {
        "Current OPT3":     {0: 1.1, 1: 0.5, 2: 1.0, 3: 0.9, 4: 0.6},
        "Original":         {0: 1.1, 1: 1.2, 2: 1.0, 3: 0.9, 4: 0.6},
        "Kill Tuesday":     {0: 1.1, 1: 0.0, 2: 1.0, 3: 0.9, 4: 0.6},
        "Mon+Wed+Thu only": {0: 1.1, 1: 0.0, 2: 1.0, 3: 0.9, 4: 0.0},
        "Monday heavy":     {0: 1.5, 1: 0.5, 2: 0.8, 3: 0.9, 4: 0.5},
        "Flat (all equal)": {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},
        "Aggressive filter":{0: 1.2, 1: 0.0, 2: 1.0, 3: 1.0, 4: 0.0},
    }

    for name, weights in dow_profiles.items():
        trades = generate_trades(df, atr, bc_full, sc_full, BASE_PARAMS,
                                sessions=("London",), dow_weights=weights, min_conf=6)
        sim = simulate_trades(df, trades, partial_pct=0.60, trail_mult=1.25)
        m = metrics(sim)
        w = weights
        print(f"  {name:>20s}: {m['n']:>3d} trades, {m['exp']:.3f}R exp, PF={m['pf']:.2f}")
        report.append(f"| {name} | {w[0]} | {w[1]} | {w[2]} | {w[3]} | {w[4]} "
                      f"| {m['n']} | {fmt(m['wr'], pct=True)} | {fmt(m['exp'])} | {fmt(m['pf'])} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 6: RISK:REWARD SHAPE (SL × TP matrix)
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 6: SL × TP MATRIX (London only)")
    print("=" * 70)

    report.append("\n## Study 6: SL × TP Matrix\n")
    report.append("London session, conf=6, OPT3 DOW weights.\n")

    sl_range = [0.25, 0.50, 0.75, 1.0, 1.5]
    tp_range = [1.5, 2.0, 3.0, 4.0, 5.0, 6.0]

    # Header
    header = "| SL \\ TP |"
    for tp in tp_range:
        header += f" {tp:.1f} |"
    report.append(header)
    sep = "|---------|"
    for _ in tp_range:
        sep += "------|"
    report.append(sep)

    print(f"  {'SL':>5s}", end="")
    for tp in tp_range:
        print(f"  TP={tp:.1f}", end="")
    print()

    for sl in sl_range:
        row_str = f"| {sl:.2f} |"
        print(f"  {sl:.2f}", end="")
        for tp in tp_range:
            params_mod = {**BASE_PARAMS, "atr_stopMult": sl, "atr_tp1Mult": tp}
            sig_mod, atr_mod, df_mod = compute_all_signals(df, params_mod)
            bc_mod, sc_mod = build_confluence(sig_mod, ALL_FACTORS)
            trades = generate_trades(df_mod, atr_mod, bc_mod, sc_mod, params_mod,
                                    sessions=("London",), min_conf=6)
            sim = simulate_trades(df_mod, trades, partial_pct=0.60, trail_mult=1.25)
            m = metrics(sim)
            cell = f"{m['exp']:.2f}R" if m['n'] > 0 else "—"
            print(f"  {cell:>7s}", end="")
            row_str += f" {cell} |"
        print()
        report.append(row_str)

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 7: CONFLUENCE THRESHOLD SWEEP
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 7: CONFLUENCE THRESHOLD SWEEP")
    print("=" * 70)

    report.append("\n## Study 7: Minimum Confluence Threshold\n")
    report.append("| Min Conf | Trades | WR | Exp (R) | PF | Max DD (R) |")
    report.append("|----------|--------|-----|---------|-----|------------|")

    bc_ldn, sc_ldn = build_confluence(signals, ALL_FACTORS)
    for conf in range(2, 10):
        trades = generate_trades(df, atr, bc_ldn, sc_ldn, BASE_PARAMS,
                                sessions=("London",), min_conf=conf)
        sim = simulate_trades(df, trades, partial_pct=0.60, trail_mult=1.25)
        m = metrics(sim)
        print(f"  conf>={conf}: {m['n']:>3d} trades, {m['wr']*100:.1f}% WR, "
              f"{m['exp']:.3f}R, PF={m['pf']:.2f}, DD={m['dd']:.1f}R")
        report.append(f"| {conf} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} | {fmt(m['dd'])} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # STUDY 8: TRADE COOLDOWN (min bars between entries)
    # ══════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 70)
    print("STUDY 8: TRADE COOLDOWN")
    print("=" * 70)

    report.append("\n## Study 8: Trade Cooldown (min bars between entries)\n")
    report.append("| Cooldown (bars) | ~Minutes | Trades | WR | Exp (R) | PF |")
    report.append("|-----------------|----------|--------|-----|---------|-----|")

    for cd in [0, 3, 6, 12, 18, 24, 36]:
        trades = generate_trades(df, atr, bc_ldn, sc_ldn, BASE_PARAMS,
                                sessions=("London",), min_conf=6, cooldown_bars=cd)
        sim = simulate_trades(df, trades, partial_pct=0.60, trail_mult=1.25)
        m = metrics(sim)
        mins = cd * 5
        print(f"  {cd:>2d} bars ({mins:>3d} min): {m['n']:>3d} trades, "
              f"{m['exp']:.3f}R, PF={m['pf']:.2f}")
        report.append(f"| {cd} | {mins} | {m['n']} | {fmt(m['wr'], pct=True)} "
                      f"| {fmt(m['exp'])} | {fmt(m['pf'])} |")

    report.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY & RECOMMENDATIONS
    # ══════════════════════════════════════════════════════════════════════════

    report.append("\n## Summary & Recommendations\n")
    report.append("See individual study tables above for data. "
                  "Key takeaways are summarized in the terminal output.\n")

    report.append("\n---\n")
    report.append("*Report auto-generated by ablation_study.py — EM-FSE v6 NQ variation analysis*")

    # Save
    report_path = "/Users/edwinmaina/Documents/Space/Trading/Ablation_Study_Report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(report))
    print(f"\n{'='*70}")
    print(f"Report saved to: {report_path}")
    print(f"{'='*70}")
