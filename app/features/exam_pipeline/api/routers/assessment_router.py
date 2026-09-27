from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_framework

router=APIRouter(prefix="/assessments",tags=["Assessments"])

@router.get("/interviews/{session_id}/assessment")
def get_assessment(session_id: str, framework=Depends(get_framework)):
    try: return framework.get_abet_assessment(session_id)
    except ValueError as exc: raise HTTPException(404,str(exc)) from exc

@router.get("/interviews/{session_id}/traceability")
def get_traceability(session_id: str, framework=Depends(get_framework)):
    try:
        data=framework.get_abet_assessment(session_id)
        return {"plan_id":data.get("plan_id"),"traceability":data.get("traceability",[])}
    except ValueError as exc: raise HTTPException(404,str(exc)) from exc
