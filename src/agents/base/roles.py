"""
Concrete base implementations for each of the 10 agent roles.

Groups import these and override _execute() for their specific logic.
Roles that are not applicable to a group remain as no-ops.

Source: /docs/agent_registry/role_registry.md
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .agent import AgentRole, RoleContext, RoleResult


# ---------------------------------------------------------------------------
# Role 1 — Research
# ---------------------------------------------------------------------------

class ResearchAgent(AgentRole):
    """
    Load and prepare inputs needed for this processing cycle.
    Fetches bars from FeatureStore, retrieves open positions,
    loads cached structural levels, etc.

    LLM: NOT permitted.
    """
    role_name = "research"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        # Subclasses override: fetch bars, features, positions from store.
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 2 — Parser
# ---------------------------------------------------------------------------

class ParserAgent(AgentRole):
    """
    Convert raw unstructured input (news, JSON feeds) into structured
    data that downstream roles can consume.

    LLM: PERMITTED for unstructured text only (News/Macro group).
         All other groups: NOT permitted.
    """
    role_name = "parser"
    llm_permitted = False   # Groups that use LLM override this to True

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 3 — Signal
# ---------------------------------------------------------------------------

class SignalAgent(AgentRole):
    """
    Detect patterns, compute indicator signals, or identify candlestick
    formations. Emits zero or more CandidateSignal objects.

    ALL logic must be deterministic (no LLM). Bar-close only.
    Breakout confirmation must reach CONFIRMED state before emitting.
    """
    role_name = "signal"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 4 — Validator
# ---------------------------------------------------------------------------

class ValidatorAgent(AgentRole):
    """
    Apply hypothesis-specific filters before a signal is forwarded.
    Checks: hypothesis active, pattern CONFIRMED, structural level present
    (if required), hypothesis not in blocked_patterns list.

    Deterministic. Returns filtered signal list.
    """
    role_name = "validator"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 5 — Scoring
# ---------------------------------------------------------------------------

class ScoringAgent(AgentRole):
    """
    Assign quality_score to each validated signal.
    Inputs: pattern quality, volume confirmation, structural alignment,
    regime filter, win rate from journal (if available).

    Deterministic formula. Output: signal with quality_score populated.
    """
    role_name = "scoring"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 6 — Conflict
# ---------------------------------------------------------------------------

class ConflictAgent(AgentRole):
    """
    Detect direction conflicts across signal bundles from multiple groups.
    Produces ConflictReport for Entry group; does NOT resolve on its own.
    Resolution strategy: highest composite_score wins; tie → skip.
    """
    role_name = "conflict"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 7 — Context
# ---------------------------------------------------------------------------

class ContextAgent(AgentRole):
    """
    Enrich signals with current regime, structural context, open positions.
    Reads from SystemState (read-only). Tags signals with context flags.
    May suppress signals that fail regime filters.
    """
    role_name = "context"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 8 — Historian
# ---------------------------------------------------------------------------

class HistorianAgent(AgentRole):
    """
    Query the journal for historical analogs to the current signal.
    Returns HistoricalAnalog with win rate, avg R, last 10 outcomes.
    Used to populate CandidateTradeProposal.historian_analog.

    Deterministic SQL query. Advisory only.
    """
    role_name = "historian"
    llm_permitted = False

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )


# ---------------------------------------------------------------------------
# Role 9 — Critic
# ---------------------------------------------------------------------------

class CriticAgent(AgentRole):
    """
    LLM-powered devil's advocate. Called ONLY when composite_score >= 0.60.
    Produces CriticReport with bullish_case, bearish_case, failure_modes.
    Advisory only — Risk Engine never reads CriticReport.
    Timeout: 2000ms hard cap. On timeout: proceed with empty CriticReport.

    LLM: PERMITTED (RESEARCH mode: skipped. SHADOW/LIVE: optional).
    """
    role_name = "critic"
    llm_permitted = True   # ADR-003

    LLM_TIMEOUT_MS: int = 2000

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )

    async def _call_llm_with_timeout(self, prompt: str) -> Optional[str]:
        """
        Call LLM with hard 2000ms timeout. Returns None on timeout.
        Subclasses use this helper for LLM calls.
        """
        try:
            return await asyncio.wait_for(
                self._call_llm(prompt),
                timeout=self.LLM_TIMEOUT_MS / 1000,
            )
        except asyncio.TimeoutError:
            self._logger.warning("CriticAgent LLM call timed out after %dms", self.LLM_TIMEOUT_MS)
            return None

    async def _call_llm(self, prompt: str) -> str:
        """Override in concrete implementation to call LLM API."""
        raise NotImplementedError("Concrete CriticAgent must implement _call_llm()")


# ---------------------------------------------------------------------------
# Role 10 — Summarizer
# ---------------------------------------------------------------------------

class SummarizerAgent(AgentRole):
    """
    LLM-powered narrative synthesis. Used ONLY by Performance/Journal/Learning
    group to produce human-readable edge reports, decay notices, and
    sprint recommendations.

    Output is always advisory/narrative — never influences order generation.
    LLM: PERMITTED (Learning group only).
    """
    role_name = "summarizer"
    llm_permitted = True   # ADR-003, Learning group only

    async def _execute(self, context: RoleContext) -> RoleResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _execute()"
        )
