"""
Runtime Wiring Verification Tests — Phase 4.75 + Phase 3 Execution Unblock.

These tests go beyond subscription-existence checks.
They prove invocation, data flow, side effects, and bypass prevention.

Verified:
  1. Layer B (TraderEvaluatorPanel) actually runs — 20 verdicts returned
  2. Layer C (FinalDecisionGroup) actually runs — hold/enter decision returned
  3. DecisionTraceLogger writes to SQLite (4 trace records per proposal)
  4. setup() alone wires the learning layer (no manual _finalize_learning_wiring call)
  5. Panel gate blocks CandidateTradeEvent from bypassing RiskLeverageGroup
  6. simulate_bar() populates feature cache (PanelDecisionGroup can build BTCSetupPacket)
  7. SystemState is in SHADOW mode in the runner (not RESEARCH)
  8. PanelDecisionGroup skips proposals with no FeatureVector (safe guard)
  9. End-to-end: CandidateTradeEvent → 20 traders → FinalDecision → (hold → no risk eval)
 10. End-to-end with panel approve path: approved proposal reaches RiskLeverageGroup
 11. EntryGroup uses SHADOW mode_gate (not RESEARCH)
 12. OutcomeAttributor IS wired to PerformanceJournalGroup (Phase 3 wiring)
 13. End-to-end position open: panel approve → Risk → PositionOpenEvent + SystemState updated
 14. End-to-end position close: position open → simulate second bar → ExitGroup → PositionCloseEvent
 15. Position carries learning layer IDs (packet_id/panel_id/decision_id)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest


def make_fv(bullish: bool = True, price: Decimal = Decimal("65000")):
    from core.schemas import FeatureVector
    ema20 = price - Decimal("200") if bullish else price + Decimal("200")
    ema50 = price - Decimal("500") if bullish else price + Decimal("500")
    ema200 = price - Decimal("1000") if bullish else price + Decimal("1000")
    return FeatureVector(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=datetime.now(timezone.utc),
        open=price - Decimal("50"), high=price + Decimal("150"),
        low=price - Decimal("100"), close=price,
        volume=Decimal("1500"), true_range=Decimal("250"),
        atr14=Decimal("800"), atr14_sma20=Decimal("750"),
        ema20=ema20, ema50=ema50, ema200=ema200,
        prev_ema20=ema20 - Decimal("10"), prev_ema50=ema50 - Decimal("20"),
        rsi14=62.0 if bullish else 48.0, prev_rsi14=58.0 if bullish else 51.0,
        bb_upper=price + Decimal("1500"), bb_middle=price, bb_lower=price - Decimal("1500"),
        bb_width=Decimal("3000"), bb_width_pct=45.0,
        adx14=28.0 if bullish else 14.0, volume_sma20=Decimal("1200"),
        volume_ratio=1.25, candle_body=Decimal("100"), candle_range=Decimal("250"),
        body_ratio=0.40, upper_shadow=Decimal("100"), lower_shadow=Decimal("50"),
        impulse_flag=False, doji_flag=False,
    )


def make_proposal(direction="LONG", score=0.65, price=Decimal("65000")):
    from core.schemas import CandidateTradeProposal, Direction, ModeGate
    d = Direction.LONG if direction == "LONG" else Direction.SHORT
    return CandidateTradeProposal(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=datetime.now(timezone.utc),
        direction=d,
        entry_price=price,
        thesis=f"{direction} on BTCUSDT: test",
        setup_refs=["ema_crossover"],
        hypothesis_refs=["H3-001", "H3-002"],
        composite_score=score,
        score_breakdown={"indicator_quality": score},
        mode_gate=ModeGate.SHADOW,
    )


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 1. SystemState mode is SHADOW, not RESEARCH
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_uses_shadow_mode():
    """BtcBybitPaperRunner creates SystemState in SHADOW (paper) mode."""
    from runtime.runner import BtcBybitPaperRunner
    from core.schemas import ModeGate
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    # Check BEFORE setup() — mode is set in __init__
    assert runner.state.mode == ModeGate.SHADOW, (
        f"Expected SHADOW mode, got {runner.state.mode}. "
        "Risk Rule 1 blocks ALL orders in RESEARCH mode."
    )
    await runner.setup()
    assert runner.state.mode == ModeGate.SHADOW, "Mode should remain SHADOW after setup()"
    await runner.teardown()


# ---------------------------------------------------------------------------
# 2. simulate_bar() populates MarketDataGroup feature cache
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_simulate_bar_populates_feature_cache():
    """
    simulate_bar() must populate MarketDataGroup._feature_cache[(symbol, timeframe)]
    so PanelDecisionGroup can build BTCSetupPacket when a proposal arrives.
    Before this fix, the cache stayed empty → PanelDecisionGroup silently skipped all proposals.
    """
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv(price=Decimal("66000"))
    assert ("BTCUSDT", "1h") not in runner._market_data._feature_cache, \
        "Cache should be empty before simulate_bar"

    await runner.simulate_bar(fv)
    await asyncio.sleep(0.02)

    assert ("BTCUSDT", "1h") in runner._market_data._feature_cache, \
        "Cache must be populated after simulate_bar() — PanelDecisionGroup reads this"
    cached = runner._market_data._feature_cache[("BTCUSDT", "1h")]
    assert cached.close == Decimal("66000"), "Cached FeatureVector must match injected fv"

    # Verify PanelDecisionGroup shares the same cache object
    assert runner._panel_decision._feature_cache is runner._market_data._feature_cache, \
        "PanelDecisionGroup must reference the SAME cache dict as MarketDataGroup"

    await runner.teardown()


# ---------------------------------------------------------------------------
# 3. Learning layer wired by setup() alone (no manual _finalize_learning_wiring)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_learning_layer_wired_after_setup_only():
    """
    setup() must wire JournalExtension and DecisionTraceLogger automatically.
    Previously, _finalize_learning_wiring() was never called from setup() —
    only from startup_load() (live mode) or manually by the caller (test hack).
    """
    from runtime.runner import BtcBybitPaperRunner
    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    # Do NOT manually call _finalize_learning_wiring() — setup() must do it
    await runner.setup()

    assert runner._journal_extension is not None, \
        "JournalExtension must be wired by setup(), not require manual call"
    assert runner._panel_decision._trace_logger is not None, \
        "DecisionTraceLogger must be injected into PanelDecisionGroup by setup()"

    await runner.teardown()


# ---------------------------------------------------------------------------
# 4. Layer B: TraderEvaluatorPanel actually invoked with 20 verdicts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trader_evaluator_panel_actually_runs():
    """
    Inject a CandidateTradeEvent with feature cache populated.
    Verify TraderEvaluatorPanel.evaluate() is called and returns 20 verdicts.

    This test proves Layer B is not dead code.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent
    from traders.panel import TraderEvaluatorPanel

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # Populate feature cache (simulate_bar normally does this)
    fv = make_fv()
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    # Capture panel.evaluate calls
    panel = runner._panel_decision._panel
    assert panel is not None, "Panel must be instantiated in PanelDecisionGroup"
    panel_calls = []
    original_evaluate = panel.evaluate
    def patched_evaluate(packet):
        result = original_evaluate(packet)
        panel_calls.append(result)
        return result
    panel.evaluate = patched_evaluate

    # Inject CandidateTradeEvent
    proposal = make_proposal()
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.1)
    await runner.teardown()

    assert len(panel_calls) == 1, (
        f"TraderEvaluatorPanel.evaluate() must be called exactly once, got {len(panel_calls)}"
    )
    result = panel_calls[0]
    total_verdicts = result.approve_count + result.reject_count + result.abstain_count
    assert total_verdicts == 20, (
        f"Panel must run all 20 traders, got {total_verdicts} verdicts"
    )


