"""
Regression guard for walk-forward optimization.

Before accepting any parameter change, the guard runs the locked baseline
fixtures through the pipeline with the proposed parameters and verifies
that no fixture regresses beyond acceptable thresholds.

Regression rules:
  - Fixtures that currently ENTER (14/20+) must still ENTER.
  - Fixtures that currently HOLD (<14/20) must NOT spuriously ENTER.
  - Best approve_count may not drop by more than 1 from baseline.
  - No fixture may produce new errors.

The guard uses the same RuntimeReplayHarness as the walk-forward runner,
with parameter overrides applied.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.schemas import FeatureVector

logger = logging.getLogger(__name__)


# Baseline fixture expectations (from Phase 7 baseline lock)
# Format: fixture_id → (must_enter: bool, min_approve_count: int, description)
BASELINE_EXPECTATIONS: dict[str, tuple[bool, int, str]] = {
    "btc_bull_breakout_v1":              (False, 9,  "Crossover bars — should HOLD"),
    "btc_bear_breakdown_v1":             (False, 9,  "Bear crossover — should HOLD"),
    "btc_ranging_v1":                    (False, 9,  "Sideways — should HOLD"),
    "btc_bull_continuation_pullback_v1": (True,  14, "Pullback in uptrend — should ENTER"),
    "btc_bear_continuation_pullback_v1": (False, 11, "Pullback in downtrend — should HOLD"),
    "btc_long_established_trend_v1":     (False, 13, "Mature trend near-miss — should HOLD"),
    "btc_w_bottom_long_v1":              (False, 13, "W-bottom near-miss — should HOLD"),
    "btc_m_top_short_v1":                (False, 13, "M-top near-miss — should HOLD"),
    "btc_triple_touch_long_v1":          (False, 13, "Triple touch near-miss — should HOLD"),
    "btc_w_bottom_long_v2":              (True,  14, "W-bottom V2 — should ENTER"),
    "btc_double_bottom_long_v1":         (True,  16, "Double bottom — should ENTER (strong)"),
}


@dataclass
class FixtureCheckResult:
    """Result of checking one fixture against baseline."""
    fixture_id: str
    passed: bool
    expected_enter: bool
    actual_enter: bool
    best_approve_count: int
    min_approve_count: int
    errors: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RegressionResult:
    """Result of the full regression guard check."""
    passed: bool
    fixtures_checked: int
    fixtures_passed: int
    fixtures_failed: int
    results: list[FixtureCheckResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "fixtures_checked": self.fixtures_checked,
            "fixtures_passed": self.fixtures_passed,
            "fixtures_failed": self.fixtures_failed,
            "results": [
                {
                    "fixture_id": r.fixture_id,
                    "passed": r.passed,
                    "expected_enter": r.expected_enter,
                    "actual_enter": r.actual_enter,
                    "best_approve_count": r.best_approve_count,
                    "reason": r.reason,
                }
                for r in self.results
            ],
            "skipped": self.skipped,
        }


async def run_regression_guard(
    param_overrides: Optional[dict] = None,
    fixture_ids: Optional[list[str]] = None,
) -> RegressionResult:
    """
    Run baseline fixtures through the pipeline and check for regressions.

    Args:
        param_overrides: Parameter values to override (from optimization trial).
                         If None, uses current production values.
        fixture_ids: Subset of fixtures to check. If None, checks all.

    Returns:
        RegressionResult with pass/fail for each fixture.
    """
    from console.replay_manager import _FIXTURE_BUILDERS

    ids_to_check = fixture_ids or list(BASELINE_EXPECTATIONS.keys())
    results: list[FixtureCheckResult] = []
    skipped: list[str] = []

    for fid in ids_to_check:
        if fid not in BASELINE_EXPECTATIONS:
            skipped.append(fid)
            logger.warning("regression_guard: unknown fixture_id '%s', skipping", fid)
            continue

        builder = _FIXTURE_BUILDERS.get(fid)
        if builder is None:
            skipped.append(fid)
            logger.warning("regression_guard: no builder for '%s', skipping", fid)
            continue

        try:
            fixture = builder()
            check = await _check_fixture(fid, fixture.feature_vectors, param_overrides)
            results.append(check)
        except Exception as e:
            results.append(FixtureCheckResult(
                fixture_id=fid,
                passed=False,
                expected_enter=BASELINE_EXPECTATIONS[fid][0],
                actual_enter=False,
                best_approve_count=0,
                min_approve_count=BASELINE_EXPECTATIONS[fid][1],
                errors=[str(e)],
                reason=f"Exception during check: {e}",
            ))

    passed_count = sum(1 for r in results if r.passed)
    failed_count = sum(1 for r in results if not r.passed)
    all_passed = failed_count == 0

    if not all_passed:
        failed_names = [r.fixture_id for r in results if not r.passed]
        logger.error(
            "regression_guard: FAILED — %d fixtures regressed: %s",
            failed_count, failed_names,
        )
    else:
        logger.info(
            "regression_guard: PASSED — %d/%d fixtures OK",
            passed_count, len(results),
        )

    return RegressionResult(
        passed=all_passed,
        fixtures_checked=len(results),
        fixtures_passed=passed_count,
        fixtures_failed=failed_count,
        results=results,
        skipped=skipped,
    )


async def _check_fixture(
    fixture_id: str,
    feature_vectors: list[FeatureVector],
    param_overrides: Optional[dict],
) -> FixtureCheckResult:
    """
    Run one fixture through the pipeline and verify against baseline.

    This creates a fresh runner, applies parameter overrides, feeds
    all FeatureVectors through, and checks the outcome.
    """
    from runtime.runner import BtcBybitPaperRunner
    from core.events import (
        CandidateTradeEvent,
        PanelApprovedProposalEvent,
        PositionOpenEvent,
    )

    must_enter, min_approve, description = BASELINE_EXPECTATIONS[fixture_id]
    errors: list[str] = []

    runner = BtcBybitPaperRunner(simulation_mode=True, journal_db_path=":memory:")
    await runner.setup()

    # Apply parameter overrides
    if param_overrides:
        _apply_overrides(runner, param_overrides)

    # Capture events
    approved_events = []
    position_opens = []

    original_publish = runner.bus.publish

    async def capture_publish(event):
        if isinstance(event, PanelApprovedProposalEvent):
            approved_events.append(event)
        elif isinstance(event, PositionOpenEvent):
            position_opens.append(event)
        return await original_publish(event)

    runner.bus.publish = capture_publish

    try:
        for fv in feature_vectors:
            await runner.simulate_bar(fv)
            await asyncio.sleep(0)
    except Exception as e:
        errors.append(f"Runtime error: {e}")
    finally:
        try:
            await runner.teardown()
        except Exception:
            pass

    actual_enter = len(position_opens) > 0
    best_approve = 0
    for ev in approved_events:
        ac = getattr(ev, "approve_count", 0)
        if ac > best_approve:
            best_approve = ac

    # Check regression rules
    passed = True
    reason_parts = []

    if must_enter and not actual_enter:
        passed = False
        reason_parts.append(f"Expected ENTER but got HOLD")

    if not must_enter and actual_enter:
        passed = False
        reason_parts.append(f"Expected HOLD but got spurious ENTER")

    if best_approve < min_approve - 1:
        passed = False
        reason_parts.append(
            f"approve_count {best_approve} dropped >1 below baseline {min_approve}"
        )

    if errors:
        passed = False
        reason_parts.append(f"Errors: {errors}")

    reason = "; ".join(reason_parts) if reason_parts else "OK"

    return FixtureCheckResult(
        fixture_id=fixture_id,
        passed=passed,
        expected_enter=must_enter,
        actual_enter=actual_enter,
        best_approve_count=best_approve,
        min_approve_count=min_approve,
        errors=errors,
        reason=reason,
    )


def _apply_overrides(runner, overrides: dict) -> None:
    """
    Apply parameter overrides to a live runner instance.

    Reaches into the runner's group instances and modifies their
    configuration attributes. This is the bridge between the parameter
    space and the runtime.

    Supported overrides (module-level constants):
      - Entry weights/thresholds: groups.entry.group module globals
      - Risk params: groups.risk_leverage.group module globals
      - Leverage params: groups.risk_leverage.group module globals
      - Exit time stop: groups.exit.group module globals
      - ATR stop: risk.sizing module globals

    Class-level overrides (via runner group instances):
      - Panel thresholds: TraderEvaluatorPanel class attributes

    NOT YET OVERRIDABLE (inline hardcoded values):
      - Safety rails in FinalDecisionGroup.decide() (5.0, 12, 1.5)
      - Exit trailing stop multiplier (hardcoded `2 * features.atr14`)
      These require a small refactor to extract into module-level constants.
    """
    import groups.entry.group as entry_mod
    import groups.exit.group as exit_mod
    import groups.risk_leverage.group as risk_mod
    import risk.sizing as sizing_mod
    from decimal import Decimal

    for name, value in overrides.items():
        # --- Entry weights (module-level dict) ---
        if name == "indicator_weight":
            entry_mod._ACTIVE_SCORE_COMPONENTS["indicator"] = value
        elif name == "candlestick_weight":
            entry_mod._ACTIVE_SCORE_COMPONENTS["candlestick"] = value
        elif name == "structural_weight":
            entry_mod._ACTIVE_SCORE_COMPONENTS["structural"] = value

        # --- Entry thresholds (module-level constants) ---
        elif name == "composite_score_threshold":
            entry_mod.COMPOSITE_SCORE_THRESHOLD = value
        elif name == "confirmation_gate_min_groups":
            entry_mod.CONFIRMATION_GATE_MIN_GROUPS = value

        # --- Panel thresholds (class-level on TraderEvaluatorPanel) ---
        elif name == "panel_approve_threshold":
            # Override on the panel instance within PanelDecisionGroup
            panel_group = _find_group(runner, "PanelDecisionGroup")
            if panel_group and hasattr(panel_group, "_panel"):
                panel_group._panel.APPROVE_THRESHOLD = int(value)
        elif name == "panel_min_avg_score":
            panel_group = _find_group(runner, "PanelDecisionGroup")
            if panel_group and hasattr(panel_group, "_panel"):
                panel_group._panel.MIN_AVG_SCORE = float(value)
                panel_group._panel.AVG_SCORE_THRESHOLD = float(value)

        # --- Risk parameters (module-level constants) ---
        elif name == "risk_fraction":
            risk_mod.DEFAULT_RISK_FRACTION = Decimal(str(value))
            sizing_mod.DEFAULT_RISK_FRACTION = Decimal(str(value))
        elif name == "daily_loss_limit":
            risk_mod.DAILY_LOSS_LIMIT = value

        # --- Leverage parameters (module-level constants) ---
        elif name == "min_leverage":
            risk_mod.MIN_LEVERAGE = float(value)
        elif name == "max_risk_per_trade":
            risk_mod.MAX_RISK_PER_TRADE = float(value)
        elif name == "max_drawdown_halt":
            risk_mod.MAX_DRAWDOWN_HALT = float(value)

        # --- Time stop (module-level constants in exit + risk_leverage) ---
        elif name == "time_stop_bars":
            exit_mod.MAX_BARS_TO_HOLD = int(value)
            risk_mod.DEFAULT_MAX_BARS = int(value)

        # --- ATR stop placement (module-level constant) ---
        elif name == "atr_stop_multiplier":
            sizing_mod.ATR_STOP_MULTIPLIER = Decimal(str(value))

        # --- Not yet overridable (logged as warning) ---
        elif name in ("safety_avg_score_floor", "safety_reject_ceiling",
                       "safety_min_rr_ratio", "trailing_stop_atr_mult"):
            logger.debug(
                "regression_guard: override '%s' not yet supported "
                "(requires inline constant extraction)", name
            )
        else:
            logger.warning("regression_guard: unknown override '%s'", name)


def _find_group(runner, group_class_name: str):
    """Find a group instance in the runner by class name."""
    for group in getattr(runner, "_groups", []):
        if type(group).__name__ == group_class_name:
            return group
    return None


def _save_module_state() -> dict:
    """Capture current module-level constants so they can be restored."""
    import groups.entry.group as entry_mod
    import groups.exit.group as exit_mod
    import groups.risk_leverage.group as risk_mod
    import risk.sizing as sizing_mod

    return {
        "entry_components": dict(entry_mod._ACTIVE_SCORE_COMPONENTS),
        "composite_threshold": entry_mod.COMPOSITE_SCORE_THRESHOLD,
        "confirmation_gate": entry_mod.CONFIRMATION_GATE_MIN_GROUPS,
        "risk_fraction": risk_mod.DEFAULT_RISK_FRACTION,
        "daily_loss_limit": risk_mod.DAILY_LOSS_LIMIT,
        "min_leverage": risk_mod.MIN_LEVERAGE,
        "max_risk_per_trade": risk_mod.MAX_RISK_PER_TRADE,
        "max_drawdown_halt": risk_mod.MAX_DRAWDOWN_HALT,
        "default_max_bars": risk_mod.DEFAULT_MAX_BARS,
        "max_bars_to_hold": exit_mod.MAX_BARS_TO_HOLD,
        "atr_stop_mult": sizing_mod.ATR_STOP_MULTIPLIER,
        "sizing_risk_fraction": sizing_mod.DEFAULT_RISK_FRACTION,
    }


def _restore_module_state(state: dict) -> None:
    """Restore module-level constants from saved state."""
    import groups.entry.group as entry_mod
    import groups.exit.group as exit_mod
    import groups.risk_leverage.group as risk_mod
    import risk.sizing as sizing_mod

    entry_mod._ACTIVE_SCORE_COMPONENTS.update(state["entry_components"])
    entry_mod.COMPOSITE_SCORE_THRESHOLD = state["composite_threshold"]
    entry_mod.CONFIRMATION_GATE_MIN_GROUPS = state["confirmation_gate"]
    risk_mod.DEFAULT_RISK_FRACTION = state["risk_fraction"]
    risk_mod.DAILY_LOSS_LIMIT = state["daily_loss_limit"]
    risk_mod.MIN_LEVERAGE = state["min_leverage"]
    risk_mod.MAX_RISK_PER_TRADE = state["max_risk_per_trade"]
    risk_mod.MAX_DRAWDOWN_HALT = state["max_drawdown_halt"]
    risk_mod.DEFAULT_MAX_BARS = state["default_max_bars"]
    exit_mod.MAX_BARS_TO_HOLD = state["max_bars_to_hold"]
    sizing_mod.ATR_STOP_MULTIPLIER = state["atr_stop_mult"]
    sizing_mod.DEFAULT_RISK_FRACTION = state["sizing_risk_fraction"]
