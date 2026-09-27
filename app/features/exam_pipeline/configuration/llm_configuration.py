from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class LLMConfiguration:
    """
    Configuration for the LLM infrastructure adapter.

    The application uses an OpenAI-compatible HTTP interface exposed
    by the local/self-hosted Qwen inference server.

    The configured base URL is the API root:

        http://94.184.177.171:8000/v1

    LLMProvider is responsible for adding:

        /chat/completions

    Therefore the final request URL is:

        http://94.184.177.171:8000/v1/chat/completions

    API authentication is optional because the original local LLM
    configuration did not require an API key.
    """

    provider: str = "openai_compatible"

    model: str = "Qwen/Qwen2.5-7B-Instruct-AWQ"

    temperature: float = 0.2

    # Evaluation JSON can contain evidence quotes plus concise feedback.
    # 300 was unnecessarily tight and could truncate JSON before the closing brace.
    max_tokens: int = 700

    timeout_seconds: int = 25

    api_key: str | None = None

    base_url: str = (
        "http://94.184.177.171:8000/v1"
    )

    @classmethod
    def from_env(cls) -> "LLMConfiguration":
        """
        Build LLM configuration from environment variables.

        Environment variables override the local Qwen defaults.
        """

        return cls(
            provider=os.getenv(
                "LLM_PROVIDER",
                "openai_compatible",
            ),

            model=os.getenv(
                "LLM_MODEL",
                "Qwen/Qwen2.5-7B-Instruct-AWQ",
            ),

            temperature=float(
                os.getenv(
                    "LLM_TEMPERATURE",
                    "0.2",
                )
            ),

            max_tokens=int(
                os.getenv(
                    "LLM_MAX_TOKENS",
                    "700",
                )
            ),

            timeout_seconds=int(
                os.getenv(
                    "LLM_TIMEOUT_SECONDS",
                    "25",
                )
            ),

            api_key=(
                os.getenv("LLM_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or None
            ),

            base_url=(
                os.getenv(
                    "LLM_BASE_URL",
                    "http://94.184.177.171:8000/v1",
                )
                .rstrip("/")
            ),
        )