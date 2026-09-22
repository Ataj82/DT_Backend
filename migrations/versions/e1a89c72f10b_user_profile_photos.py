"""user_profile_photos

Revision ID: e1a89c72f10b
Revises: 40be355a50c8
Create Date: 2026-09-06 00:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1a89c72f10b'
down_revision: Union[str, Sequence[str], None] = '40be355a50c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_profile_photos',
        sa.Column('photo_id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('photo_url', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('photo_id')
    )
    op.create_index(op.f('ix_user_profile_photos_user_id'), 'user_profile_photos', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_profile_photos_user_id'), table_name='user_profile_photos')
    op.drop_table('user_profile_photos')
