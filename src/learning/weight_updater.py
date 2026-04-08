"""
EvaluatorWeightUpdater: computes Sharpe-based weights for all panel evaluators.

Algorithm:
  For each evaluator, using only approved trades (vote='approve'):
    1. Compute E[R] = mean(pnl_r)
    2. Compute σ[R] = stddev(pnl_r)
    3. Compute Sharpe[R] = E[R] / σ[R]
    4. Compute 95% CI: E[R] ± 1.96 × (σ[R] / √N)
    5. If N < MIN_APPROVALS or CI crosses zero: weight = 1.0 (fallback, no adjustment)
    6. Else: weight = clamp(Sharpe[R], MIN_WEIGHT, MAX_WEIGHT)

Weights are saved to data/evaluator_weights.json and loaded by
TraderEvaluatorPanel._load_weights() for weighted_avg_score computation.

Anti-overfitting guards:
  - MIN_APPROVALS = 30: never adjust weights on fewer than 30 approved trades
  - 95% CI significance gate: both tails of CI must be same sign (CI doesn't cross 0)
  - Weight clamped to [0.1, 3.0]: no evaluator is silenced or trusted absolutely

Source: /docs/learning_logic.md (Phase 4 — Evaluator Calibration)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_APPROVALS  = 30     # minimum approved trades to compute significance
MIN_WEIGHT     = 0.1    # floor: evaluator is always heard (just quieter)
MAX_WEIGHT     = 3.0    # ceiling: no single evaluator dominates
FALLBACK_WEIGHT = 1.0   # used when CI is not significant or N < MIN_APPROVALS
CI_Z           = 1.96   # 95% confidence interval z-score

DEFAULT_WEIGHTS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "evaluator_weights.json"
)


class EvaluatorWeightUpdater:
    """
    Computes Sharpe-based evaluator weights from the learning DB and
    saves them to JSON for panel consumption.

    Usage:
        updater = EvaluatorWeightUpdater()
        weights = updater.compute_from_history("data/backtest_learning.db")
        updater.save_weights(weights)
        updater.print_report(weights)
    """

    def compute_from_history(
        self,
        db_path: str,
        min_approvals: int = MIN_APPROVALS,
    ) -> dict[str, float]:
        """
        Read trader_reviews + outcome_attributions from the learning DB,
        compute per-evaluator Sharpe weights, and return a name→weight dict.

        Returns a dict where missing evaluators default to FALLBACK_WEIGHT.
        """
        if not os.path.exists(db_path):
            logger.warning("Weight updater: DB not found at %s — returning fallback weights.", db_path)
            return {}

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        weights: dict[str, float] = {}

        try:
            # Query: per-evaluator approved-trade pnl_r values
            rows = conn.execute("""
                SELECT
                    tr.trader_name,
                    oa.pnl_r
                FROM trader_reviews tr
                JOIN outcome_attributions oa ON tr.trade_id = oa.trade_id
                WHERE tr.vote = 'approve'
                  AND tr.trade_id IS NOT NULL
                  AND oa.pnl_r IS NOT NULL
                ORDER BY tr.trader_name
            """).fetchall()

            # Group pnl_r values per evaluator
            evaluator_pnls: dict[str, list[float]] = {}
            for row in rows:
                name = row["trader_name"]
                pnl_r = row["pnl_r"]
                if name not in evaluator_pnls:
                    evaluator_pnls[name] = []
                evaluator_pnls[name].append(float(pnl_r))

            # Compute weight per evaluator
            for name, pnls in evaluator_pnls.items():
                n = len(pnls)
                if n < min_approvals:
                    weights[name] = FALLBACK_WEIGHT
                    logger.debug(
                        "  %s: N=%d < %d (fallback weight=%.1f)",
                        name, n, min_approvals, FALLBACK_WEIGHT,
                    )
                    continue

                mean_r = sum(pnls) / n
                variance_r = sum((x - mean_r) ** 2 for x in pnls) / max(1, n - 1)
                stddev_r = math.sqrt(max(0.0, variance_r))

                if stddev_r == 0:
                    # Zero variance: perfectly consistent (or only one outcome)
                    weights[name] = MAX_WEIGHT if mean_r > 0 else MIN_WEIGHT
                    continue

                sharpe_r = mean_r / stddev_r

                # 95% CI significance gate
                se = stddev_r / math.sqrt(n)
                ci_low  = mean_r - CI_Z * se
                ci_high = mean_r + CI_Z * se
                significant = (ci_low > 0) or (ci_high < 0)   # CI doesn't cross zero

                if not significant:
                    weights[name] = FALLBACK_WEIGHT
                    logger.debug(
                        "  %s: CI [%.3f, %.3f] crosses zero — fallback weight",
                        name, ci_low, ci_high,
                    )
                else:
                    weight = max(MIN_WEIGHT, min(MAX_WEIGHT, sharpe_r))
                    weights[name] = weight

        except Exception as exc:
            logger.error("EvaluatorWeightUpdater: DB query failed: %s", exc)
        finally:
            conn.close()

        logger.info(
            "EvaluatorWeightUpdater: computed weights for %d evaluators "
            "from %d approve records in %s",
            len(weights), len(rows) if "rows" in dir() else 0, db_path,
        )
        return weights

    def save_weights(
        self,
        weights: dict[str, float],
        path: Optional[str] = None,
    ) -> str:
        """
        Save weights to JSON. Returns the path written.

        JSON format:
            {
                "_meta": {"updated_at": "...", "evaluator_count": N},
                "TrendFollowing": 1.23,
                "Momentum": 0.87,
                ...
            }
        """
        out_path = path or DEFAULT_WEIGHTS_PATH
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        payload: dict = {
            "_meta": {
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "evaluator_count": len(weights),
                "min_approvals": MIN_APPROVALS,
                "ci_z": CI_Z,
                "weight_range": [MIN_WEIGHT, MAX_WEIGHT],
                "fallback_weight": FALLBACK_WEIGHT,
            }
        }
        payload.update(weights)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        logger.info("EvaluatorWeightUpdater: weights saved → %s", out_path)
        return out_path

    def load_weights(
        self,
        path: Optional[str] = None,
    ) -> dict[str, float]:
        """
        Load weights from JSON. Returns empty dict if file doesn't exist.
        Filters out the '_meta' key automatically.
        """
        in_path = path or DEFAULT_WEIGHTS_PATH
        if not os.path.exists(in_path):
            logger.debug("EvaluatorWeightUpdater: weights file not found at %s", in_path)
            return {}

        try:
            with open(in_path, encoding="utf-8") as f:
                data = json.load(f)
            weights = {k: float(v) for k, v in data.items() if not k.startswith("_")}
            logger.info(
                "EvaluatorWeightUpdater: loaded %d weights from %s",
                len(weights), in_path,
            )
            return weights
        except Exception as exc:
            logger.warning("EvaluatorWeightUpdater: failed to load weights: %s", exc)
            return {}

    def print_report(
        self,
        weights: dict[str, float],
        db_path: Optional[str] = None,
        min_approvals: int = MIN_APPROVALS,
    ) -> None:
        """
        Print a formatted ranking table of evaluator weights.

        If db_path is provided, also shows N, E[R], σ[R], Sharpe, and CI.
        """
        sep = "=" * 72
        print(sep)
        print("  EVALUATOR WEIGHT REPORT")
        if db_path and os.path.exists(db_path):
            print(f"  DB: {db_path}")
        print(f"  Significance gate: 95% CI (z={CI_Z}), min N={min_approvals}")
        print(sep)

        if not weights:
            print("  No weights computed yet — run offline learning loop first.")
            print(sep)
            return

        # Optionally fetch stats from DB for richer output
        stats: dict[str, dict] = {}
        if db_path and os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT
                        tr.trader_name,
                        COUNT(*) AS n,
                        AVG(oa.pnl_r) AS mean_r,
                        AVG(oa.pnl_r * oa.pnl_r) - AVG(oa.pnl_r) * AVG(oa.pnl_r) AS var_r
                    FROM trader_reviews tr
                    JOIN outcome_attributions oa ON tr.trade_id = oa.trade_id
                    WHERE tr.vote = 'approve'
                      AND tr.trade_id IS NOT NULL
                      AND oa.pnl_r IS NOT NULL
                    GROUP BY tr.trader_name
                """).fetchall()
                conn.close()
                for row in rows:
                    n = row["n"]
                    mean_r = row["mean_r"] or 0.0
                    var_r = max(0.0, row["var_r"] or 0.0)
                    std_r = math.sqrt(var_r)
                    sharpe = mean_r / std_r if std_r > 0 else 0.0
                    se = std_r / math.sqrt(max(1, n))
                    ci_low = mean_r - CI_Z * se
                    ci_high = mean_r + CI_Z * se
                    stats[row["trader_name"]] = {
                        "n": n,
                        "mean_r": mean_r,
                        "std_r": std_r,
                        "sharpe": sharpe,
                        "ci_low": ci_low,
                        "ci_high": ci_high,
                        "significant": (ci_low > 0) or (ci_high < 0),
                    }
            except Exception as exc:
                logger.warning("print_report: DB stats failed: %s", exc)

        sorted_items = sorted(weights.items(), key=lambda x: -x[1])

        if stats:
            print(f"  {'Evaluator':<28} {'N':>5} {'E[R]':>7} {'σ[R]':>7} {'Sharpe':>8} {'95% CI':>18} {'Weight':>7}")
            print("  " + "-" * 70)
            for name, weight in sorted_items:
                s = stats.get(name)
                if s:
                    ci_str = f"[{s['ci_low']:+.3f},{s['ci_high']:+.3f}]"
                    sig = "✓" if s["significant"] else "—"
                    print(
                        f"  {name:<28} {s['n']:>5} {s['mean_r']:>+7.3f} {s['std_r']:>7.3f} "
                        f"{s['sharpe']:>+8.3f} {ci_str:>18} {weight:>6.2f}×  {sig}"
                    )
                else:
                    print(f"  {name:<28} {'?':>5} {'?':>7} {'?':>7} {'?':>8} {'?':>18} {weight:>6.2f}×")
        else:
            print(f"  {'Evaluator':<28} {'Weight':>7}  {'Change':>8}")
            print("  " + "-" * 46)
            for name, weight in sorted_items:
                delta = weight - FALLBACK_WEIGHT
                bar = "+" * int(max(0, weight - 1.0) * 5) if weight > 1.0 else "-" * int(max(0, 1.0 - weight) * 5)
                print(f"  {name:<28} {weight:>6.2f}×  {delta:>+7.2f}  {bar}")

        print(sep)
        effective = sum(1 for w in weights.values() if w != FALLBACK_WEIGHT)
        print(f"  Evaluators with adjusted weight: {effective}/{len(weights)}")
        print(sep)
