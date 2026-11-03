"""b1 withholding tax (TDS)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-03 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HEADERS = ['oqut', 'ordr', 'odln', 'ordn', 'oinv', 'orin', 'opqt', 'opor', 'opdn', 'orpd', 'opch', 'orpc', 'oign', 'oige', 'owtr']


def upgrade() -> None:
    op.create_table('owht',
    sa.Column('WTCode', sa.String(length=4), nullable=False),
    sa.Column('WTName', sa.String(length=50), nullable=False),
    sa.Column('Rate', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('Category', sa.String(length=1), nullable=False),
    sa.Column('BaseType', sa.String(length=1), nullable=False),
    sa.Column('Account', sa.String(length=15), nullable=False),
    sa.Column('Section', sa.String(length=10), nullable=False),
    sa.Column('ThrSingle', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('ThrAnnual', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('ThrType', sa.String(length=1), nullable=False),
    sa.Column('RateNoPAN', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('Inactive', sa.String(length=1), nullable=False),
    sa.ForeignKeyConstraint(['Account'], ['oact.AcctCode'], name='fk_owht_account_oact'),
    sa.PrimaryKeyConstraint('WTCode')
    )
    op.create_table('crd4',
    sa.Column('CardCode', sa.String(length=15), nullable=False),
    sa.Column('WTCode', sa.String(length=4), nullable=False),
    sa.ForeignKeyConstraint(['CardCode'], ['ocrd.CardCode'], name='fk_crd4_card_ocrd'),
    sa.ForeignKeyConstraint(['WTCode'], ['owht.WTCode'], name='fk_crd4_wt_owht'),
    sa.PrimaryKeyConstraint('CardCode', 'WTCode')
    )
    for table, header in (('pch5', 'opch'), ('rpc5', 'orpc')):
        op.create_table(table,
    sa.Column('LineNum', sa.Integer(), nullable=False),
    sa.Column('WTCode', sa.String(length=4), nullable=False),
    sa.Column('Rate', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('TaxbleAmnt', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('WTAmnt', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('WTAmntFC', sa.Numeric(precision=19, scale=6), nullable=False),
    sa.Column('Account', sa.String(length=15), nullable=False),
    sa.Column('Category', sa.String(length=1), nullable=False),
    sa.Column('Section', sa.String(length=10), nullable=True),
    sa.Column('NoPAN', sa.String(length=1), nullable=False),
    sa.Column('DocEntry', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['DocEntry'], [f'{header}.DocEntry'], name=f'fk_{table}_doc_{header}'),
        sa.PrimaryKeyConstraint('DocEntry', 'LineNum')
        )
    with op.batch_alter_table('ocrd') as batch_op:
        batch_op.add_column(sa.Column('WTLiable', sa.String(length=1), server_default='N', nullable=False))
        batch_op.add_column(sa.Column('PANNo', sa.String(length=10), nullable=True))
    for header in HEADERS:
        with op.batch_alter_table(header) as batch_op:
            batch_op.add_column(sa.Column('WTSum', sa.Numeric(precision=19, scale=6), server_default='0', nullable=False))
            batch_op.add_column(sa.Column('WTSumFC', sa.Numeric(precision=19, scale=6), server_default='0', nullable=False))


def downgrade() -> None:
    for header in HEADERS:
        with op.batch_alter_table(header) as batch_op:
            batch_op.drop_column('WTSumFC')
            batch_op.drop_column('WTSum')
    with op.batch_alter_table('ocrd') as batch_op:
        batch_op.drop_column('PANNo')
        batch_op.drop_column('WTLiable')
    op.drop_table('rpc5')
    op.drop_table('pch5')
    op.drop_table('crd4')
    op.drop_table('owht')
