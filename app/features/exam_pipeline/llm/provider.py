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
import logging
import socket
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..configuration.llm_configuration import LLMConfiguration

logger = logging.getLogger("llm_provider")


def _resolve_target_info(url: str) -> tuple[str, str]:
    """Returns (host_or_ip_with_port, resolved_ip)."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            resolved_ip = socket.gethostbyname(host)
        except Exception:
            resolved_ip = host
        return f"{host}:{port}", resolved_ip
    except Exception:
        return "unknown", "unknown"


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

        dest_host_port, dest_ip = _resolve_target_info(url)
        roles_summary = ", ".join(f"{m.get('role', 'unknown')}:{len(str(m.get('content', '')))}c" for m in messages)
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        last_user_content = next((str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), "")
        preview_text = " ".join(last_user_content[:120].split())
        if len(last_user_content) > 120:
            preview_text += "..."

        logger.info(
            "\n"
            "====================================================================\n"
            ">>> [LLM REQUEST OUTGOING]\n"
            "  -> Destination IP : %s (Host: %s)\n"
            "  -> Target URL     : %s\n"
            "  -> Model Name     : %s\n"
            "  -> Parameters     : temp=%s, max_tokens=%s, timeout=%ss\n"
            "  -> Message Items  : %d msgs [%s] (Total %d chars)\n"
            "  -> User Prompt    : \"%s\"\n"
            "====================================================================",
            dest_ip,
            dest_host_port,
            url,
            configuration.model,
            configuration.temperature,
            configuration.max_tokens,
            configuration.timeout_seconds,
            len(messages),
            roles_summary,
            total_chars,
            preview_text,
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

        start_time = time.perf_counter()
        try:
            with urlopen(
                request,
                timeout=configuration.timeout_seconds,
            ) as response:
                body = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as exc:
            elapsed_sec = time.perf_counter() - start_time
            detail = exc.read().decode(
                "utf-8",
                errors="replace",
            )
            logger.error(
                "\n"
                "====================================================================\n"
                "!!! [LLM REQUEST FAILED - HTTP %s]\n"
                "  !- Destination IP : %s (Host: %s)\n"
                "  !- URL            : %s\n"
                "  !- Duration       : %.2fs\n"
                "  !- Error Detail   : %s\n"
                "====================================================================",
                exc.code,
                dest_ip,
                dest_host_port,
                url,
                elapsed_sec,
                detail[:500],
            )
            raise LLMProviderError(
                f"LLM request failed with HTTP {exc.code}: "
                f"{detail}"
            ) from exc

        except URLError as exc:
            elapsed_sec = time.perf_counter() - start_time
            logger.error(
                "\n"
                "====================================================================\n"
                "!!! [LLM REQUEST FAILED - NETWORK ERROR]\n"
                "  !- Destination IP : %s (Host: %s)\n"
                "  !- URL            : %s\n"
                "  !- Duration       : %.2fs\n"
                "  !- Reason         : %s\n"
                "====================================================================",
                dest_ip,
                dest_host_port,
                url,
                elapsed_sec,
                exc.reason,
            )
            raise LLMProviderError(
                f"LLM request failed: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            elapsed_sec = time.perf_counter() - start_time
            logger.error(
                "\n"
                "====================================================================\n"
                "!!! [LLM REQUEST FAILED - TIMEOUT]\n"
                "  !- Destination IP : %s (Host: %s)\n"
                "  !- URL            : %s\n"
                "  !- Duration       : %.2fs (Limit: %ss)\n"
                "====================================================================",
                dest_ip,
                dest_host_port,
                url,
                elapsed_sec,
                configuration.timeout_seconds,
            )
            raise LLMProviderError(
                "LLM request timed out."
            ) from exc

        except json.JSONDecodeError as exc:
            elapsed_sec = time.perf_counter() - start_time
            logger.error(
                "\n"
                "====================================================================\n"
                "!!! [LLM REQUEST FAILED - INVALID JSON]\n"
                "  !- Destination IP : %s\n"
                "  !- Duration       : %.2fs\n"
                "====================================================================",
                dest_ip,
                elapsed_sec,
            )
            raise LLMProviderError(
                "LLM returned invalid JSON."
            ) from exc

        elapsed_sec = time.perf_counter() - start_time

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
            logger.error(
                "\n"
                "====================================================================\n"
                "!!! [LLM RESPONSE MALFORMED]\n"
                "  !- Destination IP : %s\n"
                "  !- Duration       : %.2fs\n"
                "  !- Missing choices[0].message.content\n"
                "====================================================================",
                dest_ip,
                elapsed_sec,
            )
            raise LLMProviderError(
                "LLM response did not contain "
                "choices[0].message.content."
            ) from exc

        text_result = ""
        if isinstance(content, str):
            text_result = content
        elif isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            text_result = "".join(text_parts)
        else:
            raise LLMProviderError(
                "LLM response content has an unsupported format."
            )

        usage = body.get("usage") if isinstance(body, dict) else {}
        usage_info = ""
        if isinstance(usage, dict) and usage:
            usage_info = f"Tokens: prompt={usage.get('prompt_tokens', '?')}, completion={usage.get('completion_tokens', '?')}, total={usage.get('total_tokens', '?')}"

        resp_preview = " ".join(str(text_result)[:120].split())
        if len(str(text_result)) > 120:
            resp_preview += "..."

        logger.info(
            "\n"
            "====================================================================\n"
            "<<< [LLM RESPONSE INCOMING - 200 OK]\n"
            "  <- Source IP      : %s (Host: %s)\n"
            "  <- Duration       : %.2fs\n"
            "  <- Model          : %s\n"
            "  <- %s\n"
            "  <- Output Length  : %d chars\n"
            "  <- Content Preview: \"%s\"\n"
            "====================================================================",
            dest_ip,
            dest_host_port,
            elapsed_sec,
            configuration.model,
            usage_info or "Tokens: N/A",
            len(text_result),
            resp_preview,
        )

        return text_result