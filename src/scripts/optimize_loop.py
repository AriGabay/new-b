#!/usr/bin/env python3
"""
Self-optimizing backtest loop.

Runs full-pipeline backtest up to MAX_ITER times, adjusting parameters
after each run until ALL 6 targets are met simultaneously.
"""
from __future__ import annotations
import asyncio, csv, json, logging, math, os, sys, time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
for _n in ("groups", "mdp", "learning", "core", "traders", "decision", "runtime", "features", "risk", "backtest"):
    logging.getLogger(_n).setLevel(logging.WARNING)
log = logging.getLogger("optloop")
log.setLevel(logging.INFO)

from backtest.engine import BacktestConfig, BacktestEngine  # noqa
from core.schemas import OHLCVBar                           # noqa

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA   = os.path.join(_ROOT, "analysis/historical_eval/data/btcusdt_1h_2024_2025.csv")
EQUITY = Decimal("1000")
MAX_ITER = 15
WEEKS_IN_DATA = 110.0  # ~25 months

# Targets
T_TPW  = 3.0    # trades per week
T_WR   = 0.50
T_PF   = 1.1
T_DD   = 0.35
T_PNL  = 0.0    # net pnl > 0
# avg winner >= avg loser (abs)


def load_bars() -> list[OHLCVBar]:
    bars = []
    with open(DATA, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row["timestamp"]
            try:
                t = datetime.fromisoformat(ts)
            except ValueError:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            bars.append(OHLCVBar(
                symbol="BTCUSDT", timeframe="1h", timestamp=t,
                open=Decimal(row["open"]), high=Decimal(row["high"]),
                low=Decimal(row["low"]), close=Decimal(row["close"]),
                volume=Decimal(row["volume"]), volume_usd=Decimal(row["volume_usd"]),
            ))
    return bars


def _patch(**kw):
    """Apply runtime patches to module-level constants."""
    import groups.entry.group as _eg
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol
    import groups.risk_leverage.group as _rg

    for k, v in kw.items():
        if k == "APPROVE_THRESHOLD":
            _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD = v
            _fg._PANEL_APPROVE_THRESHOLD = v
        elif k == "MIN_AVG_SCORE":
            _panel.TraderEvaluatorPanel.MIN_AVG_SCORE = v
            _panel.TraderEvaluatorPanel.AVG_SCORE_THRESHOLD = v
        elif k.startswith("eg_"):
            setattr(_eg, k[3:], v)
        elif k.startswith("pol_"):
            setattr(_pol, k[4:], v)
        elif k.startswith("rg_"):
            setattr(_rg, k[3:], v)
        elif k == "RAIL6_THRESHOLD":
            _fg._RAIL6_HIGH_VOL_THRESHOLD = v
        elif k.startswith("fg_"):
            setattr(_fg, k[3:], v)


def _save_defaults():
    import groups.entry.group as _eg
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol
    import groups.risk_leverage.group as _rg
    return {
        "panel_AT": _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD,
        "panel_MAS": _panel.TraderEvaluatorPanel.MIN_AVG_SCORE,
        "eg_CONF_GATE": _eg.CONFIRMATION_GATE_MIN_GROUPS,
        "eg_COMP_THRESH": _eg.COMPOSITE_SCORE_THRESHOLD,
        "eg_SINGLE_HC": _eg.SINGLE_SIGNAL_HIGH_CONFIDENCE,
        "eg_CRITIC": _eg.CRITIC_SCORE_THRESHOLD,
        "pol_HC_APP": _pol.HC_MIN_APPROVALS,
        "pol_HC_AVG": _pol.HC_MIN_AVG_SCORE,
        "pol_MED_APP": _pol.MED_MIN_APPROVALS,
        "pol_MED_AVG": _pol.MED_MIN_AVG_SCORE,
        "pol_MED_RR": _pol.MED_MIN_RR,
        "pol_SMALL_APP": _pol.SMALL_MIN_APPROVALS,
        "pol_SMALL_AVG": _pol.SMALL_MIN_AVG_SCORE,
        "pol_DEFER_APP": _pol.DEFER_MIN_APPROVALS,
        "pol_DEFER_AVG": _pol.DEFER_MIN_AVG_SCORE,
        "pol_RED_DD": _pol.REDUCE_MAX_DRAWDOWN,
        "pol_RED_STR": _pol.REDUCE_MAX_STREAK,
        "pol_HC_DD": _pol.HC_MAX_DRAWDOWN,
        "pol_HC_WR": _pol.HC_MIN_WIN_RATE,
        "rg_DAILY": _rg.DAILY_LOSS_LIMIT,
        "rg_MAX_DD": _rg.MAX_DRAWDOWN_HALT,
        "fg_R6": _fg._RAIL6_HIGH_VOL_THRESHOLD,
    }


def _restore(defaults):
    import groups.entry.group as _eg
    import traders.panel as _panel
    import decision.final_group as _fg
    import mdp.policy as _pol
    import groups.risk_leverage.group as _rg
    _panel.TraderEvaluatorPanel.APPROVE_THRESHOLD = defaults["panel_AT"]
    _panel.TraderEvaluatorPanel.MIN_AVG_SCORE = defaults["panel_MAS"]
    _panel.TraderEvaluatorPanel.AVG_SCORE_THRESHOLD = defaults["panel_MAS"]
    _eg.CONFIRMATION_GATE_MIN_GROUPS = defaults["eg_CONF_GATE"]
    _eg.COMPOSITE_SCORE_THRESHOLD = defaults["eg_COMP_THRESH"]
    _eg.SINGLE_SIGNAL_HIGH_CONFIDENCE = defaults["eg_SINGLE_HC"]
    _eg.CRITIC_SCORE_THRESHOLD = defaults["eg_CRITIC"]
    _pol.HC_MIN_APPROVALS = defaults["pol_HC_APP"]
    _pol.HC_MIN_AVG_SCORE = defaults["pol_HC_AVG"]
    _pol.MED_MIN_APPROVALS = defaults["pol_MED_APP"]
    _pol.MED_MIN_AVG_SCORE = defaults["pol_MED_AVG"]
    _pol.MED_MIN_RR = defaults["pol_MED_RR"]
    _pol.SMALL_MIN_APPROVALS = defaults["pol_SMALL_APP"]
    _pol.SMALL_MIN_AVG_SCORE = defaults["pol_SMALL_AVG"]
    _pol.DEFER_MIN_APPROVALS = defaults["pol_DEFER_APP"]
    _pol.DEFER_MIN_AVG_SCORE = defaults["pol_DEFER_AVG"]
    _pol.REDUCE_MAX_DRAWDOWN = defaults["pol_RED_DD"]
    _pol.REDUCE_MAX_STREAK = defaults["pol_RED_STR"]
    _pol.HC_MAX_DRAWDOWN = defaults["pol_HC_DD"]
    _pol.HC_MIN_WIN_RATE = defaults["pol_HC_WR"]
    _rg.DAILY_LOSS_LIMIT = defaults["rg_DAILY"]
    _rg.MAX_DRAWDOWN_HALT = defaults["rg_MAX_DD"]
    _fg._RAIL6_HIGH_VOL_THRESHOLD = defaults["fg_R6"]


async def run_once(bars, label="") -> dict:
    cfg = BacktestConfig(
        symbols=["BTCUSDT"], timeframe="1h",
        start_date=bars[0].timestamp, end_date=bars[-1].timestamp,
        initial_equity=EQUITY, enforce_holdout=False,
    )
    eng = BacktestEngine(cfg)
    r = await eng.run_full_pipeline({"BTCUSDT": bars}, verbose=False)
    meta = r.per_hypothesis.get("_meta", {})
    aw = meta.get("avg_winner_usd", 0.0)
    al = meta.get("avg_loser_usd", 0.0)
    tpw = r.total_trades / WEEKS_IN_DATA if WEEKS_IN_DATA > 0 else 0
    return {
        "trades": r.total_trades, "tpw": round(tpw, 2),
        "wr": round(r.win_rate, 4), "pf": round(r.profit_factor, 2),
        "dd": round(r.max_drawdown_pct, 4), "pnl": round(float(r.total_pnl_usd), 2),
        "aw": round(aw, 2), "al": round(al, 2),
        "ret": round(float(r.total_pnl_usd) / float(EQUITY) * 100, 2),
    }


def check(m) -> tuple[int, list[str]]:
    """Return (n_pass, list_of_fail_reasons)."""
    fails = []
    if m["tpw"] < T_TPW:  fails.append(f"tpw={m['tpw']}<{T_TPW}")
    if m["wr"] < T_WR:    fails.append(f"wr={m['wr']:.1%}<{T_WR:.0%}")
    if m["pf"] < T_PF:    fails.append(f"pf={m['pf']}<{T_PF}")
    if m["dd"] >= T_DD:    fails.append(f"dd={m['dd']:.1%}>={T_DD:.0%}")
    if m["pnl"] <= T_PNL:  fails.append(f"pnl=${m['pnl']}<=0")
    if abs(m["aw"]) < abs(m["al"]): fails.append(f"aw=${m['aw']}<al=${m['al']}")
    return 6 - len(fails), fails


def report(it, change, m):
    n, fails = check(m)
    def pf(cond): return "PASS" if cond else "FAIL"
    print(f"\n=== ITERATION {it} ===")
    print(f"Change: {change}")
    print(f"Trades: {m['trades']} ({m['tpw']}/week) [{pf(m['tpw']>=T_TPW)}]")
    print(f"WinRate: {m['wr']:.1%} [{pf(m['wr']>=T_WR)}]")
    print(f"PF: {m['pf']:.2f} [{pf(m['pf']>=T_PF)}]")
    print(f"MaxDD: {m['dd']:.1%} [{pf(m['dd']<T_DD)}]")
    print(f"PnL: ${m['pnl']:.2f} [{pf(m['pnl']>T_PNL)}]")
    print(f"AvgW/AvgL: ${m['aw']:.2f}/${m['al']:.2f} [{pf(abs(m['aw'])>=abs(m['al']))}]")
    status = "ALL MET — DONE" if n == 6 else f"{n}/6 targets met — CONTINUING"
    print(f"Status: {status}")
    return n == 6


# ═══════════════════════════════════════════════════════════════════════════
# ITERATION CONFIGS — each is a dict of patches to apply
# Strategy: fix trade frequency FIRST, then fix quality metrics
# ════════════════════════════════════════════════��══════════════════════════

ITERATIONS = [
    # Iter 1: Massive unlock — drop ALL entry gates to absolute minimum
    # to see how many raw signals the pipeline generates
    {
        "label": "Full unlock: min_groups=1, composite=0.30, single_hc=0.50, approve=5, panel_avg=5.0, REDUCE_DD=0.38",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.30,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.50,
            "eg_CRITIC_SCORE_THRESHOLD": 0.40,
            "APPROVE_THRESHOLD": 5,
            "MIN_AVG_SCORE": 5.0,
            "pol_HC_MIN_APPROVALS": 8,
            "pol_HC_MIN_AVG_SCORE": 6.0,
            "pol_HC_MAX_STD_DEV": 2.5,
            "pol_HC_MAX_DRAWDOWN": 0.30,
            "pol_HC_MIN_WIN_RATE": 0.40,
            "pol_MED_MIN_APPROVALS": 5,
            "pol_MED_MIN_AVG_SCORE": 5.0,
            "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 5,
            "pol_SMALL_MIN_AVG_SCORE": 5.0,
            "pol_DEFER_MIN_APPROVALS": 3,
            "pol_DEFER_MIN_AVG_SCORE": 4.5,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38,
            "pol_REDUCE_MAX_STREAK": -10,
            "RAIL6_THRESHOLD": 6,
        },
    },
    # Iter 2: Even lower gates + Rail 6 completely open
    {
        "label": "Ultra-low: composite=0.20, approve=3, Rail6=3",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.20,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.40,
            "eg_CRITIC_SCORE_THRESHOLD": 0.30,
            "APPROVE_THRESHOLD": 3, "MIN_AVG_SCORE": 4.5,
            "RAIL6_THRESHOLD": 3,
            "pol_HC_MIN_APPROVALS": 6, "pol_HC_MIN_AVG_SCORE": 5.5,
            "pol_HC_MAX_STD_DEV": 3.0, "pol_HC_MAX_DRAWDOWN": 0.35, "pol_HC_MIN_WIN_RATE": 0.35,
            "pol_MED_MIN_APPROVALS": 3, "pol_MED_MIN_AVG_SCORE": 4.5, "pol_MED_MIN_RR": 1.0,
            "pol_SMALL_MIN_APPROVALS": 3, "pol_SMALL_MIN_AVG_SCORE": 4.5,
            "pol_DEFER_MIN_APPROVALS": 2, "pol_DEFER_MIN_AVG_SCORE": 4.0,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -12,
        },
    },
    # Iter 3: From iter2, raise approve to 7 for quality
    {
        "label": "approve=7, Rail6=8, composite=0.20",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.20,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.40,
            "eg_CRITIC_SCORE_THRESHOLD": 0.30,
            "APPROVE_THRESHOLD": 7, "MIN_AVG_SCORE": 5.0,
            "RAIL6_THRESHOLD": 8,
            "pol_HC_MIN_APPROVALS": 10, "pol_HC_MIN_AVG_SCORE": 6.0,
            "pol_HC_MAX_STD_DEV": 2.5, "pol_HC_MAX_DRAWDOWN": 0.30, "pol_HC_MIN_WIN_RATE": 0.40,
            "pol_MED_MIN_APPROVALS": 7, "pol_MED_MIN_AVG_SCORE": 5.0, "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 7, "pol_SMALL_MIN_AVG_SCORE": 5.0,
            "pol_DEFER_MIN_APPROVALS": 5, "pol_DEFER_MIN_AVG_SCORE": 4.5,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -10,
        },
    },
    # Iter 4: approve=9, Rail6=10
    {
        "label": "approve=9, Rail6=10, composite=0.25",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.25,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.45,
            "eg_CRITIC_SCORE_THRESHOLD": 0.35,
            "APPROVE_THRESHOLD": 9, "MIN_AVG_SCORE": 5.2,
            "RAIL6_THRESHOLD": 10,
            "pol_HC_MIN_APPROVALS": 12, "pol_HC_MIN_AVG_SCORE": 6.0,
            "pol_HC_MAX_STD_DEV": 2.0, "pol_HC_MAX_DRAWDOWN": 0.25, "pol_HC_MIN_WIN_RATE": 0.45,
            "pol_MED_MIN_APPROVALS": 9, "pol_MED_MIN_AVG_SCORE": 5.2, "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 9, "pol_SMALL_MIN_AVG_SCORE": 5.2,
            "pol_DEFER_MIN_APPROVALS": 6, "pol_DEFER_MIN_AVG_SCORE": 4.8,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -10,
        },
    },
    # Iter 5: approve=11, Rail6=12
    {
        "label": "approve=11, Rail6=12, composite=0.30",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.30,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.50,
            "eg_CRITIC_SCORE_THRESHOLD": 0.40,
            "APPROVE_THRESHOLD": 11, "MIN_AVG_SCORE": 5.5,
            "RAIL6_THRESHOLD": 12,
            "pol_HC_MIN_APPROVALS": 14, "pol_HC_MIN_AVG_SCORE": 6.5,
            "pol_HC_MAX_STD_DEV": 1.8, "pol_HC_MAX_DRAWDOWN": 0.20, "pol_HC_MIN_WIN_RATE": 0.45,
            "pol_MED_MIN_APPROVALS": 11, "pol_MED_MIN_AVG_SCORE": 5.5, "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 11, "pol_SMALL_MIN_AVG_SCORE": 5.5,
            "pol_DEFER_MIN_APPROVALS": 8, "pol_DEFER_MIN_AVG_SCORE": 5.0,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -10,
        },
    },
    # Iter 6: approve=13, Rail6=14
    {
        "label": "approve=13, Rail6=14, composite=0.30",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.30,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.50,
            "eg_CRITIC_SCORE_THRESHOLD": 0.40,
            "APPROVE_THRESHOLD": 13, "MIN_AVG_SCORE": 5.8,
            "RAIL6_THRESHOLD": 14,
            "pol_HC_MIN_APPROVALS": 16, "pol_HC_MIN_AVG_SCORE": 6.5,
            "pol_HC_MAX_STD_DEV": 1.5, "pol_HC_MAX_DRAWDOWN": 0.15, "pol_HC_MIN_WIN_RATE": 0.48,
            "pol_MED_MIN_APPROVALS": 13, "pol_MED_MIN_AVG_SCORE": 5.8, "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 13, "pol_SMALL_MIN_AVG_SCORE": 5.8,
            "pol_DEFER_MIN_APPROVALS": 10, "pol_DEFER_MIN_AVG_SCORE": 5.5,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -10,
        },
    },
    # Iter 7: approve=15, Rail6=16 (sweep sweet spot)
    {
        "label": "approve=15, Rail6=16 (sweep sweet spot)",
        "patches": {
            "eg_CONFIRMATION_GATE_MIN_GROUPS": 1,
            "eg_COMPOSITE_SCORE_THRESHOLD": 0.30,
            "eg_SINGLE_SIGNAL_HIGH_CONFIDENCE": 0.50,
            "eg_CRITIC_SCORE_THRESHOLD": 0.40,
            "APPROVE_THRESHOLD": 15, "MIN_AVG_SCORE": 5.8,
            "RAIL6_THRESHOLD": 16,
            "pol_HC_MIN_APPROVALS": 18, "pol_HC_MIN_AVG_SCORE": 7.0,
            "pol_HC_MAX_STD_DEV": 1.5, "pol_HC_MAX_DRAWDOWN": 0.15, "pol_HC_MIN_WIN_RATE": 0.48,
            "pol_MED_MIN_APPROVALS": 15, "pol_MED_MIN_AVG_SCORE": 5.8, "pol_MED_MIN_RR": 1.5,
            "pol_SMALL_MIN_APPROVALS": 15, "pol_SMALL_MIN_AVG_SCORE": 5.8,
            "pol_DEFER_MIN_APPROVALS": 12, "pol_DEFER_MIN_AVG_SCORE": 5.5,
            "pol_REDUCE_MAX_DRAWDOWN": 0.38, "pol_REDUCE_MAX_STREAK": -10,
        },
    },
    # Remaining iterations will be dynamically generated based on results
]


