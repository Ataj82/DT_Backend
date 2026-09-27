from __future__ import annotations

import os

from .framework_configuration import FrameworkConfiguration


class ConfigurationLoader:

    @staticmethod
    def load() -> FrameworkConfiguration:

        config = FrameworkConfiguration()

        config.debug = (
            os.getenv("FRAMEWORK_DEBUG", "false").lower() == "true"
        )

        config.llm.provider = os.getenv(
            "LLM_PROVIDER",
            config.llm.provider,
        )

        config.llm.model = os.getenv(
            "LLM_MODEL",
            config.llm.model,
        )

        config.llm.api_key = os.getenv(
            "LLM_API_KEY",
            config.llm.api_key,
        )

        config.persistence.provider = os.getenv(
            "PERSISTENCE_PROVIDER",
            config.persistence.provider,
        )

        config.persistence.connection_string = os.getenv(
            "DATABASE_URL",
            config.persistence.connection_string,
        )

        return config