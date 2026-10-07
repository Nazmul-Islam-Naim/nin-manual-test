from typing import Protocol


class LLMError(Exception):
    """Provider/infrastructure failure; the message is shown to the user as the run error."""


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's raw text answer (expected to be JSON). Raise LLMError on failure."""
