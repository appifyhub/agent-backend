"""model_upgrades_gpt5.6_opus5

Revision ID: 32b3ae52bbdf
Revises: f2b61532a933
Create Date: 2026-07-25 17:07:15.586401

"""
from typing import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "32b3ae52bbdf"
down_revision: str | None = "f2b61532a933"
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
    "tool_choice_api_stock_quote",
    "tool_choice_api_twitter",
)

RENAMES: tuple[tuple[str, str], ...] = (
    ("gpt-4.1", "gpt-5.5"),
    ("gpt-4.1-mini", "gpt-5.6-terra"),
    ("gpt-5", "gpt-5.5"),
    ("gpt-5-mini", "gpt-5.6-terra"),
    ("gpt-5.1", "gpt-5.5"),
    ("gpt-5.2", "gpt-5.5"),
    ("gpt-4o", "gpt-5.5"),
    ("gpt-4o-mini", "gpt-5.6-terra"),
    ("claude-opus-4-7", "claude-sonnet-5"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"))


def downgrade() -> None:
    # no-op: target model choices may have existed before this migration
    pass
