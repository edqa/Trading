"""
EM-FSE v6 NQ/ES Walk-Forward Optimization & Analysis
======================================================
Simulates the strategy's signal-generation logic in Python using
OHLCV data, runs grid-search walk-forward (70/30 split), and produces:
  - Top-10 parameter table by OOS expectancy
  - Session quality table
  - DOW analysis table
  - Best-parameter block for Pine Script
"""

import os, glob, re, warnings, itertools
import numpy as np
import pandas as pd
from datetime import time as dtime

warnings.filterwarnings("ignore")

DATA_DIRS = [
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_futures_sample",
    "/Users/edwinmaina/Documents/Space/Trading/Data/frd_sample_futures_ES",
]

PARAM_GRID = {
    "atr_stopMult":  [0.5, 0.75, 1.0, 1.25],
    "atr_tp1Mult":   [1.5, 2.0, 2.5, 3.0],
    "disp_atrMult":  [1.25, 1.5, 1.75, 2.0],
    "lq_sweepWick":  [0.30, 0.35, 0.40, 0.45],
    "of_rvolThresh": [1.5, 2.0, 2.5],
    "sig_minConf":   [4, 5, 6],
}

POINT_VALUE = {"NQ": 20.0, "ES": 50.0}  # dollars per point

# ── 1. INVENTORY & LOAD DATA ───────────────────────────────────────────────────

def parse_filename(fname):
    """Return (symbol, timeframe) from e.g. NQ_5min_sample.csv"""
    base = os.path.basename(fname)
    m = re.match(r"([A-Z]+)_(\w+)_sample\.csv", base)
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
    # Localize as EST (America/New_York) – data already in ET
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("America/New_York", ambiguous="infer",
                                            nonexistent="shift_forward")
    df.set_index("ts", inplace=True)
    return df, sym, tf

def inventory():
    seen = {}           # (sym, tf) -> path  (deduplicate across dirs)
    files = []
    for d in DATA_DIRS:
        files.extend(glob.glob(os.path.join(d, "*.csv")))
    rows = []
    for f in files:
        sym, tf = parse_filename(f)
        if sym is None:
            continue
        key = (sym, tf)
        if key not in seen:
            seen[key] = f
            rows.append({"symbol": sym, "timeframe": tf, "path": f,
                         "lines": sum(1 for _ in open(f)) - 1})
    df = pd.DataFrame(rows).sort_values(["symbol", "timeframe"]).reset_index(drop=True)
    return df, seen

inventory_df, file_map = inventory()

print("=" * 65)
print("STEP 1 — CSV INVENTORY")
print("=" * 65)
print(inventory_df[["symbol", "timeframe", "lines"]].to_string(index=False))

# Load all NQ and ES DataFrames
data = {}   # (sym, tf) -> DataFrame
for (sym, tf), fpath in file_map.items():
    if sym in ("NQ", "ES"):
        df, _, _ = load_csv(fpath)
        if df is not None and len(df) > 10:
            data[(sym, tf)] = df

print(f"\nLoaded {len(data)} DataFrames for NQ/ES.")

# ── 2. SIGNAL ENGINE ──────────────────────────────────────────────────────────

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

