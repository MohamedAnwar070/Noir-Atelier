"""Initial 32-table Noir Atelier schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-11-03
"""
from typing import Sequence, Union

from alembic import op

from backend.app.models import Base

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
