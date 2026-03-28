"""Base agent role classes."""
from .agent import AgentRole, RoleContext
from .roles import (
    ResearchAgent,
    ParserAgent,
    SignalAgent,
    ValidatorAgent,
    ScoringAgent,
    ConflictAgent,
    ContextAgent,
    HistorianAgent,
    CriticAgent,
    SummarizerAgent,
)

__all__ = [
    "AgentRole",
    "RoleContext",
    "ResearchAgent",
    "ParserAgent",
    "SignalAgent",
    "ValidatorAgent",
    "ScoringAgent",
    "ConflictAgent",
    "ContextAgent",
    "HistorianAgent",
    "CriticAgent",
    "SummarizerAgent",
]
