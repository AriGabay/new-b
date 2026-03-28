# Learning System Contract
## Phase: 2 — Architecture
## Date: 2026-03-28

---

## Purpose

The learning system enables the trading system to monitor signal performance over time, detect edge decay, update its knowledge base from historical outcomes, and surface failure patterns. It does NOT modify live trading rules autonomously — it generates reports and flags that require human review before any rule change.

**Hard boundary:** The learning system can OBSERVE and REPORT. It cannot CHANGE configuration, signal logic, or risk parameters without explicit human approval.

---

## Architecture

```
[All System Events]
       │
       ▼ (async subscriber)
[JournalWriter] ──writes──► [AppendOnlyJournal (SQLite/Parquet)]
                                        │
                          ┌─────────────┼──────────────┐
                          ▼             ▼              ▼
                   [SignalPerf      [EdgeDecay     [Historian
                    Analyzer]       Detector]       Indexer]
                          │             │              │
                          └─────────────┴──────────────┘
                                        │
                                        ▼
                              [LearningReport (structured)]
                                        │
                               [SummarizerAgent - LLM optional]
                                        │
                                        ▼
                              [Human Review Required]
                                        │
                               [Manual Config Update]
```

---

## 1. Journal Schema (Minimal Phase 2)

### AppendOnlyJournal

Tables (SQLite or DuckDB):

```sql
CREATE TABLE trades (
    journal_id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    logged_at TIMESTAMP NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,       -- 'long' | 'short'
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_price REAL NOT NULL,
    target_price REAL NOT NULL,
    position_size_usd REAL,
    leverage REAL DEFAULT 1.0,
    pnl_usd REAL,
    pnl_r REAL,                    -- P&L in R multiples
    bars_held INTEGER,
    exit_reason TEXT,
    outcome TEXT,                  -- 'win' | 'loss' | 'breakeven' | 'open'
    composite_score REAL,
    primary_signal_type TEXT,
    primary_hypothesis_ref TEXT,   -- e.g., 'H1-001'
    regime_btc_macro TEXT,
    regime_trending INTEGER,       -- boolean as 0/1
    regime_volatility TEXT,
    atr14_at_entry REAL,
    ema200_at_entry REAL,
    is_backtest INTEGER DEFAULT 0,
    backtest_run_id TEXT
);

CREATE TABLE signals (
    journal_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    group_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_subtype TEXT NOT NULL,
    hypothesis_ref TEXT,
    direction TEXT NOT NULL,
    quality_score REAL,
    composite_score REAL,
    was_traded INTEGER DEFAULT 0,  -- boolean
    rejection_reason TEXT,
    is_backtest INTEGER DEFAULT 0
);

CREATE TABLE system_events (
    event_id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL,
    symbol TEXT,
    details_json TEXT,
    severity TEXT DEFAULT 'info'   -- 'info' | 'warning' | 'alert'
);
```

---

## 2. Signal Performance Analyzer

Runs every 100 trades (scheduled). Computes per-hypothesis metrics.

```python
class SignalPerformanceAnalyzer:
    min_sample_size: int = 30  # From Phase 1 OQ-009

    def compute_hypothesis_stats(
        self,
        hypothesis_ref: str,
        lookback_days: int = 365
    ) -> HypothesisPerformanceStats:
        """
        Returns performance stats for a specific hypothesis.
        Requires >= 30 trades to compute (returns None if insufficient).
        """
        trades = self.journal.query(
            hypothesis_ref=hypothesis_ref,
            days=lookback_days,
            is_backtest=False  # Live/shadow only
        )
        if len(trades) < self.min_sample_size:
            return None

        wins = [t for t in trades if t.outcome == "win"]
        losses = [t for t in trades if t.outcome == "loss"]

        return HypothesisPerformanceStats(
            hypothesis_ref=hypothesis_ref,
            sample_size=len(trades),
            win_rate=len(wins) / len(trades),
            avg_win_r=mean(t.pnl_r for t in wins) if wins else 0,
            avg_loss_r=mean(t.pnl_r for t in losses) if losses else 0,
            profit_factor=(
                sum(t.pnl_r for t in wins) /
                abs(sum(t.pnl_r for t in losses))
                if losses else float('inf')
            ),
            sharpe_ratio=self._compute_sharpe(trades),
            max_drawdown=self._compute_max_drawdown(trades),
            avg_bars_held=mean(t.bars_held for t in trades),
            exit_reason_distribution=Counter(t.exit_reason for t in trades),
            regime_breakdown=self._breakdown_by_regime(trades)
        )
```

---

## 3. Edge Decay Detector

Compares recent performance window vs. full history.

```python
class EdgeDecayDetector:
    recent_window: int = 50    # Last 50 trades
    full_window: int = 200     # Full history
    decay_threshold: float = 0.40  # >40% degradation = alert

    def detect(self, hypothesis_ref: str) -> EdgeDecayResult:
        recent_stats = self.analyzer.compute_hypothesis_stats(
            hypothesis_ref, lookback_days=90
        )
        full_stats = self.analyzer.compute_hypothesis_stats(
            hypothesis_ref, lookback_days=730
        )

        if recent_stats is None or full_stats is None:
            return EdgeDecayResult(status="insufficient_data")

        # Compare key metrics
        pf_decay = (full_stats.profit_factor - recent_stats.profit_factor) / full_stats.profit_factor
        wr_decay = (full_stats.win_rate - recent_stats.win_rate) / full_stats.win_rate

        if pf_decay > self.decay_threshold or wr_decay > self.decay_threshold:
            return EdgeDecayResult(
                status="DECAY_DETECTED",
                hypothesis_ref=hypothesis_ref,
                profit_factor_change=pf_decay,
                win_rate_change=wr_decay,
                action_required="Review hypothesis; consider downgrading to research mode",
                recent_stats=recent_stats,
                full_stats=full_stats
            )

        return EdgeDecayResult(status="stable", ...)
```

