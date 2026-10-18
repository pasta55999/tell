"""Optional language-model adapter interface.

The default copilot is rule-based and needs no model. An adapter may be plugged
in later to rephrase answers or to map free text to a supported intent. Any
adapter must return one of the supported intent names - it never writes SQL and
never has access to the database.
"""

from __future__ import annotations

from typing import Protocol


class LanguageModelAdapter(Protocol):
    name: str

    def classify_intent(self, question: str, intents: list[str]) -> str | None:  # pragma: no cover - interface
        """Return one of `intents` or None if unsure."""

    def rephrase(self, answer_text: str) -> str:  # pragma: no cover - interface
        """Optionally improve readability of a deterministic answer. Must not add facts."""


class NullAdapter:
    """No model. Intent recognition is keyword based and answers are templated."""

    name = "Rule-based Analyst Copilot (no language model)"

    def classify_intent(self, question: str, intents: list[str]) -> str | None:
        return None

    def rephrase(self, answer_text: str) -> str:
        return answer_text
