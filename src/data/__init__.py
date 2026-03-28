"""
Data layer: FeatureStore, OHLCV ingestion, Binance adapter.

Phase 2: Parquet-backed FeatureStore + Binance REST polling.
Phase 3: TimescaleDB + WebSocket streaming.

Source: /docs/data_contracts/data_contracts.md (FeatureStore API)
"""
from .store import FeatureStore
from .binance import BinanceAdapter

__all__ = ["FeatureStore", "BinanceAdapter"]
