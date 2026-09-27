from __future__ import annotations
from copy import deepcopy
from .models import *
from .attainment import build_attainment

class ABETService:
    """Application service for explicit ABET blueprints and assessment traceability."""
    def __init__(self): self._plans={}
    def save_plan(self, plan):
        self._validate(plan); self._plans[plan.id]=deepcopy(plan); return deepcopy(plan)
    def get_plan(self, plan_id): return deepcopy(self._plans.get(str(plan_id).strip()))
    def list_plans(self): return [deepcopy(x) for x in self._plans.values()]
    def attach_plan(self, plan_id, session):
        plan=self.get_plan(plan_id)
        if plan is None: raise ValueError(f"ABET assessment plan '{plan_id}' not found.")
        if plan.goal_model_id and str(getattr(getattr(session,'goal_model',None),'id','')) != plan.goal_model_id:
            raise ValueError("ABET plan goal_model_id does not match the interview goal model.")
        session.metadata.setdefault("abet",{})["plan"]=plan.to_dict()
        return plan
    def assessment(self, session):
        data=session.metadata.get("abet",{}) if getattr(session,"metadata",None) else {}
        raw=data.get("plan")
        if not raw: return {"enabled":False,"completed":False,"reason":"No ABET assessment plan is attached."}
        plan=self._from_dict(raw)
        return {"enabled":True,**build_attainment(plan,session)}
    def target_for(self, session, goal_id, indicator_id):
        raw=(getattr(session,"metadata",{}) or {}).get("abet",{}).get("plan")
        if not raw: return None
        plan=self._from_dict(raw)
        used={}
        for t in getattr(session,"turns",[]) or []:
            x=((getattr(t,"metadata",{}) or {}).get("abet") or {}).get("target") or {}
            if x.get("criterion_id"): used[x["criterion_id"]]=1
        # Criteria are assigned by explicit target metadata when present; otherwise first criterion
        # belonging to the indicator is selected. This is intentionally conservative.
        for c in plan.criteria:
            for t in getattr(session,"turns",[]) or []:
                if t.goal_id==goal_id and t.indicator_id==indicator_id:
                    old=((t.metadata.get("abet") or {}).get("target") or {})
                    if old.get("criterion_id")==c.id: return AssessmentTarget(**{k:old[k] for k in AssessmentTarget.__annotations__ if k in old})
        candidates=[c for c in plan.criteria if c.indicator_id==indicator_id and (c.goal_id is None or c.goal_id==goal_id)]
        if candidates:
            c=next((c for c in candidates if c.id not in used),candidates[0])
            lo=next((x for x in plan.learning_outcomes if goal_id in x.goal_ids or x.id==c.learning_outcome_id),None)
            o=next((x for x in plan.outcomes if lo and lo.id in x.learning_outcome_ids),None)
            if lo and o:
                return AssessmentTarget(o.id,lo.id,goal_id,indicator_id,c.id,c.description,c.rubric_id)
        return None
    @staticmethod
    def _validate(plan):
        outcomes={x.id for x in plan.outcomes}; los={x.id for x in plan.learning_outcomes}; rubrics={x.id for x in plan.rubrics}
        for lo in plan.learning_outcomes:
            if lo.outcome_id not in outcomes: raise ValueError(f"Learning outcome '{lo.id}' references unknown outcome.")
        for o in plan.outcomes:
            if any(x not in los for x in o.learning_outcome_ids): raise ValueError(f"Outcome '{o.id}' references unknown learning outcome.")
        for c in plan.criteria:
            if c.rubric_id and c.rubric_id not in rubrics: raise ValueError(f"Criterion '{c.id}' references unknown rubric.")
            if c.learning_outcome_id and c.learning_outcome_id not in los: raise ValueError(f"Criterion '{c.id}' references unknown learning outcome.")
            if c.outcome_id and c.outcome_id not in outcomes: raise ValueError(f"Criterion '{c.id}' references unknown outcome.")
    @staticmethod
    def _from_dict(d):
        rubrics=[Rubric(id=r["id"],name=r["name"],passing_level=r.get("passing_level",4),levels=[RubricLevel(**l) for l in r.get("levels",[])]) for r in d.get("rubrics",[])]
        criteria=[PerformanceCriterion(**x) for x in d.get("criteria",[])]
        los=[LearningOutcome(**x) for x in d.get("learning_outcomes",[])]
        outcomes=[ABETOutcome(**x) for x in d.get("outcomes",[])]
        return AssessmentPlan(id=d["id"],name=d.get("name","ABET Assessment Plan"),outcomes=outcomes,learning_outcomes=los,criteria=criteria,rubrics=rubrics,goal_model_id=d.get("goal_model_id"),required_coverage=d.get("required_coverage",1),minimum_attainment=d.get("minimum_attainment",.7))
