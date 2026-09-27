from dataclasses import dataclass, field
from datetime import datetime
@dataclass
class Competency:
    id: str
    name: str
    description: str
    mastery_threshold: float
@dataclass
class Skill:
    id: str
    competency_id: str
    name: str
    description: str
@dataclass
class Evidence:
    skill_id: str
    score: float
    confidence: float
    timestamp: datetime
@dataclass
class CompetencyState:
    competency_id: str
    mastery_score: float
    evidence_count: int
    achieved: bool

