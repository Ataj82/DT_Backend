"""
app/api/routers/knowledge.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...api.dependencies import get_framework
from ...api.schemas.knowledge import (
    CreateKnowledgeRequest,
    KnowledgeResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSummary,
)
from ...framework.assessment_framework import AssessmentFramework

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["Knowledge"],
)


# ----------------------------------------------------------
# Create
# ----------------------------------------------------------

@router.post(
    "",
    response_model=KnowledgeSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    request: CreateKnowledgeRequest,
    framework: AssessmentFramework = Depends(get_framework),
):
    result = framework.create_knowledge_base(
        title=request.title,
        description=request.description,
        resources=request.resources,
        metadata=request.metadata,
    )

    kb = result.knowledge_base

    return KnowledgeSummary(
        id=kb.id,
        title=kb.title,
        description=kb.description,
        resource_count=len(kb.documents),
        concept_count=len(kb.concepts),
        relationship_count=len(kb.relationships),
        language="en",
        metadata=kb.metadata,
    )

# ----------------------------------------------------------
# Get
# ----------------------------------------------------------

@router.get(
    "/{knowledge_id}",
    response_model=KnowledgeResponse,
)
def get_knowledge_base(
    knowledge_id: str,
    framework: AssessmentFramework = Depends(get_framework),
):
    kb = framework.get_knowledge_base(knowledge_id)

    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    return KnowledgeResponse(
        id=kb.id,
        title=kb.title,
        description=kb.description,
        language="en",
        resources=[
            d.filename
            for d in kb.documents
        ],
        concepts=[
            c.name
            for c in kb.concepts
        ],
        metadata=kb.metadata,
    )


# ----------------------------------------------------------
# List
# ----------------------------------------------------------

@router.get(
    "",
    response_model=list[KnowledgeSummary],
)
def list_knowledge_bases(
    framework: AssessmentFramework = Depends(get_framework),
):

    return [

        KnowledgeSummary(
            id=kb.id,
            title=kb.title,
            description=kb.description,
            resource_count=len(kb.documents),
            concept_count=len(kb.concepts),
            relationship_count=len(kb.relationships),
            language="en",
            metadata=kb.metadata,
        )

        for kb in framework.list_knowledge_bases()

    ]


# ----------------------------------------------------------
# Search
# ----------------------------------------------------------

@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
)
def search(
    request: KnowledgeSearchRequest,
    framework: AssessmentFramework = Depends(get_framework),
):

    results = framework.search_knowledge(
        knowledge_id=request.knowledge_id,
        query=request.query,
        top_k=request.top_k,
    )

    return KnowledgeSearchResponse(
        query=request.query,
        results=results,
    )


# ----------------------------------------------------------
# Delete
# ----------------------------------------------------------

@router.delete(
    "/{knowledge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_knowledge_base(
    knowledge_id: str,
    framework: AssessmentFramework = Depends(get_framework),
):

    framework.delete_knowledge_base(
        knowledge_id
    )