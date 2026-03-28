# Trade Plan Enrichment Design

**Date:** 2026-03-28
**Context:** Phase 3 fix — raw_target enrichment in PanelDecisionGroup

---

## Problem Statement

`CandidateTradeProposal.raw_target` defaults to `Decimal("0")`. `EntryGroup._build_proposal()` does not compute a target price — it assembles signal metadata and composite score but defers trade plan geometry to the Layer B evaluation.

Risk Rule 9 (`_check_plan_completeness`) in `RiskLeverageGroup` rejects any proposal where `raw_target <= 0` with `RejectionCode.INCOMPLETE_TRADE_PLAN`. Without enrichment, every proposal reaching `RiskLeverageGroup` fails Rule 9.

---

## Source of target_price

`build_btc_setup_packet()` calls `build_setup_proposal(proposal, fv)` which computes:

```python
stop_price = entry_price - 2 × fv.atr14    # for LONG; entry + 2×ATR for SHORT
stop_dist  = abs(entry_price - stop_price)
target_price = entry_price + 2 × stop_dist  # 2R target (default)
```

This gives a `SetupProposal.target_price` that is always > 0 for a valid FeatureVector with `atr14 > 0`. The BTCSetupPacket is built by `PanelDecisionGroup` before the panel runs — so `packet.proposal.target_price` is available before the forwarding step.

---

## Enrichment Point

The enrichment happens in `PanelDecisionGroup._evaluate_proposal()`, after `packet` is built and `final_decision == "enter"` is confirmed:

```python
enriched_proposal = proposal
if (
    packet.proposal.target_price > Decimal("0")
    and proposal.raw_target == Decimal("0")
):
    enriched_proposal = dataclass_replace(
        proposal, raw_target=packet.proposal.target_price
    )
await self.bus.publish(
    PanelApprovedProposalEvent(
        proposal=enriched_proposal,  # enriched, not original
        ...
    )
)
```

**Key design decisions:**

1. **Only enrich when raw_target == 0** — If `EntryGroup` sets a valid `raw_target` in the future (e.g. from ChartPatternGroup measured move), that value is preserved. Enrichment is a fill-in, not an override.

2. **Only enrich when decision == "enter"** — No enrichment for held proposals. The enriched proposal is only used in the forwarded `PanelApprovedProposalEvent`. The original proposal in `CandidateTradeEvent` is unchanged.

3. **Immutable via `dataclass_replace`** — `CandidateTradeProposal` is a dataclass (not frozen). Using `dataclass_replace` creates a new instance rather than mutating the original, preventing any upstream state corruption if the bus delivers the same event to multiple subscribers.

4. **Stop_price not enriched** — `RiskLeverageGroup._compute_order()` computes its own stop price via `ATRStopPlacer.compute()`. Setting `stop_price` on the proposal is not necessary for Rule 9 (only `raw_target`, `hypothesis_refs`, and `composite_score` are checked).

---

## Why Not Enrich in EntryGroup?

EntryGroup could compute `raw_target = entry_price + 2 × atr14` directly. However:

1. `EntryGroup` does not have a `FeatureVector` reference at proposal-build time — it receives `GroupSignalBundle` objects from specialist groups. It would need to read from `MarketDataGroup._feature_cache` or receive `FeatureVector` directly.

2. The `BTCSetupPacket`-level target computation already applies the right logic (ATR-based, accounting for direction, defaulting correctly). Duplicating this in EntryGroup would create drift if the logic changes.

3. The enrichment belongs in the Layer B+C bridge because it is the point where trade geometry is evaluated and confirmed. Enriching before the panel would cause the panel to see a target that EntryGroup hadn't validated.

---

## Future Enhancement

When `ChartPatternGroup` is activated, `CandidateTradeProposal.raw_target` should be set to `ChartPatternSignal.conservative_target` (50% of measured move) by EntryGroup. The enrichment guard (`proposal.raw_target == Decimal("0")`) will then correctly skip enrichment when a real target exists.