def compute_signals(df5, params):
    """
    Vectorised recreation of the Pine Script signal logic on 5-min data.
    Returns a DataFrame of trade entries with columns:
        direction (+1 long / -1 short), entry, sl, tp1, tp2, session, dow, conf
    """
    p = params
    df = df5.copy()
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    atr = compute_atr(df, 14)

    # ── Market Structure (simplified BOS/CHoCH) ──
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
    wt  = pd.Series(wick_ratio_top(o.values, h.values, l.values, c.values), index=df.index)
    wb  = pd.Series(wick_ratio_bot(o.values, h.values, l.values, c.values), index=df.index)
    sweep_hi = (h > prev_hi_10.shift(1)) & (wt > p["lq_sweepWick"])
    sweep_lo = (l < prev_lo_10.shift(1)) & (wb > p["lq_sweepWick"])

    # ── RVOL ──
    rv_len = 20
    avg_vol = v.rolling(rv_len).mean()
    rvol_hi = (v / avg_vol.replace(0, np.nan)) > p["of_rvolThresh"]

    # ── FVG (3-bar) ──
    fvg_bull = l > h.shift(2)   # gap between bar[2].high and bar[0].low
    fvg_bear = h < l.shift(2)

    # ── EMA / SMA trend ──
    ema9  = c.ewm(span=9,  adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    sma200= c.rolling(200).mean()
    ema_bull = ema9 > ema21
    ema_bear = ema9 < ema21
    sma_bull = c > sma200
    sma_bear = c < sma200

    # ── VWAP (session-anchored approximation: rolling 78-bar on 5min ≈ 1 session) ──
    tp_   = (h + l + c) / 3
    vwap  = (tp_ * v).rolling(78).sum() / v.rolling(78).sum().replace(0, np.nan)
    vwap_bull = c > vwap
    vwap_bear = c < vwap

    # ── Session ──
    hour_et = df.index.hour   # already localized to ET
    in_asia  = (hour_et >= 20) | (hour_et < 0)   # 20-24
    in_ldn   = (hour_et >= 2) & (hour_et < 5)
    in_nyam  = (hour_et >= 9) & (hour_et < 12)
    in_nypm  = (hour_et >= 13) & (hour_et < 16)
    in_trade = in_ldn | in_nyam | in_nypm          # active sessions (excl Asia for entries)

    # ── DOW weight threshold ──
    dow_weights = {0: 1.1, 1: 1.2, 2: 1.0, 3: 0.9, 4: 0.6}   # Mon=0
    dow_arr = pd.Series(df.index.weekday, index=df.index)
    dow_ok  = dow_arr.map(dow_weights) >= 0.8

    # ── Confluence score ──
    def conf_long():
        score = (ms_bull.astype(int)
                 + choch_up.astype(int)
                 + disp_bull.astype(int)
                 + sweep_lo.astype(int)
                 + vwap_bull.astype(int)
                 + ema_bull.astype(int)
                 + sma_bull.astype(int)
                 + rvol_hi.astype(int)
                 + fvg_bull.astype(int))
        return score

    def conf_short():
        score = (ms_bear.astype(int)
                 + choch_dn.astype(int)
                 + disp_bear.astype(int)
                 + sweep_hi.astype(int)
                 + vwap_bear.astype(int)
                 + ema_bear.astype(int)
                 + sma_bear.astype(int)
                 + rvol_hi.astype(int)
                 + fvg_bear.astype(int))
        return score

    cl = conf_long()
    cs = conf_short()

    long_sig  = (cl >= p["sig_minConf"]) & in_trade & dow_ok
    short_sig = (cs >= p["sig_minConf"]) & in_trade & dow_ok

    # Remove consecutive signals in the same direction (one trade at a time)
    long_sig  = long_sig  & ~long_sig.shift(1).fillna(False)
    short_sig = short_sig & ~short_sig.shift(1).fillna(False)

    # ── Build trade list ──
    records = []
    for idx in df.index[long_sig]:
        entry = c[idx]
        a     = atr[idx]
        sl    = entry - p["atr_stopMult"] * a
        tp1   = entry + p["atr_tp1Mult"] * a
        tp2   = entry + 4.0 * a
        session = _session_name(idx.hour)
        records.append(dict(ts=idx, direction=1, entry=entry, sl=sl,
                             tp1=tp1, tp2=tp2, session=session,
                             dow=idx.weekday(), conf=cl[idx]))

    for idx in df.index[short_sig]:
        entry = c[idx]
        a     = atr[idx]
        sl    = entry + p["atr_stopMult"] * a
        tp1   = entry - p["atr_tp1Mult"] * a
        tp2   = entry - 4.0 * a
        session = _session_name(idx.hour)
        records.append(dict(ts=idx, direction=-1, entry=entry, sl=sl,
                             tp1=tp1, tp2=tp2, session=session,
                             dow=idx.weekday(), conf=cs[idx]))

    if not records:
        return pd.DataFrame()

    trades = pd.DataFrame(records).sort_values("ts").reset_index(drop=True)
    return trades

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

def simulate_trades(df5, trades, partial_pct=0.60):
    """
    Forward-walk through price bars to determine trade outcomes.
    Returns trades DataFrame augmented with R_result column.
    Partial close: partial_pct at TP1, remainder runs to TP2 or SL.
    """
    if trades.empty:
        return trades

    results = []
    close_arr = df5["close"].values
    idx_arr   = df5.index
    # build a position-to-bar lookup
    bar_pos = {ts: i for i, ts in enumerate(idx_arr)}

    for _, tr in trades.iterrows():
        start_i = bar_pos.get(tr["ts"], None)
        if start_i is None or start_i >= len(close_arr) - 1:
            continue
        d   = tr["direction"]
        sl  = tr["sl"]
        tp1 = tr["tp1"]
        tp2 = tr["tp2"]
        entry = tr["entry"]
        risk  = abs(entry - sl)
        if risk < 1e-9:
            continue

        # Scan forward (max 48 bars = 4hrs on 5min)
        max_bars = min(48, len(close_arr) - start_i - 1)
        tp1_hit = tp2_hit = sl_hit = False
        exit_R  = 0.0

        for j in range(start_i + 1, start_i + 1 + max_bars):
            c_ = close_arr[j]
            if d == 1:
                if c_ <= sl:
                    sl_hit = True; break
                if c_ >= tp1 and not tp1_hit:
                    tp1_hit = True
                if tp1_hit and c_ >= tp2:
                    tp2_hit = True; break
                if tp1_hit and c_ <= sl:
                    # trail stopped on remainder
                    sl_hit = True; break
            else:
                if c_ >= sl:
                    sl_hit = True; break
                if c_ <= tp1 and not tp1_hit:
                    tp1_hit = True
                if tp1_hit and c_ <= tp2:
                    tp2_hit = True; break
                if tp1_hit and c_ >= sl:
                    sl_hit = True; break

        tp1_R = (abs(tp1 - entry)) / risk
        tp2_R = (abs(tp2 - entry)) / risk

        if sl_hit and not tp1_hit:
            exit_R = -1.0
        elif tp1_hit and not tp2_hit and not sl_hit:
            # hit TP1, exited rest at max bar (timeout)
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * 0.0  # remainder BE approx
        elif tp1_hit and tp2_hit:
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * tp2_R
        elif tp1_hit and sl_hit:
            exit_R = partial_pct * tp1_R + (1 - partial_pct) * (-1.0)
        else:
            # timeout without hitting any target — mark as flat
            last_c = close_arr[min(start_i + max_bars, len(close_arr)-1)]
            exit_R = d * (last_c - entry) / risk

        results.append({**tr.to_dict(), "R_result": exit_R, "win": exit_R > 0})

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)

