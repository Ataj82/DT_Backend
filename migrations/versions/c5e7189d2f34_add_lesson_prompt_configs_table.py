"""add lesson prompt configs table

Revision ID: c5e7189d2f34
Revises: b7e289f3a14c
Create Date: 2026-10-29 21:55:00.000000

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c5e7189d2f34'
down_revision: Union[str, Sequence[str], None] = 'b7e289f3a14c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS lesson_prompt_configs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        lesson_id UUID REFERENCES lessons(lesson_id) ON DELETE CASCADE,
        prompt_type VARCHAR(64) NOT NULL,
        name VARCHAR(255),
        name_fa VARCHAR(255),
        category VARCHAR(64),
        description TEXT,
        description_fa TEXT,
        system_prompt TEXT NOT NULL,
        tone_and_style VARCHAR(64),
        custom_rules JSONB DEFAULT '[]'::jsonb,
        model_override VARCHAR(128),
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_lesson_prompt_configs_lesson_id ON lesson_prompt_configs(lesson_id);
    """)

    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_lesson_prompt_configs_type ON lesson_prompt_configs(prompt_type);
    """)

    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_lesson_prompt_configs_lesson_type 
    ON lesson_prompt_configs(lesson_id, prompt_type) 
    WHERE lesson_id IS NOT NULL;
    """)

    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_lesson_prompt_configs_global_type 
    ON lesson_prompt_configs(prompt_type) 
    WHERE lesson_id IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lesson_prompt_configs CASCADE;")
