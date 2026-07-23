"""grok_4_5_upgrade

Revision ID: 2c3d61b37410
Revises: 600635b77b75
Create Date: 2026-07-23 23:23:30.327454

"""
from typing import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "2c3d61b37410"
down_revision: str | None = "600635b77b75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOOL_CHOICE_COLUMNS: tuple[str, ...] = (
    "tool_choice_chat",
    "tool_choice_reasoning",
    "tool_choice_copywriting",
    "tool_choice_vision",
    "tool_choice_hearing",
    "tool_choice_images_gen",
    "tool_choice_images_edit",
    "tool_choice_search",
    "tool_choice_embedding",
    "tool_choice_api_fiat_exchange",
    "tool_choice_api_crypto_exchange",
    "tool_choice_api_twitter",
)

RENAMES: tuple[tuple[str, str], ...] = (
    ("grok-4.20-non-reasoning", "grok-4.3"),
    ("grok-4.20-reasoning", "grok-4.3"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(
                text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"),
            )


def downgrade() -> None:
    # no-op: both previous model choices map to the same replacement.
    pass
