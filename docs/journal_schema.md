# Journal Schema — Full Reference

**Phase:** 4 Learning Layer
**Date:** 2026-03-28

---

## Original 3 Tables (Phase 3, unchanged)

### `trades`
| Column | Type | Notes |
|---|---|---|
| trade_id | TEXT PK | UUID |
| order_id | TEXT | |
| proposal_id | TEXT | |
| symbol | TEXT | |
| timeframe | TEXT | |
| direction | TEXT | LONG / SHORT |
| entry_price | REAL | |
| stop_price | REAL | |
| target_price | REAL | |
| position_size_usd | REAL | |
| r_amount | REAL | |
| opened_at | TEXT | ISO8601 UTC |
| closed_at | TEXT | NULL if open |
| exit_reason | TEXT | NULL if open |
| exit_price | REAL | NULL if open |
| pnl_usd | REAL | NULL if open |
| pnl_r | REAL | NULL if open |
| outcome | TEXT | win/loss/breakeven/open |
| hypothesis_refs | TEXT | JSON array |
| setup_refs | TEXT | JSON array |
| composite_score | REAL | |
| bars_held | INTEGER | |

**Append-only.** One UPDATE allowed per trade_id on close.

### `signals`
| Column | Type | Notes |
|---|---|---|
| signal_id | TEXT PK | |
| group_id | TEXT | |
| symbol | TEXT | |
| timeframe | TEXT | |
| timestamp | TEXT | |
| direction | TEXT | |
| signal_type | TEXT | indicator/candlestick/chart_pattern |
| signal_subtype | TEXT | |
| hypothesis_ref | TEXT | |
| quality_score | REAL | |
| trade_id | TEXT | NULL if no trade |
| metadata | TEXT | JSON |

**Append-only.**

### `journal_events`
| Column | Type | Notes |
|---|---|---|
| event_id | TEXT PK | UUID |
| timestamp | TEXT | ISO8601 UTC |
| event_type | TEXT | signal/trade_open/trade_close/risk_decision/alert/bar |
| source | TEXT | |
| payload | TEXT | JSON |
| severity | TEXT | NULL unless alert |

**Append-only.**

---

## Phase 4 Extension Tables (src/learning/journal_extension.py)

### `setup_packets`
Archives BTCSetupPackets at decision time.

| Column | Type | Notes |
|---|---|---|
| packet_id | TEXT PK | UUID |
| symbol | TEXT | |
| timeframe | TEXT | |
| bar_timestamp | TEXT | ISO8601 |
| stored_at | TEXT | ISO8601 |
| outcome_source | TEXT | See OutcomeSource enum |
| packet_json | TEXT | Full serialized BTCSetupPacket |
| trade_id | TEXT | Populated when trade closes |

**Append-only.**

### `trader_reviews`
One row per TraderVerdict per setup evaluation.

| Column | Type | Notes |
|---|---|---|
| review_id | TEXT PK | UUID |
| packet_id | TEXT | FK → setup_packets |
| trader_name | TEXT | |
| outcome_source | TEXT | |
| vote | TEXT | approve/reject/abstain |
| score | REAL | 1-10 |
| confidence | REAL | 0.0-1.0 |
| pro_reason | TEXT | |
| anti_reason | TEXT | |
| execution_concern | TEXT | |
| risk_concern | TEXT | |
| explanation | TEXT | |
| reviewed_at | TEXT | ISO8601 |
| trade_id | TEXT | Populated when trade closes |

**Append-only.**

### `panel_summaries`
One row per panel evaluation (20-trader vote aggregate).

| Column | Type | Notes |
|---|---|---|
| panel_id | TEXT PK | UUID |
| packet_id | TEXT | FK → setup_packets |
| outcome_source | TEXT | |
| approve_count | INTEGER | |
| reject_count | INTEGER | |
| abstain_count | INTEGER | |
| avg_score | REAL | |
| weighted_score | REAL | |
| panel_recommendation | TEXT | enter/hold |
| key_risks | TEXT | JSON array |
| key_strengths | TEXT | JSON array |
| evaluated_at | TEXT | |
| trade_id | TEXT | |

**Append-only.**

### `final_decisions`
One row per FinalDecisionGroup output.

| Column | Type | Notes |
|---|---|---|
| decision_id | TEXT PK | UUID |
| packet_id | TEXT | FK → setup_packets |
| panel_id | TEXT | FK → panel_summaries |
| outcome_source | TEXT | |
| decision | TEXT | enter/hold |
| safety_rails_triggered | TEXT | JSON array |
| rationale | TEXT | |
| decided_at | TEXT | |
| trade_id | TEXT | |

**Append-only.**

### `outcome_attributions`
Links closed trades back to decision traces.

| Column | Type | Notes |
|---|---|---|
| attribution_id | TEXT PK | UUID |
| trade_id | TEXT | FK → trades |
| packet_id | TEXT | |
| panel_id | TEXT | |
| decision_id | TEXT | |
| outcome_source | TEXT | |
| outcome | TEXT | win/loss/breakeven |
| pnl_r | REAL | |
| exit_reason | TEXT | |
| bars_held | INTEGER | |
| setup_family | TEXT | e.g. "ema_crossover" |
| attributed_at | TEXT | |

**Append-only.**

### `trader_calibration`
Running calibration state. One row per (trader_name, outcome_source). UPSERT semantics.

| Column | Type | Notes |
|---|---|---|
| trader_name | TEXT PK (composite) | |
| outcome_source | TEXT PK (composite) | |
| calibration_json | TEXT | Serialized TraderCalibrationRecord |
| last_updated | TEXT | |

### `setup_family_records`
Per-setup-family performance. UPSERT semantics.

| Column | Type | Notes |
|---|---|---|
| setup_family | TEXT PK (composite) | |
| outcome_source | TEXT PK (composite) | |
| record_json | TEXT | Serialized SetupFamilyRecord |
| last_updated | TEXT | |

### `specialist_group_records`
Per-specialist-group signal contribution. UPSERT semantics.

| Column | Type | Notes |
|---|---|---|
| group_id | TEXT PK (composite) | |
| outcome_source | TEXT PK (composite) | |
| record_json | TEXT | Serialized SpecialistGroupRecord |
| last_updated | TEXT | |

### `learning_recommendations`
Generated recommendations (advisory only). Append-only.

| Column | Type | Notes |
|---|---|---|
| recommendation_id | TEXT PK | UUID |
| created_at | TEXT | |
| outcome_source | TEXT | |
| recommendation_type | TEXT | reweight/quarantine/caution/none |
| target | TEXT | trader name / setup family / group_id |
| reason | TEXT | |
| evidence | TEXT | |
| sample_size | INTEGER | |
| confidence | TEXT | low/medium/high |
| applied | INTEGER | 0 or 1 |
| applied_at | TEXT | NULL until applied |

---

## Append-Only Policy

All Phase 4 tables follow the same append-only rule as Phase 3:
- No UPDATE or DELETE on any table except calibration/family/specialist records (UPSERT)
- Recommendations are append-only; `applied` flag is updated in-place
- All timestamps are ISO8601 UTC strings
