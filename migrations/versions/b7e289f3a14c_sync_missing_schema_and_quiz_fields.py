"""sync missing schema and quiz fields

Revision ID: b7e289f3a14c
Revises: f2b8c91a0293
Create Date: 2026-10-21 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7e289f3a14c'
down_revision: Union[str, Sequence[str], None] = 'f2b8c91a0293'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users: theme, language
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS theme VARCHAR DEFAULT 'light'")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'fa'")

    # 2. lessons: avatar_url
    op.execute("ALTER TABLE lessons ADD COLUMN IF NOT EXISTS avatar_url TEXT")

    # 3. lesson_materials: rag_status, rag_metadata
    op.execute("ALTER TABLE lesson_materials ADD COLUMN IF NOT EXISTS rag_status VARCHAR(64) DEFAULT 'ready'")
    op.execute("ALTER TABLE lesson_materials ADD COLUMN IF NOT EXISTS rag_metadata JSONB DEFAULT '{}'::jsonb")

    # 4. lesson_quizzes: goals, student_ids, gap_minutes, exam_date, language
    op.execute("ALTER TABLE lesson_quizzes ADD COLUMN IF NOT EXISTS goals JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE lesson_quizzes ADD COLUMN IF NOT EXISTS student_ids JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE lesson_quizzes ADD COLUMN IF NOT EXISTS gap_minutes INTEGER DEFAULT 5")
    op.execute("ALTER TABLE lesson_quizzes ADD COLUMN IF NOT EXISTS exam_date VARCHAR(50)")
    op.execute("ALTER TABLE lesson_quizzes ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'fa'")

    # 5. user_biometric_profiles table
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_biometric_profiles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id VARCHAR UNIQUE NOT NULL,
        is_enrolled BOOLEAN NOT NULL DEFAULT false,
        enrolled_at TIMESTAMPTZ,
        face_embedding JSONB,
        liveness_status VARCHAR DEFAULT 'genuine',
        is_gaze_calibrated BOOLEAN NOT NULL DEFAULT false,
        gaze_calibrated_at TIMESTAMPTZ,
        gaze_samples_count INTEGER NOT NULL DEFAULT 0,
        gaze_weights JSONB,
        is_neutral_calibrated BOOLEAN NOT NULL DEFAULT false,
        neutral_calibrated_at TIMESTAMPTZ,
        neutral_samples_count INTEGER NOT NULL DEFAULT 0,
        neutral_baseline_mean JSONB,
        neutral_baseline_std JSONB,
        can_edit BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_biometric_profiles_user_id ON user_biometric_profiles (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_biometric_profiles CASCADE")
    op.execute("ALTER TABLE lesson_quizzes DROP COLUMN IF EXISTS language")
    op.execute("ALTER TABLE lesson_quizzes DROP COLUMN IF EXISTS exam_date")
    op.execute("ALTER TABLE lesson_quizzes DROP COLUMN IF EXISTS gap_minutes")
    op.execute("ALTER TABLE lesson_quizzes DROP COLUMN IF EXISTS student_ids")
    op.execute("ALTER TABLE lesson_quizzes DROP COLUMN IF EXISTS goals")
    op.execute("ALTER TABLE lesson_materials DROP COLUMN IF EXISTS rag_metadata")
    op.execute("ALTER TABLE lesson_materials DROP COLUMN IF EXISTS rag_status")
    op.execute("ALTER TABLE lessons DROP COLUMN IF EXISTS avatar_url")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS language")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS theme")
