"""
app/assessment/evidence.py

Canonical evaluated outcome evidence.

OutcomeEvidence represents the semantic result of evaluating one
learner answer. It is produced by the evaluation layer and consumed
by OutcomeManager.

Responsibilities
----------------
- Represent evidence for exactly one indicator.
- Preserve the discrete achievement level (1..6).
- Preserve evaluator confidence and evidence strength.
- Preserve qualitative evidence and feedback.

Non-responsibilities
--------------------
- Mutating GoalState.
- Calculating aggregate coverage.
- Calculating mastery.
- Calculating completion.
- Selecting the next indicator.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OutcomeEvidence:
    """
    Canonical semantic evaluation of one learner answer.

    ``achievement_level`` is deliberately discrete and must be in the
    range 1..6. Aggregate mastery normalization belongs to
    CoverageEngine, not to this evidence object.
    """

    MIN_ACHIEVEMENT_LEVEL = 1
    MAX_ACHIEVEMENT_LEVEL = 6
    MIN_PROBABILITY = 0.0
    MAX_PROBABILITY = 1.0

    indicator_id: str
    achievement_level: int
    confidence: float
    feedback: str

    evidence_strength: float = 0.0
    indicator_demonstrated: bool = False

    rationale: str = ""
    bloom_level: str = ""

    missing_elements: list[str] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        """
        Validate the evidence contract immediately.

        Evidence should never enter the outcome layer in an invalid
        semantic state.
        """

        self.indicator_id = self._normalize_indicator_id(
            self.indicator_id
        )

        self.achievement_level = self._normalize_achievement_level(
            self.achievement_level
        )

        self.confidence = self._normalize_probability(
            self.confidence,
            field_name="confidence",
        )

        self.evidence_strength = self._normalize_probability(
            self.evidence_strength,
            field_name="evidence_strength",
        )

        if not isinstance(self.indicator_demonstrated, bool):
            raise ValueError(
                "indicator_demonstrated must be a boolean."
            )

        self.feedback = self._normalize_text(
            self.feedback,
            field_name="feedback",
            required=True,
        )

        self.rationale = self._normalize_text(
            self.rationale,
            field_name="rationale",
            required=False,
        )

        self.bloom_level = self._normalize_text(
            self.bloom_level,
            field_name="bloom_level",
            required=False,
        )

        self.missing_elements = self._normalize_missing_elements(
            self.missing_elements
        )

    @property
    def achieved_level(self) -> int:
        """
        Backward-compatible alias.

        Canonical field name is ``achievement_level``.
        """

        return self.achievement_level

    @property
    def supporting_text(self) -> str:
        """
        Backward-compatible alias for legacy consumers.

        ``feedback`` is the canonical qualitative evaluation text.
        """

        return self.feedback

    @property
    def demonstrated(self) -> bool:
        """
        Compatibility alias for consumers using a shorter name.
        """

        return self.indicator_demonstrated

    @classmethod
    def _normalize_achievement_level(
        cls,
        value: object,
    ) -> int:
        """
        Normalize and validate the discrete achievement level.
        """

        if isinstance(value, bool):
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            ) from exc

        # Do not silently convert values such as 3.5 to 3.
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            ) from exc

        if numeric_value != normalized:
            raise ValueError(
                "achievement_level must be an integer from 1 to 6."
            )

        if not (
            cls.MIN_ACHIEVEMENT_LEVEL
            <= normalized
            <= cls.MAX_ACHIEVEMENT_LEVEL
        ):
            raise ValueError(
                "achievement_level must be between "
                f"{cls.MIN_ACHIEVEMENT_LEVEL} and "
                f"{cls.MAX_ACHIEVEMENT_LEVEL}."
            )

        return normalized

    @classmethod
    def _normalize_probability(
        cls,
        value: object,
        *,
        field_name: str,
    ) -> float:
        """
        Normalize and validate a probability-like value.
        """

        if isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be a number between "
                f"{cls.MIN_PROBABILITY} and "
                f"{cls.MAX_PROBABILITY}."
            )

        try:
            normalized = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name} must be a number between "
                f"{cls.MIN_PROBABILITY} and "
                f"{cls.MAX_PROBABILITY}."
            ) from exc

        if not (
            cls.MIN_PROBABILITY
            <= normalized
            <= cls.MAX_PROBABILITY
        ):
            raise ValueError(
                f"{field_name} must be between "
                f"{cls.MIN_PROBABILITY} and "
                f"{cls.MAX_PROBABILITY}."
            )

        return normalized

    @staticmethod
    def _normalize_indicator_id(value: object) -> str:
        """
        Normalize and validate the target indicator identity.
        """

        if not isinstance(value, str):
            raise ValueError(
                "indicator_id must be a non-empty string."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "indicator_id must be a non-empty string."
            )

        return normalized

    @staticmethod
    def _normalize_text(
        value: object,
        *,
        field_name: str,
        required: bool,
    ) -> str:
        """
        Normalize textual evidence fields.
        """

        if value is None:
            if required:
                raise ValueError(
                    f"{field_name} must be a non-empty string."
                )
            return ""

        if not isinstance(value, str):
            raise ValueError(
                f"{field_name} must be a string."
            )

        normalized = value.strip()

        if required and not normalized:
            raise ValueError(
                f"{field_name} must be a non-empty string."
            )

        return normalized

    @staticmethod
    def _normalize_missing_elements(
        value: object,
    ) -> list[str]:
        """
        Normalize missing-element descriptions.

        Empty entries are discarded and duplicate entries are removed
        while preserving their original order.
        """

        if value is None:
            return []

        if isinstance(value, str):
            values = [value]
        else:
            try:
                values = list(value)
            except TypeError as exc:
                raise ValueError(
                    "missing_elements must be a sequence of strings."
                ) from exc

        normalized: list[str] = []
        seen: set[str] = set()

        for item in values:
            if not isinstance(item, str):
                raise ValueError(
                    "Each missing element must be a string."
                )

            text = item.strip()

            if not text or text in seen:
                continue

            seen.add(text)
            normalized.append(text)

        return normalized