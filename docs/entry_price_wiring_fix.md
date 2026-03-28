# Entry Price Wiring Fix

**Phase:** 3.5 Stabilization
**Date:** 2026-03-28
**File:** `src/groups/entry/group.py`, `src/core/state.py`, `src/groups/market_data/group.py`

---

## What Was Broken

`EntryGroup._build_proposal()` needed a valid entry price to construct a
`CandidateTradeProposal`. The original code used:

```python
entry_price = getattr(self.state, "last_close", None)
```

`last_close` never existed as an attribute on `SystemState`. The fallback
was to read `close` from signal metadata, but upstream groups do not reliably
populate signal metadata with the bar's close price. The result was that
`entry_price` could silently remain `Decimal("0")`, and a proposal with
`entry_price=0` would be published — poisoning downstream risk sizing
(R-multiple computation, position sizing) and the journal record.

---

## What Was Fixed

### 1. `SystemState` — added `last_close_by_symbol`

`src/core/state.py` now contains:

```python
self.last_close_by_symbol: dict[str, Decimal] = {}
```

and the async writer method:

```python
async def update_last_close(self, symbol: str, price: Decimal) -> None:
    """Record the latest close price for a symbol. Called by MarketDataGroup."""
    async with self._lock:
        self.last_close_by_symbol[symbol] = price
```

The dict is keyed by symbol (e.g. `"BTCUSDT"`) and updated under the
existing `asyncio.Lock` to be consistent with all other state mutations.

### 2. `MarketDataGroup.fetch_and_process()` — populates state before publishing

`src/groups/market_data/group.py` calls `state.update_last_close` immediately
after a successful `FeatureComputer.compute()` call and before publishing
`FeatureReadyEvent`:

```python
if fv is not None:
    await self.state.update_last_close(symbol, fv.close)
    await self.bus.publish(
        FeatureReadyEvent(source=self.group_id.value, features=fv)
    )
```

This guarantees that when `FeatureReadyEvent` is dispatched to downstream
groups, `state.last_close_by_symbol[symbol]` already holds the bar's close.

### 3. `EntryGroup._build_proposal()` — two-source resolution with fail-loud abort

The build logic now follows a strict resolution order:

**Source 1:** `state.last_close_by_symbol.get(symbol, Decimal("0"))`
Set by `MarketDataGroup` on every processed bar. This is the canonical source.

**Source 2:** Signal metadata fallback — iterates `primary_signals` looking
for `s.metadata["close"]`. This covers edge cases where a signal is emitted
with close data in metadata but `fetch_and_process()` has not yet run for
this symbol on this bar.

**Source 3 (abort):** If both sources return zero, the method logs a `WARNING`
and returns `None`. The calling method checks for `None` and skips publishing:

```python
if entry_price == Decimal("0"):
    logger.warning(
        "EntryGroup: entry_price unavailable for %s — proposal aborted. "
        "Ensure MarketDataGroup.fetch_and_process() runs before EntryGroup "
        "receives bundles (state.last_close_by_symbol not populated).",
        symbol,
    )
    return None
```

No proposal can be published without a valid entry price.

---

## Runtime Event Flow

The normal runtime sequence guarantees entry price is populated before
`EntryGroup` evaluates:

```
MarketDataGroup.fetch_and_process()
  → FeatureComputer.compute()
  → state.update_last_close(symbol, fv.close)   ← price stored here
  → bus.publish(FeatureReadyEvent)
      → IndicatorsGroup._handle_event()
          → bus.publish(GroupSignalEvent)
              → EntryGroup._collect_bundle()
                  → EntryGroup._evaluate_trade_opportunity()
                      → EntryGroup._build_proposal()
                          → state.last_close_by_symbol[symbol]  ← reads here
```

Because EventBus dispatches subscribers sequentially (asyncio, not threading),
`update_last_close` completes before `FeatureReadyEvent` is received by any
downstream subscriber. The ordering guarantee holds.

---

## Remaining Limitation

`startup_load()` in `MarketDataGroup` does **not** call `update_last_close`.
It fetches historical bars and computes `FeatureVector` objects to warm up the
rolling buffer, but it does not write to `state.last_close_by_symbol`.

Consequence: on the very first call to `fetch_and_process()` after startup,
`last_close_by_symbol` is populated. If `EntryGroup` somehow receives a
`GroupSignalEvent` before `fetch_and_process()` runs at least once (which
would require another group to publish signals independently before any bar
is processed via `fetch_and_process()`), the abort path will trigger and no
proposal will be published. This is the safe failure mode — it will log a
WARNING but not crash and not produce a zero-price proposal.

In the current runtime (`main_btc.py`), `startup_load()` runs first, then
`fetch_and_process()` is called in the polling loop. `EntryGroup` only
receives bundles after `fetch_and_process()` has run at least once. The
one-bar lag is therefore not a practical issue in the current runner, but
it is a latent risk if the startup sequence is reordered.
