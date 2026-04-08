"""
BTCClassifier: walk-forward LightGBM binary classifier for trade outcome prediction.

Architecture:
  - Input: 20-feature vector from BTCSetupPacket (see feature_extractor.py)
  - Output: P(win) ∈ [0, 1] where win = pnl_r > 0
  - Model: LightGBM with max_depth=4, n_estimators=100 (anti-overfitting)
  - Training data: setup_packets × outcome_attributions JOIN from learning DB

Anti-overfitting guards:
  - MIN_SAMPLES = 100: model only activates after 100+ trade outcomes
  - Walk-forward: 80/20 chronological split; no leakage
  - Complexity cap: max_depth=4, n_estimators=100, min_child_samples=10
  - No single feature > 25% importance (logged as warning if violated)

Lifecycle:
  1. BtcBybitPaperRunner runs and accumulates outcomes in learning DB
  2. Offline: BTCClassifier.retrain(db_path) reads DB, trains, saves model
  3. MLSignalEvaluator.evaluate() loads singleton, calls predict_proba()
  4. If untrained or < MIN_SAMPLES: evaluator abstains

Usage:
    classifier = BTCClassifier()
    if not classifier.is_trained:
        classifier.retrain("data/backtest_learning.db")
    p_win = classifier.predict_proba(features)  # float 0-1
"""
from __future__ import annotations

import json
import logging
import math
import os
import pickle
import sqlite3
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MIN_SAMPLES      = 100       # minimum outcomes to train
MIN_FEATURE_DIM  = 20
MAX_DEPTH        = 4
N_ESTIMATORS     = 100
MIN_CHILD_SAMPLES = 10
MAX_FEATURE_IMPORTANCE_FRACTION = 0.25   # warn if any feature > 25%
TRAIN_SPLIT      = 0.80      # 80% train, 20% validation (chronological)

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "btc_classifier.pkl"
)


