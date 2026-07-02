"""update_claude_models_fable

Revision ID: 87e83d8b46dc
Revises: 7006448c522a
Create Date: 2026-07-02 15:13:20.552402

"""
from typing import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "87e83d8b46dc"
down_revision: str | None = "7006448c522a"
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
    ("claude-sonnet-4-5", "claude-sonnet-4-6"),
    ("claude-opus-4-6", "claude-opus-4-7"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(
                text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"),
            )


def downgrade() -> None:
    # no-op: target model choices may have existed before this migration.
    pass
