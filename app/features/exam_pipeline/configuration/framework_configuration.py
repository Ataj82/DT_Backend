from __future__ import annotations

from dataclasses import dataclass, field

from .api_configuration import APIConfiguration
from .interview_configuration import InterviewConfiguration
from .llm_configuration import LLMConfiguration
from .persistence_configuration import PersistenceConfiguration


@dataclass(slots=True)
class FrameworkConfiguration:

    interview: InterviewConfiguration = field(
        default_factory=InterviewConfiguration
    )

    llm: LLMConfiguration = field(
        default_factory=LLMConfiguration
    )

    persistence: PersistenceConfiguration = field(
        default_factory=PersistenceConfiguration
    )

    api: APIConfiguration = field(
        default_factory=APIConfiguration
    )

    debug: bool = False