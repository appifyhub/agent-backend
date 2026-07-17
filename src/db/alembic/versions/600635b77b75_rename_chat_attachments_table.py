"""rename_chat_attachments_table

Revision ID: 600635b77b75
Revises: 6faaf160de6e
Create Date: 2026-07-17 16:42:23.539255

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "600635b77b75"
down_revision: Union[str, None] = "6faaf160de6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("chat_message_attachments", "chat_attachments")


def downgrade() -> None:
    op.rename_table("chat_attachments", "chat_message_attachments")
