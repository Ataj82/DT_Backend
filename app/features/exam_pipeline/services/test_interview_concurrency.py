from __future__ import annotations

import threading
import time

import pytest

from app.services.interview_service import InterviewService
from app.framework.assessment_framework import AssessmentFramework


class _FakeUow:
    pass


class _FakeRuntime:
    def __init__(self, session):
        self.session = session

    def next_turn(self, answer=None):
        self.session.calls.append(answer)
        time.sleep(0.02)
        return object()


class _FakeSession:
    def __init__(self, index=1):
        self.last_turn = type("Turn", (), {"index": index})()
        self.calls = []


class _FakeInterviewService:
    def __init__(self):
        self.session = _FakeSession()
        self.service = InterviewService.__new__(InterviewService)
        self.service.uow = _FakeUow()
        self.service._session_locks = {}
        self.service._session_locks_guard = threading.RLock()
        self.concurrent = 0
        self.max_concurrent = 0
        self.guard = threading.Lock()

    def session_lock(self, session_id):
        return self.service.session_lock(session_id)


def test_session_lock_serializes_same_session():
    helper = _FakeInterviewService()
    active = 0
    max_active = 0
    guard = threading.Lock()

    def worker():
        nonlocal active, max_active
        with helper.session_lock("session-1"):
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with guard:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_framework_rejects_stale_turn_index_before_runtime():
    class FakeInterviewService:
        def __init__(self):
            self.runtime_called = False

        def session_lock(self, session_id):
            from contextlib import nullcontext
            return nullcontext()

        def get_session(self, session_id):
            return type("Session", (), {
                "last_turn": type("Turn", (), {"index": 7})(),
            })()

        def start_interview(self, session_id):
            self.runtime_called = True
            raise AssertionError("runtime must not run for stale submissions")

    service = FakeInterviewService()
    framework = AssessmentFramework(services=type("Services", (), {
        "interview_service": service,
    })())

    with pytest.raises(RuntimeError, match="Stale or out-of-order answer"):
        framework.next_turn(
            session_id="session-1",
            answer="late answer",
            expected_turn_index=6,
        )

    assert service.runtime_called is False


def test_framework_same_turn_same_answer_is_idempotent_before_runtime():
    class FakeInterviewService:
        def __init__(self):
            self.runtime_called = False
            self.turn = type("Turn", (), {"index": 3, "answer": "same answer"})()

        def session_lock(self, session_id):
            from contextlib import nullcontext
            return nullcontext()

        def get_session(self, session_id):
            return type("Session", (), {"last_turn": self.turn})()

        def start_interview(self, session_id):
            self.runtime_called = True
            raise AssertionError("runtime must not run for an idempotent retry")

    service = FakeInterviewService()
    framework = AssessmentFramework(services=type("Services", (), {
        "interview_service": service,
    })())

    result = framework.next_turn(
        session_id="session-1",
        answer="same answer",
        expected_turn_index=3,
    )

    assert result is service.turn
    assert service.runtime_called is False
