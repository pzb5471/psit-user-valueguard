"""Persist human review execution notes.

Revision ID: b6d9f2a7c103
Revises: dc4c1050e0af
"""

import sqlalchemy as sa
from alembic import op

revision = "b6d9f2a7c103"
down_revision = "dc4c1050e0af"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("execution_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "execution_note")
