"""
EM-FSE v6 — Multi-Market Backtest & Optimization
==================================================
Tests the ICT/SMC confluence strategy across ALL 10 instruments in the
historical data, using the same signal engine as optimize_nq.py.

For each market it runs:
  1. Walk-forward optimization (70/30 split) across a parameter grid
  2. Session quality analysis (Asia / London / NY AM / NY PM)
  3. Per-market best-parameter report
  4. Cross-market comparison ranking

Outputs: Multi_Market_Report.md
"""

import os, glob, re, warnings, itertools, sys
import numpy as np
import pandas as pd
from datetime import time as dtime

warnings.filterwarnings("ignore")

# ── CONFIG ──────────────────────────────────────────────────────────────────────

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

# Point values for dollar P&L calculation
POINT_VALUE = {
    "NQ": 20.0,    # E-mini NASDAQ-100
    "ES": 50.0,    # E-mini S&P 500
    "GC": 100.0,   # Gold (COMEX)
    "SI": 5000.0,  # Silver (COMEX)
    "HG": 25000.0, # Copper (COMEX)
    "PL": 50.0,    # Platinum (NYMEX)
    "PA": 100.0,   # Palladium (NYMEX)
    "J1": 125000.0,# Japanese Yen (CME) — actually 6J
    "RP": 50.0,    # E-mini Russell 2000
    "ZW": 50.0,    # Wheat (CBOT) — using as proxy for ZW
}

# Tick sizes for context
TICK_SIZE = {
    "NQ": 0.25, "ES": 0.25, "GC": 0.10, "SI": 0.005,
    "HG": 0.0005, "PL": 0.10, "PA": 0.10, "J1": 0.0000005,
    "RP": 0.10, "ZW": 0.25,
}

# Parameter grid — same as your NQ optimizer but we also test looser confluence
# thresholds since some markets may have different signal density
PARAM_GRID = {
    "atr_stopMult":  [0.50, 0.75, 1.0, 1.5],
    "atr_tp1Mult":   [1.5, 2.0, 3.0, 4.0],
    "disp_atrMult":  [1.0, 1.25, 1.5, 2.0],
    "lq_sweepWick":  [0.30, 0.40, 0.50],
    "of_rvolThresh": [1.5, 2.0, 2.5],
    "sig_minConf":   [3, 4, 5, 6],
}

TRAIN_FRAC = 0.70

# ── DATA LOADING ────────────────────────────────────────────────────────────────

def parse_filename(fname):
    base = os.path.basename(fname)
    m = re.match(r"([A-Z0-9]+)_(\w+)_sample\.csv", base)
    if m:
        return m.group(1), m.group(2)
    return None, None

def load_csv(fpath):
    sym, tf = parse_filename(fpath)
    if sym is None:
        return None, None, None
    df = pd.read_csv(fpath, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "ts"})
    df = df.sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("America/New_York", ambiguous="infer",
                                            nonexistent="shift_forward")
    df.set_index("ts", inplace=True)
    return df, sym, tf

def load_all_data():
    """Load all 5min CSVs across all data directories."""
    seen = {}
    files = []
    for d in DATA_DIRS:
        if os.path.exists(d):
            files.extend(glob.glob(os.path.join(d, "*.csv")))

    data = {}
    inventory = []
    for f in sorted(files):
        sym, tf = parse_filename(f)
        if sym is None:
            continue
        key = (sym, tf)
        if key not in seen:
            seen[key] = f
            df, _, _ = load_csv(f)
            if df is not None and len(df) > 50:
                data[key] = df
                inventory.append({"symbol": sym, "timeframe": tf,
                                  "bars": len(df),
                                  "start": str(df.index[0].date()),
                                  "end": str(df.index[-1].date())})

    return data, pd.DataFrame(inventory)

# ── SIGNAL ENGINE (same as optimize_nq.py) ──────────────────────────────────────

