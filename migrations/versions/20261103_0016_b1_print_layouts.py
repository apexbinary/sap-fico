"""b1 print layouts and company logo

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-03 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('rdoc',
    sa.Column('DocCode', sa.String(length=20), nullable=False),
    sa.Column('DocName', sa.String(length=100), nullable=False),
    sa.Column('TypeCode', sa.String(length=20), nullable=False),
    sa.Column('Style', sa.String(length=10), nullable=False),
    sa.Column('Color', sa.String(length=7), nullable=False),
    sa.Column('ShowLogo', sa.String(length=1), nullable=False),
    sa.Column('ShowHSN', sa.String(length=1), nullable=False),
    sa.Column('ShowBank', sa.String(length=1), nullable=False),
    sa.Column('ShowSign', sa.String(length=1), nullable=False),
    sa.Column('Footer', sa.String(length=254), nullable=True),
    sa.Column('Default', sa.String(length=1), nullable=False),
    sa.PrimaryKeyConstraint('DocCode')
    )
    op.create_index(op.f('ix_rdoc_TypeCode'), 'rdoc', ['TypeCode'], unique=False)
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.add_column(sa.Column('LogoImage', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.drop_column('LogoImage')
    op.drop_index(op.f('ix_rdoc_TypeCode'), table_name='rdoc')
    op.drop_table('rdoc')
