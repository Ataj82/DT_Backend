from __future__ import annotations

from ..repositories.goal_repository import GoalRepository


class SqlGoalRepository(GoalRepository):

    def __init__(self, session):
        self._session = session

    def add(self, goal_model):
        raise NotImplementedError

    def get(self, goal_model_id):
        raise NotImplementedError

    def list(self):
        raise NotImplementedError

    def update(self, goal_model):
        raise NotImplementedError

    def delete(self, goal_model_id):
        raise NotImplementedError