class BTCClassifier:
    """
    LightGBM binary classifier for trade win/loss prediction.

    Thread-safety: not thread-safe. Use one instance per process.
    Serialisation: uses pickle for model persistence (model + metadata).
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._model_path = model_path or DEFAULT_MODEL_PATH
        self._model = None          # lgb.Booster or sklearn wrapper
        self._feature_names: list[str] = []
        self._n_training_samples: int = 0
        self._train_accuracy: float = 0.0
        self._val_accuracy: float = 0.0
        self._trained_at: Optional[str] = None
        self._load_if_exists()

    @property
    def is_trained(self) -> bool:
        return self._model is not None and self._n_training_samples >= MIN_SAMPLES

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def retrain(self, db_path: str) -> bool:
        """
        Load training data from the learning DB and train the model.

        Returns True if training succeeded (MIN_SAMPLES met), False otherwise.
        Saves the trained model to self._model_path.
        """
        X, y, timestamps = self._load_training_data(db_path)
        if X is None or len(X) < MIN_SAMPLES:
            logger.info(
                "BTCClassifier: not enough samples to train (have %d, need %d).",
                0 if X is None else len(X), MIN_SAMPLES,
            )
            return False

        logger.info("BTCClassifier: training on %d samples...", len(X))
        success = self._fit(X, y)
        if success:
            self.save()
        return success

    def _load_training_data(
        self,
        db_path: str,
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[list]]:
        """
        Load (feature_vector, pnl_r) pairs from the learning DB.

        Returns (X, y, timestamps) or (None, None, None) on failure.

        Joins:
          setup_packets.packet_json → feature extraction
          outcome_attributions.pnl_r → binary label (pnl_r > 0 → 1)
        Ordered by bar_timestamp so chronological split is meaningful.
        """
        if not os.path.exists(db_path):
            logger.warning("BTCClassifier: DB not found: %s", db_path)
            return None, None, None

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT
                    sp.packet_json,
                    sp.bar_timestamp,
                    oa.pnl_r
                FROM setup_packets sp
                JOIN outcome_attributions oa ON sp.trade_id = oa.trade_id
                WHERE oa.pnl_r IS NOT NULL
                  AND sp.packet_json IS NOT NULL
                ORDER BY sp.bar_timestamp ASC
            """).fetchall()
            conn.close()
        except Exception as exc:
            logger.error("BTCClassifier: DB query failed: %s", exc)
            return None, None, None

        if not rows:
            logger.info("BTCClassifier: no labelled data in DB.")
            return None, None, None

        from ml.feature_extractor import extract_features

        X_list: list[list[float]] = []
        y_list: list[int] = []
        ts_list: list[str] = []
        skipped = 0

        for row in rows:
            try:
                packet_data = json.loads(row["packet_json"])
                packet = self._dict_to_packet(packet_data)
                if packet is None:
                    skipped += 1
                    continue
                features = extract_features(packet)
                if len(features) != MIN_FEATURE_DIM:
                    skipped += 1
                    continue
                label = 1 if float(row["pnl_r"]) > 0 else 0
                X_list.append(features)
                y_list.append(label)
                ts_list.append(row["bar_timestamp"] or "")
            except Exception as exc:
                logger.debug("BTCClassifier: skipping row: %s", exc)
                skipped += 1

        if skipped:
            logger.debug("BTCClassifier: skipped %d rows during data loading.", skipped)

        if not X_list:
            return None, None, None

        logger.info(
            "BTCClassifier: loaded %d labelled samples "
            "(win_rate=%.1f%%, skipped=%d).",
            len(X_list),
            100 * sum(y_list) / len(y_list),
            skipped,
        )
        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32), ts_list

    def _fit(self, X: np.ndarray, y: np.ndarray) -> bool:
        """
        Train LightGBM classifier with chronological 80/20 split.
        Returns True on success.
        """
        try:
            import lightgbm as lgb
        except ImportError:
            logger.error("BTCClassifier: lightgbm not installed. Run: pip install lightgbm")
            return False

        n = len(X)
        split = int(n * TRAIN_SPLIT)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        if len(X_train) < MIN_CHILD_SAMPLES:
            logger.warning(
                "BTCClassifier: train set too small (%d samples).", len(X_train)
            )
            return False

        from ml.feature_extractor import FEATURE_NAMES
        self._feature_names = FEATURE_NAMES

        params = {
            "objective":         "binary",
            "metric":            "binary_logloss",
            "max_depth":         MAX_DEPTH,
            "n_estimators":      N_ESTIMATORS,
            "min_child_samples": MIN_CHILD_SAMPLES,
            "learning_rate":     0.05,
            "num_leaves":        15,        # 2^max_depth - 1
            "feature_fraction":  0.8,       # subsample features
            "bagging_fraction":  0.8,
            "bagging_freq":      5,
            "verbose":          -1,
            "random_state":      42,
        }

        model = lgb.LGBMClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)] if len(X_val) > 0 else None,
            callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(-1)]
            if len(X_val) >= MIN_CHILD_SAMPLES else None,
        )

        # Record metrics
        self._model = model
        self._n_training_samples = n

        from datetime import datetime, timezone
        self._trained_at = datetime.now(timezone.utc).isoformat()

        if len(X_train) > 0:
            train_pred = model.predict(X_train)
            self._train_accuracy = float(np.mean(train_pred == y_train))
        if len(X_val) > 0:
            val_pred = model.predict(X_val)
            self._val_accuracy = float(np.mean(val_pred == y_val))

        logger.info(
            "BTCClassifier: trained — n=%d  train_acc=%.1f%%  val_acc=%.1f%%",
            n, self._train_accuracy * 100, self._val_accuracy * 100,
        )

        # Anti-overfitting: check feature importance concentration
        self._check_feature_importance(model)

        return True

    def _check_feature_importance(self, model) -> None:
        """Log a warning if any feature dominates (> 25% importance)."""
        try:
            importances = model.feature_importances_
            total = sum(importances)
            if total <= 0:
                return
            for name, imp in zip(self._feature_names, importances):
                frac = imp / total
                if frac > MAX_FEATURE_IMPORTANCE_FRACTION:
                    logger.warning(
                        "BTCClassifier: feature '%s' has %.0f%% importance "
                        "(> %.0f%% threshold — possible overfitting signal).",
                        name, frac * 100, MAX_FEATURE_IMPORTANCE_FRACTION * 100,
                    )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_proba(self, features: list[float]) -> float:
        """
        Return P(win) for a given feature vector.

        Returns 0.5 (no-opinion neutral) if model is not trained.
        Raises ValueError if features has wrong dimension.
        """
        if not self.is_trained:
            return 0.5

        if len(features) != MIN_FEATURE_DIM:
            raise ValueError(
                f"Expected {MIN_FEATURE_DIM} features, got {len(features)}"
            )

        X = np.array([features], dtype=np.float32)
        proba = self._model.predict_proba(X)[0][1]   # P(class=1) = P(win)
        return float(proba)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> str:
        """Save model + metadata to pickle. Returns path written."""
        out_path = path or self._model_path
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        payload = {
            "model":             self._model,
            "feature_names":     self._feature_names,
            "n_training_samples": self._n_training_samples,
            "train_accuracy":    self._train_accuracy,
            "val_accuracy":      self._val_accuracy,
            "trained_at":        self._trained_at,
        }
        with open(out_path, "wb") as f:
            pickle.dump(payload, f)

        logger.info(
            "BTCClassifier: saved → %s  (n=%d, val_acc=%.1f%%)",
            out_path, self._n_training_samples, self._val_accuracy * 100,
        )
        return out_path

    def _load_if_exists(self) -> None:
        """Load model from disk if it exists. Silent on failure."""
        if not os.path.exists(self._model_path):
            return
        try:
            with open(self._model_path, "rb") as f:
                payload = pickle.load(f)
            self._model             = payload.get("model")
            self._feature_names     = payload.get("feature_names", [])
            self._n_training_samples = payload.get("n_training_samples", 0)
            self._train_accuracy    = payload.get("train_accuracy", 0.0)
            self._val_accuracy      = payload.get("val_accuracy", 0.0)
            self._trained_at        = payload.get("trained_at")
            if self.is_trained:
                logger.info(
                    "BTCClassifier: loaded from %s  (n=%d, val_acc=%.1f%%, trained=%s)",
                    self._model_path,
                    self._n_training_samples,
                    self._val_accuracy * 100,
                    self._trained_at or "unknown",
                )
        except Exception as exc:
            logger.warning("BTCClassifier: could not load model: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dict_to_packet(self, data: dict):
        """
        Reconstruct a minimal BTCSetupPacket-compatible object from stored JSON.

        We use a lightweight stub rather than full deserialisation to avoid
        importing the entire runtime stack during offline training.
        """
        try:
            return _PacketStub(data)
        except Exception as exc:
            logger.debug("BTCClassifier._dict_to_packet: %s", exc)
            return None

    def print_report(self) -> None:
        """Print a human-readable model status report."""
        sep = "=" * 60
        print(sep)
        print("  BTCClassifier STATUS")
        print(sep)
        if not self.is_trained:
            print(f"  Status:  NOT TRAINED  (need {MIN_SAMPLES} samples)")
            print(sep)
            return
        print(f"  Status:  TRAINED")
        print(f"  Samples: {self._n_training_samples}")
        print(f"  Trained: {self._trained_at or 'unknown'}")
        print(f"  Train accuracy: {self._train_accuracy:.1%}")
        print(f"  Val accuracy:   {self._val_accuracy:.1%}")
        if self._feature_names and self._model is not None:
            try:
                importances = self._model.feature_importances_
                total = max(1, sum(importances))
                print(f"\n  Feature importances:")
                for name, imp in sorted(
                    zip(self._feature_names, importances),
                    key=lambda x: -x[1],
                ):
                    bar = "█" * int(imp / total * 20)
                    print(f"    {name:<25} {imp/total:>5.1%}  {bar}")
            except Exception:
                pass
        print(sep)


# ---------------------------------------------------------------------------
# Lightweight stub for packet reconstruction (avoids full runtime import)
# ---------------------------------------------------------------------------

class _IndicatorStub:
    __slots__ = [
        "close", "ema20", "ema50", "ema200",
        "ema_alignment", "rsi14", "prev_rsi14",
        "bb_upper", "bb_middle", "bb_lower", "bb_width_pct",
        "adx14", "volume_ratio", "atr14", "atr14_vs_sma20",
        "volatility_regime", "volume_character",
    ]

    def __init__(self, d: dict) -> None:
        from decimal import Decimal
        self.close           = Decimal(str(d.get("close", 0)))
        self.ema20           = Decimal(str(d.get("ema20", 0)))
        self.ema50           = Decimal(str(d.get("ema50", 0)))
        self.ema200          = Decimal(str(d.get("ema200", 0)))
        self.ema_alignment   = d.get("ema_alignment", "mixed")
        self.rsi14           = float(d.get("rsi14", 50))
        self.prev_rsi14      = float(d.get("prev_rsi14", 50))
        self.bb_upper        = Decimal(str(d.get("bb_upper", 0)))
        self.bb_middle       = Decimal(str(d.get("bb_middle", 0)))
        self.bb_lower        = Decimal(str(d.get("bb_lower", 0)))
        self.bb_width_pct    = float(d.get("bb_width_pct", 50))
        self.adx14           = float(d.get("adx14", 20))
        self.volume_ratio    = float(d.get("volume_ratio", 1))
        self.atr14           = Decimal(str(d.get("atr14", 0)))
        self.atr14_vs_sma20  = float(d.get("atr14_vs_sma20", 1))
        self.volatility_regime = d.get("volatility_regime", "normal")
        self.volume_character  = d.get("volume_character", "normal")


class _StructureStub:
    __slots__ = [
        "at_resistance", "at_support",
        "resistance_distance_pct", "support_distance_pct",
    ]

    def __init__(self, d: dict) -> None:
        self.at_resistance          = bool(d.get("at_resistance", False))
        self.at_support             = bool(d.get("at_support", False))
        self.resistance_distance_pct = d.get("resistance_distance_pct")
        self.support_distance_pct    = d.get("support_distance_pct")


class _ProposalStub:
    __slots__ = ["direction", "r_r_ratio", "stop_distance_pct"]

    def __init__(self, d: dict) -> None:
        from core.schemas import Direction
        raw_dir = d.get("direction", "LONG")
        if isinstance(raw_dir, str):
            self.direction = Direction.LONG if raw_dir.upper() == "LONG" else Direction.SHORT
        else:
            self.direction = raw_dir
        self.r_r_ratio        = float(d.get("r_r_ratio", 2.0))
        self.stop_distance_pct = float(d.get("stop_distance_pct", 0.02))


class _RegimeStub:
    __slots__ = ["btc_macro"]

    def __init__(self, d: dict) -> None:
        self.btc_macro = d.get("btc_macro", "ranging")


class _PacketStub:
    """
    Minimal packet-compatible object reconstructed from stored JSON.
    Only exposes the fields required by feature_extractor.extract_features().
    """
    __slots__ = ["indicators", "structure", "proposal", "regime", "recent_closes", "bar_timestamp"]

    def __init__(self, data: dict) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        ind_d  = data.get("indicators", {})
        str_d  = data.get("structure", {})
        prop_d = data.get("proposal", {})
        reg_d  = data.get("regime", {})

        self.indicators   = _IndicatorStub(ind_d)
        self.structure    = _StructureStub(str_d)
        self.proposal     = _ProposalStub(prop_d)
        self.regime       = _RegimeStub(reg_d)

        # Reconstruct recent_closes
        rc = data.get("recent_closes", [])
        self.recent_closes = [Decimal(str(c)) for c in rc] if rc else []

        # Reconstruct timestamp
        ts_str = data.get("bar_timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self.bar_timestamp = ts
        except Exception:
            self.bar_timestamp = datetime.now(timezone.utc)
