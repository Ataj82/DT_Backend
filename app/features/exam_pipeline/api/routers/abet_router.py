from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from ..dependencies import get_framework
from ..schemas.abet import AssessmentPlanRequest
from ...abet.models import AssessmentPlan, ABETOutcome, LearningOutcome, PerformanceCriterion, Rubric, RubricLevel
from ...framework.assessment_framework import AssessmentFramework

router=APIRouter(prefix="/abet",tags=["ABET"])

def _plan(req):
    rubrics=[]
    for r in req.rubrics:
        levels=r.levels or [
            {"level":1,"label":"Beginning","description":"Major misunderstanding or no usable evidence."},
            {"level":2,"label":"Developing","description":"Very limited understanding with major gaps."},
            {"level":3,"label":"Partial","description":"Partial understanding with significant gaps."},
            {"level":4,"label":"Adequate","description":"Adequate evidence of the required performance."},
            {"level":5,"label":"Strong","description":"Strong evidence with only minor gaps."},
            {"level":6,"label":"Comprehensive","description":"Comprehensive and highly convincing evidence."},
        ]
        rubrics.append(Rubric(id=r.id or str(uuid4()),name=r.name,passing_level=r.passing_level,levels=[RubricLevel(**(x if isinstance(x,dict) else x.model_dump())) for x in levels]))
    return AssessmentPlan(
        id=req.id or str(uuid4()),name=req.name,goal_model_id=req.goal_model_id,
        outcomes=[ABETOutcome(**x.model_dump()) for x in req.outcomes],
        learning_outcomes=[LearningOutcome(**x.model_dump()) for x in req.learning_outcomes],
        criteria=[PerformanceCriterion(**x.model_dump()) for x in req.criteria],rubrics=rubrics,
        required_coverage=req.required_coverage,minimum_attainment=req.minimum_attainment)

@router.post('/plans',status_code=status.HTTP_201_CREATED)
def create_plan(request: AssessmentPlanRequest, framework: AssessmentFramework=Depends(get_framework)):
    try: return framework.save_abet_plan(_plan(request)).to_dict()
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc

@router.get('/plans')
def list_plans(framework: AssessmentFramework=Depends(get_framework)):
    return [x.to_dict() for x in framework.list_abet_plans()]

@router.get('/plans/{plan_id}')
def get_plan(plan_id: str, framework: AssessmentFramework=Depends(get_framework)):
    plan=framework.get_abet_plan(plan_id)
    if plan is None: raise HTTPException(404,'ABET assessment plan not found.')
    return plan.to_dict()

@router.post('/plans/{plan_id}/attach/{session_id}')
def attach_plan(plan_id: str, session_id: str, framework: AssessmentFramework=Depends(get_framework)):
    try: return {"attached":True,"plan":framework.attach_abet_plan(session_id,plan_id).to_dict()}
    except ValueError as exc: raise HTTPException(404,str(exc)) from exc
