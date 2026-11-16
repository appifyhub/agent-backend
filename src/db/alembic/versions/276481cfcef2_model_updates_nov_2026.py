"""model_updates_nov_2026

Revision ID: 276481cfcef2
Revises: 300b9b81d251
Create Date: 2026-11-16 22:50:44.264225

"""
from typing import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "276481cfcef2"
down_revision: str | None = "300b9b81d251"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOOL_CHOICE_COLUMNS: tuple[str, ...] = (
    "tool_choice_chat",
    "tool_choice_reasoning",
    "tool_choice_copywriting",
    "tool_choice_vision",
    "tool_choice_hearing",
    "tool_choice_images_gen",
    "tool_choice_videos_gen",
    "tool_choice_search",
    "tool_choice_embedding",
    "tool_choice_api_fiat_exchange",
    "tool_choice_api_crypto_exchange",
    "tool_choice_api_stock_quote",
    "tool_choice_api_twitter",
)

RENAMES: tuple[tuple[str, str], ...] = (
    # Replicate images
    ("openai/gpt-image-2.5-flare", "openai/gpt-image-2.6-flare"),
    ("openai/gpt-image-2.5-sunburst", "openai/gpt-image-2.6-sunburst"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(
                text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"),
            )


def downgrade() -> None:
    # no-op: the 2.5 models are no longer available
    pass
