# EM Strategy Lab — Novel Strategy Discovery Report

**Generated:** 2026-04-15 20:05 ET  
**Instruments:** ES, GC, HG, J1, NQ, PA, PL, RP, SI, ZW  
**Strategies tested:** 8  
**Walk-forward:** 70/30 split

## Phase 1: Strategy × Market Heatmap (Expectancy R, full data)

| Strategy | ES | GC | HG | J1 | NQ | PA | PL | RP | SI | ZW |
|----------|------|------|------|------|------|------|------|------|------|------|
| Gap Fill | +0.00R | +0.00R | **+0.53R** | **+0.55R** | +0.00R | -0.48R | **+1.24R** | -0.11R | +0.00R | -0.38R |
| Momentum Ignite | -0.47R | +0.14R | +0.14R | -0.06R | -0.40R | +0.45R | +0.14R | +0.43R | -0.50R | -0.06R |
| Narrow Range | -0.74R | -0.47R | -0.58R | -0.67R | -0.59R | -0.19R | -0.58R | +0.18R | -0.59R | -0.35R |
| ORB (London) | +0.20R | +0.36R | +0.25R | +0.34R | +0.12R | +0.34R | -0.44R | -0.33R | -0.62R | **+1.40R** |
| ORB (NY AM) | +0.09R | +0.08R | +0.23R | +0.14R | +0.09R | +0.40R | +0.03R | -0.88R | **+0.87R** | +0.00R |
| Squeeze Breakout | **+0.79R** | +0.00R | **+1.25R** | +0.29R | **+0.52R** | -0.43R | -0.44R | -1.00R | +0.41R | +0.20R |
| TOD Reversal | -0.25R | -0.21R | -0.32R | +0.04R | -0.22R | +0.50R | +0.17R | -0.00R | -0.33R | -0.32R |
| VWAP Reversion | -0.19R | -0.37R | -0.60R | -0.13R | -0.78R | -0.06R | -0.42R | **+0.72R** | -0.13R | -0.22R |


## Phase 2: Walk-Forward Validated Results

Only showing combos with positive OOS expectancy.

| Rank | Strategy | Market | IS Trades | IS Exp | OOS Trades | OOS Exp | OOS WR | OOS PF | Overfit |
|------|----------|--------|-----------|--------|------------|---------|--------|--------|---------|
| 1 | ORB (London) | PA | 7 | -0.799 | 3 | 3.000 | 100.0% | 999.000 | No |
| 2 | ORB (NY AM) | SI | 7 | 0.416 | 3 | 1.929 | 100.0% | 999.000 | No |
| 3 | ORB (NY AM) | PL | 7 | -0.687 | 3 | 1.698 | 100.0% | 999.000 | No |
| 4 | Momentum Ignite | PL | 11 | -0.273 | 3 | 1.667 | 66.7% | 6.000 | No |
| 5 | ORB (London) | GC | 7 | -0.201 | 3 | 1.663 | 100.0% | 999.000 | No |
| 6 | ORB (NY AM) | HG | 7 | -0.295 | 3 | 1.447 | 100.0% | 999.000 | No |
| 7 | ORB (London) | J1 | 8 | 0.000 | 3 | 1.242 | 66.7% | 4.727 | No |
| 8 | TOD Reversal | PL | 11 | -0.455 | 7 | 1.143 | 71.4% | 5.000 | No |
| 9 | ORB (NY AM) | PA | 7 | 0.143 | 3 | 1.014 | 66.7% | 4.043 | No |
| 10 | Squeeze Breakout | NQ | 15 | 0.333 | 6 | 1.000 | 50.0% | 3.000 | No |
| 11 | Squeeze Breakout | HG | 10 | 1.400 | 6 | 1.000 | 50.0% | 3.000 | No |
| 12 | ORB (NY AM) | ES | 7 | -0.429 | 4 | 1.000 | 50.0% | 3.000 | No |
| 13 | ORB (NY AM) | NQ | 7 | -0.429 | 4 | 1.000 | 50.0% | 3.000 | No |
| 14 | Momentum Ignite | GC | 5 | -0.200 | 2 | 1.000 | 50.0% | 3.000 | No |
| 15 | Momentum Ignite | PA | 14 | 0.429 | 6 | 1.000 | 50.0% | 3.000 | No |
| 16 | TOD Reversal | PA | 11 | 0.364 | 7 | 0.714 | 57.1% | 2.667 | No |
| 17 | ORB (London) | NQ | 8 | -0.042 | 3 | 0.571 | 33.3% | 2.329 | No |
| 18 | Squeeze Breakout | ES | 12 | 1.000 | 9 | 0.514 | 44.4% | 1.925 | No |
| 19 | Squeeze Breakout | J1 | 16 | 0.250 | 7 | 0.374 | 42.9% | 1.655 | No |
| 20 | ORB (NY AM) | GC | 7 | -0.022 | 3 | 0.333 | 33.3% | 1.500 | No |
| 21 | ORB (London) | ZW | 7 | 1.857 | 3 | 0.333 | 33.3% | 1.500 | Yes |
| 22 | ORB (London) | ES | 8 | 0.148 | 3 | 0.333 | 33.3% | 1.500 | No |
| 23 | TOD Reversal | J1 | 17 | 0.059 | 9 | 0.000 | 33.3% | 1.000 | Yes |
| 24 | Squeeze Breakout | ZW | 6 | 0.333 | 4 | 0.000 | 25.0% | 1.000 | Yes |