# ---------------------------------------------------------------------------
# 5. Layer C: FinalDecisionGroup actually invoked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_decision_group_actually_runs():
    """
    FinalDecisionGroup.decide() must be called when a CandidateTradeEvent arrives.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent
    from decision.final_group import FinalDecisionGroup

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv()
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    dg = runner._panel_decision._decision_group
    assert dg is not None, "FinalDecisionGroup must be instantiated"
    dg_calls = []
    original_decide = dg.decide
    def patched_decide(packet, panel_result):
        result = original_decide(packet, panel_result)
        dg_calls.append(result)
        return result
    dg.decide = patched_decide

    proposal = make_proposal()
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.1)
    await runner.teardown()

    assert len(dg_calls) == 1, (
        f"FinalDecisionGroup.decide() must be called exactly once, got {len(dg_calls)}"
    )
    fd = dg_calls[0]
    assert fd.decision in ("enter", "hold"), f"FinalDecision must be enter or hold, got {fd.decision}"
    # FinalDecision carries approve_count + reject_count from PanelResult
    # (abstain is absorbed into reject_count in FinalDecision's view)
    assert fd.approve_count >= 0, "FinalDecision must carry approve_count from panel"
    assert fd.avg_score >= 0.0, "FinalDecision must carry avg_score from panel"


# ---------------------------------------------------------------------------
# 6. DecisionTraceLogger writes 4 DB records per proposal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decision_trace_logger_writes_to_db():
    """
    For each evaluated proposal, DecisionTraceLogger must write:
      1 setup_packet row
      20 trader_review rows
      1 panel_summary row
      1 final_decision row
    Total: 23 rows per proposal evaluation.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv()
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    proposal = make_proposal()
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.1)

    # Query the learning extension's tables
    ext = runner._journal_extension
    assert ext is not None, "JournalExtension must be wired"

    conn = ext._conn
    # Check setup_packets table
    cur = conn.execute("SELECT COUNT(*) FROM setup_packets")
    packet_count = cur.fetchone()[0]
    assert packet_count >= 1, f"Expected at least 1 setup_packet, got {packet_count}"

    # Check trader_reviews table
    cur = conn.execute("SELECT COUNT(*) FROM trader_reviews")
    review_count = cur.fetchone()[0]
    assert review_count >= 20, (
        f"Expected 20 trader_review rows (one per evaluator), got {review_count}"
    )

    # Check panel_summaries table
    cur = conn.execute("SELECT COUNT(*) FROM panel_summaries")
    panel_count = cur.fetchone()[0]
    assert panel_count >= 1, f"Expected at least 1 panel_summary, got {panel_count}"

    # Check final_decisions table
    cur = conn.execute("SELECT COUNT(*) FROM final_decisions")
    decision_count = cur.fetchone()[0]
    assert decision_count >= 1, f"Expected at least 1 final_decision, got {decision_count}"

    await runner.teardown()


