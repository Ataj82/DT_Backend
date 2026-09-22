"""user_contacts table

Revision ID: f2b8c91a0293
Revises: 40be355a50c8
Create Date: 2026-09-11 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f2b8c91a0293'
down_revision: Union[str, Sequence[str], None] = 'e1a89c72f10b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_contacts',
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('custom_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['contact_user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('contact_id'),
        sa.UniqueConstraint('user_id', 'contact_user_id', name='uq_user_contact'),
        sa.CheckConstraint('user_id != contact_user_id', name='ck_no_self_contact')
    )
    op.create_index('ix_user_contacts_user_id', 'user_contacts', ['user_id'], unique=False)
    op.create_index('ix_user_contacts_contact_user_id', 'user_contacts', ['contact_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_contacts_contact_user_id', table_name='user_contacts')
    op.drop_index('ix_user_contacts_user_id', table_name='user_contacts')
    op.drop_table('user_contacts')
