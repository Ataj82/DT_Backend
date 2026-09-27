from dataclasses import dataclass

from ..interview.interview_session import InterviewSession
from ..assessment.goal_state import GoalState
from ..goals.models import Goal
from ..goals.models import GoalIndicator
from ..templates.models import InterviewTemplate


@dataclass(slots=True)
class QuestionRequest:

    session: InterviewSession

    goal: Goal

    indicator: GoalIndicator

    goal_state: GoalState

    interview_template: InterviewTemplate

    previous_feedback: str = ""

    question_focus: str = ""

    # Adaptive cognitive demand. This is a runtime target; the Goal
    # bloom_level itself remains immutable for learning-outcome alignment.
    target_bloom_level: str = ""

    # Semantic task-shape guidance. This changes question form, not the
    # learning outcome, indicator, Bloom floor, or difficulty contract.
    question_strategy: str = ""

    # Adaptive difficulty
    difficulty: float = 0.5

    difficulty_reason: str = ""

    # Optional ABET criterion target. Empty values preserve v7.x behavior.
    criterion_id: str | None = None
    criterion_description: str = ""