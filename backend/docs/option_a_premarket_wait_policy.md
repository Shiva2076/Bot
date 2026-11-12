# Option A — Premarket WAIT policy (current)

## Stance

Stay on **Option A**: document the WAIT policy; do **not** change gates, scores, weights, or thresholds based on a single quiet day.

## Rules

1. **Decay affects the Pre-Market factor only.** Factor decay/stale midday inputs can change the directional score and confidence. They do not automatically clear a WAIT action.
2. **WAIT is an independent hard prediction gate.** When `recommended_action` is WAIT, prediction paths force WAIT (via `PredictionWaitGate` / `PREMARKET_WAIT`). Clear BEARISH/BULLISH sentiment with confidence ≥ 55 does **not** authorize CALL/PUT while WAIT is on.
3. **Typed override is the only entry escape.** Manual API override with a typed reason is the supported way past WAIT for paper order entry. Live gate redesigns (B/D) are out of scope until multi-session evidence exists.
4. **ORB is always blocked under WAIT.** Opening-range / strategy paths that respect premarket action must not execute when action is WAIT.

## `gap_pct` definition

`NiftyOpeningContext.gap_pct` is **current LTP vs previous close**, as a percent:

`(ltp - prev_close) / prev_close * 100`

It is **not** a frozen official opening auction gap. In PRE_MARKET / PRE_OPEN the collector warns that free feeds may only provide an indicative print. Later in the REGULAR session the same field is still LTP vs previous close (live deviation), so a large gap can keep WAIT active all day when `|gap_pct| >= premarket_large_gap_pct` (default 0.8).

## Decision table (pre-registered)

| Finding | Meaning | Policy |
|---|---|---|
| Large gap or high VIX | Caution tied to open / all-day-ish conditions | Stay on A (document; no redesign) |
| Conflicting / stale midday factors | Gate may be stickier than needed | Only then consider B/D with tests |
| Default fallback | Possible logic gap | Fix or document |

## Logging (additive)

Prediction logs store `gate_reason`, `premarket_action`, `premarket_generated_at`, `premarket_wait_trigger`, and per-quote `freshness_diagnostics` on UF/STALE rows. Premarket reports persist `wait_trigger`. Hypothetical gated outcomes live only in `prediction_research_outcomes` and must never be read by live trading/prediction paths.
