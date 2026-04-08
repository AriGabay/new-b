#!/usr/bin/env python3
"""
Train (or retrain) the LightGBM ML signal classifier from the learning DB.

The classifier reads (BTCSetupPacket, pnl_r) pairs stored by the full
pipeline backtest engine and trains a binary win/loss predictor.

Once trained it is saved to data/btc_classifier.pkl and loaded automatically
by MLSignalEvaluator (evaluator #22) in future backtest/live runs.

Anti-overfitting requirements:
  - Minimum 100 labelled outcomes (otherwise exits with a warning)
  - Chronological 80/20 train/validation split (no leakage)
  - max_depth=4, n_estimators=100 (complexity cap)
  - Feature importance check: warns if any feature > 25%

Usage:
  python src/scripts/train_ml_classifier.py
  python src/scripts/train_ml_classifier.py --db data/backtest_learning.db
  python src/scripts/train_ml_classifier.py --report   # show model status only
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SRC_DIR, "..", ".."))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "backtest_learning.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LightGBM ML signal classifier.")
    parser.add_argument(
        "--db", default=DEFAULT_DB_PATH,
        help=f"Learning DB path (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Show current model status and exit (no training)"
    )
    args = parser.parse_args()

    from ml.btc_classifier import BTCClassifier

    clf = BTCClassifier()

    if args.report:
        clf.print_report()
        return

    logger.info("Training BTCClassifier from: %s", args.db)
    if not os.path.exists(args.db):
        logger.error("Learning DB not found: %s", args.db)
        logger.error("Run the offline learning loop first:")
        logger.error("  python src/scripts/learn_and_test.py --reset")
        sys.exit(1)

    success = clf.retrain(args.db)
    if success:
        clf.print_report()
        logger.info("Classifier saved. MLSignalEvaluator will use it on the next run.")
    else:
        logger.warning(
            "Training failed — insufficient labelled data in %s.\n"
            "Run more backtests to accumulate trade outcomes:\n"
            "  python src/scripts/learn_and_test.py --reset",
            args.db,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