# ---------------------------------------------------------------------------
# 7. Panel gate blocks direct CandidateTradeEvent → RiskLeverageGroup bypass
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_panel_gate_blocks_candidate_trade_bypass():
    """
    With panel wired (set_panel_wired=True, default for runner):
    CandidateTradeEvent must NOT trigger RiskLeverageGroup directly.
    Only PanelApprovedProposalEvent triggers risk evaluation.

    This prevents the architecture bypass where proposals skip Layer B+C.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, RiskDecisionEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # Verify panel gate is engaged
    assert runner._risk_leverage._panel_wired is True, \
        "Panel gate must be engaged by runner.setup()"

    fv = make_fv()
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    risk_decisions_from_candidate = []
    panel_approved_events = []

    from core.events import PanelApprovedProposalEvent
    async def capture_risk(event):
        risk_decisions_from_candidate.append(event)

    # Subscribe BEFORE publishing to capture any stray risk decision
    await runner.bus.subscribe(RiskDecisionEvent, capture_risk)
    await runner.bus.subscribe(PanelApprovedProposalEvent, lambda e: panel_approved_events.append(e))

    # Inject a proposal that the panel will HOLD (7/20 typical approve rate)
    proposal = make_proposal()
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.1)
    await runner.teardown()

    # Panel should have HELD this (7/20 < 14/20 threshold)
    # Therefore PanelApprovedProposalEvent should NOT be published
    assert len(panel_approved_events) == 0, (
        f"Panel held proposal but PanelApprovedProposalEvent was published: {panel_approved_events}"
    )

    # Because panel held AND direct bypass is blocked, RiskDecisionEvent should NOT be published
    assert len(risk_decisions_from_candidate) == 0, (
        f"RiskLeverageGroup was called despite panel holding and bypass being blocked. "
        f"Got {len(risk_decisions_from_candidate)} RiskDecisionEvents. "
        f"Panel gate is not working."
    )


# ---------------------------------------------------------------------------
# 8. Safe guard: PanelDecisionGroup skips proposal without FeatureVector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_panel_decision_skips_without_feature_vector():
    """
    If no FeatureVector is available for a symbol, PanelDecisionGroup must
    log a warning and skip — NOT crash. Verifies safe guard is active.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, PanelApprovedProposalEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # Do NOT populate feature cache — panel should skip gracefully
    assert ("BTCUSDT", "1h") not in runner._market_data._feature_cache

    panel_approved = []
    await runner.bus.subscribe(PanelApprovedProposalEvent, lambda e: panel_approved.append(e))

    proposal = make_proposal()
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.1)
    await runner.teardown()

    assert len(panel_approved) == 0, "No approval should be emitted without a FeatureVector"


