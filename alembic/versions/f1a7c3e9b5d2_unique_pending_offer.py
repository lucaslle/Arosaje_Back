"""one pending care offer per member and plant

Revision ID: f1a7c3e9b5d2
Revises: e8c4a1b6d2f7
Create Date: 2026-10-21 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a7c3e9b5d2'
down_revision: Union[str, None] = 'e8c4a1b6d2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # duplicates created before the index existed: keep the oldest pending offer, cancel the others
    op.execute(
        "UPDATE care_offers SET status = 'cancelled' WHERE status = 'pending' AND id NOT IN ("
        "SELECT MIN(id) FROM care_offers WHERE status = 'pending' GROUP BY plant_id, sitter_id)"
    )
    op.create_index(
        'uq_care_offers_pending_sitter', 'care_offers', ['plant_id', 'sitter_id'], unique=True,
        postgresql_where=sa.text("status = 'pending'"), sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index('uq_care_offers_pending_sitter', table_name='care_offers')
