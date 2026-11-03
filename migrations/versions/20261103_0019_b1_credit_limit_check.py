"""b1 credit limit / commitment limit check settings

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-03 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.add_column(sa.Column('CrdLmtChk', sa.String(length=1), server_default='N', nullable=False))
        batch_op.add_column(sa.Column('CmtLmtChk', sa.String(length=1), server_default='N', nullable=False))
        batch_op.add_column(sa.Column('CrdLmtDocs', sa.String(length=30), server_default='17,15,13', nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.drop_column('CrdLmtDocs')
        batch_op.drop_column('CmtLmtChk')
        batch_op.drop_column('CrdLmtChk')
