"""add otp_attempts column to users

Revision ID: e6f5d4c3b2a1
Revises: d5f4e3b2a1c0
Create Date: 2026-04-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f5d4c3b2a1'
down_revision = 'd5f4e3b2a1c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('otp_attempts', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('users', 'otp_attempts')