"""b1 freight / additional expenses

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-03 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FREIGHT = [('qut3', 'oqut'), ('rdr3', 'ordr'), ('dln3', 'odln'), ('rdn3', 'ordn'), ('inv3', 'oinv'), ('rin3', 'orin'), ('pqt3', 'opqt'), ('por3', 'opor'), ('pdn3', 'opdn'), ('rpd3', 'orpd'), ('pch3', 'opch'), ('rpc3', 'orpc')]
HEADERS = ['oqut', 'ordr', 'odln', 'ordn', 'oinv', 'orin', 'opqt', 'opor', 'opdn', 'orpd', 'opch', 'orpc', 'oign', 'oige', 'owtr']


def upgrade() -> None:
    op.create_table('oexd',
    sa.Column('ExpnsCode', sa.Integer(), nullable=False),
    sa.Column('ExpnsName', sa.String(length=20), nullable=False),
    sa.Column('RevAcct', sa.String(length=15), nullable=False),
    sa.Column('ExpnsAcct', sa.String(length=15), nullable=False),
    sa.Column('VatGroupO', sa.String(length=8), nullable=True),
    sa.Column('VatGroupI', sa.String(length=8), nullable=True),
    sa.Column('SACCode', sa.String(length=8), nullable=True),
    sa.Column('FixAmnt', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.ForeignKeyConstraint(['RevAcct'], ['oact.AcctCode'], name='fk_oexd_rev_oact'),
    sa.ForeignKeyConstraint(['ExpnsAcct'], ['oact.AcctCode'], name='fk_oexd_exp_oact'),
    sa.PrimaryKeyConstraint('ExpnsCode')
    )
    for table, header in FREIGHT:
        op.create_table(table,
    sa.Column('LineNum', sa.Integer(), nullable=False),
    sa.Column('ExpnsCode', sa.Integer(), nullable=False),
    sa.Column('LineTotal', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('TotalFrgn', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('VatGroup', sa.String(length=8), nullable=True),
    sa.Column('VatPrcnt', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('VatSum', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('VatSumFrgn', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('GrsAmount', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('DocEntry', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['DocEntry'], [f'{header}.DocEntry'], name=f'fk_{table}_doc_{header}'),
        sa.PrimaryKeyConstraint('DocEntry', 'LineNum')
        )
    for header in HEADERS:
        with op.batch_alter_table(header) as batch_op:
            batch_op.add_column(sa.Column('TotalExpns', sa.Numeric(precision=19, scale=6), server_default='0', nullable=False))
            batch_op.add_column(sa.Column('TotalExpFC', sa.Numeric(precision=19, scale=6), server_default='0', nullable=False))


def downgrade() -> None:
    for header in HEADERS:
        with op.batch_alter_table(header) as batch_op:
            batch_op.drop_column('TotalExpFC')
            batch_op.drop_column('TotalExpns')
    for table, _ in reversed(FREIGHT):
        op.drop_table(table)
    op.drop_table('oexd')