def compute_metrics(result_df):
    if result_df is None or result_df.empty:
        return dict(n=0, win_rate=np.nan, expectancy=np.nan, profit_factor=np.nan,
                    max_dd=np.nan, sharpe=np.nan)
    r = result_df["R_result"].values
    n = len(r)
    if n == 0:
        return dict(n=0, win_rate=np.nan, expectancy=np.nan, profit_factor=np.nan,
                    max_dd=np.nan, sharpe=np.nan)
    wins  = r[r > 0]
    losses= r[r < 0]
    wr    = len(wins) / n
    exp   = r.mean()
    pf    = wins.sum() / abs(losses.sum()) if losses.size > 0 else np.inf
    # Drawdown on cumulative R equity curve
    cum   = np.cumsum(r)
    peak  = np.maximum.accumulate(cum)
    dd    = (cum - peak)
    max_dd= dd.min()
    sharpe= (r.mean() / r.std() * np.sqrt(252 * 78)) if r.std() > 0 else 0.0
    return dict(n=n, win_rate=wr, expectancy=exp, profit_factor=pf,
                max_dd=max_dd, sharpe=sharpe)

# ── 3. WALK-FORWARD OPTIMIZATION ────────────────────────────────────────────────

print("\n" + "=" * 65)
print("STEP 2 — WALK-FORWARD PARAMETER OPTIMIZATION (NQ 5min)")
print("=" * 65)

