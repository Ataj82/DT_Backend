"""
Plugin type definitions.
"""

from enum import Enum


class PluginType(str, Enum):

    QUESTION_GENERATOR = "question_generator"

    ANSWER_EVALUATOR = "answer_evaluator"

    KNOWLEDGE_EXTRACTOR = "knowledge_extractor"

    GOAL_GENERATOR = "goal_generator"

    INTERVIEW_STRATEGY = "interview_strategy"

    NAVIGATION_STRATEGY = "navigation_strategy"

    REPORT_EXPORTER = "report_exporter"

    LLM_PROVIDER = "llm_provider"