"""Route goal wording by resolved language without changing English wording."""
from __future__ import annotations

from .resolver import normalize_language
from .persian.goal_text import build_persian_goal_title, build_persian_goal_description


def build_goal_text(*, language: str | None, label: str, description: str | None) -> tuple[str, str]:
    if normalize_language(language, default="en") == "fa":
        return (
            build_persian_goal_title(label),
            build_persian_goal_description(label, description),
        )
    return (
        f"Demonstrate understanding of {label}",
        description or f"Assess understanding of {label}.",
    )
