"""
Data shapes for summaries and diagnostic steps.

Every statement in a summary says WHERE IT CAME FROM (`origin`):
    observed       read directly from log records
    runbook        taken from a retrieved runbook section (with a citation)
    rule           a conclusion drawn by a fixed, readable rule in this code (still not proof)
    ai_hypothesis  written by the optional AI model; it may be wrong

`strength` says how well the statement is supported (strong / moderate / weak). It is not a probability.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Origin = Literal["observed", "runbook", "rule", "ai_hypothesis"]
Strength = Literal["strong", "moderate", "weak"]


class Fact(BaseModel):
    statement: str
    evidence_ids: list[int]
    origin: Literal["observed"] = "observed"


class RetrievedPoint(BaseModel):
    """A runbook section found for this incident. The text is quoted, not interpreted."""

    citation: str
    document_id: str
    chunk_id: int
    relevance: str
    text: str
    origin: Literal["runbook"] = "runbook"


class Hypothesis(BaseModel):
    statement: str
    reasoning: str
    origin: Literal["rule", "ai_hypothesis"]
    strength: Strength
    evidence_ids: list[int]
    caveat: str = "A hypothesis is not a confirmed cause."


class DiagnosticStep(BaseModel):
    """A check for a human to do. It only looks at things; nothing here changes a system."""

    id: str
    title: str
    instruction: str
    origin: Literal["runbook", "rule", "ai_hypothesis"]
    strength: Strength
    strength_reason: str
    evidence_ids: list[int]
    evidence_match: Literal["specific", "general"]  # "general": no record matches this check in particular
    citation: str | None = None
    expected_observation: str
    documented_commands: list[str] = Field(default_factory=list)  # shown as text; this application never runs them
    read_only: Literal[True] = True


class NotSuggested(BaseModel):
    """Something a runbook or model mentioned that looks like a change to a system. It is listed, not recommended."""

    text: str
    reason: str
    citation: str | None = None
    origin: Literal["runbook", "ai_hypothesis"]


class SummaryOut(BaseModel):
    incident_id: str
    incident_label: str
    generated_by: str  # "deterministic" or "<provider>:<model>"
    used_ai: bool
    ai_error: str | None = None
    ai_available: bool
    headline: str
    ai_narrative: str | None = None  # only ever written by the model, always shown as AI text
    facts: list[Fact]
    retrieved: list[RetrievedPoint]
    no_relevant_source: bool
    hypotheses: list[Hypothesis]
    steps: list[DiagnosticStep]
    not_suggested: list[NotSuggested]
    limitations: list[str]
    created_at: str
    notice: str = "Suggestions only. This application never runs commands or changes any system."


# ---- what the model is asked to return (validated before use) -------------------------------------------------------
class LLMHypothesis(BaseModel):
    statement: str = Field(min_length=5, max_length=400)
    reasoning: str = Field(min_length=5, max_length=600)
    evidence_ids: list[int] = Field(min_length=1, max_length=10)


class LLMStep(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    instruction: str = Field(min_length=5, max_length=500)
    expected_observation: str = Field(min_length=3, max_length=400)
    evidence_ids: list[int] = Field(min_length=1, max_length=10)


class LLMSummary(BaseModel):
    headline: str = Field(min_length=5, max_length=200)
    narrative: str = Field(min_length=5, max_length=1200)
    hypotheses: list[LLMHypothesis] = Field(default_factory=list, max_length=5)
    steps: list[LLMStep] = Field(default_factory=list, max_length=6)


class LLMAnswer(BaseModel):
    answer: str = Field(min_length=2, max_length=1500)
    evidence_ids: list[int] = Field(default_factory=list, max_length=10)
    uncertainty: str = Field(default="", max_length=400)