---

## 4. Historian Indexer

Updates the HistorianAgent's knowledge base with new trade outcomes.

```python
class HistorianIndexer:
    def index_completed_trade(self, trade: TradeJournalEntry) -> None:
        """
        Indexes completed trade by:
        - Pattern type + direction + regime → outcome
        - Useful for HistorianAgent.query() in Entry Group
        """
        self.index.upsert(
            key=(trade.primary_hypothesis_ref,
                 trade.direction,
                 trade.regime_btc_macro,
                 trade.regime_trending),
            value=TradeOutcomeRecord(
                trade_id=trade.trade_id,
                pnl_r=trade.pnl_r,
                outcome=trade.outcome,
                exit_reason=trade.exit_reason,
                bars_held=trade.bars_held,
                timestamp=trade.logged_at
            )
        )

    def query_analogs(
        self,
        hypothesis_ref: str,
        direction: str,
        regime: RegimeContext,
        max_results: int = 10
    ) -> HistoricalAnalog:
        """
        Returns up to max_results analogous trades.
        """
        ...
```

---

## 5. Learning Report Schema

```python
class LearningReport:
    report_id: str
    generated_at: datetime
    period_days: int

    # Per-hypothesis performance
    hypothesis_stats: dict[str, HypothesisPerformanceStats]

    # Decay alerts
    decay_alerts: list[EdgeDecayResult]

    # Portfolio-level metrics
    total_trades: int
    overall_win_rate: float
    overall_profit_factor: float
    overall_sharpe: float
    overall_max_drawdown: float

    # Signal-level insights
    most_profitable_signal_type: str
    least_reliable_signal_type: str
    most_common_exit_reason: str
    regime_performance: dict[str, float]  # regime → avg_r_multiple

    # Recommendations (ADVISORY ONLY - human review required)
    recommendations: list[LearningRecommendation]

class LearningRecommendation:
    recommendation_id: str
    type: str  # "downgrade_to_research" | "increase_confidence_threshold" |
               # "reduce_position_size" | "review_regime_filter"
    target: str  # hypothesis_ref or component name
    reason: str
    supporting_data: dict
    requires_human_approval: bool = True  # Always True
    auto_actionable: bool = False         # Always False in Phase 2
```

---

## 6. Validation Methodology

This implements Phase 1 OQ-016 (anti-p-hacking) and the hypothesis validation decision tree.

```python
class HypothesisValidator:
    """
    Manages the promotion pipeline:
    RESEARCH → SHADOW → LIVE

    Enforces Phase 1's validation decision tree:
    1. IS backtest must pass
    2. Parameter sensitivity must be stable (no single optimal point)
    3. OOS backtest must retain >= 60% of IS performance
    4. Bonferroni-corrected p-value < 0.002 (for 25 hypotheses)
    5. Human sign-off required for promotion
    """

    bonferroni_threshold: float = 0.002  # 0.05 / 25 hypotheses
    oos_retention_minimum: float = 0.60  # OOS must be >= 60% of IS

    def assess_promotion(
        self,
        hypothesis_ref: str,
        is_results: BacktestResult,
        oos_results: BacktestResult
    ) -> PromotionAssessment:
        # Check OOS retention
        oos_pf = oos_results.profit_factor
        is_pf = is_results.profit_factor
        oos_retention = oos_pf / is_pf if is_pf > 0 else 0

        if oos_retention < self.oos_retention_minimum:
            return PromotionAssessment(
                decision="REJECT",
                reason=f"OOS profit_factor {oos_pf:.2f} is only "
                       f"{oos_retention:.0%} of IS {is_pf:.2f} "
                       f"(minimum {self.oos_retention_minimum:.0%})"
            )

        # Statistical significance (simplified; real implementation uses
        # bootstrap or permutation test)
        p_value = self._compute_p_value(oos_results)
        if p_value >= self.bonferroni_threshold:
            return PromotionAssessment(
                decision="REJECT",
                reason=f"p-value {p_value:.4f} >= Bonferroni threshold "
                       f"{self.bonferroni_threshold}"
            )

        return PromotionAssessment(
            decision="CANDIDATE",
            reason="Passes OOS retention and significance tests",
            recommended_mode="shadow",
            requires_human_sign_off=True
        )
```

---

## What the Learning System Can and Cannot Do

| Can Do | Cannot Do |
|---|---|
| Compute performance metrics | Modify signal detection code |
| Detect edge decay | Change risk parameters |
| Surface recommendations | Auto-promote patterns to live |
| Write to journal | Delete journal entries |
| Generate narrative reports (LLM optional) | Override risk vetoes |
| Update HistorianAgent knowledge base | Change scoring weights |
| Flag anomalous trade sequences | Auto-adjust position sizes |
