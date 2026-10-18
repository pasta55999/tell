"""Typed models for findings and evidence produced by the analysis engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
Status = Literal["detected", "needs_investigation", "verified", "dismissed"]
Classification = Literal["discrepancy", "suspected_risk", "observation"]
Confidence = Literal["high", "medium", "low"]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class Evidence(BaseModel):
    source_table: str
    source_id: int | None = None
    source_ref: str | None = None
    description: str
    value: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Question(BaseModel):
    question: str
    rationale: str
    requested_items: str
    priority: Literal["high", "medium", "low"] = "medium"


class Finding(BaseModel):
    """A single analytical result. `finding_key` is stable across runs on the
    same data so that runs can be compared."""

    rule_id: str
    rule_version: str
    subject: str
    title: str
    category: str
    severity: Severity
    classification: Classification = "discrepancy"
    status: Status = "detected"
    summary: str
    explanation: str
    method: str
    period_start: str | None = None
    period_end: str | None = None
    measured: dict[str, Any] = Field(default_factory=dict)
    estimated_impact: float | None = None
    impact_basis: str | None = None
    confidence: Confidence = "medium"
    confidence_note: str | None = None
    next_action: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)

    @property
    def finding_key(self) -> str:
        return f"{self.rule_id}:{self.subject}"


class ModuleResult(BaseModel):
    """Output of one analysis module: findings plus the tables it computed
    (kept so the UI and copilot can show the same numbers the rules used)."""

    module: str
    findings: list[Finding] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)   # human-readable reasons analyses were skipped
    notes: list[str] = Field(default_factory=list)
