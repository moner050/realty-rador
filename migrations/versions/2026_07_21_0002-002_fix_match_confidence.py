"""fix match_confidence column type

Revision ID: 002_fix_match_confidence
Revises: 001_initial
Create Date: 2026-07-21 15:24:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_fix_match_confidence'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # complex_alias 테이블의 match_confidence 컬럼을 DECIMAL(5, 2)로 변경
    op.alter_column(
        'complex_alias',
        'match_confidence',
        existing_type=sa.Numeric(3, 2),
        type_=sa.Numeric(5, 2),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'complex_alias',
        'match_confidence',
        existing_type=sa.Numeric(5, 2),
        type_=sa.Numeric(3, 2),
        existing_nullable=True,
    )
