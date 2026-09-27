from __future__ import annotations

from threading import RLock

from .models import AssignmentStudent, InterviewAssignment, User


class InMemoryMultiUserRepository:
    """Development repository. Replace with a DB-backed repository in production."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._users_by_email: dict[str, str] = {}
        self._assignments: dict[str, InterviewAssignment] = {}
        self._lock = RLock()

    def add_user(self, user: User) -> User:
        email = user.email.strip().lower()
        with self._lock:
            if email in self._users_by_email:
                raise ValueError("A user with this email already exists.")
            self._users[user.id] = user
            self._users_by_email[email] = user.id
        return user

    def save_user(self, user: User) -> User:
        email = user.email.strip().lower()
        with self._lock:
            self._users[user.id] = user
            self._users_by_email[email] = user.id
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._lock:
            return self._users.get(str(user_id))

    def get_user_by_email(self, email: str) -> User | None:
        with self._lock:
            user_id = self._users_by_email.get(email.strip().lower())
            return self._users.get(user_id) if user_id else None

    def list_users(self, role=None) -> list[User]:
        with self._lock:
            users = list(self._users.values())
        if role is not None:
            users = [u for u in users if u.role == role]
        return users

    def save_assignment(self, assignment: InterviewAssignment) -> InterviewAssignment:
        with self._lock:
            self._assignments[assignment.id] = assignment
        return assignment

    def get_assignment(self, assignment_id: str) -> InterviewAssignment | None:
        with self._lock:
            return self._assignments.get(str(assignment_id))

    def list_assignments(self, professor_id: str | None = None) -> list[InterviewAssignment]:
        with self._lock:
            assignments = list(self._assignments.values())
        if professor_id is not None:
            assignments = [a for a in assignments if a.professor_id == professor_id]
        return assignments

    def assignment_for_student_session(self, session_id: str) -> tuple[InterviewAssignment, AssignmentStudent] | None:
        with self._lock:
            for assignment in self._assignments.values():
                for enrollment in assignment.students.values():
                    if enrollment.session_id == session_id:
                        return assignment, enrollment
        return None
