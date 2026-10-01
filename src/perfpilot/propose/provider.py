"""Proposal-provider boundary and OpenAI Responses adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast


class ProviderError(RuntimeError):
    """A proposal provider could not return a complete response."""


@dataclass(frozen=True)
class ProviderOutput:
    provider: str
    model: str
    raw_response: bytes


class ProposalProvider(Protocol):
    def generate(self, prompt: str) -> ProviderOutput: ...


class RecordedProposalProvider:
    """Replay a checked-in response for deterministic offline testing."""

    def __init__(self, path: Path, model: str = "fixture-recording") -> None:
        self.path = path
        self.model = model

    def generate(self, prompt: str) -> ProviderOutput:
        if not prompt:
            raise ProviderError("proposal prompt cannot be empty")
        return ProviderOutput(
            provider="recorded",
            model=self.model,
            raw_response=self.path.read_bytes(),
        )


_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "risk": {"type": "string"},
                    "expected_effect": {"type": "string"},
                    "patch": {"type": "string"},
                },
                "required": ["title", "rationale", "risk", "expected_effect", "patch"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


class OpenAIProposalProvider:
    """Generate strict proposal JSON with the OpenAI Responses API."""

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, prompt: str) -> ProviderOutput:
        # Imported lazily so offline validation never initializes a network client.
        from openai import OpenAI

        client = OpenAI()
        responses = cast(Any, client.responses)
        response = responses.create(
            model=self.model,
            instructions=(
                "You are a conservative C++ performance engineer. Propose at most three small "
                "unified-diff candidates. Do not claim that a candidate is faster or correct; "
                "state risks and let the verifier decide. Return only the requested JSON schema."
            ),
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "perfpilot_proposals",
                    "strict": True,
                    "schema": _PROPOSAL_SCHEMA,
                }
            },
            store=False,
            max_output_tokens=8_000,
        )
        output_text = getattr(response, "output_text", None)
        status = getattr(response, "status", None)
        if status != "completed" or not isinstance(output_text, str) or not output_text:
            raise ProviderError(f"OpenAI response was not complete: status={status!r}")
        return ProviderOutput(
            provider="openai",
            model=self.model,
            raw_response=output_text.encode("utf-8"),
        )

