"""
app/framework/assessment_framework.py

Public façade for the Digital Twin Assessment Framework.

The API layer communicates only with this class.

AssessmentFramework is intentionally thin:
- coordinates service calls
- resolves cross-service dependencies where required
- keeps routers independent from repositories and runtime internals

Business logic remains inside application services and assessment
runtime components.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..assessment.goal_time_manager import GoalTimeManager


@dataclass(slots=True)
class AssessmentFramework:
    """
    Public application façade.

    Routers should communicate only with this class.

    The façade hides:
        - repositories
        - UnitOfWork implementations
        - runtime factories
        - assessment algorithms
        - knowledge-processing internals
    """

    services: Any

    # ==========================================================
    # Knowledge Base
    # ==========================================================

    def create_knowledge_base(
        self,
        *,
        title: str,
        resources,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Create and ingest a knowledge base.
        """

        metadata = metadata or {}

        return self.services.knowledge_service.ingest_resources(
            resources=resources,
            title=title,
            description=description or "",
            language=metadata.get("language", "en"),
            metadata=metadata,
        )

    def get_knowledge_base(
        self,
        knowledge_id: str,
    ):
        """
        Retrieve a knowledge base by ID.
        """

        return self.services.knowledge_service.get_knowledge_base(
            knowledge_id
        )

    def list_knowledge_bases(self):
        """
        Return all knowledge bases.
        """

        return self.services.knowledge_service.list_knowledge_bases()

    def delete_knowledge_base(
        self,
        knowledge_id: str,
    ) -> None:
        """
        Delete a knowledge base.
        """

        self.services.knowledge_service.delete_knowledge_base(
            knowledge_id
        )

    def search_knowledge(
        self,
        *,
        knowledge_id: str,
        query: str,
        top_k: int = 5,
    ):
        """
        Search a knowledge base.
        """

        return self.services.knowledge_service.search(
            knowledge_id=knowledge_id,
            query=query,
            top_k=top_k,
        )

    # ==========================================================
    # Goals
    # ==========================================================

    def generate_goals(
        self,
        *,
        knowledge_id: str,
        max_goals: int | None = None,
        include_optional: bool = True,
    ):
        """
        Generate a GoalModel from a KnowledgeBase.
        """

        return self.services.goal_service.generate(
            knowledge_id=knowledge_id,
            max_goals=max_goals,
            include_optional=include_optional,
        )

    def get_goal_model(
        self,
        goal_model_id: str,
    ):
        """
        Retrieve a goal model by ID.
        """

        return self.services.goal_service.get(
            goal_model_id
        )

    def list_goal_models(self):
        """
        Return all goal models.
        """

        return self.services.goal_service.list()

    def save_goal_model(
        self,
        goal_model,
    ):
        """
        Persist a goal model.
        """

        return self.services.goal_service.save(
            goal_model
        )

    def review_goals(
        self,
        *,
        goal_model_id: str,
        approved_goal_ids: list[str],
    ):
        """
        Review and approve selected goals.
        """

        return self.services.goal_service.review(
            goal_model_id=goal_model_id,
            approved_goal_ids=approved_goal_ids,
        )

    def delete_goal_model(
        self,
        goal_model_id: str,
    ) -> None:
        """
        Delete a goal model.
        """

        self.services.goal_service.delete(
            goal_model_id
        )

    # ==========================================================
    # ABET Assessment
    # ==========================================================

    def save_abet_plan(self, plan):
        return self.services.abet_service.save_plan(plan)

    def list_abet_plans(self):
        return self.services.abet_service.list_plans()

    def get_abet_plan(self, plan_id: str):
        return self.services.abet_service.get_plan(plan_id)

    def attach_abet_plan(self, session_id: str, plan_id: str):
        session = self.get_interview(session_id)
        if session is None:
            raise ValueError(f"Interview session '{session_id}' not found.")
        return self.services.abet_service.attach_plan(plan_id, session)

    def get_abet_assessment(self, session_id: str):
        session = self.get_interview(session_id)
        if session is None:
            raise ValueError(f"Interview session '{session_id}' not found.")
        return self.services.abet_service.assessment(session)

    # ==========================================================
    # Interview
    # ==========================================================

    def create_interview(
        self,
        *,
        student_id: str,
        knowledge_id: str | None = None,
        goal_model_id: str | None = None,
        configuration=None,
        interviewer_id: str | None = None,
        knowledge_model=None,
        goal_model=None,
    ):
        """
        Create a persistent interview session.

        Preferred API:
            student_id
            knowledge_id
            goal_model_id
            configuration

        ``knowledge_model`` and ``goal_model`` are retained as
        compatibility arguments for internal callers that already
        resolved the domain objects.
        """

        # ------------------------------------------------------
        # Resolve knowledge model
        # ------------------------------------------------------

        if knowledge_model is None:

            if not knowledge_id:
                raise ValueError(
                    "knowledge_id is required to create an interview."
                )

            knowledge_model = self.get_knowledge_base(
                knowledge_id
            )

            if knowledge_model is None:
                raise ValueError(
                    f"Knowledge base '{knowledge_id}' not found."
                )

        # ------------------------------------------------------
        # Resolve goal model
        # ------------------------------------------------------

        if goal_model is None:

            if not goal_model_id:
                raise ValueError(
                    "goal_model_id is required to create an interview."
                )

            goal_model = self.get_goal_model(
                goal_model_id
            )

            if goal_model is None:
                raise ValueError(
                    f"Goal model '{goal_model_id}' not found."
                )

        # ------------------------------------------------------
        # Validate explicit goal-time configuration before persistence.
        # ------------------------------------------------------

        GoalTimeManager.validate_configuration(
            configuration,
            list(getattr(goal_model, "goals", []) or []),
        )

        # ------------------------------------------------------
        # Delegate session creation
        # ------------------------------------------------------

        return self.services.interview_service.create_session(
            student_id=student_id,
            knowledge_model=knowledge_model,
            goal_model=goal_model,
            configuration=configuration,
            interviewer_id=interviewer_id,
        )

    def start_interview(
        self,
        session_id: str,
    ):
        """
        Reconstruct the runtime for an interview session.
        """

        return self.services.interview_service.start_interview(
            session_id
        )

    def get_interview(
        self,
        session_id: str,
    ):
        """
        Retrieve an interview session.
        """

        return self.services.interview_service.get_session(
            session_id
        )

    def get_session(
        self,
        session_id: str,
    ):
        """
        Backward-compatible alias for get_interview().
        """

        return self.get_interview(
            session_id
        )

    def list_interviews(self):
        """
        List all interview sessions.
        """

        return self.services.interview_service.list_sessions()

    def save_interview(
        self,
        session,
    ):
        """
        Persist an interview session.
        """

        return self.services.interview_service.save(
            session
        )

    def next_turn(
            self,
            session_id: str,
            answer: str | None = None,
            expected_turn_index: int | None = None,
    ):
        """Process exactly one session turn as a serialized transaction.

        The session is loaded, evaluated, navigated, and persisted while the
        same per-session lock is held. This prevents concurrent /turn requests
        from evaluating the same question against different runtime snapshots
        and then overwriting each other's assessment state.
        """
        interview_service = self.services.interview_service

        with interview_service.session_lock(session_id):
            session = interview_service.get_session(session_id)
            if session is None:
                raise ValueError(
                    f"Interview session '{session_id}' not found."
                )

            current_turn = getattr(session, "last_turn", None)
            current_index = getattr(current_turn, "index", None)

            if expected_turn_index is not None:
                if current_turn is None:
                    raise RuntimeError(
                        "A turn identity was supplied, but the interview has no current question."
                    )

                # A browser/client can lose the HTTP response after the server
                # has already committed an answer. Retrying the same answer is
                # therefore a normal at-least-once delivery case, not an
                # out-of-order answer. Make the endpoint idempotent for an
                # already-committed turn: if the exact turn and answer are
                # already persisted, return the existing current turn instead
                # of evaluating the answer a second time.
                # If the current turn itself is already answered with the
                # exact same payload, the previous request committed the answer
                # but has not yet advanced the in-memory cursor. Treat retries
                # as idempotent instead of invoking the evaluator twice.
                if current_index == expected_turn_index:
                    stored_answer = getattr(current_turn, "answer", None)
                    if stored_answer is not None and str(stored_answer).strip() == str(answer or "").strip():
                        return current_turn

                if current_index != expected_turn_index:
                    turns = list(getattr(session, "turns", ()) or ())
                    answered_turn = next(
                        (t for t in turns if getattr(t, "index", None) == expected_turn_index),
                        None,
                    )
                    stored_answer = getattr(answered_turn, "answer", None) if answered_turn else None
                    if (
                        current_index is not None
                        and current_index > expected_turn_index
                        and answered_turn is not None
                        and stored_answer is not None
                        and str(stored_answer).strip() == str(answer or "").strip()
                    ):
                        # The first request already committed this exact turn.
                        # current_turn is the already-generated next question
                        # (or the terminal answered turn), which is exactly what
                        # the router needs to reconstruct the original response.
                        return current_turn

                    raise RuntimeError(
                        "Stale or out-of-order answer: expected turn "
                        f"{current_index}, received turn {expected_turn_index}."
                    )

            runtime = interview_service.start_interview(session_id)

            # No answer means: create the first question.
            turn = runtime.next_turn(answer=answer)

            interview_service.save(runtime.session)

            return turn


    def reset_interview(
        self,
        session_id: str,
    ) -> None:
        """
        Reset an interview while preserving its session identity.
        """

        runtime = self.services.interview_service.start_interview(
            session_id
        )

        runtime.reset()

        self.services.interview_service.save(
            runtime.session
        )

    def delete_interview(
        self,
        session_id: str,
    ) -> None:
        """
        Permanently delete an interview session.
        """

        self.services.interview_service.delete(
            session_id
        )

    # ==========================================================
    # Assessment
    # ==========================================================

    def complete_assessment(
            self,
            session_id: str,
    ):
        """
        Complete an already-finished assessment and return its
        final result.

        The assessment runtime remains responsible for determining
        whether the interview has actually completed.
        """

        return self.services.assessment_service.complete(
            session_id
        )

    def get_assessment_result(
            self,
            session_id: str,
    ):
        """
        Retrieve/build the assessment result for a completed
        interview.
        """

        return self.services.assessment_service.get_result(
            session_id
        )

    def build_result(
            self,
            session_id: str,
    ):
        """
        Build the assessment result.

        This is retained as a façade-level convenience method.
        """

        # v10.2: preserve the first integrity manifest as the trusted
        # baseline for this completed session. Later result builds verify
        # against that stored baseline instead of silently replacing it.
        from ..assessment.assessment_integrity import AssessmentIntegrity

        session = self.get_interview(session_id)
        existing_manifest = dict(
            getattr(session, "metadata", {}).get("assessment_integrity", {})
            or {}
        )

        result = self.services.assessment_service.build_result(
            session_id
        )

        if existing_manifest:
            result.metadata["assessment_integrity"] = existing_manifest
            evidence_records = []
            for goal_state in getattr(session, "goal_states", {}).values():
                evidence_records.extend(getattr(goal_state, "evidence", []) or [])
            result.metadata["assessment_integrity_verification"] = AssessmentIntegrity.verify_manifest(
                result=result,
                manifest=existing_manifest,
                evidence_records=evidence_records,
            )
        else:
            manifest = result.metadata.get("assessment_integrity")
            if manifest:
                session.metadata["assessment_integrity"] = manifest
                self.save_interview(session)

        return result




# ==========================================================
    # Reports
    # ==========================================================

    def build_report(
        self,
        session_id: str,
    ):
        """
        Build a report for an interview session.
        """

        assessment_result = self.build_result(
            session_id
        )

        return self.services.report_service.build_report(
            assessment_result
        )

    def verify_assessment_integrity(
        self,
        session_id: str,
        result=None,
    ):
        """Verify an existing result manifest against its current contents.

        When ``result`` is omitted a fresh canonical result is built.
        """
        from ..assessment.assessment_integrity import AssessmentIntegrity

        if result is None:
            result = self.build_result(session_id)

        manifest = result.metadata.get("assessment_integrity", {})
        session = self.get_interview(session_id)
        evidence_records = []
        for goal_state in getattr(session, "goal_states", {}).values():
            evidence_records.extend(getattr(goal_state, "evidence", []) or [])
        return AssessmentIntegrity.verify_manifest(
            result=result,
            manifest=manifest,
            evidence_records=evidence_records,
        )

    def get_metrics(
        self,
        session_id: str,
    ):
        """
        Return report metrics for an interview session.
        """

        report = self.build_report(
            session_id
        )

        if report is None:
            return None

        return report.metrics