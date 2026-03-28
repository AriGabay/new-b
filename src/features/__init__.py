"""
Feature computation layer.

All features are computed from OHLCV history at bar close time only.
No lookahead. All computations are deterministic and reproducible.

Source: /docs/data_contracts/data_contracts.md (FeatureVector spec)
"""
from .compute import FeatureComputer

__all__ = ["FeatureComputer"]
