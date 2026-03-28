# PHASE 6 HANDOFF

**Date:** 2026-03-29
**Phase completed:** 6 — Candidate Generator Repair
**Next phase:** 6.1 — Live Observation / Extended Replay

---

## What Was Wrong with Upstream Proposal Generation (Before Phase 6)

The Phase 5.75 runtime generated 8 proposals across 900 replay bars. All 8 were at **EMA crossover transition bars** (H3-002: exact moment EMA20 crosses EMA50). These bars have properties that are structurally incompatible with the panel's requirements:

| Signal at crossover bars | Why it fails the panel |
|-------------------------|----------------------|
| `ema_alignment = "mixed"` | TrendFollowing scores 4.5 (reject) — biggest single blocker |
| No candlestick patterns | Candlestick scores 4.0 (abstain), WickAnalysis scores low |
| Volume 0.92x | VolumeProfile abstains |
| RSI 75.14 rising | Momentum penalizes for SHORT |
| EMA separation ~0% | Trend not committed |

Three additional problems existed in the EntryGroup:
1. **Evaluation triggered before CandlestickGroup published** — `candlestick_quality = 0.0` in every proposal
2. **Candlestick gate not enforced** — two indicator signals could pass the gate without bar-level confirmation
3. **No signal type for established trends** — only H3-002 (transition) existed; no signal for the continuation phase

---

## What Was Repaired

Three targeted changes in two files:

### 1. H3-005: Trend Continuation Signal (new — `src/groups/indicators/group.py`)

New signal that fires during **established trend phases** (not transition bars):

- **SHORT**: full_bear EMA alignment (EMA20 < EMA50 < EMA200), EMA separation ≥ 0.2%, price within 3% of EMA20 (pullback zone), ADX ≥ 25, volume ≥ 1.0x, RSI 35–65
- **LONG**: mirror conditions for full_bull

At H3-005 bars: `ema_alignment = "full_bear"` → TrendFollowing scores 8.0+ (approve, not reject).

### 2. Wait for candlestick bundle (`src/groups/entry/group.py`)

EntryGroup now triggers evaluation when **both** indicators AND candlestick bundles arrive (previously: indicators alone). CandlestickGroup always publishes every bar, so this is safe. Now `candlestick_quality > 0` whenever a pattern fires.

### 3. Enforce candlestick/chart_pattern requirement (`src/groups/entry/group.py`)

Added gate enforcement: proposals require at least 1 `signal_type == "candlestick"` or `"chart_pattern"` in the primary signals. Pure indicator-only proposals are suppressed.

Combined effect: only proposals combining H3-005 (established trend) + candlestick pattern (bar-level confirmation) can pass the gate.

---

## Whether Natural Proposals Are Now Stronger

**Yes — by design.** Every proposal that passes the Phase 6 gate has:
- `ema_alignment = "full_bear"` or `"full_bull"` (established trend confirmed)
- Candlestick pattern detected at the entry bar
- Volume ≥ 1.0x (H3-005 requirement)
- RSI in the 35–65 mid-zone (not overbought at entry)
- ADX ≥ 25 (trending, not ranging)

The old crossover proposals (which the panel rejected) can no longer pass the gate. The new continuation + candlestick proposals have the signal profile the panel was designed to evaluate.

---

## Whether Any Natural Proposals Now Pass the Panel

**We cannot confirm this yet.** This is the honest answer.

What we CAN confirm:
- **Unit tests (20)**: H3-005 fires correctly in established trend conditions and is suppressed in 6 failure conditions (ADX<25, vol<1.0, EMA sep<0.2%, RSI out of range, price too far from EMA20, mixed alignment)
- **Gate tests**: indicator-only proposals blocked, H3-005+candlestick proposals pass gate
- **Composite score test**: H3-005 + candlestick + structural scores ~0.83 (well above 0.50 threshold)
- **Panel regression**: ideal Phase 3 proposal (full_bear, evening_star, R:R=3.5) still produces 16/20 approvals, avg=7.78 → ENTER (unchanged from Phase 5.9)
- **Weak proposal regression**: crossover-era proposals still rejected by panel

What we CANNOT confirm without running a full replay:
- Whether the Phase 5.75 replay fixtures (btc_bull_breakout_v1, btc_bear_drop_v1) actually contain bars where H3-005 AND a candlestick pattern fire simultaneously
- Whether those bars produce proposals with R:R sufficient for DrawdownRisk to approve
- Whether the exact proposal count increases or what percentage pass the panel

**To confirm panel passes**: Run the Phase 5.75 replay harness against the Phase 6 codebase and observe whether any proposals reach the panel and what the panel decides.

---

## Whether Positions Can Open Naturally Without Forcing

**Yes — IF the runtime produces proposals with the required signal conditions.** The system is structurally capable of opening positions naturally:

