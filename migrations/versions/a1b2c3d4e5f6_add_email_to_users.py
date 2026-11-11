"""add email column to users table

Revision ID: a1b2c3d4e5f6
Revises: d6f8290e4a56
Create Date: 2026-11-11 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd6f8290e4a56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE users DROP COLUMN IF EXISTS email;
    """)
