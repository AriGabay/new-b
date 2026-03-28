"""
Phase 5 Validation Framework — BTC/Bybit runtime pipeline.

Provides:
  replay_harness      — feeds bar sequences through the real wired runner
  scenario_loader     — deterministic BTCSetupPacket and FeatureVector factories
  panel_analyzer      — panel behavior measurement (NO forced approvals)
  risk_analyzer       — risk gate rejection analysis
  calibration_reporter — trader calibration with MIN_SAMPLES gates
  threshold_analyzer  — panel threshold sensitivity (READ-ONLY, no mutation)
  source_enforcer     — OutcomeSource separation enforcement
  metrics             — win rate, expectancy, profit factor, drawdown
  report_builder      — formats all validation results into human-readable reports

Source separation is mandatory. All validation outputs carry an explicit
validation_source tag. Sources are never silently mixed.

Valid validation sources:
  event_driven_runtime_replay     — real runner, real bar sequences, no forcing
  event_driven_runtime_simulation — real runner, synthetic bars, no forcing
  synthetic_control_scenarios     — forced-approval or controlled path tests (plumbing only)
  simplified_backtest             — BacktestEngine EMA-crossover (NOT runtime pipeline)
  live_exchange_fed_paper         — future: live Bybit paper mode
"""

VALIDATION_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "event_driven_runtime_simulation",
    "synthetic_control_scenarios",
    "simplified_backtest",
    "live_exchange_fed_paper",
})

RUNTIME_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "event_driven_runtime_simulation",
    "live_exchange_fed_paper",
})

EDGE_EVIDENCE_SOURCES = frozenset({
    "event_driven_runtime_replay",
    "live_exchange_fed_paper",
})
