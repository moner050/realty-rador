"""scheduler_log 테이블 추가

Revision ID: 0008_scheduler_log
Revises: 17f93a0cedcb
Create Date: 2026-07-31 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '0008_scheduler_log'
down_revision: Union[str, None] = '17f93a0cedcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scheduler_log',
        sa.Column('log_id', mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column('job_name', sa.String(120), nullable=False),
        sa.Column('trigger_type', sa.String(20), nullable=False, server_default=sa.text("'cron'")),
        sa.Column('status', mysql.TINYINT(unsigned=True), nullable=False, server_default=sa.text("1")),
        sa.Column('jobs_created', mysql.INTEGER(unsigned=True), nullable=False, server_default=sa.text("0")),
        sa.Column('error_message', sa.String(512), nullable=True),
        sa.Column('started_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('finished_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.PrimaryKeyConstraint('log_id'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_scheduler_log_recent', 'scheduler_log', ['started_at', 'log_id'])


def downgrade() -> None:
    op.drop_index('ix_scheduler_log_recent', table_name='scheduler_log')
    op.drop_table('scheduler_log')
