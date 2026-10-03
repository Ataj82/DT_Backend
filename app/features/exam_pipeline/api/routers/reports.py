"""Report API, including downloadable report exports."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from ..dependencies import get_framework
from ..schemas.reports import ReportResponse

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/{session_id}", response_model=ReportResponse)
def generate_report(session_id: str, framework=Depends(get_framework)):
    try:
        report = framework.build_report(session_id)
        return ReportResponse.model_validate(report)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@router.get("/{session_id}/download/{format}")
def download_report(session_id: str, format: str, framework=Depends(get_framework)):
    try:
        report = framework.build_report(session_id)
        payload, media_type, extension = framework.services.report_service.export(report, format)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    from ..header_utils import content_disposition_attachment
    filename = f"interview-report-{session_id}.{extension}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": content_disposition_attachment(filename)},
    )

@router.get("/{session_id}/integrity")
def verify_integrity(session_id: str, framework=Depends(get_framework)):
    try:
        return framework.verify_assessment_integrity(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
