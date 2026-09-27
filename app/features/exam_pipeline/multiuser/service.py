from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from threading import RLock
from uuid import uuid4

from ..api.schemas.interviews import InterviewConfigurationRequest
from ..assessment.goal_time_manager import GoalTimeManager
from .models import AssignmentStatus, AssignmentStudent, EnrollmentStatus, InterviewAssignment, User, UserRole
from .repository import InMemoryMultiUserRepository
from .security import TokenStore, hash_password, verify_password


class MultiUserService:
    """Application layer for identities, professor assignments and student sessions."""

    VERSION = "12.3"

    def __init__(self, *, interview_service, knowledge_service, goal_service) -> None:
        self.repository = InMemoryMultiUserRepository()
        self.tokens = TokenStore()
        self._assignment_mutation_lock = RLock()
        self.interview_service = interview_service
        self.knowledge_service = knowledge_service
        self.goal_service = goal_service

    # ---------------------------------------------------------
    # Identity
    # ---------------------------------------------------------
    def register(self, *, email: str, display_name: str, password: str, role: UserRole) -> User:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise ValueError("A valid email address is required.")
        if not display_name.strip():
            raise ValueError("display_name is required.")
        user = User(
            id=str(uuid4()),
            email=email,
            display_name=display_name.strip(),
            role=role,
            password_hash=hash_password(password),
        )
        return self.repository.add_user(user)

    def login(self, *, email: str, password: str) -> tuple[User, str]:
        user = self.repository.get_user_by_email(email)
        if user is None or not user.active or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")
        return user, self.tokens.issue(user.id)

    def authenticate(self, token: str | None) -> User:
        user_id = self.tokens.resolve(token)
        user = self.repository.get_user(user_id) if user_id else None
        if user is None or not user.active:
            raise ValueError("Authentication required.")
        return user

    # ---------------------------------------------------------
    # Assignments
    # ---------------------------------------------------------
    def create_assignment(
        self,
        *,
        professor: User,
        title: str,
        description: str,
        knowledge_base_id: str,
        goal_model_id: str,
        duration_seconds: int,
        goal_time_allocations_seconds: dict[str, int] | None = None,
        passing_threshold: float = 0.70,
        allow_followup_questions: bool = True,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        assignment_id: str | None = None,
    ) -> InterviewAssignment:
        if professor.role not in {UserRole.PROFESSOR, UserRole.ADMIN}:
            raise PermissionError("Only professors can create assignments.")

        knowledge = self.knowledge_service.get_knowledge_base(knowledge_base_id)
        if knowledge is None:
            raise ValueError(f"Knowledge base '{knowledge_base_id}' not found.")
        goal_model = self.goal_service.get(goal_model_id)
        if goal_model is None:
            raise ValueError(f"Goal model '{goal_model_id}' not found.")
        if str(getattr(goal_model, "knowledge_base_id", "")) != str(knowledge_base_id):
            raise ValueError("Goal model does not belong to the selected knowledge base.")

        approved = [g for g in getattr(goal_model, "goals", []) if str(getattr(g, "status", "")) == "approved"]
        if not approved:
            # Preserve compatibility with existing projects whose generated model
            # has not gone through the optional review endpoint.
            approved = list(getattr(goal_model, "goals", []) or [])
        if not approved:
            raise ValueError("The selected goal model contains no usable goals.")

        config = InterviewConfigurationRequest(
            duration_seconds=duration_seconds,
            goal_time_allocations_seconds=goal_time_allocations_seconds,
            passing_threshold=passing_threshold,
            allow_followup_questions=allow_followup_questions,
        )
        GoalTimeManager.validate_configuration(config, approved)

        knowledge_snapshot = copy.deepcopy(knowledge)
        goal_snapshot = copy.deepcopy(goal_model)
        config_snapshot = config.model_dump(mode="json")

        assignment = InterviewAssignment(
            id=str(assignment_id) if assignment_id else str(uuid4()),
            professor_id=professor.id,
            title=title.strip(),
            description=description.strip(),
            knowledge_base_id=knowledge_base_id,
            goal_model_id=goal_model_id,
            duration_seconds=duration_seconds,
            goal_time_allocations_seconds=copy.deepcopy(goal_time_allocations_seconds),
            configuration_snapshot=config_snapshot,
            knowledge_snapshot=knowledge_snapshot,
            goal_model_snapshot=goal_snapshot,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        return self.repository.save_assignment(assignment)

    def publish_assignment(self, *, professor: User, assignment_id: str) -> InterviewAssignment:
        with self._assignment_mutation_lock:
            assignment = self._owned_assignment(professor, assignment_id)
            assignment.status = AssignmentStatus.PUBLISHED
            return self.repository.save_assignment(assignment)

    def close_assignment(self, *, professor: User, assignment_id: str) -> InterviewAssignment:
        with self._assignment_mutation_lock:
            assignment = self._owned_assignment(professor, assignment_id)
            assignment.status = AssignmentStatus.CLOSED
            return self.repository.save_assignment(assignment)

    def enroll_students(self, *, professor: User, assignment_id: str, student_ids: list[str]) -> InterviewAssignment:
        with self._assignment_mutation_lock:
            assignment = self._owned_assignment(professor, assignment_id)
            if assignment.status != AssignmentStatus.DRAFT:
                raise ValueError("Students can only be added while an assignment is in draft status.")
    
            for student_id in dict.fromkeys(str(x).strip() for x in student_ids):
                student = self.repository.get_user(student_id)
                if student is None:
                    raise ValueError(f"Student '{student_id}' not found.")
                if student.role != UserRole.STUDENT:
                    raise ValueError(f"User '{student_id}' is not a student.")
                if student_id in assignment.students:
                    continue
    
                configuration = InterviewConfigurationRequest.model_validate(assignment.configuration_snapshot)
                session = self.interview_service.create_session(
                    student_id=student_id,
                    knowledge_model=copy.deepcopy(assignment.knowledge_snapshot),
                    goal_model=copy.deepcopy(assignment.goal_model_snapshot),
                    configuration=configuration,
                    interviewer_id=assignment.professor_id,
                )
                session.metadata.update({
                    "multi_user_version": self.VERSION,
                    "assignment_id": assignment.id,
                    # Stable round-robin opening strategy for students in the same
                    # published assignment.  The conversation layer uses this only
                    # for first-question task-form diversity.
                    "opening_question_variant": len(assignment.students),
                    "professor_id": assignment.professor_id,
                    "student_id": student_id,
                    "assignment_snapshot": {
                        "knowledge_base_id": assignment.knowledge_base_id,
                        "goal_model_id": assignment.goal_model_id,
                        "configuration": copy.deepcopy(assignment.configuration_snapshot),
                    },
                })
                self.interview_service.save(session)
                assignment.students[student_id] = AssignmentStudent(
                    assignment_id=assignment.id,
                    student_id=student_id,
                    session_id=session.id,
                )
    
            return self.repository.save_assignment(assignment)
    
    # ---------------------------------------------------------
    # Student views / lifecycle
    # ---------------------------------------------------------
    def student_assignments(self, *, student: User) -> list[tuple[InterviewAssignment, AssignmentStudent]]:
        if student.role != UserRole.STUDENT:
            raise PermissionError("Student access required.")
        output = []
        for assignment in self.repository.list_assignments():
            enrollment = assignment.students.get(student.id)
            if enrollment is not None:
                # Keep the dashboard/report visibility synchronized with the
                # canonical interview session lifecycle.  This does not mutate
                # assessment state; it only mirrors completion into enrollment.
                self.sync_enrollment_status(assignment=assignment, enrollment=enrollment)
                output.append((assignment, enrollment))
        return output

    def get_student_session(self, *, student: User, assignment_id: str):
        assignment = self.repository.get_assignment(assignment_id)
        if assignment is None:
            raise ValueError("Assignment not found.")
        enrollment = assignment.students.get(student.id)
        if enrollment is None:
            raise PermissionError("You are not assigned to this interview.")
        return assignment, enrollment, self.interview_service.get_session(enrollment.session_id)

    def mark_started(self, *, student: User, assignment_id: str) -> AssignmentStudent:
        assignment, enrollment, session = self.get_student_session(student=student, assignment_id=assignment_id)
        if assignment.status != AssignmentStatus.PUBLISHED:
            raise ValueError("This assignment is not published.")
        now = datetime.now(timezone.utc)
        s_at = assignment.starts_at
        if s_at and s_at.tzinfo is None:
            s_at = s_at.replace(tzinfo=timezone.utc)
        e_at = assignment.ends_at
        if e_at and e_at.tzinfo is None:
            e_at = e_at.replace(tzinfo=timezone.utc)

        from datetime import timedelta
        if s_at and now < s_at - timedelta(minutes=2):
            raise ValueError("زمان شروع این آزمون هنوز فرا نرسیده است.")
        if e_at and now > e_at:
            raise ValueError("زمان برگزاری این آزمون به پایان رسیده است.")
        if enrollment.status == EnrollmentStatus.ASSIGNED:
            enrollment.status = EnrollmentStatus.STARTED
            enrollment.started_at = now
            self.repository.save_assignment(assignment)
        return enrollment

    def sync_enrollment_status(self, *, assignment: InterviewAssignment, enrollment: AssignmentStudent) -> AssignmentStudent:
        session = self.interview_service.get_session(enrollment.session_id)
        if session is not None:
            is_completed = getattr(session, "completed", False)
            if not is_completed:
                config = getattr(session, "configuration", None)
                dur = None
                if isinstance(config, dict):
                    dur = config.get("duration_seconds")
                elif config is not None:
                    dur = getattr(config, "duration_seconds", None)
                dur = dur or assignment.duration_seconds
                started_at = getattr(session, "started_at", None) or enrollment.started_at
                if started_at and dur:
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - started_at).total_seconds() >= dur:
                        is_completed = True
                        session.completed = True
                        if hasattr(session, "finished_at") and not session.finished_at:
                            session.finished_at = started_at + timedelta(seconds=dur)
                        self.interview_service.save(session)
            if is_completed:
                enrollment.status = EnrollmentStatus.COMPLETED
                if enrollment.completed_at is None:
                    enrollment.completed_at = getattr(session, "finished_at", None) or datetime.now(timezone.utc)
                self.repository.save_assignment(assignment)
        return enrollment

    # ---------------------------------------------------------
    # Professor views
    # ---------------------------------------------------------
    def professor_assignments(self, *, professor: User) -> list[InterviewAssignment]:
        if professor.role not in {UserRole.PROFESSOR, UserRole.ADMIN}:
            raise PermissionError("Professor access required.")
        return self.repository.list_assignments(None if professor.role == UserRole.ADMIN else professor.id)

    def assignment_detail(self, *, professor: User, assignment_id: str) -> InterviewAssignment:
        return self._owned_assignment(professor, assignment_id)

    def assignment_student_sessions(self, *, professor: User, assignment_id: str):
        assignment = self._owned_assignment(professor, assignment_id)
        rows = []
        for enrollment in assignment.students.values():
            session = self.interview_service.get_session(enrollment.session_id)
            self.sync_enrollment_status(assignment=assignment, enrollment=enrollment)
            rows.append((enrollment, session))
        return assignment, rows

    def assignment_for_session(self, session_id: str):
        return self.repository.assignment_for_student_session(session_id)

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _owned_assignment(self, professor: User, assignment_id: str) -> InterviewAssignment:
        if professor.role not in {UserRole.PROFESSOR, UserRole.ADMIN}:
            raise PermissionError("Professor access required.")
        assignment = self.repository.get_assignment(assignment_id)
        if assignment is None:
            raise ValueError("Assignment not found.")
        if professor.role != UserRole.ADMIN and assignment.professor_id != professor.id:
            raise PermissionError("You do not own this assignment.")
        return assignment

    @staticmethod
    def user_public(user: User) -> dict[str, Any]:
        return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role.value}

    @staticmethod
    def assignment_public(assignment: InterviewAssignment) -> dict[str, Any]:
        return {
            "id": assignment.id,
            "professor_id": assignment.professor_id,
            "title": assignment.title,
            "description": assignment.description,
            "knowledge_base_id": assignment.knowledge_base_id,
            "goal_model_id": assignment.goal_model_id,
            "duration_seconds": assignment.duration_seconds,
            "goal_time_allocations_seconds": assignment.goal_time_allocations_seconds,
            "status": assignment.status.value,
            "starts_at": assignment.starts_at,
            "ends_at": assignment.ends_at,
            "student_count": len(assignment.students),
        }
