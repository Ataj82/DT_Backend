"""
app/assessment/evaluation/llm_provider.py

LLM provider abstraction.

This module contains the infrastructure adapter used by the
assessment/evaluation layer.

Responsibilities
----------------
- Validate LLM messages.
- Send the messages to the configured LLM backend.
- Return the backend's textual response.
- Normalize common OpenAI-compatible response formats.

Non-responsibilities
--------------------
- Assessment logic.
- Goal logic.
- Indicator logic.
- Bloom levels.
- Interview strategy.
- Answer evaluation.
- Caching.
- Previous-answer state.

The provider is intentionally stateless. Every ``chat()`` call sends
the supplied messages to the configured backend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..configuration.llm_configuration import LLMConfiguration


class LLMProviderError(RuntimeError):
    """Raised when an LLM request cannot be completed or parsed."""


@dataclass(slots=True)
class LLMProvider:
    """
    Thin LLM gateway.

    A callable ``transport`` can be injected by tests, local adapters,
    or another provider implementation.

    If no transport is supplied, an OpenAI-compatible HTTP endpoint
    is used.

    Authentication is optional because the local Qwen inference
    server used by the original application does not require an API
    key.

    The provider has no knowledge of:
    - goals,
    - indicators,
    - Bloom levels,
    - ABET,
    - interview strategy,
    - learner state,
    - previous evaluations.

    It also performs no response caching.
    """

    configuration: LLMConfiguration
    transport: object | None = None

    # ==========================================================
    # Public API
    # ==========================================================

    def chat(
        self,
        messages: list[dict],
    ) -> str:
        """
        Send chat messages to the configured LLM and return text.

        Each call is independent. No previous response is retained
        or reused by this provider.
        """

        self._validate_messages(messages)

        if self.transport is not None:
            response = self.transport(
                messages,
                self.configuration,
            )
        else:
            response = self._chat_openai_compatible(
                messages,
                self.configuration,
            )

        if not isinstance(response, str):
            raise LLMProviderError(
                "LLM transport must return a string."
            )

        response = response.strip()

        if not response:
            raise LLMProviderError(
                "LLM returned an empty response."
            )

        return response

    # ==========================================================
    # Message Validation
    # ==========================================================

    @staticmethod
    def _validate_messages(
        messages: list[dict],
    ) -> None:
        if not isinstance(messages, list) or not messages:
            raise ValueError(
                "messages must be a non-empty list."
            )

        for message in messages:
            if not isinstance(message, dict):
                raise ValueError(
                    "Each LLM message must be a dictionary."
                )

            role = message.get("role")

            if not isinstance(role, str) or not role.strip():
                raise ValueError(
                    "Each LLM message must contain a non-empty role."
                )

            if "content" not in message:
                raise ValueError(
                    "Each LLM message must contain content."
                )

    # ==========================================================
    # OpenAI-Compatible Transport
    # ==========================================================

    @staticmethod
    def _chat_openai_compatible(
        messages: list[dict],
        configuration: LLMConfiguration,
    ) -> str:
        """
        Call an OpenAI-compatible chat-completions endpoint.

        Authentication is optional because the local Qwen endpoint
        used by the original application did not require an API key.
        """

        url = (
            configuration.base_url.rstrip("/")
            + "/chat/completions"
        )

        payload = {
            "model": configuration.model,
            "messages": messages,
            "temperature": configuration.temperature,
            "max_tokens": configuration.max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if configuration.api_key:
            headers["Authorization"] = (
                f"Bearer {configuration.api_key}"
            )

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=configuration.timeout_seconds,
            ) as response:
                body = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as exc:
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise LLMProviderError(
                f"LLM request failed with HTTP {exc.code}: "
                f"{detail}"
            ) from exc

        except URLError as exc:
            raise LLMProviderError(
                f"LLM request failed: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise LLMProviderError(
                "LLM request timed out."
            ) from exc

        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                "LLM returned invalid JSON."
            ) from exc

        try:
            content = (
                body["choices"][0]
                ["message"]
                ["content"]
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise LLMProviderError(
                "LLM response did not contain "
                "choices[0].message.content."
            ) from exc

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []

            for block in content:
                if not isinstance(block, dict):
                    continue

                text = block.get("text")

                if isinstance(text, str):
                    text_parts.append(text)

            return "".join(text_parts)

        raise LLMProviderError(
            "LLM response content has an unsupported format."
        )