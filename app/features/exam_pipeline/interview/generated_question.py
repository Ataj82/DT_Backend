"""
app/interview/generated_question.py

Canonical value object representing a question generated for an
interview indicator.

A GeneratedQuestion carries the question text together with the
indicator identity for which the question was generated.

The indicator identity is important because the same indicator may
legitimately receive multiple questions across repeated attempts.

Example:

    Turn 4
        indicator_id = "python_file_handling"
        question = "How would you handle a missing file?"

    Turn 5
        indicator_id = "python_file_handling"
        question = "How would you check whether a string is a palindrome?"

    Turn 6
        indicator_id = "python_file_handling"
        question = "How would you determine whether a number is prime?"

The indicator can remain the same while the question changes.

GeneratedQuestion therefore acts as the identity boundary between
QuestionGenerator and ConversationService.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeneratedQuestion:
    """
    Canonical result returned by QuestionGenerator.

    Attributes
    ----------
    question:
        The actual interviewer question.

    context:
        Optional generation context or supporting information.

    indicator_id:
        The indicator for which this question was generated.

        ConversationService validates this against the indicator it
        requested before creating the ConversationTurn.
    """

    question: str
    context: str
    indicator_id: str
    difficulty: float | None = None
    difficulty_reason: str = ""

    def __post_init__(self) -> None:
        # ----------------------------------------------------------
        # Question identity
        # ----------------------------------------------------------

        if not isinstance(self.question, str):
            raise TypeError(
                "GeneratedQuestion.question must be a string."
            )

        normalized_question = self.question.strip()

        if not normalized_question:
            raise ValueError(
                "GeneratedQuestion.question cannot be empty."
            )

        # Because this dataclass is frozen, normal assignment such as
        # self.question = ... is not allowed inside __post_init__.
        object.__setattr__(
            self,
            "question",
            normalized_question,
        )

        # ----------------------------------------------------------
        # Context
        #
        # Preserve the existing public contract while making sure
        # the field is always usable as text.
        # ----------------------------------------------------------

        if self.context is None:
            normalized_context = ""
        elif isinstance(self.context, str):
            normalized_context = self.context.strip()
        else:
            normalized_context = str(self.context).strip()

        object.__setattr__(
            self,
            "context",
            normalized_context,
        )

        # ----------------------------------------------------------
        # Indicator identity
        # ----------------------------------------------------------

        if self.indicator_id is None:
            raise ValueError(
                "GeneratedQuestion.indicator_id is required."
            )

        if isinstance(self.indicator_id, str):
            normalized_indicator_id = self.indicator_id.strip()
        else:
            normalized_indicator_id = str(self.indicator_id).strip()

        if not normalized_indicator_id:
            raise ValueError(
                "GeneratedQuestion.indicator_id cannot be empty."
            )

        object.__setattr__(
            self,
            "indicator_id",
            normalized_indicator_id,
        )

        if self.difficulty is not None:
            try:
                normalized_difficulty = float(self.difficulty)
            except (TypeError, ValueError) as exc:
                raise ValueError("GeneratedQuestion.difficulty must be numeric.") from exc
            if not 0.0 <= normalized_difficulty <= 1.0:
                raise ValueError("GeneratedQuestion.difficulty must be between 0 and 1.")
            object.__setattr__(self, "difficulty", normalized_difficulty)

        object.__setattr__(
            self,
            "difficulty_reason",
            str(self.difficulty_reason or "").strip(),
        )

    def validate_for_indicator(
        self,
        indicator_id: str,
    ) -> None:
        """
        Validate that this question belongs to the requested indicator.

        This is intentionally strict.

        A question generated for indicator A must never silently become
        a question for indicator B.

        Raises
        ------
        ValueError
            If the requested indicator is invalid or does not match
            this GeneratedQuestion.
        """

        if indicator_id is None:
            raise ValueError(
                "Cannot validate GeneratedQuestion without an indicator_id."
            )

        expected = str(indicator_id).strip()

        if not expected:
            raise ValueError(
                "Cannot validate GeneratedQuestion against an empty "
                "indicator_id."
            )

        actual = self.indicator_id.strip()

        if actual != expected:
            raise ValueError(
                "GeneratedQuestion indicator mismatch: "
                f"generated_for={actual!r}, "
                f"requested={expected!r}."
            )
