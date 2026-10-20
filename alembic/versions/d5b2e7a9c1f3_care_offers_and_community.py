"""care offers, messages, journal, favorites, botanist advice and reviews

Revision ID: d5b2e7a9c1f3
Revises: c3a1f0d2e4b5
Create Date: 2026-10-20 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5b2e7a9c1f3'
down_revision: Union[str, None] = 'c3a1f0d2e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('botanist_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('plants') as batch_op:
        batch_op.add_column(sa.Column('care_requested_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('care_start', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('care_end', sa.Date(), nullable=True))

    op.create_table('care_offers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('sitter_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('wait_seconds', sa.Integer(), nullable=True),
    )
    op.create_table('messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('care_offers.id'), nullable=False, index=True),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table('care_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table('favorites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'plant_id'),
    )
    op.create_table('advice_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('question', sa.String(length=1000), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_table('reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('care_offers.id'), nullable=False, unique=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('sitter_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    for table in ('reviews', 'advice_requests', 'favorites', 'care_logs', 'messages', 'care_offers'):
        op.drop_table(table)
    with op.batch_alter_table('plants') as batch_op:
        batch_op.drop_column('care_end')
        batch_op.drop_column('care_start')
        batch_op.drop_column('care_requested_at')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('botanist_verified')
