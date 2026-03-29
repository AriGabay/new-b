"""
Walk-Forward Optimization framework for BTC/Bybit trading system.

Modules:
  data_loader           — Chronological CSV OHLCV loading with validation
  featurevector_builder — Convert OHLCV bars to FeatureVectors via FeatureComputer
  fold_builder          — Rolling train/test windows
  parameter_space       — Tunable parameter definitions with bounds
  objective             — Multi-factor objective function
  regression_guard      — Baseline fixture verification after param changes
  walk_forward_runner   — Orchestrator: grid search on train, evaluate OOS
  reporting             — Fold-by-fold results with elapsed time
"""
