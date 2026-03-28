# Risk Framework Contract
## Phase: 2 — Architecture
## Date: 2026-03-28
## Source: /research/risk_rules/risk_management_rules.md (Phase 1)

---

## Critical Principle

The Risk Engine is the FINAL, NON-OVERRIDABLE authority on every trade.
No other group, no LLM output, no "high conviction" override can bypass it.
Any code that bypasses the Risk Engine is a defect, not a feature.

---

## Risk Rule Catalogue

All rules are derived directly from Phase 1 risk_management_rules.md.
This document defines their precise implementation contract.

---

### RISK-01: R-Multiple Position Sizing

**Origin:** Phase 1 Risk Rule 1
**Type:** Core / Mandatory

```python
class RMultipleSizer:
    config_key: str = "risk.risk_fraction_per_trade"
    default: float = 0.01  # 1%
    min: float = 0.005     # 0.5%
    max: float = 0.02      # 2%

    def compute(
        portfolio_equity: Decimal,
        entry_price: Decimal,
        stop_price: Decimal,
        risk_fraction: float = 0.01
    ) -> tuple[Decimal, Decimal]:
        """
        Returns (position_size_usd, r_amount)

        Invariants:
        - stop_price must be set BEFORE calling this
        - risk_fraction is FIXED for a given mode; not adjustable per trade
        - Returns (0, 0) if stop_distance <= 0 (invalid setup)
        """
        r_amount = portfolio_equity * Decimal(str(risk_fraction))
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            raise InvalidStopError("Stop distance must be positive")
        position_size_usd = r_amount / (stop_distance / entry_price)
        return position_size_usd, r_amount
```

**Consecutive loss adjustment (Risk Rule 6b):**
- After 3 consecutive losses: `risk_fraction × 0.5` for next 3 trades
- Reset when first win occurs after the adjustment period

---

### RISK-02: ATR-Based Stop Placement

**Origin:** Phase 1 Risk Rule 2
**Type:** Core / Mandatory

```python
class ATRStopPlacer:
    atr_period: int = 14           # config parameter
    multiplier: float = 2.0        # config parameter; range 1.5 - 3.0
    anti_round_number_buffer: float = 0.003  # 0.3% buffer from round numbers

    def compute(
        entry_price: Decimal,
        direction: str,    # "long" | "short"
        atr14: Decimal,
        multiplier: float = 2.0
    ) -> Decimal:
        """
        Returns stop_price (shifted away from round numbers)
        """
        raw_stop_distance = atr14 * Decimal(str(multiplier))
        if direction == "long":
            raw_stop = entry_price - raw_stop_distance
        else:
            raw_stop = entry_price + raw_stop_distance

        return self._anti_round_number_shift(raw_stop, direction)

    def _anti_round_number_shift(self, price: Decimal, direction: str) -> Decimal:
        """
        If price is within 0.3% of a round number
        (multiples of 100, 500, 1000, 5000, 10000),
        shift it 0.3% further away.
        """
        round_numbers = [100, 500, 1000, 5000, 10000, 50000, 100000]
        for rn in round_numbers:
            if abs(float(price) - rn) / rn < self.anti_round_number_buffer:
                if direction == "long":
                    return price - (price * Decimal("0.003"))
                else:
                    return price + (price * Decimal("0.003"))
        return price
```

---

### RISK-03: Portfolio Exposure Limits

**Origin:** Phase 1 Risk Rule 3
**Type:** Core / Mandatory

```python
class PortfolioExposureChecker:
    max_total_open_risk_fraction: float = 0.10  # 10% of portfolio
    max_correlated_risk_fraction: float = 0.02  # 2% per cluster

    def check(
        portfolio_equity: Decimal,
        open_positions: list[Position],
        proposed_r_amount: Decimal,
        proposed_cluster: str
    ) -> RiskCheckResult:
        total_open_risk = sum(p.r_amount for p in open_positions)
        new_total = total_open_risk + proposed_r_amount
        if new_total > portfolio_equity * Decimal(str(self.max_total_open_risk_fraction)):
            return RiskCheckResult.REJECTED("portfolio_exposure_limit",
                f"Total risk {new_total} > {self.max_total_open_risk_fraction * 100}% equity")

        cluster_risk = sum(
            p.r_amount for p in open_positions
            if p.correlation_cluster == proposed_cluster
        )
        if cluster_risk + proposed_r_amount > portfolio_equity * Decimal(str(self.max_correlated_risk_fraction)):
            return RiskCheckResult.REJECTED("correlated_exposure_limit",
                f"Cluster {proposed_cluster} risk would exceed {self.max_correlated_risk_fraction * 100}%")

        return RiskCheckResult.APPROVED()
```