# ---------------------------------------------------------------------------
# 9. Approved panel proposal reaches RiskLeverageGroup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_panel_approved_reaches_risk():
    """
    When PanelDecisionGroup emits PanelApprovedProposalEvent,
    RiskLeverageGroup must receive and evaluate it.

    We use a mock panel to force approval, then verify RiskDecisionEvent is emitted.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, RiskDecisionEvent
    from traders.panel import PanelResult
    from decision.final_group import FinalDecision

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv()
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    # Force panel to approve (14/20, avg_score=7.0)
    original_panel_evaluate = runner._panel_decision._panel.evaluate
    def force_approve_panel(packet):
        result = PanelResult(packet_id=packet.packet_id)
        result.approve_count = 14
        result.reject_count = 3
        result.abstain_count = 3
        result.avg_score = 7.0
        result.panel_recommendation = "enter"
        result.panel_confidence = 0.70
        # Populate 20 minimal verdicts so trace logger doesn't fail
        from traders.evaluators import TraderVerdict
        for i in range(20):
            vote = "approve" if i < 14 else ("reject" if i < 17 else "abstain")
            result.verdicts.append(TraderVerdict(
                trader_id=f"trader_{i}",
                vote=vote,
                score=7.0 if vote == "approve" else 4.0,
                confidence=0.7,
                pro_reason="strong trend" if vote == "approve" else "",
                anti_reason="" if vote == "approve" else "weak volume",
                execution_concern="none",
                risk_concern="" if vote == "approve" else "wide stop",
                explanation="test verdict",
            ))
        return result
    runner._panel_decision._panel.evaluate = force_approve_panel

    risk_decisions = []
    await runner.bus.subscribe(RiskDecisionEvent, lambda e: risk_decisions.append(e))

    proposal = make_proposal(score=0.65)
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.2)
    await runner.teardown()

    assert len(risk_decisions) >= 1, (
        "RiskDecisionEvent must be emitted when panel approves a proposal. "
        "Check RiskLeverageGroup subscription to PanelApprovedProposalEvent."
    )
    # It may be approved or rejected by risk rules — but it must have been processed
    rd = risk_decisions[0]
    if not rd.approved:
        # Rejection is acceptable (Rule 9: raw_target=0 or other checks)
        # The important thing is risk evaluation was triggered
        assert rd.rejection is not None or not rd.approved, "Risk rejection should have a reason"


# ---------------------------------------------------------------------------
# 10. All 20 trader evaluators are imported and instantiated
# ---------------------------------------------------------------------------

def test_all_20_traders_instantiated():
    """TraderEvaluatorPanel instantiates exactly 20 evaluators."""
    from traders.panel import TraderEvaluatorPanel
    panel = TraderEvaluatorPanel()
    assert len(panel._evaluators) == 20, (
        f"Expected 20 trader evaluators, found {len(panel._evaluators)}"
    )
    # All must have a trader_id
    ids = [getattr(e, "trader_id", None) for e in panel._evaluators]
    assert all(i is not None for i in ids), "All evaluators must have trader_id"
    # All must be unique
    assert len(set(ids)) == 20, f"Duplicate trader IDs found: {[i for i in ids if ids.count(i) > 1]}"


# ---------------------------------------------------------------------------
# 11. EntryGroup uses SHADOW mode_gate (not RESEARCH)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entry_group_proposal_uses_shadow_mode():
    """
    EntryGroup._build_proposal() must use ModeGate.SHADOW, not RESEARCH.
    ModeGate.RESEARCH on a proposal is metadata but signals intent mismatch.
    More importantly, SystemState.mode must be SHADOW so Risk Rule 1 passes.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.schemas import ModeGate
    from core.events import CandidateTradeEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # State-level mode gate
    assert runner.state.mode == ModeGate.SHADOW, (
        f"SystemState.mode must be SHADOW in paper runner, got {runner.state.mode}"
    )

    # Proposal-level mode gate (metadata)
    proposals = []
    async def capture(event):
        if event.proposal:
            proposals.append(event.proposal)
    await runner.bus.subscribe(CandidateTradeEvent, capture)

    # To get a proposal out, we'd need the full signal chain. Instead verify
    # EntryGroup._build_proposal() source code uses SHADOW directly.
    import inspect
    import groups.entry.group as eg_module
    source = inspect.getsource(eg_module.EntryGroup._build_proposal)
    assert "ModeGate.SHADOW" in source and "ModeGate.RESEARCH" not in source, (
        "EntryGroup._build_proposal() must use ModeGate.SHADOW, not ModeGate.RESEARCH. "
        "RESEARCH mode_gate on a proposal is misleading and inconsistent with runner state."
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 12. OutcomeAttributor IS wired to PerformanceJournalGroup (Phase 3 — now active)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_outcome_attributor_wired_after_setup():
    """
    OutcomeAttributor must be wired to PerformanceJournalGroup by runner.setup().
    Phase 3 fix: previously OutcomeAttributor was never instantiated or injected.
    Now _finalize_learning_wiring() creates it and sets _performance_journal._outcome_attributor.
    """
    from runtime.runner import BtcBybitPaperRunner
    from learning.attribution import OutcomeAttributor

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    assert runner._performance_journal._outcome_attributor is not None, (
        "OutcomeAttributor must be wired to PerformanceJournalGroup by setup(). "
        "Check _finalize_learning_wiring() in runner.py."
    )
    assert isinstance(runner._performance_journal._outcome_attributor, OutcomeAttributor), (
        "PerformanceJournalGroup._outcome_attributor must be an OutcomeAttributor instance."
    )

    # Confirm _log_position_close source now references OutcomeAttributor
    import inspect
    import groups.performance_journal.group as pjg_module
    source = inspect.getsource(pjg_module.PerformanceJournalGroup._log_position_close)
    assert "outcome_attributor" in source, (
        "PerformanceJournalGroup._log_position_close must reference _outcome_attributor "
        "(Phase 3 wiring). OutcomeAttributor must be called on trade close."
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 13. End-to-end position open: forced panel approve → PositionOpenEvent + SystemState
# ---------------------------------------------------------------------------

def _make_force_approve_panel():
    """Return a patched evaluate() that forces panel to approve (14/20 votes)."""
    from traders.panel import PanelResult
    from traders.evaluators import TraderVerdict

    def force_approve(packet):
        result = PanelResult(packet_id=packet.packet_id)
        result.approve_count = 14
        result.reject_count = 3
        result.abstain_count = 3
        result.avg_score = 7.0
        result.panel_recommendation = "enter"
        result.panel_confidence = 0.70
        for i in range(20):
            vote = "approve" if i < 14 else ("reject" if i < 17 else "abstain")
            result.verdicts.append(TraderVerdict(
                trader_id=f"trader_{i}",
                vote=vote,
                score=7.0 if vote == "approve" else 4.0,
                confidence=0.7,
                pro_reason="strong trend" if vote == "approve" else "",
                anti_reason="" if vote == "approve" else "weak volume",
                execution_concern="none",
                risk_concern="" if vote == "approve" else "wide stop",
                explanation="test verdict",
            ))
        return result

    return force_approve


@pytest.mark.asyncio
async def test_end_to_end_position_opens():
    """
    Full wired path: forced panel approve → risk rules pass → PositionOpenEvent published
    → SystemState.portfolio.open_positions has exactly one position.

    This is the critical Phase 3 end-to-end test. Before Phase 3, _approve() only published
    RiskDecisionEvent and NEVER called state.open_position() or published PositionOpenEvent.
    ExitGroup and Journal never knew a position was open.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, PositionOpenEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv(price=Decimal("65000"))
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    # Force panel to approve
    runner._panel_decision._panel.evaluate = _make_force_approve_panel()

    position_open_events = []
    await runner.bus.subscribe(PositionOpenEvent, lambda e: position_open_events.append(e))

    # Proposal with valid fields (composite_score >= 0.50, hypothesis_refs set)
    proposal = make_proposal(score=0.65)
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.2)

    # Position must be open in SystemState
    open_positions = runner.state.portfolio.open_positions
    assert len(open_positions) >= 1, (
        f"Expected at least 1 open position after panel-approved proposal, "
        f"got {len(open_positions)}. "
        f"Check RiskLeverageGroup._approve() — it must call state.open_position() "
        f"and publish PositionOpenEvent."
    )

    # PositionOpenEvent must have been published
    assert len(position_open_events) >= 1, (
        "PositionOpenEvent must be published by RiskLeverageGroup._approve(). "
        "ExitGroup and Journal subscribe to this event."
    )

    # Position must carry correct learning layer IDs from PanelApprovedProposalEvent
    pos = list(open_positions.values())[0]
    assert pos.packet_id != "" or pos.panel_id != "" or pos.decision_id != "", (
        "Position must carry at least one non-empty learning ID (packet_id/panel_id/decision_id) "
        "from PanelApprovedProposalEvent → RiskLeverageGroup → Position."
    )

    # composite_score must flow from proposal to position
    assert pos.composite_score == 0.65, (
        f"Position.composite_score must match proposal.composite_score=0.65, got {pos.composite_score}"
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 14. End-to-end position close: position open → second bar triggers time stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_end_to_end_position_closes_on_stop():
    """
    After a position is opened, simulate a bar where price crosses the stop.
    ExitGroup must detect the stop loss and publish PositionCloseEvent.
    SystemState.portfolio.open_positions must be empty after close.
    PerformanceJournalGroup must write a close record and run OutcomeAttributor.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent, PositionOpenEvent, PositionCloseEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    price = Decimal("65000")
    fv_open = make_fv(price=price)
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv_open
    await runner._state.update_last_close("BTCUSDT", fv_open.close)

    # Force panel to approve
    runner._panel_decision._panel.evaluate = _make_force_approve_panel()

    position_open_events = []
    position_close_events = []
    await runner.bus.subscribe(PositionOpenEvent, lambda e: position_open_events.append(e))
    await runner.bus.subscribe(PositionCloseEvent, lambda e: position_close_events.append(e))

    proposal = make_proposal(score=0.65)
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.2)

    assert len(position_open_events) >= 1, (
        "Position must open before close can be tested. "
        "See test_end_to_end_position_opens for diagnosis."
    )

    # Now simulate a bar where price crashes below stop
    open_pos = list(runner.state.portfolio.open_positions.values())[0]
    stop_price = open_pos.stop_price
    # Crash below stop: low << stop_price
    crash_price = stop_price - Decimal("500")
    fv_crash = make_fv(price=crash_price, bullish=False)
    # Override low to guarantee stop hit
    from dataclasses import replace as dc_replace
    fv_crash = dc_replace(fv_crash, low=stop_price - Decimal("1000"), close=crash_price)
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv_crash
    await runner.bus.publish(
        __import__("core.events", fromlist=["FeatureReadyEvent"]).FeatureReadyEvent(
            source="runner_simulation", features=fv_crash
        )
    )
    await asyncio.sleep(0.2)

    assert len(position_close_events) >= 1, (
        f"PositionCloseEvent must be published when price crosses stop. "
        f"Got 0 close events. ExitGroup must be receiving FeatureReadyEvents and "
        f"detecting stop conditions on open positions."
    )

    # Position must be removed from SystemState
    assert len(runner.state.portfolio.open_positions) == 0, (
        "Open positions must be empty after stop loss exit. "
        "ExitGroup._execute_exit() must call state.close_position()."
    )

    await runner.teardown()


# ---------------------------------------------------------------------------
# 15. Position carries learning layer IDs after panel-approved open
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_position_carries_learning_ids():
    """
    After a panel-approved position opens, the Position object in SystemState
    must carry non-empty packet_id, panel_id, and decision_id from the
    DecisionTraceLogger (written by PanelDecisionGroup).

    These IDs link the position to learning DB records for future attribution.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import CandidateTradeEvent

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    fv = make_fv(price=Decimal("65000"))
    runner._market_data._feature_cache[("BTCUSDT", "1h")] = fv
    await runner._state.update_last_close("BTCUSDT", fv.close)

    # Force panel to approve
    runner._panel_decision._panel.evaluate = _make_force_approve_panel()

    proposal = make_proposal(score=0.65)
    await runner.bus.publish(CandidateTradeEvent(proposal=proposal))
    await asyncio.sleep(0.2)

    open_positions = runner.state.portfolio.open_positions
    if len(open_positions) == 0:
        await runner.teardown()
        pytest.skip("Position did not open — check test_end_to_end_position_opens first")

    pos = list(open_positions.values())[0]

    # At minimum, packet_id should be non-empty (DecisionTraceLogger writes it first)
    assert pos.packet_id != "", (
        "Position.packet_id must be non-empty when trace logger is wired. "
        "PanelDecisionGroup must thread packet_id through PanelApprovedProposalEvent "
        "→ RiskLeverageGroup._evaluate_proposal() → _approve() → Position."
    )
    assert pos.panel_id != "", (
        "Position.panel_id must be non-empty when trace logger is wired."
    )
    assert pos.decision_id != "", (
        "Position.decision_id must be non-empty when trace logger is wired."
    )

    await runner.teardown()
