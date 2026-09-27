from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PersistenceConfiguration:

    provider: str = "memory"

    connection_string: str = "sqlite:///assessment.db"

    echo_sql: bool = False