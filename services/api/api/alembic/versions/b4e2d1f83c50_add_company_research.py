"""add_company_research

Revision ID: b4e2d1f83c50
Revises: a3f1c8e92b40
Create Date: 2026-03-25 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4e2d1f83c50'
down_revision: Union[str, None] = 'a3f1c8e92b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('analysis_results', sa.Column('company_research', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('analysis_results', 'company_research')