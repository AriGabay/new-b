"""
Risk rule implementations: portfolio exposure, drawdown, leverage, pump detection.

These are standalone stateless/stateful check classes used by:
  - RiskLeverageGroup (live path)
  - Backtest engine (replay path)

All checks return RiskCheckResult (approved=True/False with code and detail).

Source: /docs/risk_framework/risk_contract.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from core.schemas import CandidateTradeProposal, RejectionCode, RiskCheckResult

logger = logging.getLogger(__name__)

# Correlation cluster taxonomy
# Assign each asset to ONE cluster for correlated exposure tracking.
# Clusters: "btc", "eth", "alt_l1", "defi", "meme", "stablecoin"
CORRELATION_CLUSTERS: dict[str, str] = {
    "BTCUSDT": "btc",
    "BTCBUSD": "btc",
    "ETHUSDT": "eth",
    "ETHBUSD": "eth",
    "BNBUSDT": "alt_l1",
    "SOLUSDT": "alt_l1",
    "AVAXUSDT": "alt_l1",
    "ADAUSDT": "alt_l1",
    "UNIUSDT": "defi",
    "AAVEUSDT": "defi",
    "DOGEUSDT": "meme",
    "SHIBUSDT": "meme",
}

MAX_PORTFOLIO_EXPOSURE_PCT  = Decimal("0.25")   # 25% total
MAX_CLUSTER_EXPOSURE_PCT    = Decimal("0.15")   # 15% per cluster
MAX_LEVERAGE                = 35.0
PUMP_VOLUME_RATIO_THRESHOLD = 5.0
PUMP_LOOKBACK_BARS          = 3


def get_correlation_cluster(symbol: str) -> str:
    """Return cluster name for a symbol. Defaults to 'alt_l1' if unknown."""
    return CORRELATION_CLUSTERS.get(symbol, "alt_l1")


class PortfolioExposureChecker:
    """
    Rule 4: Total portfolio exposure ≤ 25% of equity.
    Rule 5: Per-cluster exposure ≤ 15% of equity.
    """

    def check(
        self,
        proposal: CandidateTradeProposal,
        open_positions: dict,
        equity: Decimal,
        proposed_size_usd: Decimal,
    ) -> RiskCheckResult:
        """
        Check both total and cluster exposure limits.
        Returns first failure or approved.
        """
        raise NotImplementedError("PortfolioExposureChecker.check() — Phase 2 implementation pending")

    def _total_exposure(self, open_positions: dict) -> Decimal:
        """Sum position_size_usd across all open positions."""
        raise NotImplementedError("Phase 2 pending")

    def _cluster_exposure(self, open_positions: dict, cluster: str) -> Decimal:
        """Sum position_size_usd for all positions in the given cluster."""
        raise NotImplementedError("Phase 2 pending")


class DrawdownController:
    """
    Rule 3 / ongoing: Monitor drawdown and apply size reduction ladder.

    Drawdown ladder:
      0-5%:   size_reduction = 1.0 (full size)
      5-10%:  size_reduction = 0.75 (75% size)
      >10%:   HALT — no new entries (RiskState.halted = True)

    This class computes the appropriate size_reduction given current drawdown.
    The actual halt is enforced in RiskLeverageGroup._check_max_drawdown().
    """

    def get_size_reduction(self, drawdown_pct: float) -> float:
        """Return size reduction multiplier based on current drawdown."""
        if drawdown_pct > 0.10:
            return 0.0   # Halted
        elif drawdown_pct > 0.05:
            return 0.75
        else:
            return 1.0


class LeverageGovernor:
    """
    Rule: Hard cap on leverage.

    Leverage range: 5×–35× (perpetual futures model).
    Leverage is determined by RiskLeverageGroup._compute_leverage()
    based on setup quality, volatility, and drawdown.

    If leverage > MAX_LEVERAGE: reject.
    If mode is RESEARCH: leverage forced to 1.0.
    """

    def check(self, leverage: float, mode: str) -> RiskCheckResult:
        if mode == "research":
            return RiskCheckResult.approved_ok()   # Research mode: no execution anyway
        if leverage > MAX_LEVERAGE:
            return RiskCheckResult.rejected(
                RejectionCode.INCOMPLETE_TRADE_PLAN,
                f"Leverage {leverage:.1f}× exceeds max {MAX_LEVERAGE:.1f}×.",
            )
        return RiskCheckResult.approved_ok()


class PumpDetector:
    """
    Rule 7: Block entries when pump signal detected.

    Pump detection criteria:
      volume_ratio > PUMP_VOLUME_RATIO_THRESHOLD (5.0×) on any of last PUMP_LOOKBACK_BARS bars.
      AND price moved > 10% in same window (optional additional filter).

    Returns True if pump signal active.
    """

    def is_pump_active(self, feature_history: list) -> bool:
        """
        feature_history: list of FeatureVector, newest first.
        Check last PUMP_LOOKBACK_BARS entries for pump conditions.
        """
        raise NotImplementedError("PumpDetector.is_pump_active() — Phase 2 implementation pending")