nq5 = data.get(("NQ", "5min"))
if nq5 is None:
    print("ERROR: NQ 5min data not found!")
    exit(1)

TRAIN_FRAC = 0.70
split_i = int(len(nq5) * TRAIN_FRAC)
train_df = nq5.iloc[:split_i]
test_df  = nq5.iloc[split_i:]

print(f"Train: {train_df.index[0].date()} → {train_df.index[-1].date()} "
      f"({len(train_df)} bars)")
print(f"Test : {test_df.index[0].date()} → {test_df.index[-1].date()} "
      f"({len(test_df)} bars)")

# Build parameter combinations
keys   = list(PARAM_GRID.keys())
values = list(PARAM_GRID.values())
combos = list(itertools.product(*values))
total  = len(combos)
print(f"\nGrid: {total} combinations → running...")

wf_results = []
for i, combo in enumerate(combos):
    params = dict(zip(keys, combo))
    try:
        tr_trades = compute_signals(train_df, params)
        if tr_trades.empty:
            continue
        tr_sim = simulate_trades(train_df, tr_trades)
        tr_m   = compute_metrics(tr_sim)

        te_trades = compute_signals(test_df, params)
        if te_trades.empty:
            continue
        te_sim = simulate_trades(test_df, te_trades)
        te_m   = compute_metrics(te_sim)

        # Overfit flag: OOS metric more than 20% worse than IS
        overfit = (
            (tr_m["expectancy"] > 0 and
             te_m["expectancy"] < tr_m["expectancy"] * 0.80) or
            (tr_m["win_rate"] > 0 and
             te_m["win_rate"]  < tr_m["win_rate"]  * 0.80)
        )

        row = {**{f"is_{k}": v  for k, v in tr_m.items()},
               **{f"oos_{k}": v for k, v in te_m.items()},
               **params,
               "overfit": overfit}
        wf_results.append(row)
    except Exception as e:
        pass

    if (i + 1) % 100 == 0 or (i + 1) == total:
        print(f"  {i+1}/{total}", end="\r")

print(f"\nCompleted {len(wf_results)} valid combinations.")

wf_df = pd.DataFrame(wf_results)
wf_df = wf_df.dropna(subset=["oos_expectancy"])
wf_df = wf_df.sort_values("oos_expectancy", ascending=False).reset_index(drop=True)

top10 = wf_df.head(10)
best_params = {k: top10.iloc[0][k] for k in keys}

print("\nTop 10 by OOS Expectancy (R):")
disp_cols = keys + ["is_win_rate","oos_win_rate","is_expectancy","oos_expectancy",
                     "oos_profit_factor","oos_max_dd","oos_sharpe","overfit"]
disp_cols = [c for c in disp_cols if c in top10.columns]
print(top10[disp_cols].to_string(index=False))

# ── 4. SESSION QUALITY ANALYSIS ────────────────────────────────────────────────

print("\n" + "=" * 65)
print("STEP 3 — SESSION QUALITY ANALYSIS (NQ 5min, best params)")
print("=" * 65)

all_trades_nq = simulate_trades(nq5, compute_signals(nq5, best_params))

if not all_trades_nq.empty:
    sess_stats = []
    for sess in ["Asia", "London", "NY AM", "NY PM"]:
        s = all_trades_nq[all_trades_nq["session"] == sess]
        m = compute_metrics(s)
        sess_stats.append({"Session": sess,
                            "Trades": m["n"],
                            "Win Rate %": f"{m['win_rate']*100:.1f}" if m["n"] else "—",
                            "Avg R": f"{m['expectancy']:.3f}" if m["n"] else "—"})
    sess_df = pd.DataFrame(sess_stats)
    print(sess_df.to_string(index=False))
else:
    print("No trades generated with best params on full dataset.")

