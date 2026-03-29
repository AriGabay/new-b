"""
Walk-forward fold builder.

Splits a chronological FeatureVector sequence into rolling train/test folds.
Each fold has:
  - A warmup prefix (discarded from scoring but needed for indicator warm-up)
  - A train window (in-sample for parameter optimization)
  - A test window (out-of-sample for validation)

Folds advance by `step` bars. Train and test windows never overlap.

Default configuration (1h timeframe, BTCUSDT):
  - warmup:     250 bars  (250 hours ~ 10.4 days)
  - train:     4320 bars  (180 days)
  - test:       720 bars  (30 days)
  - step:       720 bars  (30 days)

The warmup prefix is prepended to each fold's train window so that
the RuntimeReplayHarness has enough history for indicator computation.
It is NOT included in objective function scoring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.schemas import FeatureVector
from utils.bar_duration import format_bars

logger = logging.getLogger(__name__)

# Default fold parameters for 1h BTC/Bybit
DEFAULT_WARMUP_BARS = 250     # ~10.4 days
DEFAULT_TRAIN_BARS = 4320     # 180 days
DEFAULT_TEST_BARS = 720       # 30 days
DEFAULT_STEP_BARS = 720       # 30 days


@dataclass(frozen=True)
class Fold:
    """A single train/test fold."""
    fold_index: int
    warmup: list[FeatureVector]     # Prepended to train for indicator warm-up
    train: list[FeatureVector]      # In-sample (optimize on this)
    test: list[FeatureVector]       # Out-of-sample (evaluate on this)
    timeframe: str

    @property
    def train_start(self) -> Optional[datetime]:
        return self.train[0].timestamp if self.train else None

    @property
    def train_end(self) -> Optional[datetime]:
        return self.train[-1].timestamp if self.train else None

    @property
    def test_start(self) -> Optional[datetime]:
        return self.test[0].timestamp if self.test else None

    @property
    def test_end(self) -> Optional[datetime]:
        return self.test[-1].timestamp if self.test else None

    @property
    def train_with_warmup(self) -> list[FeatureVector]:
        """Train window with warmup prefix prepended (for harness input)."""
        return self.warmup + self.train

    def summary(self) -> dict:
        return {
            "fold_index": self.fold_index,
            "warmup_bars": len(self.warmup),
            "train_bars": len(self.train),
            "test_bars": len(self.test),
            "train_duration": format_bars(len(self.train), self.timeframe),
            "test_duration": format_bars(len(self.test), self.timeframe),
            "train_start": self.train_start.isoformat() if self.train_start else None,
            "train_end": self.train_end.isoformat() if self.train_end else None,
            "test_start": self.test_start.isoformat() if self.test_start else None,
            "test_end": self.test_end.isoformat() if self.test_end else None,
        }


def build_folds(
    feature_vectors: list[FeatureVector],
    warmup_bars: int = DEFAULT_WARMUP_BARS,
    train_bars: int = DEFAULT_TRAIN_BARS,
    test_bars: int = DEFAULT_TEST_BARS,
    step_bars: int = DEFAULT_STEP_BARS,
    timeframe: str = "1h",
) -> list[Fold]:
    """
    Build rolling walk-forward folds from a FeatureVector sequence.

    Args:
        feature_vectors: Chronological FeatureVectors (already computed from OHLCV).
        warmup_bars: Bars prepended to train for indicator warm-up.
        train_bars: In-sample window size.
        test_bars: Out-of-sample window size.
        step_bars: How many bars to advance between folds.
        timeframe: Timeframe string for duration display.

    Returns:
        List of Fold objects. Empty if data is insufficient for even one fold.
    """
    total = len(feature_vectors)
    min_required = warmup_bars + train_bars + test_bars

    if total < min_required:
        logger.warning(
            "fold_builder: insufficient data — have %s, need at least %s "
            "(warmup=%d + train=%d + test=%d)",
            format_bars(total, timeframe),
            format_bars(min_required, timeframe),
            warmup_bars, train_bars, test_bars,
        )
        return []

    folds: list[Fold] = []
    fold_idx = 0
    offset = 0

    while True:
        warmup_start = offset
        warmup_end = offset + warmup_bars
        train_start = warmup_end
        train_end = train_start + train_bars
        test_start = train_end
        test_end = test_start + test_bars

        if test_end > total:
            break

        fold = Fold(
            fold_index=fold_idx,
            warmup=feature_vectors[warmup_start:warmup_end],
            train=feature_vectors[train_start:train_end],
            test=feature_vectors[test_start:test_end],
            timeframe=timeframe,
        )
        folds.append(fold)

        logger.info(
            "Fold %d: train %s → %s (%s), test %s → %s (%s)",
            fold_idx,
            fold.train_start, fold.train_end,
            format_bars(len(fold.train), timeframe),
            fold.test_start, fold.test_end,
            format_bars(len(fold.test), timeframe),
        )

        fold_idx += 1
        offset += step_bars

    logger.info(
        "fold_builder: built %d folds from %s of data",
        len(folds), format_bars(total, timeframe),
    )
    return folds


def estimate_fold_count(
    total_bars: int,
    warmup_bars: int = DEFAULT_WARMUP_BARS,
    train_bars: int = DEFAULT_TRAIN_BARS,
    test_bars: int = DEFAULT_TEST_BARS,
    step_bars: int = DEFAULT_STEP_BARS,
) -> int:
    """Estimate number of folds without building them."""
    min_required = warmup_bars + train_bars + test_bars
    if total_bars < min_required:
        return 0
    remaining = total_bars - min_required
    return 1 + remaining // step_bars