1. H3-005 fires during established trend pullbacks (no forcing)
2. CandlestickGroup detects patterns at structural levels (no forcing)
3. Gate passes when both signals are present in same direction
4. Composite score ~0.83 (well above threshold)
5. Panel evaluates with real evaluators (no hardcoded approvals)
6. Panel can reach 14+/20 approvals for full_bear + evening_star + R:R≥2.5 proposals
7. FinalDecisionGroup safety rails unchanged
8. RiskLeverageGroup receives panel-approved proposals (path unchanged)

**The path is open. Whether a position actually opens depends on whether the replay fixtures or live data produce qualifying bars.**

The most likely bottleneck is now:
- **R:R adequacy**: The stop/target placement in `setup_packet_builder.py` determines R:R. If the distance to EMA20 (stop) and next structural support (target) doesn't produce R:R ≥ 2.0, DrawdownRisk and RiskParity score low.
- **Structural level quality**: Contrary requires `structure_quality="strong"` + R:R>3.0. Most replay bars will have structure_quality="B" at best.
- **Candlestick/H3-005 coincidence frequency**: Both signals must fire on the same bar. In the replay fixtures this may happen 0, 1, 2, or more times.

---

## What Remains Before Serious Paper Performance Observation

### Required:
1. **Run Phase 6 replay** — execute the Phase 5.75 replay harness with Phase 6 code. Count proposals, panel outcomes, positions. This is Phase 6.1.

2. **Verify R:R at H3-005 bars** — The setup_packet_builder calculates stop/target from price levels. Confirm that pullback-to-EMA proposals produce R:R ≥ 2.0 (minimum) to 2.5 (preferred for DrawdownRisk).

3. **Review SetupProposal short-stop logic** — For SHORT proposals at EMA20 pullback: stop is above EMA20, target is at next structural support. Confirm this produces valid R:R for BTC price levels (e.g., stop = +1.5%, target = -3.5%).

### Deferred (not blockers):
- ChartPatternGroup activation (Phase 4)
- LeverageSpecialist SHORT leverage sign fix (Phase 4)
- HistorianAgent, CriticAgent wiring (Phase 4+)
- Pullback-to-EMA50 and pullback-to-EMA200 setup types
- Structure quality "strong" detection improvement

---

## What Must Not Be Misrepresented

1. **Positions have not opened yet.** Phase 6 sets up the conditions for positions to open, but no confirmation from a live replay run.

2. **The 8 Phase 5.75 proposals are now blocked by the gate.** They would be rejected before reaching the panel (indicator-only). This is correct behavior — they were weak proposals.

3. **H3-005 firing frequently does not mean proposals are being generated.** H3-005 can fire every bar in an established trend's pullback zone. Proposals only fire when CandlestickGroup ALSO fires a pattern on the same bar. The panel provides a further quality filter.

4. **The H3-005 RSI range (35–65) is strict.** During a deep decline, RSI may be below 35 (oversold). H3-005 won't fire in those conditions. This is intentional — deep oversold conditions are a different setup type.

5. **Contrary evaluator still requires R:R > 3.0 AND structure_quality = "strong".** Most proposals will not satisfy this. Contrary will continue to reject most proposals (by design).

6. **The ideal synthetic packet (16/20, avg=7.78) is a proof of capability, not an expectation.** It requires ideal conditions on all dimensions simultaneously. Real proposals will be more varied.

---

## Test Suite State

**244 tests total, all passing.**

| Test File | Tests | Phase |
|-----------|-------|-------|
| test_candidate_generator_repair.py | 20 | 6 |
| test_panel_viability.py | 32 | 5.9 |
| test_entry_policy_viability.py | 22 | 5.75 |
| (prior phases) | 170 | 1–5.5 |

---

## Documentation Index

| Document | Location |
|----------|----------|
| Phase summary | `docs/PHASE_6_CANDIDATE_GENERATOR_REPAIR.md` |
| Upstream trigger audit | `docs/upstream_signal_trigger_audit.md` |
| Approved vs rejected profile | `docs/approved_vs_rejected_signal_profile.md` |
| Trend maturity and pullback logic | `docs/trend_maturity_and_pullback_logic.md` |
| Before/after replay results | `docs/candidate_generator_before_after_replay.md` |
| Panel compatibility | `docs/panel_compatibility_of_upstream_proposals.md` |
| **This handoff** | `docs/PHASE_6_HANDOFF.md` |

---

## Passing to Phase 6.1

Phase 6.1 (Live Replay Observation) begins from:

- Layer A (candidate generation): repaired — H3-005 + candlestick gate
- Layer B (panel evaluation): repaired (Phase 5.9) — panel viable for strong proposals
- Layer C (execution): wired — path from panel approval to position open is intact
- Risk management: all safety rails active and unmodified
- Test suite: 244 tests passing, all phases covered

**The primary task for Phase 6.1**: Run the replay harness, observe whether any proposals fire, whether they pass the panel, and whether positions open. Do not adjust thresholds based on this observation — record what actually happens and assess whether the signal conditions in the replay fixtures are sufficient.