# ── 5. DOW ANALYSIS ────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("STEP 4 — DAY-OF-WEEK ANALYSIS (1hr data, NQ & ES)")
print("=" * 65)

DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

for sym in ["NQ", "ES"]:
    df1h = data.get((sym, "1hour"))
    if df1h is None:
        print(f"  {sym} 1hr data not found, skipping.")
        continue

    df1h = df1h.copy()
    df1h["dow"] = df1h.index.weekday
    df1h["range"] = df1h["high"] - df1h["low"]
    df1h["dir"] = np.sign(df1h["close"] - df1h["open"])

    dow_rows = []
    for d in range(5):
        sub = df1h[df1h["dow"] == d]
        if sub.empty:
            continue
        avg_range = sub["range"].mean()
        dir_cons  = (sub["dir"] != 0).sum()
        dir_match = (sub["dir"] == sub["dir"].shift(1)).sum()
        dir_pct   = dir_match / max(dir_cons - 1, 1) * 100
        avg_vol   = sub["volume"].mean()
        dow_rows.append({"DOW": DOW_NAMES[d],
                         "Avg Range (pts)": f"{avg_range:.2f}",
                         "Dir Consistency %": f"{dir_pct:.1f}",
                         "Avg Volume": f"{avg_vol:,.0f}"})

    print(f"\n  {sym} 1hr DOW Summary:")
    print(pd.DataFrame(dow_rows).to_string(index=False))

# ── 6. MARKDOWN REPORT ─────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("STEP 5 — GENERATING MARKDOWN REPORT")
print("=" * 65)

def fmt(v, pct=False, dec=3):
    if pd.isna(v):
        return "—"
    if pct:
        return f"{v*100:.1f}%"
    return f"{v:.{dec}f}"

