"""care_requested replaces plant_sitting

Revision ID: c3a1f0d2e4b5
Revises: b167118927ca
Create Date: 2026-10-20 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a1f0d2e4b5'
down_revision: Union[str, None] = 'b167118927ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode keeps SQLite (tests) working; the checks let it run on databases first built by create_all
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('plants')}
    with op.batch_alter_table('plants') as batch_op:
        if 'care_requested' not in columns:
            batch_op.add_column(sa.Column('care_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
        if 'plant_sitting' in columns:
            batch_op.drop_column('plant_sitting')


def downgrade() -> None:
    with op.batch_alter_table('plants') as batch_op:
        batch_op.add_column(sa.Column('plant_sitting', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('plants_plant_sitting_fkey', 'users', ['plant_sitting'], ['id'])
        batch_op.drop_column('care_requested')
