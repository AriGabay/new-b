"""
Risk engine components.

The risk engine applies 9 deterministic rules to every CandidateTradeProposal.
These rules are also used directly in the RiskLeverageGroup.
They are extracted here as standalone classes for unit testing and backtest use.

Source: /docs/risk_framework/risk_contract.md
"""
from .sizing import RMultipleSizer, ATRStopPlacer
from .checks import (
    PortfolioExposureChecker,
    DrawdownController,
    LeverageGovernor,
    PumpDetector,
)

__all__ = [
    "RMultipleSizer",
    "ATRStopPlacer",
    "PortfolioExposureChecker",
    "DrawdownController",
    "LeverageGovernor",
    "PumpDetector",
]
