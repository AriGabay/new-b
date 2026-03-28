"""
SourceEnforcer — enforces source-of-outcome separation across all validation artifacts.

CRITICAL POLICY (mirrors learning/outcome_source.py):
  Never silently mix validation sources.
  Never compute aggregate metrics across incompatible sources.
  Every report must carry an explicit validation_source field.
  Forced-approval (synthetic_control_scenarios) must never contaminate
  event_driven_runtime_replay findings.

Usage:
    enforcer = SourceEnforcer()
    enforcer.assert_single_source(["event_driven_runtime_replay"] * n)
    enforcer.assert_not_edge_evidence("synthetic_control_scenarios")
    enforcer.validate_report(report_dict, expected="event_driven_runtime_replay")
"""
from __future__ import annotations

from validation import VALIDATION_SOURCES, EDGE_EVIDENCE_SOURCES


class SourceSeparationError(Exception):
    """Raised when sources are illegally mixed."""


class SourceEnforcer:
    """
    Validates source tagging across all validation artifacts.
    Stateless — all methods are pure functions wrapped in a class for
    testability and explicit import.
    """

    @staticmethod
    def assert_single_source(sources: list[str]) -> str:
        """
        Raise SourceSeparationError if multiple sources present.
        Returns the single source value.
        """
        unique = set(sources)
        if not unique:
            raise SourceSeparationError("Empty source list.")
        if len(unique) > 1:
            raise SourceSeparationError(
                f"Source mixing violation: found {unique}. "
                "Segment results by source before computing metrics."
            )
        src = unique.pop()
        SourceEnforcer._assert_known_source(src)
        return src

    @staticmethod
    def assert_not_mixed(sources: list[str]) -> None:
        """Assert no incompatible mixing: runtime never mixed with simplified_backtest."""
        unique = set(sources)
        runtime = {"event_driven_runtime_replay", "event_driven_runtime_simulation", "live_exchange_fed_paper"}
        backtest = {"simplified_backtest"}
        synthetic = {"synthetic_control_scenarios"}
        has_runtime = bool(unique & runtime)
        has_backtest = bool(unique & backtest)
        has_synthetic = bool(unique & synthetic)
        if has_runtime and has_backtest:
            raise SourceSeparationError(
                f"Cannot mix runtime sources {unique & runtime} with "
                f"simplified_backtest sources. They use different signal logic."
            )
        if has_runtime and has_synthetic:
            raise SourceSeparationError(
                f"Cannot mix runtime sources {unique & runtime} with "
                f"synthetic_control_scenarios. Forced-approval data must stay separate."
            )

    @staticmethod
    def assert_not_edge_evidence(source: str, claim: str = "edge") -> None:
        """
        Raise SourceSeparationError if source is not in EDGE_EVIDENCE_SOURCES
        and caller is making an edge claim.
        """
        if source not in EDGE_EVIDENCE_SOURCES:
            raise SourceSeparationError(
                f"Source '{source}' is NOT in EDGE_EVIDENCE_SOURCES {EDGE_EVIDENCE_SOURCES}. "
                f"Cannot make {claim!r} claim from this source. "
                "Use event_driven_runtime_replay or live_exchange_fed_paper only."
            )

    @staticmethod
    def validate_report(report: dict, expected_source: str) -> None:
        """
        Validate that a report dict carries the expected validation_source field.
        Raises SourceSeparationError if missing or mismatched.
        """
        if "validation_source" not in report:
            raise SourceSeparationError(
                f"Report missing 'validation_source' field. "
                "All validation reports must carry an explicit source tag."
            )
        actual = report["validation_source"]
        if actual != expected_source:
            raise SourceSeparationError(
                f"Report source mismatch: expected {expected_source!r}, got {actual!r}."
            )
        SourceEnforcer._assert_known_source(actual)

    @staticmethod
    def _assert_known_source(source: str) -> None:
        if source not in VALIDATION_SOURCES:
            raise SourceSeparationError(
                f"Unknown validation source: {source!r}. "
                f"Valid sources: {sorted(VALIDATION_SOURCES)}"
            )

    @staticmethod
    def source_summary(sources: list[str]) -> dict:
        """
        Returns a breakdown of how many records came from each source.
        For use in reports to prove no silent mixing.
        """
        counts: dict[str, int] = {}
        for s in sources:
            counts[s] = counts.get(s, 0) + 1
        return {
            "source_breakdown": counts,
            "total_records": len(sources),
            "is_single_source": len(set(sources)) <= 1,
            "has_mixing_risk": len(set(sources)) > 1,
        }
