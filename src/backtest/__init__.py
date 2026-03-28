"""
Backtest framework.

Replay historical OHLCV bars through the same group pipeline as live.
Enforces bar-close-only signal generation (no lookahead).
Uses same schemas, same risk rules, same feature computation as runtime.

Phase 2 deliverable: single-symbol daily bar replay, in-sample period only.
Phase 3: multi-symbol, walkforward, Monte Carlo.

Source: /docs/architecture/runtime_model.md (Backtesting Runtime section)
        /docs/adr/ADR-004-validation-gates-before-live-promotion.md
"""
from .engine import BacktestEngine
from .holdout import HoldoutManager
from .metrics import PerformanceMetrics

__all__ = ["BacktestEngine", "HoldoutManager", "PerformanceMetrics"]