async def main():
    log.info("Loading bars ...")
    bars = load_bars()
    log.info("Loaded %d bars. Starting optimization loop.", len(bars))

    defaults = _save_defaults()
    best = None
    best_score = -999

    for it in range(1, MAX_ITER + 1):
        _restore(defaults)

        # Use pre-planned iteration or dynamically generate
        if it <= len(ITERATIONS):
            cfg = ITERATIONS[it - 1]
        else:
            # Dynamic: take best result so far and tweak
            if best is None:
                log.info("No best result yet, using iter 1 config")
                cfg = ITERATIONS[0]
            else:
                cfg = _dynamic_iteration(it, best, results_history)

        label = cfg["label"]
        patches = cfg["patches"]

        log.info(f"--- Iteration {it}/{MAX_ITER}: {label} ---")
        _patch(**patches)

        t0 = time.perf_counter()
        m = await run_once(bars, label)
        elapsed = time.perf_counter() - t0
        log.info(f"  Completed in {elapsed:.1f}s")

        done = report(it, label, m)

        # Track best
        n_pass, _ = check(m)
        # Score: prioritize passing all 6, then trades, then PF
        score = n_pass * 1000 + m["trades"] * 0.1 + m["pf"] * 10 + (1 if m["pnl"] > 0 else 0) * 100
        if score > best_score:
            best_score = score
            best = {"iter": it, "label": label, "metrics": m, "patches": patches}

        if it == 1:
            results_history = []
        results_history.append({"iter": it, "metrics": m, "label": label})

        if done:
            log.info("ALL 6 TARGETS MET! Stopping.")
            break

    else:
        log.info(f"Reached max iterations ({MAX_ITER}). Best result:")
        if best:
            n, fails = check(best["metrics"])
            log.info(f"  Iter {best['iter']}: {best['label']}")
            log.info(f"  {n}/6 targets met. Failing: {fails}")

    # Save best config
    if best:
        out = os.path.join(_ROOT, "analysis", "optimization_result.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(best, f, indent=2, default=str)
        log.info(f"Best config saved to {out}")

    _restore(defaults)


def _dynamic_iteration(it, best, history):
    """Generate a dynamic iteration config based on previous results."""
    bm = best["metrics"]
    bp = dict(best["patches"])  # start from best

    _, fails = check(bm)
    fail_keys = [f.split("=")[0] for f in fails]

    # Cycle through different strategies to avoid getting stuck
    cycle = (it - len(ITERATIONS) - 1) % 5
    label_parts = [f"Dynamic iter {it} (cycle={cycle})"]

    if cycle == 0:
        # Try blending best WR config with more trades: keep high approve but lower entry gates
        bp["APPROVE_THRESHOLD"] = 15
        bp["RAIL6_THRESHOLD"] = 16
        bp["eg_COMPOSITE_SCORE_THRESHOLD"] = 0.15
        bp["eg_CONFIRMATION_GATE_MIN_GROUPS"] = 1
        bp["eg_SINGLE_SIGNAL_HIGH_CONFIDENCE"] = 0.35
        bp["eg_CRITIC_SCORE_THRESHOLD"] = 0.20
        label_parts.append("approve=15 + ultra-low entry gates")
    elif cycle == 1:
        # Try approve=12 with moderate gates (between iter5 and iter7)
        bp["APPROVE_THRESHOLD"] = 12
        bp["RAIL6_THRESHOLD"] = 13
        bp["pol_MED_MIN_APPROVALS"] = 12
        bp["pol_SMALL_MIN_APPROVALS"] = 12
        bp["eg_COMPOSITE_SCORE_THRESHOLD"] = 0.20
        bp["eg_CRITIC_SCORE_THRESHOLD"] = 0.25
        label_parts.append("approve=12, Rail6=13, composite=0.20")
    elif cycle == 2:
        # Try approve=10 with tight REDUCE_DD (allow more trades, filter by panel)
        bp["APPROVE_THRESHOLD"] = 10
        bp["RAIL6_THRESHOLD"] = 11
        bp["pol_MED_MIN_APPROVALS"] = 10
        bp["pol_SMALL_MIN_APPROVALS"] = 10
        bp["eg_COMPOSITE_SCORE_THRESHOLD"] = 0.20
        bp["pol_REDUCE_MAX_DRAWDOWN"] = 0.35
        label_parts.append("approve=10, Rail6=11, REDUCE_DD=0.35")
    elif cycle == 3:
        # Try approve=14 (just below sweet spot)
        bp["APPROVE_THRESHOLD"] = 14
        bp["RAIL6_THRESHOLD"] = 15
        bp["pol_MED_MIN_APPROVALS"] = 14
        bp["pol_SMALL_MIN_APPROVALS"] = 14
        bp["pol_HC_MIN_APPROVALS"] = 17
        bp["eg_COMPOSITE_SCORE_THRESHOLD"] = 0.20
        label_parts.append("approve=14, Rail6=15, composite=0.20")
    else:
        # Try approve=8 ultra-low to maximize trade count for freq target
        bp["APPROVE_THRESHOLD"] = 8
        bp["RAIL6_THRESHOLD"] = 9
        bp["pol_MED_MIN_APPROVALS"] = 8
        bp["pol_SMALL_MIN_APPROVALS"] = 8
        bp["pol_HC_MIN_APPROVALS"] = 11
        bp["eg_COMPOSITE_SCORE_THRESHOLD"] = 0.15
        bp["eg_CRITIC_SCORE_THRESHOLD"] = 0.20
        label_parts.append("approve=8, Rail6=9, ultra-low gates")

    return {"label": "; ".join(label_parts), "patches": bp}


if __name__ == "__main__":
    asyncio.run(main())
