# EM-FSE v6 NQ — Ablation & Variation Study

**Generated:** 2026-04-15 19:55 ET  
**Data:** NQ 5min, 2951 bars (2026-03-22 → 2026-04-06)  
**Base Params:** stop=0.5, tp1=4.0, disp=1.25, conf=6  
**Walk-Forward:** 70/30 split

## Study 1: Confluence Factor Ablation

Remove one factor at a time and measure impact on OOS expectancy.

| Removed Factor | OOS Trades | OOS WR | OOS Exp (R) | OOS PF | Delta vs Base | Verdict |
|----------------|-----------|--------|-------------|--------|---------------|---------|
| **BASELINE** | 2 | 50.0% | 3.500 | 8.000 | — | — |
| -ms | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |
| -choch | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |
| -disp | 2 | 50.0% | 3.500 | 8.000 | +0.000R | Neutral |
| -sweep | 2 | 50.0% | 3.500 | 8.000 | +0.000R | Neutral |
| -rvol | 2 | 50.0% | 3.500 | 8.000 | +0.000R | Neutral |
| -fvg | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |
| -ema | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |
| -sma | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |
| -vwap | 1 | 0.0% | -1.000 | 0.000 | -4.500R | HELPS |


**Key factors (removing hurts performance):** ms, choch, fvg, ema, sma, vwap


## Study 2: Session Combinations

| Sessions | Trades | WR | Exp (R) | PF | Sharpe | Max DD (R) |
|----------|--------|-----|---------|-----|--------|------------|
| London | 8 | 37.5% | 2.375 | 4.800 | 76.4 | -2.000 |
| NY AM | 9 | 22.2% | 1.000 | 2.286 | 37.5 | -3.000 |
| NY PM | 3 | 0.0% | -1.000 | 0.000 | 0.0 | -2.000 |
| London + NY AM | 17 | 29.4% | 1.647 | 3.333 | 56.3 | -6.000 |
| London + NY PM | 11 | 27.3% | 1.455 | 3.000 | 50.9 | -3.000 |
| NY AM + NY PM | 12 | 16.7% | 0.500 | 1.600 | 20.9 | -5.000 |
| London + NY AM + NY PM | 20 | 25.0% | 1.250 | 2.667 | 45.0 | -7.000 |
| Asia + London | 27 | 22.2% | 0.721 | 1.927 | 29.0 | -8.000 |


## Study 3: Partial TP % at TP1

How much to close at TP1 vs let ride to TP2?

| Partial % | Trades | WR | Exp (R) | PF | Avg Winner (R) |
|-----------|--------|-----|---------|-----|----------------|
| 0% (all trails) | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 20% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 40% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 50% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 60% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 70% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 80% | 8 | 37.5% | 2.375 | 4.800 | 8.000 |
| 100% (all at TP1) | 8 | 37.5% | 2.375 | 4.800 | 8.000 |


## Study 4: Trailing Stop ATR Multiple

| Trail ATR Mult | Trades | WR | Exp (R) | PF |
|----------------|--------|-----|---------|-----|
| 0.50 | 8 | 37.5% | 2.375 | 4.800 |
| 0.75 | 8 | 37.5% | 2.375 | 4.800 |
| 1.00 | 8 | 37.5% | 2.375 | 4.800 |
| 1.25 | 8 | 37.5% | 2.375 | 4.800 |
| 1.50 | 8 | 37.5% | 2.375 | 4.800 |
| 2.00 | 8 | 37.5% | 2.375 | 4.800 |
| 2.50 | 8 | 37.5% | 2.375 | 4.800 |
| 3.00 | 8 | 37.5% | 2.375 | 4.800 |


## Study 5: Day-of-Week Weight Profiles

| Profile | Mon | Tue | Wed | Thu | Fri | Trades | WR | Exp (R) | PF |
|---------|-----|-----|-----|-----|-----|--------|-----|---------|-----|
| Current OPT3 | 1.1 | 0.5 | 1.0 | 0.9 | 0.6 | 8 | 37.5% | 2.375 | 4.800 |
| Original | 1.1 | 1.2 | 1.0 | 0.9 | 0.6 | 9 | 33.3% | 2.000 | 4.000 |
| Kill Tuesday | 1.1 | 0.0 | 1.0 | 0.9 | 0.6 | 8 | 37.5% | 2.375 | 4.800 |
| Mon+Wed+Thu only | 1.1 | 0.0 | 1.0 | 0.9 | 0.0 | 8 | 37.5% | 2.375 | 4.800 |
| Monday heavy | 1.5 | 0.5 | 0.8 | 0.9 | 0.5 | 8 | 37.5% | 2.375 | 4.800 |
| Flat (all equal) | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 11 | 27.3% | 1.455 | 3.000 |
| Aggressive filter | 1.2 | 0.0 | 1.0 | 1.0 | 0.0 | 8 | 37.5% | 2.375 | 4.800 |


## Study 6: SL × TP Matrix

London session, conf=6, OPT3 DOW weights.

| SL \ TP | 1.5 | 2.0 | 3.0 | 4.0 | 5.0 | 6.0 |
|---------|------|------|------|------|------|------|
| 0.25 | 3.28R | 4.16R | 4.03R | 3.25R | 1.42R | -1.00R |
| 0.50 | 1.39R | 1.83R | 2.68R | 2.38R | 0.92R | -0.35R |
| 0.75 | 1.07R | 1.50R | 2.17R | 2.17R | 0.81R | -0.08R |
| 1.00 | 0.71R | 1.03R | 1.53R | 1.50R | 0.45R | -0.25R |
| 1.50 | 0.35R | 0.56R | 0.90R | 0.83R | 0.25R | -0.25R |


## Study 7: Minimum Confluence Threshold

| Min Conf | Trades | WR | Exp (R) | PF | Max DD (R) |
|----------|--------|-----|---------|-----|------------|
| 2 | 30 | 13.3% | 0.200 | 1.231 | -16.000 |
| 3 | 25 | 16.0% | 0.440 | 1.524 | -14.000 |
| 4 | 23 | 17.4% | 0.565 | 1.684 | -11.000 |
| 5 | 16 | 18.8% | 0.688 | 1.846 | -7.000 |
| 6 | 8 | 37.5% | 2.375 | 4.800 | -2.000 |
| 7 | 1 | 0.0% | -1.000 | 0.000 | 0.000 |
| 8 | 0 | 0.0% | 0.000 | 0.000 | 0.000 |
| 9 | 0 | 0.0% | 0.000 | 0.000 | 0.000 |


## Study 8: Trade Cooldown (min bars between entries)

| Cooldown (bars) | ~Minutes | Trades | WR | Exp (R) | PF |
|-----------------|----------|--------|-----|---------|-----|
| 0 | 0 | 8 | 37.5% | 2.375 | 4.800 |
| 3 | 15 | 8 | 37.5% | 2.375 | 4.800 |
| 6 | 30 | 6 | 50.0% | 3.500 | 8.000 |
| 12 | 60 | 6 | 50.0% | 3.500 | 8.000 |
| 18 | 90 | 6 | 50.0% | 3.500 | 8.000 |
| 24 | 120 | 4 | 50.0% | 3.500 | 8.000 |
| 36 | 180 | 4 | 50.0% | 3.500 | 8.000 |


## Summary & Recommendations

See individual study tables above for data. Key takeaways are summarized in the terminal output.


---

*Report auto-generated by ablation_study.py — EM-FSE v6 NQ variation analysis*