def compute_atr(df, length=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
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

def compute_signals(df5, params):
    """
    Vectorised recreation of the Pine Script confluence signal logic.
    Returns a DataFrame of trade entries.
    """
    p = params
    df = df5.copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    atr = compute_atr(df, 14)

    # ── Market Structure (BOS/CHoCH) ──
    ms_len = 5
    swing_h = h.rolling(ms_len * 2 + 1, center=True).max() == h
    swing_l = l.rolling(ms_len * 2 + 1, center=True).min() == l
    prev_swing_h = h[swing_h].reindex(df.index).ffill()
    prev_swing_l = l[swing_l].reindex(df.index).ffill()
    bos_up   = (c > prev_swing_h.shift(ms_len))
    bos_dn   = (c < prev_swing_l.shift(ms_len))
    choch_up = bos_up & (c.shift(1) <= prev_swing_h.shift(ms_len).shift(1))
    choch_dn = bos_dn & (c.shift(1) >= prev_swing_l.shift(ms_len).shift(1))
    ms_bull  = bos_up | choch_up
    ms_bear  = bos_dn | choch_dn

    # ── Displacement ──
    body = (c - o).abs()
    disp_bull = (c > o) & (body > p["disp_atrMult"] * atr)
    disp_bear = (c < o) & (body > p["disp_atrMult"] * atr)

    # ── Liquidity sweep ──
    swing_hi_10 = h.rolling(21, center=True).max() == h
    swing_lo_10 = l.rolling(21, center=True).min() == l
    prev_hi_10  = h[swing_hi_10].reindex(df.index).ffill()
    prev_lo_10  = l[swing_lo_10].reindex(df.index).ffill()
    wt = pd.Series(wick_ratio_top(o.values, h.values, l.values, c.values), index=df.index)
    wb = pd.Series(wick_ratio_bot(o.values, h.values, l.values, c.values), index=df.index)
    sweep_hi = (h > prev_hi_10.shift(1)) & (wt > p["lq_sweepWick"])
    sweep_lo = (l < prev_lo_10.shift(1)) & (wb > p["lq_sweepWick"])

    # ── RVOL ──
    avg_vol = v.rolling(20).mean()
    rvol_hi = (v / avg_vol.replace(0, np.nan)) > p["of_rvolThresh"]

    # ── FVG (3-bar) ──
    fvg_bull = l > h.shift(2)
    fvg_bear = h < l.shift(2)

    # ── EMA / SMA trend ──
    ema9  = c.ewm(span=9,  adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    sma200 = c.rolling(200).mean()
    ema_bull = ema9 > ema21
    ema_bear = ema9 < ema21
    sma_bull = c > sma200
    sma_bear = c < sma200

    # ── VWAP ──
    tp_ = (h + l + c) / 3
    vwap = (tp_ * v).rolling(78).sum() / v.rolling(78).sum().replace(0, np.nan)
    vwap_bull = c > vwap
    vwap_bear = c < vwap

    # ── Session filter ──
    hour_et = df.index.hour
    in_ldn  = (hour_et >= 2) & (hour_et < 5)
    in_nyam = (hour_et >= 9) & (hour_et < 12)
    in_nypm = (hour_et >= 13) & (hour_et < 16)
    in_asia = (hour_et >= 20) | (hour_et < 2)
    in_trade = in_ldn | in_nyam | in_nypm

    # ── DOW weight ──
    dow_weights = {0: 1.1, 1: 1.2, 2: 1.0, 3: 0.9, 4: 0.6}
    dow_arr = pd.Series(df.index.weekday, index=df.index)
    dow_ok  = dow_arr.map(dow_weights) >= 0.8

    # ── Confluence scoring ──
    cl = (ms_bull.astype(int)
          + choch_up.astype(int)
          + disp_bull.astype(int)
          + sweep_lo.astype(int)
          + vwap_bull.astype(int)
          + ema_bull.astype(int)
          + sma_bull.astype(int)
          + rvol_hi.astype(int)
          + fvg_bull.astype(int))

    cs = (ms_bear.astype(int)
          + choch_dn.astype(int)
          + disp_bear.astype(int)
          + sweep_hi.astype(int)
          + vwap_bear.astype(int)
          + ema_bear.astype(int)
          + sma_bear.astype(int)
          + rvol_hi.astype(int)
          + fvg_bear.astype(int))

    long_sig  = (cl >= p["sig_minConf"]) & in_trade & dow_ok
    short_sig = (cs >= p["sig_minConf"]) & in_trade & dow_ok

    # Deduplicate consecutive same-direction signals
    long_sig  = long_sig  & ~long_sig.shift(1).fillna(False)
    short_sig = short_sig & ~short_sig.shift(1).fillna(False)

    # ── Build trade list ──
    records = []
    for idx in df.index[long_sig]:
        entry = c[idx]
        a = atr[idx]
        if pd.isna(a) or a < 1e-9:
            continue
        sl  = entry - p["atr_stopMult"] * a
        tp1 = entry + p["atr_tp1Mult"] * a
        tp2 = entry + 4.0 * a
        session = _session_name(idx.hour)
        records.append(dict(ts=idx, direction=1, entry=entry, sl=sl,
                            tp1=tp1, tp2=tp2, session=session,
                            dow=idx.weekday(), conf=cl[idx]))

    for idx in df.index[short_sig]:
        entry = c[idx]
        a = atr[idx]
        if pd.isna(a) or a < 1e-9:
            continue
        sl  = entry + p["atr_stopMult"] * a
        tp1 = entry - p["atr_tp1Mult"] * a
        tp2 = entry - 4.0 * a
        session = _session_name(idx.hour)
        records.append(dict(ts=idx, direction=-1, entry=entry, sl=sl,
                            tp1=tp1, tp2=tp2, session=session,
                            dow=idx.weekday(), conf=cs[idx]))

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values("ts").reset_index(drop=True)


def simulate_trades(df5, trades, partial_pct=0.60):
    """Forward-walk simulation with partial TP logic."""
    if trades.empty:
        return trades

    results = []
    close_arr = df5["close"].values
    high_arr  = df5["high"].values
    low_arr   = df5["low"].values
    idx_arr   = df5.index
    bar_pos   = {ts: i for i, ts in enumerate(idx_arr)}

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

        # Scan forward (max 48 bars = 4hrs on 5min)
        max_bars = min(48, len(close_arr) - start_i - 1)
        tp1_hit = tp2_hit = sl_hit = False

        for j in range(start_i + 1, start_i + 1 + max_bars):
            h_ = high_arr[j]
            l_ = low_arr[j]
            c_ = close_arr[j]
            if d == 1:
                if l_ <= sl:
                    sl_hit = True; break
                if h_ >= tp1 and not tp1_hit:
                    tp1_hit = True
                if tp1_hit and h_ >= tp2:
                    tp2_hit = True; break
                if tp1_hit and l_ <= sl:
                    sl_hit = True; break
            else:
                if h_ >= sl:
                    sl_hit = True; break
                if l_ <= tp1 and not tp1_hit:
                    tp1_hit = True
                if tp1_hit and l_ <= tp2:
                    tp2_hit = True; break
                if tp1_hit and h_ >= sl:
                    sl_hit = True; break

        tp1_R = abs(tp1 - entry) / risk
        tp2_R = abs(tp2 - entry) / risk

        if sl_hit and not tp1_hit:
            exit_R = -1.0
        elif tp1_hit and tp2_hit:
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * tp2_R
        elif tp1_hit and sl_hit:
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * (-1.0)
        elif tp1_hit and not tp2_hit and not sl_hit:
            exit_R = partial_pct * tp1_R  # remainder ~BE on timeout
        else:
            last_c = close_arr[min(start_i + max_bars, len(close_arr)-1)]
            exit_R = d * (last_c - entry) / risk

        results.append({**tr.to_dict(), "R_result": exit_R, "win": exit_R > 0})

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def compute_metrics(result_df):
    if result_df is None or result_df.empty:
        return dict(n=0, win_rate=np.nan, expectancy=np.nan, profit_factor=np.nan,
                    max_dd=np.nan, sharpe=np.nan, avg_winner=np.nan, avg_loser=np.nan)
    r = result_df["R_result"].values
    n = len(r)
    if n == 0:
        return dict(n=0, win_rate=np.nan, expectancy=np.nan, profit_factor=np.nan,
                    max_dd=np.nan, sharpe=np.nan, avg_winner=np.nan, avg_loser=np.nan)
    wins   = r[r > 0]
    losses = r[r < 0]
    wr  = len(wins) / n
    exp = r.mean()
    pf  = wins.sum() / abs(losses.sum()) if losses.size > 0 else np.inf
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(cum)
    max_dd = (cum - peak).min()
    sharpe = (r.mean() / r.std() * np.sqrt(252 * 78)) if r.std() > 0 else 0.0
    avg_w = wins.mean() if len(wins) > 0 else 0.0
    avg_l = losses.mean() if len(losses) > 0 else 0.0
    return dict(n=n, win_rate=wr, expectancy=exp, profit_factor=pf,
                max_dd=max_dd, sharpe=sharpe, avg_winner=avg_w, avg_loser=avg_l)


# ── MAIN ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("EM-FSE v6 — MULTI-MARKET BACKTEST & OPTIMIZATION")
    print("=" * 70)

    data, inv_df = load_all_data()

    # Show inventory
    print("\n📊 DATA INVENTORY:")
    for _, row in inv_df[inv_df["timeframe"] == "5min"].iterrows():
        print(f"  {row['symbol']:>3s}  5min  {row['bars']:>5d} bars  ({row['start']} → {row['end']})")

    # Symbols to test (5min only)
    symbols = sorted(set(sym for (sym, tf) in data.keys() if tf == "5min"))
    print(f"\n🔬 Testing {len(symbols)} instruments: {', '.join(symbols)}")

    # Build grid
    keys   = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combos = list(itertools.product(*values))
    total_combos = len(combos)
    print(f"📐 Parameter grid: {total_combos} combinations per market")

    # ── Per-market walk-forward optimization ─────────────────────────────────

    market_results = {}  # sym -> {best_params, best_metrics_is, best_metrics_oos, all_trades, session_stats}

    for sym in symbols:
        df5 = data.get((sym, "5min"))
        if df5 is None or len(df5) < 200:
            print(f"\n⚠️  {sym}: insufficient 5min data ({len(df5) if df5 is not None else 0} bars), skipping")
            continue

        print(f"\n{'='*70}")
        print(f"  {sym} — {len(df5)} bars ({df5.index[0].date()} → {df5.index[-1].date()})")
        print(f"{'='*70}")

        split_i  = int(len(df5) * TRAIN_FRAC)
        train_df = df5.iloc[:split_i]
        test_df  = df5.iloc[split_i:]

        print(f"  Train: {len(train_df)} bars | Test: {len(test_df)} bars")

        best_oos_exp  = -999
        best_row      = None
        valid_combos  = 0
        wf_rows       = []

        for i, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            try:
                tr_trades = compute_signals(train_df, params)
                if tr_trades.empty:
                    continue
                tr_sim = simulate_trades(train_df, tr_trades)
                tr_m   = compute_metrics(tr_sim)
                if tr_m["n"] < 3:
                    continue

                te_trades = compute_signals(test_df, params)
                if te_trades.empty:
                    continue
                te_sim = simulate_trades(test_df, te_trades)
                te_m   = compute_metrics(te_sim)

                overfit = (
                    (tr_m["expectancy"] > 0 and
                     te_m["expectancy"] < tr_m["expectancy"] * 0.80) or
                    (tr_m["win_rate"] > 0 and
                     te_m["win_rate"]  < tr_m["win_rate"]  * 0.80)
                )

                row = {**params, "is_n": tr_m["n"], "oos_n": te_m["n"],
                       "is_wr": tr_m["win_rate"], "oos_wr": te_m["win_rate"],
                       "is_exp": tr_m["expectancy"], "oos_exp": te_m["expectancy"],
                       "oos_pf": te_m["profit_factor"], "oos_dd": te_m["max_dd"],
                       "oos_sharpe": te_m["sharpe"], "overfit": overfit}
                wf_rows.append(row)
                valid_combos += 1

                if te_m["expectancy"] > best_oos_exp:
                    best_oos_exp = te_m["expectancy"]
                    best_row = row
            except Exception:
                pass

            if (i + 1) % 200 == 0:
                print(f"    {i+1}/{total_combos}...", end="\r", flush=True)

        print(f"  ✅ {valid_combos} valid combos out of {total_combos}")

        if best_row is None:
            print(f"  ❌ No valid parameter set found for {sym}")
            market_results[sym] = None
            continue

        best_params = {k: best_row[k] for k in keys}
        print(f"  🏆 Best OOS Expectancy: {best_oos_exp:.3f}R")
        print(f"     Params: stop={best_params['atr_stopMult']}, tp1={best_params['atr_tp1Mult']}, "
              f"disp={best_params['disp_atrMult']}, sweep={best_params['lq_sweepWick']}, "
              f"rvol={best_params['of_rvolThresh']}, conf={int(best_params['sig_minConf'])}")

        # Full-dataset analysis with best params
        all_trades = simulate_trades(df5, compute_signals(df5, best_params))

        # Session breakdown
        sess_stats = {}
        for sess in ["Asia", "London", "NY AM", "NY PM", "Other"]:
            s = all_trades[all_trades["session"] == sess] if not all_trades.empty else pd.DataFrame()
            sess_stats[sess] = compute_metrics(s)

        # DOW breakdown
        dow_stats = {}
        DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
        if not all_trades.empty:
            for d in range(5):
                s = all_trades[all_trades["dow"] == d]
                dow_stats[DOW_NAMES[d]] = compute_metrics(s)

        # ATR stats for context
        atr_vals = compute_atr(df5, 14)
        avg_atr = atr_vals.mean()
        median_atr = atr_vals.median()

        full_metrics = compute_metrics(all_trades)

        # Top 5 parameter sets
        wf_df = pd.DataFrame(wf_rows).sort_values("oos_exp", ascending=False)
        top5 = wf_df.head(5)

        market_results[sym] = {
            "best_params": best_params,
            "best_row": best_row,
            "full_metrics": full_metrics,
            "sess_stats": sess_stats,
            "dow_stats": dow_stats,
            "avg_atr": avg_atr,
            "median_atr": median_atr,
            "top5": top5,
            "n_bars": len(df5),
            "all_trades": all_trades,
        }

    # ── CROSS-MARKET COMPARISON ──────────────────────────────────────────────

    print("\n\n" + "=" * 70)
    print("CROSS-MARKET RANKING")
    print("=" * 70)

    ranking = []
    for sym, res in market_results.items():
        if res is None:
            continue
        m = res["full_metrics"]
        bp = res["best_params"]
        # Composite score: weighted combination of expectancy, PF, and Sharpe
        # Penalize low trade count (< 10 trades = unreliable)
        trade_penalty = min(m["n"] / 10, 1.0) if m["n"] > 0 else 0
        composite = (
            0.40 * (m["expectancy"] if not np.isnan(m["expectancy"]) else 0) +
            0.25 * min((m["profit_factor"] if not np.isnan(m["profit_factor"]) else 0) / 3, 1) +
            0.20 * min((m["sharpe"] if not np.isnan(m["sharpe"]) else 0) / 50, 1) +
            0.15 * (m["win_rate"] if not np.isnan(m["win_rate"]) else 0)
        ) * trade_penalty

        pv = POINT_VALUE.get(sym, 1)
        dollar_exp = m["expectancy"] * bp["atr_stopMult"] * res["avg_atr"] * pv if not np.isnan(m["expectancy"]) else 0

        # Best session
        best_sess = max(res["sess_stats"].items(),
                       key=lambda x: x[1]["expectancy"] if not np.isnan(x[1].get("expectancy", np.nan)) and x[1]["n"] > 0 else -999)

        ranking.append({
            "symbol": sym,
            "trades": m["n"],
            "win_rate": m["win_rate"],
            "expectancy_R": m["expectancy"],
            "profit_factor": m["profit_factor"],
            "max_dd_R": m["max_dd"],
            "sharpe": m["sharpe"],
            "composite": composite,
            "dollar_exp_per_trade": dollar_exp,
            "best_session": best_sess[0],
            "best_sess_exp": best_sess[1]["expectancy"],
            "best_sess_wr": best_sess[1]["win_rate"],
            "avg_atr": res["avg_atr"],
            "stop_mult": bp["atr_stopMult"],
            "tp1_mult": bp["atr_tp1Mult"],
            "disp_mult": bp["disp_atrMult"],
            "sweep_wick": bp["lq_sweepWick"],
            "rvol_thresh": bp["of_rvolThresh"],
            "min_conf": int(bp["sig_minConf"]),
        })

    rank_df = pd.DataFrame(ranking).sort_values("composite", ascending=False).reset_index(drop=True)
    rank_df.index += 1  # 1-indexed rank

    print("\n" + rank_df[["symbol", "trades", "win_rate", "expectancy_R",
                          "profit_factor", "sharpe", "composite",
                          "best_session"]].to_string())

    # ── GENERATE REPORT ──────────────────────────────────────────────────────

    print("\n\n📝 Generating Multi_Market_Report.md ...")

    def fmt(v, pct=False, dec=3):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        if pct:
            return f"{v*100:.1f}%"
        if isinstance(v, float):
            return f"{v:.{dec}f}"
        return str(v)

    lines = []
    lines.append("# EM-FSE v6 — Multi-Market Backtest Report\n")
    lines.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ET  ")
    lines.append(f"**Instruments tested:** {len(symbols)}  ")
    lines.append(f"**Parameter combos per market:** {total_combos}  ")
    lines.append(f"**Walk-forward split:** {int(TRAIN_FRAC*100)}/{int((1-TRAIN_FRAC)*100)}  \n")

    # ── Grand Ranking Table ──
    lines.append("## Overall Market Ranking (by Composite Score)\n")
    lines.append("| Rank | Market | Trades | Win Rate | Exp (R) | PF | Sharpe | Max DD (R) | Composite | Best Session | $/Trade |")
    lines.append("|------|--------|--------|----------|---------|-----|--------|------------|-----------|--------------|---------|")
    for rank, (_, row) in enumerate(rank_df.iterrows(), 1):
        lines.append(
            f"| {rank} "
            f"| **{row['symbol']}** "
            f"| {row['trades']} "
            f"| {fmt(row['win_rate'], pct=True)} "
            f"| {fmt(row['expectancy_R'])} "
            f"| {fmt(row['profit_factor'])} "
            f"| {fmt(row['sharpe'], dec=1)} "
            f"| {fmt(row['max_dd_R'])} "
            f"| {fmt(row['composite'])} "
            f"| {row['best_session']} "
            f"| ${fmt(row['dollar_exp_per_trade'], dec=0)} |"
        )
    lines.append("")

    # ── Per-Market Detail ──
    lines.append("---\n")
    lines.append("## Per-Market Detail\n")

    for _, row in rank_df.iterrows():
        sym = row["symbol"]
        res = market_results[sym]
        if res is None:
            continue

        lines.append(f"### {sym} {'⭐' if row['composite'] > 0.3 else ''}\n")

        # Best params
        bp = res["best_params"]
        lines.append(f"**Best Parameters:** stop={bp['atr_stopMult']}, tp1={bp['atr_tp1Mult']}, "
                     f"disp={bp['disp_atrMult']}, sweep={bp['lq_sweepWick']}, "
                     f"rvol={bp['of_rvolThresh']}, minConf={int(bp['sig_minConf'])}  ")
        lines.append(f"**Avg ATR (5min):** {res['avg_atr']:.2f} pts | "
                     f"**Median ATR:** {res['median_atr']:.2f} pts  \n")

        # Session table
        lines.append("| Session | Trades | Win Rate | Avg R |")
        lines.append("|---------|--------|----------|-------|")
        for sess in ["Asia", "London", "NY AM", "NY PM"]:
            sm = res["sess_stats"].get(sess, {})
            lines.append(f"| {sess} | {sm.get('n', 0)} "
                        f"| {fmt(sm.get('win_rate'), pct=True)} "
                        f"| {fmt(sm.get('expectancy'))} |")
        lines.append("")

        # DOW table
        if res["dow_stats"]:
            lines.append("| Day | Trades | Win Rate | Avg R |")
            lines.append("|-----|--------|----------|-------|")
            for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
                dm = res["dow_stats"].get(day, {})
                if isinstance(dm, dict) and dm.get("n", 0) > 0:
                    lines.append(f"| {day} | {dm['n']} "
                                f"| {fmt(dm['win_rate'], pct=True)} "
                                f"| {fmt(dm['expectancy'])} |")
            lines.append("")

        # Top 5 param sets
        if res["top5"] is not None and len(res["top5"]) > 0:
            lines.append("**Top 5 OOS Parameter Sets:**\n")
            lines.append("| stop | tp1 | disp | sweep | rvol | conf | OOS Exp | OOS WR | OOS PF | Overfit |")
            lines.append("|------|-----|------|-------|------|------|---------|--------|--------|---------|")
            for _, r in res["top5"].iterrows():
                of = "Yes" if r.get("overfit", False) else "No"
                lines.append(
                    f"| {r['atr_stopMult']:.2f} "
                    f"| {r['atr_tp1Mult']:.1f} "
                    f"| {r['disp_atrMult']:.2f} "
                    f"| {r['lq_sweepWick']:.2f} "
                    f"| {r['of_rvolThresh']:.1f} "
                    f"| {int(r['sig_minConf'])} "
                    f"| {fmt(r['oos_exp'])} "
                    f"| {fmt(r['oos_wr'], pct=True)} "
                    f"| {fmt(r['oos_pf'])} "
                    f"| {of} |"
                )
            lines.append("")

        lines.append("---\n")

    # ── Recommendations ──
    lines.append("## Strategy Fit Recommendations\n")
    if len(rank_df) > 0:
        top = rank_df.iloc[0]
        lines.append(f"### Best Overall Market: **{top['symbol']}**\n")
        lines.append(f"- Composite Score: {fmt(top['composite'])}")
        lines.append(f"- Expectancy: {fmt(top['expectancy_R'])}R per trade")
        lines.append(f"- Best Session: {top['best_session']} "
                     f"({fmt(top['best_sess_exp'])}R, {fmt(top['best_sess_wr'], pct=True)} WR)")
        lines.append(f"- Estimated $/trade: ${fmt(top['dollar_exp_per_trade'], dec=0)}\n")

        if len(rank_df) >= 2:
            second = rank_df.iloc[1]
            lines.append(f"### Runner-Up: **{second['symbol']}**\n")
            lines.append(f"- Composite Score: {fmt(second['composite'])}")
            lines.append(f"- Expectancy: {fmt(second['expectancy_R'])}R per trade\n")

        # Markets to avoid
        avoid = rank_df[rank_df["expectancy_R"] <= 0]
        if len(avoid) > 0:
            lines.append(f"### Markets to AVOID (negative expectancy):\n")
            for _, r in avoid.iterrows():
                lines.append(f"- **{r['symbol']}**: {fmt(r['expectancy_R'])}R, {fmt(r['win_rate'], pct=True)} WR")
            lines.append("")

    lines.append("\n---\n")
    lines.append("*Report auto-generated by backtest_all_markets.py — EM-FSE v6 multi-market analysis*")

    report_md = "\n".join(lines)
    report_path = "/Users/edwinmaina/Documents/Space/Trading/Multi_Market_Report.md"
    with open(report_path, "w") as f:
        f.write(report_md)

    print(f"\n✅ Report saved to: {report_path}")
    print("\nDone!")