## Phase 3: Parameter Variant Results (OOS only)

| Variant | Market | OOS Trades | OOS Exp | OOS WR | OOS PF |
|---------|--------|------------|---------|--------|--------|
| Mom 2.0x body, 2.0x vol | ZW | 3 | 3.000 | 100.0% | 999.000 |
| VWAP 2.5σ | PA | 4 | 2.865 | 100.0% | 999.000 |
| VWAP 3.0σ | J1 | 2 | 2.469 | 100.0% | 999.000 |
| Mom 1.5x RR4 | PL | 3 | 2.333 | 66.7% | 8.000 |
| Mom 1.5x body, 2.5x vol | ZW | 4 | 2.000 | 75.0% | 9.000 |
| ORB Ldn 15min RR2 | PA | 3 | 2.000 | 100.0% | 999.000 |
| Mom 1.5x body, 2.5x vol | PA | 4 | 2.000 | 75.0% | 9.000 |
| Mom 1.5x body, 2.0x vol | PL | 3 | 1.667 | 66.7% | 6.000 |
| Mom 1.5x body, 2.5x vol | PL | 3 | 1.667 | 66.7% | 6.000 |
| ORB Ldn 30min RR3 | J1 | 3 | 1.623 | 100.0% | 999.000 |
| Mom 1.5x RR4 | GC | 2 | 1.500 | 50.0% | 4.000 |
| ORB Ldn 15min RR2 | GC | 3 | 1.470 | 100.0% | 999.000 |
| Mom 1.5x body, 2.0x vol | ZW | 5 | 1.400 | 60.0% | 4.500 |
| VWAP 2.5σ | GC | 3 | 1.363 | 66.7% | 5.089 |
| VWAP 1.5σ | PL | 14 | 1.350 | 57.1% | 4.149 |
| ORB Ldn 30min RR2 | J1 | 3 | 1.290 | 100.0% | 999.000 |
| VWAP 1.5σ | HG | 10 | 1.286 | 40.0% | 3.144 |
| ORB Ldn 20min RR3 | J1 | 3 | 1.242 | 66.7% | 4.727 |
| VWAP 1.5σ | RP | 4 | 1.231 | 25.0% | 2.641 |
| ORB Ldn 20min RR3 | GC | 3 | 1.197 | 100.0% | 999.000 |


## Key Findings & Recommendations

### Best New Strategy: **ORB (London)** on **PA**

- OOS Expectancy: 3.000R
- OOS Win Rate: 100.0%
- OOS Profit Factor: 999.000
- Overfit: No

### Strategy Archetype Summary

- **ORB (London)**: Positive on 7/10 markets. Avg exp: +0.161R
- **ORB (NY AM)**: Positive on 8/10 markets. Avg exp: +0.106R
- **VWAP Reversion**: Positive on 1/10 markets. Avg exp: -0.219R
- **Squeeze Breakout**: Positive on 7/10 markets. Avg exp: +0.160R
- **Gap Fill**: Positive on 3/10 markets. Avg exp: +0.135R
- **Momentum Ignite**: Positive on 5/10 markets. Avg exp: -0.017R
- **TOD Reversal**: Positive on 3/10 markets. Avg exp: -0.094R
- **Narrow Range**: Positive on 1/10 markets. Avg exp: -0.460R

### Strategies That Complement Your Existing ICT Engine

Your current strategy is a **trend-following confluence** system. These archetypes use *different* market mechanics and can diversify:

1. **VWAP Mean Reversion** — profits when your trend strategy would stop out (mean-reverting sessions)
2. **ORB** — time-based entry removes subjectivity, purely mechanical
3. **Squeeze Breakout** — volatility regime detection, fires at compression → expansion transitions


---

*Report auto-generated by strategy_lab.py — EM Strategy Lab*