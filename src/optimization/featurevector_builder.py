"""
FeatureVector builder for walk-forward optimization.

Converts a chronological list of OHLCVBar objects into FeatureVectors
using the real FeatureComputer. This ensures walk-forward optimization
uses the exact same indicator calculations as the live runtime.

The builder applies a sliding window of WARM_UP_BARS (200) to produce
one FeatureVector per bar starting from bar index 199.

Usage:
    from optimization.data_loader import load_csv
    from optimization.featurevector_builder import build_feature_vectors

    result = load_csv("data/btc_1h.csv")
    fvs = build_feature_vectors(result.bars)
    # len(fvs) == len(result.bars) - 199
"""
from __future__ import annotations

import logging
from typing import Optional

from core.schemas import FeatureVector, OHLCVBar
from features.compute import FeatureComputer, WARM_UP_BARS

logger = logging.getLogger(__name__)


def build_feature_vectors(
    bars: list[OHLCVBar],
    warmup: int = WARM_UP_BARS,
) -> list[FeatureVector]:
    """
    Convert OHLCV bars into FeatureVectors using the real FeatureComputer.

    Applies a sliding window of `warmup` bars. The first FeatureVector
    corresponds to bars[warmup-1], using bars[0:warmup] as input.

    Args:
        bars: Chronological OHLCV bars (oldest first).
        warmup: Number of bars required for warm-up (default 200).

    Returns:
        List of FeatureVectors, one per bar from index warmup-1 onward.

    Raises:
        ValueError: If bars has fewer than warmup entries.
    """
    if len(bars) < warmup:
        raise ValueError(
            f"Need at least {warmup} bars to produce FeatureVectors, got {len(bars)}"
        )

    computer = FeatureComputer()
    feature_vectors: list[FeatureVector] = []
    skipped = 0

    for i in range(warmup, len(bars) + 1):
        window = bars[i - warmup : i]
        fv = computer.compute(window)
        if fv is not None:
            feature_vectors.append(fv)
        else:
            skipped += 1

    if skipped > 0:
        logger.warning(
            "featurevector_builder: %d bars skipped (FeatureComputer returned None)",
            skipped,
        )

    logger.info(
        "featurevector_builder: produced %d FeatureVectors from %d bars "
        "(warmup=%d)",
        len(feature_vectors), len(bars), warmup,
    )
    return feature_vectors


def build_feature_vectors_with_indices(
    bars: list[OHLCVBar],
    warmup: int = WARM_UP_BARS,
) -> list[tuple[int, FeatureVector]]:
    """
    Like build_feature_vectors but returns (bar_index, FeatureVector) tuples.

    bar_index is the index into the original bars list for the bar
    that produced this FeatureVector (i.e., the last bar in the window).
    """
    if len(bars) < warmup:
        raise ValueError(
            f"Need at least {warmup} bars to produce FeatureVectors, got {len(bars)}"
        )

    computer = FeatureComputer()
    results: list[tuple[int, FeatureVector]] = []

    for i in range(warmup, len(bars) + 1):
        window = bars[i - warmup : i]
        fv = computer.compute(window)
        if fv is not None:
            results.append((i - 1, fv))

    return results
