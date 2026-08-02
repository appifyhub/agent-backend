"""unify_async_image_generation

Revision ID: a5fee1e83958
Revises: d938153994a8
Create Date: 2026-08-03 01:08:53.324198

"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5fee1e83958"
down_revision: str | None = "d938153994a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE simulants
        SET tool_choice_images_gen = tool_choice_images_edit
        WHERE tool_choice_images_edit IS NOT NULL
    """))
    op.execute(sa.text("""
        UPDATE simulants
        SET tool_choice_images_gen = 'black-forest-labs/flux-2-pro'
        WHERE tool_choice_images_gen = 'black-forest-labs/flux-1.1-pro'
    """))
    op.execute(sa.text("""
        UPDATE usage_records
        SET purpose = 'images_gen'
        WHERE purpose = 'images_edit'
    """))
    op.drop_column("simulants", "tool_choice_images_edit")


def downgrade() -> None:
    # lossy downgrade: original choices, Flux IDs, and usage purposes cannot be reconstructed
    op.add_column("simulants", sa.Column("tool_choice_images_edit", sa.VARCHAR(), autoincrement = False, nullable = True))
