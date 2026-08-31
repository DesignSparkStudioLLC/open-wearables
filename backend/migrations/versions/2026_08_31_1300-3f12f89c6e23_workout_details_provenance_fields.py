"""workout_details_provenance_fields

Revision ID: 3f12f89c6e23
Revises: dc5ac28c4b94

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f12f89c6e23"
down_revision: Union[str, None] = "dc5ac28c4b94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workout_details", sa.Column("entry_source", sa.String(length=32), nullable=True))
    op.add_column("workout_details", sa.Column("intensity", sa.String(length=10), nullable=True))
    op.add_column("workout_details", sa.Column("label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("workout_details", "label")
    op.drop_column("workout_details", "intensity")
    op.drop_column("workout_details", "entry_source")
