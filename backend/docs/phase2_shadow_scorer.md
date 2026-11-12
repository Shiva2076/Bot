# Phase 2: shadow scorer v2.0 and evaluation harness

Paper-trading only. v2.0 runs next to the live scorer (`prediction_scorer_version`, currently
`v1.3_freshness`) and is **logged only**, in `prediction_logs.shadow_features.v2`. It never
changes the live direction, the gates, the UI or orders. Promotion is a Phase 4 decision.

## Baseline

The plan called for v2.0 next to v1.1. The live scorer had already absorbed several Phase 2
rules before this work (AI agents as direction x confidence with weight 0.10-0.15, ADX as a
non-directional multiplier, Max Pain weighted by days to expiry, OI walls voting only near
spot), so the baseline is v1.3. v2.0 keeps those rules and changes the ones below.

## v2.0 rules

| Live factor | v2.0 replacement | Status before enough data |
|---|---|---|
| Put-Call Ratio (level) | Change in near-spot PCR over `shadow_pcr_change_window_minutes`, from `option_chain_snapshots` | UNAVAILABLE |
| Pre-Market Bias (linear decay to 11:30) | Half-life decay from 09:15 (`shadow_premarket_half_life_minutes`); **weight** 0 when its own action is WAIT/NO_TRADE | - |
| VWAP (index, no volume) | VWAP from near-month futures 5m bars | UNAVAILABLE if today's bars fail the completeness check |
| Relative Volume (index) | Futures bar volume vs the same time-of-day bar of prior regular sessions; votes the bar's direction only when RVOL > 1 | UNAVAILABLE below `shadow_futures_rvol_min_prior_sessions` |
| ΔOI Dynamics (in-memory, no price) | Near-spot OI change from snapshots combined with spot direction: PUT_WRITING / CALL_UNWINDING (bullish), CALL_WRITING / PUT_UNWINDING (bearish); neutral otherwise | UNAVAILABLE |
| IV Rank (vote) | **Gate on buying**: ATM IV rank vs one stored reading per prior session; rank >= `shadow_iv_rank_block_buying_at` turns a CALL/PUT into NO_TRADE (`gate = IV_RANK_HIGH`) | OFF until `shadow_iv_rank_min_sessions` |

Futures volume completeness (checked 12 Nov 2026 on `NIFTY23NOV26FUT`): every 5m bar 09:15-15:25
carried volume on the last three sessions. The analyzer still checks it each time: today's
completed bars must start at 09:15, be contiguous and all have volume > 0. Bars from 15:30 on
and special sessions (e.g. Muhurat) are excluded.

Replaced factors keep the live nominal weights; ΔOI buildup uses `shadow_oi_buildup_weight`.
Every number is in `config.py` under `shadow_*` and is an unvalidated starting point. Do not
retune from a handful of sessions.

## Evaluation

```
cd backend
.venv\Scripts\python -m scripts.evaluate_predictions            # NIFTY, v0_pre_fix excluded
.venv\Scripts\python -m scripts.evaluate_predictions --json report.json
```

Per horizon (15/30/60m) it prints live hit rate and net expectancy per lot after costs,
calibration (|score| bucket vs hit rate), per-regime and per-time-bucket results, an
in-sample vs out-of-sample split by session (latest `evaluation_holdout_fraction` of sessions
held out), ablation of each factor and cluster on the raw factor score, and v2 vs the live raw
signal on the same rows. Every figure carries its sample size.

Below `evaluation_min_samples` directional outcomes or `evaluation_min_sessions` sessions the
verdict is `INSUFFICIENT SAMPLE - no conclusions` and ablation deltas are withheld.

## What needs time, not code

v2 factors that read history (PCR change, ΔOI buildup, IV rank gate) need the 3-minute chain
snapshots, which the backend records only during regular hours while it is running. The IV
gate needs 20 sessions of them. The evaluation needs at least 20 sessions and 200 resolved
directional outcomes per horizon before it will say anything.
