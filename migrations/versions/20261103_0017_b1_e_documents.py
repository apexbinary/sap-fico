"""b1 e-documents (e-invoice IRN, e-way bill) and company address

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-03 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('adm1',
    sa.Column('Code', sa.Integer(), nullable=False),
    sa.Column('Street', sa.String(length=100), nullable=True),
    sa.Column('Block', sa.String(length=100), nullable=True),
    sa.Column('City', sa.String(length=100), nullable=True),
    sa.Column('ZipCode', sa.String(length=20), nullable=True),
    sa.PrimaryKeyConstraint('Code')
    )
    op.create_table('edoc',
    sa.Column('AbsEntry', sa.Integer(), nullable=False),
    sa.Column('ObjType', sa.String(length=20), nullable=False),
    sa.Column('DocEntry', sa.Integer(), nullable=False),
    sa.Column('Kind', sa.String(length=1), nullable=False),
    sa.Column('Status', sa.String(length=1), nullable=False),
    sa.Column('Mode', sa.String(length=1), nullable=False),
    sa.Column('Irn', sa.String(length=64), nullable=True),
    sa.Column('AckNo', sa.String(length=20), nullable=True),
    sa.Column('AckDate', sa.DateTime(), nullable=True),
    sa.Column('SignedQR', sa.Text(), nullable=True),
    sa.Column('EwbNo', sa.String(length=12), nullable=True),
    sa.Column('EwbDate', sa.DateTime(), nullable=True),
    sa.Column('ValidUntil', sa.DateTime(), nullable=True),
    sa.Column('TransMode', sa.String(length=1), nullable=True),
    sa.Column('Distance', sa.Integer(), nullable=True),
    sa.Column('TransId', sa.String(length=15), nullable=True),
    sa.Column('TransName', sa.String(length=100), nullable=True),
    sa.Column('VehicleNo', sa.String(length=20), nullable=True),
    sa.Column('VehicleTyp', sa.String(length=1), nullable=True),
    sa.Column('TransDocNo', sa.String(length=15), nullable=True),
    sa.Column('TransDocDt', sa.Date(), nullable=True),
    sa.Column('CnclReason', sa.String(length=1), nullable=True),
    sa.Column('CnclRemark', sa.String(length=100), nullable=True),
    sa.Column('CnclDate', sa.DateTime(), nullable=True),
    sa.Column('Payload', sa.Text(), nullable=True),
    sa.Column('UserSign', sa.String(length=25), nullable=True),
    sa.Column('CreateDate', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('AbsEntry')
    )
    op.create_index(op.f('ix_edoc_ObjType'), 'edoc', ['ObjType'], unique=False)
    op.create_index(op.f('ix_edoc_DocEntry'), 'edoc', ['DocEntry'], unique=False)
    op.create_index(op.f('ix_edoc_Irn'), 'edoc', ['Irn'], unique=False)
    op.create_index(op.f('ix_edoc_EwbNo'), 'edoc', ['EwbNo'], unique=False)
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.add_column(sa.Column('EInvoice', sa.String(length=1), server_default='N', nullable=False))
        batch_op.add_column(sa.Column('EWayBill', sa.String(length=1), server_default='N', nullable=False))
        batch_op.add_column(sa.Column('EDocMode', sa.String(length=1), server_default='T', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('oadm') as batch_op:
        batch_op.drop_column('EDocMode')
        batch_op.drop_column('EWayBill')
        batch_op.drop_column('EInvoice')
    op.drop_index(op.f('ix_edoc_EwbNo'), table_name='edoc')
    op.drop_index(op.f('ix_edoc_Irn'), table_name='edoc')
    op.drop_index(op.f('ix_edoc_DocEntry'), table_name='edoc')
    op.drop_index(op.f('ix_edoc_ObjType'), table_name='edoc')
    op.drop_table('edoc')
    op.drop_table('adm1')
