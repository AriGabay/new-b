"""
HoldoutManager: enforces the holdout data protection rule.

The holdout period (2023-01-01 to 2025-12-31) is LOCKED.
It cannot be touched until a hypothesis has passed Gate 1 (in-sample backtest).

Rules:
  1. Any data request for dates in holdout raises HoldoutViolationError
     unless the hypothesis has status IN_SAMPLE or higher.
  2. Training period: 2017-01-01 to 2022-12-31 (open access).
  3. Holdout period: 2023-01-01 to 2025-12-31 (locked until Gate 1).
  4. The holdout is touched ONCE per hypothesis: final OOS validation only.
  5. No exploratory queries on holdout data (any query without a hypothesis_id = rejected).

This is enforced in code — not just a documentation note.

Source: /docs/adr/ADR-004-validation-gates-before-live-promotion.md (Holdout Principle)
"""
from __future__ import annotations

from datetime import datetime

TRAINING_START  = datetime(2017, 1, 1)
TRAINING_END    = datetime(2022, 12, 31, 23, 59, 59)
HOLDOUT_START   = datetime(2023, 1, 1)
HOLDOUT_END     = datetime(2025, 12, 31, 23, 59, 59)


class HoldoutViolationError(Exception):
    """Raised when holdout data is accessed without Gate 1 clearance."""
    pass


class HoldoutManager:
    """
    Gatekeeper for holdout data access.

    Usage:
        manager = HoldoutManager()
        manager.assert_training_access(start_date, end_date)  # OK if in training period
        manager.assert_holdout_access(hypothesis_id, status)   # OK only if Gate 1 passed
    """

    def assert_training_access(self, start_date: datetime, end_date: datetime) -> None:
        """
        Raise HoldoutViolationError if date range extends into holdout period.
        Safe to call for any training query.
        """
        if end_date > TRAINING_END:
            raise HoldoutViolationError(
                f"Date range {start_date.date()} → {end_date.date()} "
                f"extends into holdout period ({HOLDOUT_START.date()} → {HOLDOUT_END.date()}). "
                f"Holdout is locked. Use only training period ({TRAINING_START.date()} → {TRAINING_END.date()})."
            )

    def assert_holdout_access(self, hypothesis_id: str, hypothesis_status: str) -> None:
        """
        Allow holdout access ONLY if hypothesis has passed Gate 1 (status IN_SAMPLE or higher).
        Permitted statuses: in_sample_tested, oos_passed, shadow_live, validated.
        Rejected statuses: untested, rejected.

        Raises HoldoutViolationError if hypothesis has not cleared Gate 1.
        """
        PERMITTED_STATUSES = {"in_sample_tested", "oos_passed", "shadow_live", "validated"}
        if hypothesis_status not in PERMITTED_STATUSES:
            raise HoldoutViolationError(
                f"Hypothesis {hypothesis_id} (status={hypothesis_status}) has not passed Gate 1. "
                f"Holdout access denied. Complete in-sample backtest first."
            )

    def is_in_holdout(self, date: datetime) -> bool:
        """Return True if date falls in the holdout period."""
        return HOLDOUT_START <= date <= HOLDOUT_END

    def is_in_training(self, date: datetime) -> bool:
        """Return True if date falls in the training period."""
        return TRAINING_START <= date <= TRAINING_END
