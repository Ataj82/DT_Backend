"""add lesson prompt history table

Revision ID: d6f8290e4a56
Revises: c5e7189d2f34
Create Date: 2026-10-31 03:45:00.000000

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd6f8290e4a56'
down_revision: Union[str, Sequence[str], None] = 'c5e7189d2f34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS lesson_prompt_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        lesson_id UUID REFERENCES lessons(lesson_id) ON DELETE CASCADE,
        prompt_type VARCHAR(64) NOT NULL,
        system_prompt TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        changed_by VARCHAR(128) DEFAULT 'admin',
        change_summary TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_prompt_history_lesson_type 
    ON lesson_prompt_history(lesson_id, prompt_type, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lesson_prompt_history CASCADE;")
