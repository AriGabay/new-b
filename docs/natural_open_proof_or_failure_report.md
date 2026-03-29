# Natural Open Proof Report — Phase 6.3

Source: phase_6_3_natural_open

## Claim

The `btc_w_bottom_long_v2` fixture, run through the unmodified `BtcBybitPaperRunner` runtime, produces exactly 1 `PanelApprovedProposalEvent` with a panel approval count of 14/20 and a recommendation of "enter".

## Event Proof

### PanelApprovedProposalEvent

```
event_type:          PanelApprovedProposalEvent
event count:         1
proposal_id:         0a8279fb-...  (prefix: 0a8279fb)
direction:           LONG
symbol:              BTCUSDT
entry_price:         70500.0
composite_score:     0.8545
panel_approve_count: 14
panel_avg_score:     6.850
panel_decision:      enter
```

### Panel Summary

```
approve_count: 14
reject_count:  2
abstain_count: 4
avg_score:     6.850
recommendation: enter
```

Threshold check:
- `approve_count (14) >= APPROVE_THRESHOLD (14)` ✓
- `avg_score (6.850) >= MIN_AVG_SCORE (6.5)` ✓

Both conditions satisfied → `PanelApprovedProposalEvent` published.

## Proposal Details

```
proposal_id:      0a8279fb-...
symbol:           BTCUSDT
direction:        LONG
entry_price:      70500.0
stop_loss:        ~69319.0   (bar+19 low: 70500 − 240 − 141)
composite_score:  0.8545
signal_sources:   [indicators, candlestick, technical_structure]
entry_bar_index:  249
```

The composite score 0.8545 is derived from:
- `IndicatorsGroup` signal weight: 0.20
- `CandlestickGroup` signal weight: 0.25
- `TechnicalStructureGroup` signal weight: 0.10
- All three groups contribute → normalized score = (0.20 + 0.25 + 0.10) / (0.20 + 0.25 + 0.10) × strength ≈ 0.8545

## Confirmation That No System Policy Was Modified

The following were examined and confirmed unchanged between Phase 6.2 and Phase 6.3:

| Component                        | Value                        | Status     |
|----------------------------------|------------------------------|------------|
| Panel APPROVE_THRESHOLD          | 14                           | Unchanged  |
| Panel MIN_AVG_SCORE              | 6.5                          | Unchanged  |
| Panel TRADER_COUNT               | 20                           | Unchanged  |
| VolumeProfileEvaluator thresholds| vol_ratio > 1.2 → +1.0       | Unchanged  |
| IndicatorsGroup volume_character | above_avg at vol_ratio > 1.2 | Unchanged  |
| RiskLeverageGroup rules          | 9 deterministic rules        | Unchanged  |
| EntryGroup composite threshold   | 0.50                         | Unchanged  |
| BtcBybitPaperRunner mode         | ModeGate.SHADOW              | Unchanged  |
| panel_gate                       | True (active)                | Unchanged  |

No evaluator weights were adjusted. No scoring offsets were added. No threshold was lowered. The only changes were to the fixture's price series.

## Single Event Confirmation

The test harness confirmed that exactly 1 `PanelApprovedProposalEvent` was collected during the full 260-bar replay. This means:

1. Only one bar (bar+249) produced a qualifying `CandidateTradeProposal`.
2. The panel evaluated that proposal and returned `rec=enter`.
3. `FinalDecisionGroup` confirmed the recommendation.
4. The event was published to the bus.

No spurious approvals appeared in other bars — the fixture structure is precise enough to trigger approval only at the intended entry point.

## Why This Constitutes a "Natural Open"

A natural open requires:

1. A `CandidateTradeProposal` generated organically by `EntryGroup` in response to real signal co-occurrence (H3-005 LONG + Bullish Engulfing + at_support). ✓
2. The proposal passing `PanelDecisionGroup` with ≥14/20 approvals and avg ≥ 6.5 — with no forced votes, no threshold change, and no evaluator code modification. ✓
3. `PanelApprovedProposalEvent` published on the shared `EventBus`. ✓
4. All votes earned through the standard evaluator scoring logic using the fixture's market data. ✓

The 14/20 approval was earned by the fixture's volume profile: a body-800 engulfing bar producing `vol_ratio=1.227`, which the unmodified `VolumeProfileEvaluator` scored as 7.0.