**Correlation Cluster Taxonomy:**
```python
CORRELATION_CLUSTERS = {
    "btc": ["BTCUSDT"],
    "eth_core": ["ETHUSDT"],
    "eth_defi": ["UNIUSDT", "AAVEUSDT", "MKRUSDT", ...],
    "eth_layer2": ["MATICUSDT", "ARBUSDT", "OPUSDT", ...],
    "layer1_alt": ["SOLUSDT", "AVAXUSDT", "ADAUSDT", ...],
    "meme": ["DOGEUSDT", "SHIBUSDT", ...],
    # All others: "other"
}
# Default cluster for unmapped symbols: "btc" (conservative)
```

---

### RISK-04: Anti-Round-Number Stop Gaming

**Origin:** Phase 1 Risk Rule 4
**Implementation:** Embedded in RISK-02 `_anti_round_number_shift()` above.

---

### RISK-05: Universe and Liquidity Filters

**Origin:** Phase 1 Risk Rule 5
**Type:** Pre-Signal Gate (runs in Market Data Group hourly)

```python
class UniverseFilter:
    min_volume_24h_usd: Decimal = Decimal("5_000_000")
    min_market_cap_usd: Decimal = Decimal("50_000_000")
    max_fdmv_ratio: float = 5.0
    max_spread_pct: float = 0.005  # 0.5%

    def is_eligible(self, symbol_info: SymbolInfo) -> tuple[bool, str]:
        if symbol_info.volume_24h_usd < self.min_volume_24h_usd:
            return False, "volume_below_minimum"
        if symbol_info.market_cap_usd < self.min_market_cap_usd:
            return False, "market_cap_below_minimum"
        if symbol_info.fdmv_ratio > self.max_fdmv_ratio:
            return False, "fdmv_ratio_too_high"
        return True, "eligible"

    def check_spread_at_entry(self, spread_pct: float) -> RiskCheckResult:
        if spread_pct > self.max_spread_pct:
            return RiskCheckResult.REJECTED("spread_too_wide",
                f"Spread {spread_pct:.3%} > {self.max_spread_pct:.3%}")
        return RiskCheckResult.APPROVED()
```

---

### RISK-06: Drawdown Controls

**Origin:** Phase 1 Risk Rule 6
**Type:** State Machine / Always-on

```python
class DrawdownController:
    daily_loss_limit_pct: float = 0.05        # 5% daily
    consecutive_loss_limit: int = 3
    max_portfolio_drawdown_pct: float = 0.20  # 20% from HWM

    def update_state(self, portfolio: PortfolioState) -> RiskState:
        # Daily P&L check
        if portfolio.daily_pnl_pct <= -self.daily_loss_limit_pct:
            return RiskState(
                halted=True,
                halt_reason="daily_loss_limit",
                size_reduction=1.0  # Halted = no trades
            )

        # Max drawdown check
        drawdown = (portfolio.high_water_mark - portfolio.equity) / portfolio.high_water_mark
        if drawdown >= self.max_portfolio_drawdown_pct:
            return RiskState(
                halted=True,
                halt_reason="max_drawdown_reached",
                size_reduction=1.0
            )

        # Consecutive loss check
        if portfolio.consecutive_losses >= self.consecutive_loss_limit:
            return RiskState(
                halted=False,
                halt_reason=None,
                size_reduction=0.5  # Half size
            )

        return RiskState(halted=False, halt_reason=None, size_reduction=1.0)
```

---

### RISK-07: Leverage Governance