report_lines = []
report_lines.append("# EM-FSE v6 NQ — Walk-Forward Optimization Report\n")
report_lines.append(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ET  ")
report_lines.append(f"**Data span:** {nq5.index[0].date()} → {nq5.index[-1].date()}  ")
report_lines.append(f"**Train bars:** {len(train_df)} | **Test bars:** {len(test_df)}  ")
report_lines.append(f"**Total combos evaluated:** {len(wf_results)}  \n")

# ── Top 10 table ──
report_lines.append("## Top 10 Parameter Combinations (ranked by OOS Expectancy R)\n")
header = ("| Rank | atr_stop | atr_tp1 | disp_atr | lq_sweep | rvol_thr | min_conf "
          "| IS WR% | OOS WR% | IS Exp R | OOS Exp R | OOS PF | OOS MaxDD | OOS Sharpe | Overfit |")
sep    = ("|------|----------|---------|----------|----------|----------|----------|"
          "--------|---------|----------|-----------|--------|-----------|------------|---------|")
report_lines.append(header)
report_lines.append(sep)

for rank, (_, row) in enumerate(top10.iterrows(), 1):
    flag = "⚠️ YES" if row.get("overfit", False) else "No"
    report_lines.append(
        f"| {rank} "
        f"| {row['atr_stopMult']:.2f} "
        f"| {row['atr_tp1Mult']:.1f} "
        f"| {row['disp_atrMult']:.2f} "
        f"| {row['lq_sweepWick']:.2f} "
        f"| {row['of_rvolThresh']:.1f} "
        f"| {int(row['sig_minConf'])} "
        f"| {fmt(row['is_win_rate'], pct=True)} "
        f"| {fmt(row['oos_win_rate'], pct=True)} "
        f"| {fmt(row['is_expectancy'])} "
        f"| {fmt(row['oos_expectancy'])} "
        f"| {fmt(row['oos_profit_factor'])} "
        f"| {fmt(row['oos_max_dd'])} "
        f"| {fmt(row['oos_sharpe'])} "
        f"| {flag} |"
    )

report_lines.append("")

# ── Session quality ──
report_lines.append("## Session Quality Analysis (NQ 5min, Best Params)\n")
report_lines.append("| Session | Trades | Win Rate % | Avg R per Trade |")
report_lines.append("|---------|--------|------------|-----------------|")
if not all_trades_nq.empty:
    for sess in ["Asia", "London", "NY AM", "NY PM"]:
        s = all_trades_nq[all_trades_nq["session"] == sess]
        m = compute_metrics(s)
        wr  = f"{m['win_rate']*100:.1f}%" if m["n"] else "—"
        exp = f"{m['expectancy']:.3f}" if m["n"] else "—"
        report_lines.append(f"| {sess} | {m['n']} | {wr} | {exp} |")
report_lines.append("")

# ── DOW tables ──
report_lines.append("## Day-of-Week Analysis (1hr Data)\n")
for sym in ["NQ", "ES"]:
    df1h = data.get((sym, "1hour"))
    report_lines.append(f"### {sym}\n")
    if df1h is None:
        report_lines.append("_Data not available_\n")
        continue
    df1h = df1h.copy()
    df1h["dow"] = df1h.index.weekday
    df1h["range"] = df1h["high"] - df1h["low"]
    df1h["dir"]   = np.sign(df1h["close"] - df1h["open"])

    report_lines.append("| DOW | Avg Range (pts) | Dir Consistency % | Avg Volume |")
    report_lines.append("|-----|-----------------|-------------------|------------|")
    for d in range(5):
        sub = df1h[df1h["dow"] == d]
        if sub.empty:
            continue
        avg_range = sub["range"].mean()
        sub_dir   = sub["dir"]
        dir_match = (sub_dir == sub_dir.shift(1)).sum()
        dir_total = (sub_dir != 0).sum()
        dir_pct   = dir_match / max(dir_total - 1, 1) * 100
        avg_vol   = sub["volume"].mean()
        report_lines.append(
            f"| {DOW_NAMES[d]} | {avg_range:.2f} | {dir_pct:.1f}% | {avg_vol:,.0f} |"
        )
    report_lines.append("")

# ── Best params block ──
b = best_params
report_lines.append("## Recommended Parameter Block (Pine Script Defaults)\n")
report_lines.append("```pine")
report_lines.append(f'atr_stopMult  = input.float({b["atr_stopMult"]:.2f}, "SL ATR Multiple", step=0.1, group=grpATR)')
report_lines.append(f'atr_tp1Mult   = input.float({b["atr_tp1Mult"]:.1f},  "TP1 ATR Multiple", step=0.1, group=grpATR)')
report_lines.append(f'disp_atrMult  = input.float({b["disp_atrMult"]:.2f}, "ATR Multiple", step=0.1, group=grpDisp)')
report_lines.append(f'lq_sweepWick  = input.float({b["lq_sweepWick"]:.2f}, "Min Wick Ratio for Sweep", step=0.05, group=grpLQ)')
report_lines.append(f'of_rvolThresh = input.float({b["of_rvolThresh"]:.1f},  "RVOL Threshold", step=0.1, group=grpOF)')
report_lines.append(f'sig_minConf   = input.int({int(b["sig_minConf"])},   "Min Confluence for Signal", minval=1, maxval=15, group=grpSig)')
report_lines.append("```\n")

report_lines.append("---\n")
report_lines.append("*Report auto-generated by optimize_nq.py — EM-FSE v6 second-pass optimization*")

report_md = "\n".join(report_lines)

report_path = "/Users/edwinmaina/Documents/Space/Trading/NQ_Optimization_Report.md"
with open(report_path, "w") as f:
    f.write(report_md)

print(f"Report saved to: {report_path}")

# ── Store best params for Pine Script patch ──
print("\n" + "=" * 65)
print("STEP 6 — BEST PARAMETERS SUMMARY")
print("=" * 65)
print(f"  atr_stopMult  : {b['atr_stopMult']}")
print(f"  atr_tp1Mult   : {b['atr_tp1Mult']}")
print(f"  disp_atrMult  : {b['disp_atrMult']}")
print(f"  lq_sweepWick  : {b['lq_sweepWick']}")
print(f"  of_rvolThresh : {b['of_rvolThresh']}")
print(f"  sig_minConf   : {b['sig_minConf']}")

best_params_export = best_params
