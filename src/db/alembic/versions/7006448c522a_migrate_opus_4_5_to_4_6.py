"""migrate_opus_4_5_to_4_6

Revision ID: 7006448c522a
Revises: 0ab60975e593
Create Date: 2026-05-30 12:23:32.047011

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "7006448c522a"
down_revision: Union[str, None] = "0ab60975e593"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ID = "claude-opus-4-5"
NEW_ID = "claude-opus-4-6"

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


def upgrade() -> None:
    for column in TOOL_CHOICE_COLUMNS:
        op.execute(
            text(f"UPDATE simulants SET {column} = '{NEW_ID}' WHERE {column} = '{OLD_ID}'"),
        )


def downgrade() -> None:
    for column in TOOL_CHOICE_COLUMNS:
        op.execute(
            text(f"UPDATE simulants SET {column} = '{OLD_ID}' WHERE {column} = '{NEW_ID}'"),
        )
