"""store e-mails in lower case so login ignores case

Revision ID: e8c4a1b6d2f7
Revises: d5b2e7a9c1f3
Create Date: 2026-10-20 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8c4a1b6d2f7'
down_revision: Union[str, None] = 'd5b2e7a9c1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.security import security_manager

    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, email_encrypted, email_hash FROM users")).fetchall()
    taken = {user.email_hash for user in users}
    for user in users:
        if not user.email_encrypted:
            continue
        email = security_manager.decrypt_value(user.email_encrypted).strip().lower()
        email_hash = security_manager.hash_value(email)
        # two accounts that only differ by case: keep both untouched, an admin has to merge them
        if email_hash == user.email_hash or email_hash in taken:
            continue
        bind.execute(
            sa.text("UPDATE users SET email_hash = :hash, email_encrypted = :encrypted WHERE id = :id"),
            {"hash": email_hash, "encrypted": security_manager.encrypt_value(email), "id": user.id},
        )
        taken.add(email_hash)


def downgrade() -> None:
    # the original case is gone; lower-case addresses keep working with the previous code for exact matches
    pass
