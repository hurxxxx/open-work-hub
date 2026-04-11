"""drop_pms_project_members

Revision ID: 6b21fc0a74c8
Revises: 13e887cfb1db
Create Date: 2026-04-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6b21fc0a74c8'
down_revision: Union[str, Sequence[str], None] = '13e887cfb1db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(
        op.f('ix_pms_project_members_user_id'),
        table_name='pms_project_members',
    )
    op.drop_index(
        op.f('ix_pms_project_members_project_id'),
        table_name='pms_project_members',
    )
    op.drop_table('pms_project_members')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'pms_project_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['pms_projects.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'user_id', name='uq_pms_member'),
    )
    op.create_index(
        op.f('ix_pms_project_members_project_id'),
        'pms_project_members',
        ['project_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_pms_project_members_user_id'),
        'pms_project_members',
        ['user_id'],
        unique=False,
    )
