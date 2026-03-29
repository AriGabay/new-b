"""
MDP (Markov Decision Process) decision framework.

Sits ON TOP of the existing pipeline. The 20 evaluators become state
providers; hard safety rails remain non-overridable guards.

Phase 1: Rule-based policy + transition logging (no RL).
Phase 2: Offline policy evaluation using logged transitions.
Phase 3: Online learning via logged (state, action, reward, next_state) tuples.

Modules:
  state.py            — MDPState dataclass (rich state vector)
  actions.py          — MDPAction enum + size multipliers
  policy.py           — MDPPolicy (Phase 1: deterministic rules)
  state_builder.py    — Assembles MDPState from packet + panel + SystemState
  transition_logger.py — Logs transitions to SQLite for offline analysis
"""
from mdp.state import MDPState
from mdp.actions import MDPAction, ACTION_SIZE_MULTIPLIERS
from mdp.policy import MDPPolicy
from mdp.state_builder import MDPStateBuilder
from mdp.transition_logger import TransitionLogger

__all__ = [
    "MDPState",
    "MDPAction",
    "ACTION_SIZE_MULTIPLIERS",
    "MDPPolicy",
    "MDPStateBuilder",
    "TransitionLogger",
]
