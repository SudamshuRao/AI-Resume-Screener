"""add_ats_details

Revision ID: a3f1c8e92b40
Revises: 8b820607257d
Create Date: 2026-03-25 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f1c8e92b40'
down_revision: Union[str, None] = '8b820607257d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_results', sa.Column('ats_details', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_results', 'ats_details')