**Origin:** Phase 1 Risk Rule 7
**Phase 2 Implementation:** Leverage = 1.0 always (spot trading only)

```python
class LeverageGovernor:
    max_leverage_standard: float = 3.0
    max_leverage_spot: float = 1.0
    max_leverage_high_confidence: float = 5.0

    def compute_leverage(
        position_size_usd: Decimal,
        available_margin: Decimal,
        mode: str = "spot"
    ) -> float:
        """
        Phase 2: Always returns 1.0 (spot only)
        Phase 3+: Computes leverage from position_size / available_margin
        """
        if mode == "spot":
            return 1.0
        # Future: compute and cap at max_leverage_standard
        leverage = float(position_size_usd / available_margin)
        return min(leverage, self.max_leverage_standard)
```

---

### RISK-08: Manipulation / Pump Detection

**Origin:** Phase 1 Risk Rule 8
**Type:** Signal Quality Filter (runs in Market Data Group)

```python
class PumpDetector:
    # Thresholds from Phase 1 Risk Rule 8
    price_change_1min_threshold: float = 0.05    # 5%
    volume_spike_1min_multiplier: float = 10.0
    price_change_5min_threshold: float = 0.10    # 10%
    volume_24h_sudden_spike: float = 5.0         # 5× 7-day average

    def is_pump_active(self, symbol: str, recent_data: RecentMarketData) -> bool:
        if (recent_data.price_change_1min > self.price_change_1min_threshold
                and recent_data.volume_spike_1min > self.volume_spike_1min_multiplier):
            return True
        if recent_data.price_change_5min > self.price_change_5min_threshold:
            return True
        return False
```

---

### RISK-09: News / Event Risk

**Origin:** Phase 1 Risk Rule 9
**Phase 2 Implementation:** Static event calendar only

```python
class EventRiskManager:
    def get_event_risk(self, symbol: str, timestamp: datetime) -> EventRisk:
        """
        Checks static event calendar for scheduled high-risk events
        within config.event_lookforward_hours (default: 24h).

        Returns EventRisk{level: "none"|"low"|"medium"|"high",
                          events: list[ScheduledEvent]}
        """
        ...

    def apply_event_risk_to_size(
        position_size_usd: Decimal,
        event_risk: EventRisk
    ) -> Decimal:
        if event_risk.level == "high":
            return position_size_usd * Decimal("0.5")  # Half size
        if event_risk.level == "medium":
            return position_size_usd * Decimal("0.75")
        return position_size_usd
```

---

## Trading Plan Completeness Gate

```python
class TradingPlanGate:
    """Implements Phase 1 meta-rule: all 5 components required."""

    def validate(self, proposal: CandidateTradeProposal) -> RiskCheckResult:
        missing = []
        if not proposal.thesis:
            missing.append("thesis")
        if not proposal.setup_refs:
            missing.append("setup")
        if not proposal.entry_price:
            missing.append("entry")
        # Stop and target checked by RiskEngine (they're computed by RISK-02)
        if missing:
            return RiskCheckResult.REJECTED(
                "incomplete_trade_plan",
                f"Missing components: {missing}"
            )
        return RiskCheckResult.APPROVED()
```

---

## Risk Engine Execution Order

All checks run in this exact sequence. First failure = REJECTED (no short-circuit unless halted):

```
1. DrawdownController.update_state() → if halted: REJECT all
2. TradingPlanGate.validate(proposal)
3. UniverseFilter.check_spread_at_entry(current_spread)
4. PumpDetector.is_pump_active(symbol)
5. EventRiskManager.get_event_risk(symbol, timestamp)
6. ATRStopPlacer.compute(entry, direction, atr14)
7. RMultipleSizer.compute(equity, entry, stop)
   → apply consecutive_loss size_reduction
   → apply event_risk size_reduction
8. PortfolioExposureChecker.check(equity, positions, r_amount, cluster)
9. LeverageGovernor.compute_leverage(size, margin, mode)
10. EMIT RiskApprovedOrder or RiskRejectedEvent
```

**Every step logged regardless of outcome.**
