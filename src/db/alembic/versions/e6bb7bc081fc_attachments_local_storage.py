"""attachments_local_storage

Revision ID: e6bb7bc081fc
Revises: 87e83d8b46dc
Create Date: 2026-07-09 19:07:56.085716

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6bb7bc081fc"
down_revision: Union[str, None] = "87e83d8b46dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    the_agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "the-agent"))
    op.add_column("chat_message_attachments", sa.Column("uploader_user_id", sa.UUID(), nullable = True))
    op.add_column("chat_message_attachments", sa.Column("created_at", sa.DateTime(), nullable = True))
    op.execute(f"UPDATE chat_message_attachments SET uploader_user_id = '{the_agent_id}', created_at = NOW()")
    op.alter_column("chat_message_attachments", "uploader_user_id", nullable = False)
    op.alter_column("chat_message_attachments", "created_at", nullable = False)
    op.alter_column("chat_message_attachments", "message_id", existing_type = sa.VARCHAR(), nullable = True)
    op.drop_index(op.f("idx_external_id"), table_name = "chat_message_attachments")
    op.create_unique_constraint("uq_attachment_external_per_chat", "chat_message_attachments", ["chat_id", "external_id"])
    op.drop_constraint(op.f("chat_message_attachments_message_fkey"), "chat_message_attachments", type_ = "foreignkey")
    op.create_foreign_key("chat_message_attachments_chat_id_fkey", "chat_message_attachments", "chat_configs", ["chat_id"], ["chat_id"])  # noqa: E501
    op.create_foreign_key("chat_message_attachments_uploader_user_id_fkey", "chat_message_attachments", "simulants", ["uploader_user_id"], ["id"])  # noqa: E501
    op.add_column("chat_messages", sa.Column("is_temporary", sa.Boolean(), server_default = sa.text("false"), nullable = False))


def downgrade() -> None:
    op.drop_column("chat_messages", "is_temporary")
    op.drop_constraint("chat_message_attachments_uploader_user_id_fkey", "chat_message_attachments", type_ = "foreignkey")
    op.drop_constraint("chat_message_attachments_chat_id_fkey", "chat_message_attachments", type_ = "foreignkey")
    op.create_foreign_key(op.f("chat_message_attachments_message_fkey"), "chat_message_attachments", "chat_messages", ["chat_id", "message_id"], ["chat_id", "message_id"])  # noqa: E501
    op.drop_constraint("uq_attachment_external_per_chat", "chat_message_attachments", type_ = "unique")
    op.create_index(op.f("idx_external_id"), "chat_message_attachments", ["external_id"], unique = False)
    op.alter_column("chat_message_attachments", "message_id", existing_type = sa.VARCHAR(), nullable = False)
    op.drop_column("chat_message_attachments", "created_at")
    op.drop_column("chat_message_attachments", "uploader_user_id")
