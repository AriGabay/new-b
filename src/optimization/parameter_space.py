"""
Parameter space definition for walk-forward optimization.

Defines every tunable parameter in the BTC/Bybit trading pipeline
with its current value, min/max bounds, step size, and the code
location where it takes effect.

Parameter categories:
  1. Entry composite weights (EntryGroup)
  2. Entry thresholds (EntryGroup)
  3. Panel thresholds (TraderEvaluatorPanel)
  4. Safety rails (FinalDecisionGroup)
  5. Risk parameters (RiskLeverageGroup)
  6. Stop placement (ATRStopPlacer)
  7. Exit parameters (ExitGroup)

The grid search explores combinations within these bounds.
Parameters are applied to the runner via ParameterOverride before each run.
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Parameter:
    """A single tunable parameter."""
    name: str
    category: str
    description: str
    current_value: Any
    min_value: Any
    max_value: Any
    step: Any
    value_type: str   # "float", "int", "decimal"
    code_location: str  # file:line reference

    def grid_values(self) -> list[Any]:
        """Generate all grid values from min to max by step."""
        if self.value_type == "int":
            return list(range(
                int(self.min_value),
                int(self.max_value) + 1,
                int(self.step),
            ))
        elif self.value_type == "decimal":
            values = []
            v = Decimal(str(self.min_value))
            max_v = Decimal(str(self.max_value))
            step = Decimal(str(self.step))
            while v <= max_v:
                values.append(v)
                v += step
            return values
        else:  # float
            values = []
            v = float(self.min_value)
            max_v = float(self.max_value)
            step = float(self.step)
            while v <= max_v + step * 0.01:  # float tolerance
                values.append(round(v, 6))
                v += step
            return values


# ---------------------------------------------------------------------------
# Default parameter space
# ---------------------------------------------------------------------------

PARAMETER_SPACE: list[Parameter] = [
    # --- Entry composite weights ---
    Parameter(
        name="indicator_weight",
        category="entry_weights",
        description="Weight for indicator_quality in composite score",
        current_value=0.20, min_value=0.10, max_value=0.35, step=0.05,
        value_type="float",
        code_location="groups/entry/group.py:107",
    ),
    Parameter(
        name="candlestick_weight",
        category="entry_weights",
        description="Weight for candlestick_quality in composite score",
        current_value=0.25, min_value=0.15, max_value=0.40, step=0.05,
        value_type="float",
        code_location="groups/entry/group.py:108",
    ),
    Parameter(
        name="structural_weight",
        category="entry_weights",
        description="Weight for structural_alignment in composite score",
        current_value=0.10, min_value=0.05, max_value=0.20, step=0.05,
        value_type="float",
        code_location="groups/entry/group.py:109",
    ),

    # --- Entry thresholds ---
    Parameter(
        name="composite_score_threshold",
        category="entry_thresholds",
        description="Minimum composite score to fire CandidateTradeEvent",
        current_value=0.50, min_value=0.35, max_value=0.65, step=0.05,
        value_type="float",
        code_location="groups/entry/group.py:82",
    ),
    Parameter(
        name="confirmation_gate_min_groups",
        category="entry_thresholds",
        description="Minimum number of signal groups agreeing on direction",
        current_value=2, min_value=1, max_value=3, step=1,
        value_type="int",
        code_location="groups/entry/group.py:81",
    ),

    # --- Panel thresholds ---
    Parameter(
        name="panel_approve_threshold",
        category="panel",
        description="Minimum trader approvals out of 20 to enter",
        current_value=14, min_value=12, max_value=17, step=1,
        value_type="int",
        code_location="traders/panel.py:68",
    ),
    Parameter(
        name="panel_min_avg_score",
        category="panel",
        description="Minimum average trader score to enter",
        current_value=6.5, min_value=5.5, max_value=7.5, step=0.5,
        value_type="float",
        code_location="traders/panel.py:69",
    ),

    # --- Safety rails ---
    Parameter(
        name="safety_avg_score_floor",
        category="safety_rails",
        description="Avg score below this always holds (FinalDecisionGroup)",
        current_value=5.0, min_value=4.0, max_value=6.0, step=0.5,
        value_type="float",
        code_location="decision/final_group.py:109",
    ),
    Parameter(
        name="safety_reject_ceiling",
        category="safety_rails",
        description="Reject count above this always holds",
        current_value=12, min_value=10, max_value=14, step=1,
        value_type="int",
        code_location="decision/final_group.py:117",
    ),
    Parameter(
        name="safety_min_rr_ratio",
        category="safety_rails",
        description="Minimum R:R ratio to enter",
        current_value=1.5, min_value=1.0, max_value=2.5, step=0.25,
        value_type="float",
        code_location="decision/final_group.py:125",
    ),

    # --- Risk parameters ---
    Parameter(
        name="risk_fraction",
        category="risk",
        description="Fraction of equity risked per trade",
        current_value=0.01, min_value=0.005, max_value=0.02, step=0.005,
        value_type="float",
        code_location="groups/risk_leverage/group.py:72",
    ),
    Parameter(
        name="daily_loss_limit",
        category="risk",
        description="Daily loss threshold to block new entries (negative)",
        current_value=-0.02, min_value=-0.04, max_value=-0.01, step=0.005,
        value_type="float",
        code_location="groups/risk_leverage/group.py:74",
    ),

    # --- Stop placement ---
    Parameter(
        name="atr_stop_multiplier",
        category="exit",
        description="ATR multiplier for initial stop placement",
        current_value=2.0, min_value=1.5, max_value=3.0, step=0.25,
        value_type="float",
        code_location="risk/sizing.py:31",
    ),

    # --- Exit parameters ---
    Parameter(
        name="trailing_stop_atr_mult",
        category="exit",
        description="ATR multiplier for trailing stop",
        current_value=2.0, min_value=1.5, max_value=3.0, step=0.25,
        value_type="float",
        code_location="groups/exit/group.py:240",
    ),
    Parameter(
        name="time_stop_bars",
        category="exit",
        description="Maximum bars to hold before time-based exit",
        current_value=20, min_value=10, max_value=40, step=5,
        value_type="int",
        code_location="groups/exit/group.py:187",
    ),
]


@dataclass
class ParameterSet:
    """A specific set of parameter values for one optimization trial."""
    values: dict[str, Any]

    def __post_init__(self):
        # Validate all parameter names exist
        valid_names = {p.name for p in PARAMETER_SPACE}
        for name in self.values:
            if name not in valid_names:
                raise ValueError(f"Unknown parameter: '{name}'")

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def diff_from_baseline(self) -> dict[str, tuple[Any, Any]]:
        """Return {name: (baseline_value, new_value)} for changed params."""
        baseline = get_baseline_params()
        diffs = {}
        for name, new_val in self.values.items():
            old_val = baseline.values.get(name)
            if old_val != new_val:
                diffs[name] = (old_val, new_val)
        return diffs

    def to_dict(self) -> dict:
        return dict(self.values)


def get_baseline_params() -> ParameterSet:
    """Return the current production parameter values."""
    return ParameterSet(
        values={p.name: p.current_value for p in PARAMETER_SPACE}
    )


def build_grid(
    param_names: list[str],
    max_combinations: int = 10000,
) -> list[ParameterSet]:
    """
    Build a grid of ParameterSets for the specified parameters.

    Only the named parameters are varied; others stay at baseline values.
    If the total grid exceeds max_combinations, raises ValueError.

    Args:
        param_names: Which parameters to vary.
        max_combinations: Safety limit on grid size.

    Returns:
        List of ParameterSet objects, one per grid point.
    """
    params_to_vary = [p for p in PARAMETER_SPACE if p.name in param_names]
    missing = set(param_names) - {p.name for p in params_to_vary}
    if missing:
        raise ValueError(f"Unknown parameters: {missing}")

    grid_axes = [p.grid_values() for p in params_to_vary]
    total = 1
    for axis in grid_axes:
        total *= len(axis)

    if total > max_combinations:
        raise ValueError(
            f"Grid has {total} combinations, exceeds limit of {max_combinations}. "
            f"Reduce parameter ranges or step sizes."
        )

    baseline = get_baseline_params()
    results: list[ParameterSet] = []

    for combo in itertools.product(*grid_axes):
        values = dict(baseline.values)
        for param, val in zip(params_to_vary, combo):
            values[param.name] = val
        results.append(ParameterSet(values=values))

    logger.info(
        "build_grid: %d combinations for %d parameters: %s",
        len(results), len(params_to_vary),
        [p.name for p in params_to_vary],
    )
    return results


def get_parameter(name: str) -> Parameter:
    """Look up a parameter by name."""
    for p in PARAMETER_SPACE:
        if p.name == name:
            return p
    raise KeyError(f"Parameter '{name}' not found in PARAMETER_SPACE")
