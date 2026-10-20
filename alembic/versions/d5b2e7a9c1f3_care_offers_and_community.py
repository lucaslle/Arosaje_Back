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
    # each step is skipped when it already exists: databases first built by create_all have part of it
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    user_columns = {column['name'] for column in inspector.get_columns('users')}
    plant_columns = {column['name'] for column in inspector.get_columns('plants')}

    if 'botanist_verified' not in user_columns:
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('botanist_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('plants') as batch_op:
        for name, column_type in (('care_requested_at', sa.DateTime()), ('care_start', sa.Date()), ('care_end', sa.Date())):
            if name not in plant_columns:
                batch_op.add_column(sa.Column(name, column_type, nullable=True))

    def create(name, *columns):
        if name not in tables:
            op.create_table(name, *columns)

    create('care_offers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('sitter_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('wait_seconds', sa.Integer(), nullable=True),
    )
    create('messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('care_offers.id'), nullable=False, index=True),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    create('care_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('photo_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    create('favorites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'plant_id'),
    )
    create('advice_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plant_id', sa.Integer(), sa.ForeignKey('plants.id'), nullable=False, index=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('question', sa.String(length=1000), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    create('reviews',
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
