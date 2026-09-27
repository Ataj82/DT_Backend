"""
interview/configuration.py

Configuration describing how an interview should be executed.

The configuration is immutable and is attached to every
InterviewSession.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ============================================================
# Interview Standard
# ============================================================

class AssessmentStandard(str, Enum):
    ABET = "ABET"
    BLOOM = "BLOOM"
    CDIO = "CDIO"
    CUSTOM = "CUSTOM"


# ============================================================
# Interview Strategy
# ============================================================

class StrategyType(str, Enum):
    GOAL_BASED = "goal_based"
    COMPETENCY_BASED = "competency_based"
    BLOOM_BASED = "bloom_based"
    BEHAVIORAL = "behavioral"
    SOCRATIC = "socratic"


# ============================================================
# Navigation Policy
# ============================================================

class NavigationType(str, Enum):
    ADAPTIVE = "adaptive"
    SEQUENTIAL = "sequential"
    PREREQUISITE = "prerequisite"
    MASTERY = "mastery"


# ============================================================
# Interview Language
# ============================================================

class InterviewLanguage(str, Enum):
    ENGLISH = "en"
    PERSIAN = "fa"


# ============================================================
# Difficulty Adaptation
# ============================================================

class DifficultyPolicy(str, Enum):
    ADAPTIVE = "adaptive"
    FIXED = "fixed"


# ============================================================
# Timing
# ============================================================

class TimingPolicy(str, Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"
    UNLIMITED = "unlimited"


# ============================================================
# Probing Policy
# ============================================================

class ProbePolicy(str, Enum):
    NORMAL = "normal"
    SCAFFOLD = "scaffold"
    VERIFY = "verify"
    SIMPLIFY = "simplify"
    ADAPTIVE = "adaptive"


# ============================================================
# Reporting
# ============================================================

class ReportingLevel(str, Enum):
    BASIC = "basic"
    STANDARD = "standard"
    RESEARCH = "research"


# ============================================================
# Interview Configuration
# ============================================================

@dataclass(slots=True)
class InterviewConfiguration:
    """
    Complete configuration for an interview session.

    This object controls how the runtime is assembled.
    """

    # ------------------------------------------
    # Research / Educational Standard
    # ------------------------------------------

    standard: AssessmentStandard = AssessmentStandard.ABET

    # ------------------------------------------
    # Runtime Behaviour
    # ------------------------------------------

    strategy: StrategyType = StrategyType.GOAL_BASED

    navigation: NavigationType = NavigationType.ADAPTIVE

    # ------------------------------------------
    # Language
    # ------------------------------------------

    language: InterviewLanguage = InterviewLanguage.ENGLISH

    # ------------------------------------------
    # Interview Constraints
    # ------------------------------------------

    max_minutes: int = 30

    # Deprecated compatibility field. Never used for adaptive stopping.
    max_attempts_per_indicator: int | None = None

    # ------------------------------------------
    # Adaptive Behaviour
    # ------------------------------------------

    difficulty_policy: DifficultyPolicy = (
        DifficultyPolicy.ADAPTIVE
    )

    # Adaptive difficulty controller. Values are normalized to [0, 1].
    difficulty_min: float = 0.20
    difficulty_max: float = 0.95
    difficulty_step: float = 0.10
    difficulty_high_threshold: float = 0.78
    difficulty_low_threshold: float = 0.45
    difficulty_smoothing: float = 0.60
    difficulty_require_consecutive_strong: int = 1
    difficulty_require_consecutive_weak: int = 1

    probing_policy: ProbePolicy = (
        ProbePolicy.ADAPTIVE
    )

    timing_policy: TimingPolicy = (
        TimingPolicy.FIXED
    )

    # ------------------------------------------
    # Reporting
    # ------------------------------------------

    reporting: ReportingLevel = (
        ReportingLevel.RESEARCH
    )

    # ------------------------------------------
    # Runtime Options
    # ------------------------------------------

    allow_goal_skipping: bool = False

    allow_indicator_revisit: bool = True

    stop_when_all_goals_complete: bool = True

    enable_time_management: bool = True

    enable_information_gain: bool = True

    enable_adaptive_navigation: bool = True

    enable_adaptive_questioning: bool = True

    enable_research_metrics: bool = True