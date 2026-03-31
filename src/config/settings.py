"""
SystemConfig: centralized configuration for all groups and the runtime.

Configuration hierarchy:
  1. Defaults (hardcoded here)
  2. config/system.yaml (file overrides)
  3. Environment variables (highest priority — for secrets and deployment)

Environment variables:
  MODE_GATE            — "research" | "shadow" | "live" (default: research)
  INITIAL_EQUITY       — Decimal string (default: "100000")
  BINANCE_API_KEY      — optional for public endpoints
  BINANCE_API_SECRET   — optional for public endpoints
  JOURNAL_DB_PATH      — path to SQLite journal
  DATA_DIR             — path to Parquet bar store
  EVENT_CALENDAR_PATH  — path to macro event calendar CSV

Source: /docs/architecture/runtime_model.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from core.schemas import ModeGate


@dataclass
class MarketDataConfig:
    symbols:          list[str] = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "BNBUSDT",
    ])
    timeframe:        str     = "1d"
    poll_interval_s:  int     = 3600    # Check for new bars every hour
    min_volume_usd:   float   = 10_000_000.0   # $10M/day minimum
    history_bars:     int     = 250     # Bars to prefetch at startup


@dataclass
class RiskConfig:
    risk_fraction:         Decimal = Decimal("0.01")
    max_position_fraction: Decimal = Decimal("0.10")
    max_portfolio_exposure: Decimal = Decimal("0.25")
    max_cluster_exposure:  Decimal = Decimal("0.15")
    daily_loss_limit:      float   = -0.20   # Leveraged: 1-2 losing trades/day
    max_drawdown_halt:     float   = 0.40   # Leveraged: halt at 40% to prevent ruin
    max_leverage:          float   = 35.0  # Leveraged perpetual futures: 5×–35×
    atr_stop_multiplier:   Decimal = Decimal("2.0")


@dataclass
class EntryConfig:
    min_composite_score:   float = 0.50
    critic_score_threshold: float = 0.60
    confirmation_min_groups: int = 2
    bundle_flush_timeout_ms: int = 50    # Flush pending bundles after N ms
    panel_min_approvals: int = 11
    panel_min_avg_score: float = 5.5
    allow_pure_indicator_proposals: bool = True
    single_signal_high_confidence: float = 0.80


@dataclass
class JournalConfig:
    db_path:            str  = "data/journal.db"
    backtest_db_path:   str  = "data/backtest_journal.db"
    weekly_summary:     bool = False    # LLM weekly summary; Phase 2: disabled


@dataclass
class BacktestConfig:
    data_dir:           str  = "data/bars"
    enforce_holdout:    bool = True


@dataclass
class SystemConfig:
    """Top-level config object passed into every group at startup."""
    mode:          ModeGate        = ModeGate.RESEARCH
    initial_equity: Decimal        = Decimal("1000")
    market_data:   MarketDataConfig = field(default_factory=MarketDataConfig)
    risk:          RiskConfig       = field(default_factory=RiskConfig)
    entry:         EntryConfig      = field(default_factory=EntryConfig)
    journal:       JournalConfig    = field(default_factory=JournalConfig)
    backtest:      BacktestConfig   = field(default_factory=BacktestConfig)
    event_calendar_path: Optional[str] = None
    # Chart pattern plugin system (Phase 6.5+)
    # When False, ChartPatternGroup runs but pattern signals are only delivered
    # to PanelDecisionGroup via cache wiring (not included in composite score).
    # When True, chart pattern signals will also contribute to EntryGroup's
    # composite score via a future GroupSignalEvent pathway.
    enable_chart_patterns: bool = False


def load_config(config_file: Optional[str] = None) -> SystemConfig:
    """
    Load system config from:
    1. Defaults
    2. config_file (YAML) if provided
    3. Environment variable overrides

    Returns SystemConfig ready to inject into groups.
    """
    cfg = SystemConfig()

    # Environment overrides
    mode_env = os.environ.get("MODE_GATE", "research").lower()
    cfg.mode = ModeGate(mode_env)

    equity_env = os.environ.get("INITIAL_EQUITY")
    if equity_env:
        cfg.initial_equity = Decimal(equity_env)

    journal_db = os.environ.get("JOURNAL_DB_PATH")
    if journal_db:
        cfg.journal.db_path = journal_db

    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        cfg.backtest.data_dir = data_dir

    calendar = os.environ.get("EVENT_CALENDAR_PATH")
    if calendar:
        cfg.event_calendar_path = calendar

    # YAML file override — Phase 2 implementation pending
    if config_file:
        raise NotImplementedError("YAML config loading — Phase 2 implementation pending")

    return cfg
