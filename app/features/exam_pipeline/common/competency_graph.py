from competency_models import Competency
from dataclasses import dataclass, field
from typing import Dict, List, Optional
class CompetencyGraph:
    competencies = {}
    skills = {}
    def __init__(self):

       self.competencies = {
           competency_id: Competency
       }
       self.competency_skills = {
           competency_id: [skill_ids]
       }
    def get_next_skill(self):
        pass

    def get_mastery(self):
        pass

    def update_evidence(self):
        pass