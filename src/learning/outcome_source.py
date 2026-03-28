"""
OutcomeSource: mandatory tagging for all learning data.

CRITICAL POLICY: Calibration, attribution, and learning conclusions MUST
be segmented by outcome_source. Never aggregate across incompatible sources.

Sources:
  event_driven_runtime    — live paper/sim execution via full group pipeline
  simplified_backtest     — BacktestEngine EMA-crossover replay (NOT full pipeline)
  synthetic_data          — generated/injected data for testing
  live_exchange_fed       — live Bybit execution (Phase 5+, not yet enabled)
"""
from __future__ import annotations
from enum import Enum


class OutcomeSource(str, Enum):
    EVENT_DRIVEN_RUNTIME = "event_driven_runtime"
    SIMPLIFIED_BACKTEST  = "simplified_backtest"
    SYNTHETIC_DATA       = "synthetic_data"
    LIVE_EXCHANGE_FED    = "live_exchange_fed"

    def is_live(self) -> bool:
        return self == OutcomeSource.LIVE_EXCHANGE_FED

    def is_validated_source(self) -> bool:
        """
        Only event_driven_runtime and live_exchange_fed produce outcomes
        that come from real signal evaluation. Backtest uses simplified
        EMA-crossover only; synthetic data is fabricated.
        """
        return self in (
            OutcomeSource.EVENT_DRIVEN_RUNTIME,
            OutcomeSource.LIVE_EXCHANGE_FED,
        )


def assert_single_source(sources: list[OutcomeSource]) -> OutcomeSource:
    """
    Raise ValueError if outcomes from multiple sources are being mixed.
    Always call this before computing calibration metrics.
    """
    unique = set(sources)
    if len(unique) > 1:
        raise ValueError(
            f"OutcomeSource mixing violation: found {unique}. "
            "Segment by source before computing metrics."
        )
    if not unique:
        raise ValueError("Empty source list.")
    return unique.pop()
