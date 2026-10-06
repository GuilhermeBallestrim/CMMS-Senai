"""schema inicial

Revision ID: 6fbbdcbcf64e
Revises: 
Create Date: 2026-10-06 13:41:42.237051

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '6fbbdcbcf64e'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('sectors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('unit_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unit_name', sa.String(length=160), nullable=False),
    sa.Column('timezone_name', sa.String(length=80), nullable=False),
    sa.Column('notify_admin_new_call', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=24), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('professor', 'administrator')", name='ck_users_role'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('equipment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('sector_id', sa.Integer(), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('asset_tag', sa.String(length=80), nullable=False),
    sa.Column('serial_number', sa.String(length=100), nullable=True),
    sa.Column('acquired_at', sa.Date(), nullable=True),
    sa.Column('responsible_id', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('photo_name', sa.String(length=255), nullable=True),
    sa.Column('manual_name', sa.String(length=255), nullable=True),
    sa.Column('photo_mime', sa.String(length=40), nullable=True),
    sa.Column('manual_mime', sa.String(length=40), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['responsible_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sector_id'], ['sectors.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('asset_tag')
    )
    op.create_index(op.f('ix_equipment_name'), 'equipment', ['name'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('href', sa.String(length=255), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('purchase_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=24), nullable=False),
    sa.Column('item_type', sa.String(length=40), nullable=False),
    sa.Column('item', sa.String(length=180), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('justification', sa.Text(), nullable=False),
    sa.Column('requester_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_purchase_requests_number'), 'purchase_requests', ['number'], unique=True)
    op.create_table('maintenance_calls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=24), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('requester_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('priority', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('photo_name', sa.String(length=255), nullable=True),
    sa.Column('photo_mime', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_maintenance_calls_number'), 'maintenance_calls', ['number'], unique=True)
    op.create_table('work_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=24), nullable=False),
    sa.Column('call_id', sa.Integer(), nullable=False),
    sa.Column('responsible_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('defect', sa.Text(), nullable=True),
    sa.Column('cause', sa.Text(), nullable=True),
    sa.Column('solution', sa.Text(), nullable=True),
    sa.Column('parts', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['call_id'], ['maintenance_calls.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['responsible_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id')
    )
    op.create_index(op.f('ix_work_orders_number'), 'work_orders', ['number'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_work_orders_number'), table_name='work_orders')
    op.drop_table('work_orders')
    op.drop_index(op.f('ix_maintenance_calls_number'), table_name='maintenance_calls')
    op.drop_table('maintenance_calls')
    op.drop_index(op.f('ix_purchase_requests_number'), table_name='purchase_requests')
    op.drop_table('purchase_requests')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_equipment_name'), table_name='equipment')
    op.drop_table('equipment')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('unit_settings')
    op.drop_table('sectors')
