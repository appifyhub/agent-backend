"""model_updates_oct_2026

Revision ID: 76d67c22d89a
Revises: 10fae7224448
Create Date: 2026-10-12 02:32:58.943527

"""
from typing import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "76d67c22d89a"
down_revision: str | None = "10fae7224448"
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
    # OpenAI text
    ("gpt-5-nano", "gpt-6-luna"),
    ("gpt-5.4", "gpt-5.6-terra"),
    ("gpt-5.5", "gpt-5.6-sol"),
    # OpenAI transcription
    ("gpt-4o-mini-transcribe", "gpt-transcribe"),
    ("gpt-4o-transcribe", "gpt-transcribe"),
    ("whisper-1", "gpt-transcribe"),
    # Anthropic
    ("claude-haiku-4-5", "claude-haiku-5-5"),
    ("claude-sonnet-5", "claude-sonnet-5-5"),
    ("claude-opus-5", "claude-opus-5-5"),
    ("claude-fable-5", "claude-fable-5-1"),
    # Google AI images
    ("gemini-2.5-flash-image", "gemini-3.1-flash-lite-image"),
    ("gemini-3.1-flash-image-preview", "gemini-nano-banana-2.1"),
    ("gemini-3-pro-image-preview", "gemini-3-pro-image"),
    # xAI
    ("grok-4.5", "grok-4.7"),
    ("grok-imagine-image-quality", "grok-imagine-image-2.0"),
    # Replicate images
    ("black-forest-labs/flux-kontext-pro", "black-forest-labs/flux-3-image"),
    ("openai/gpt-image-1.5", "openai/gpt-image-2.5-flare"),
    ("openai/gpt-image-2", "openai/gpt-image-2.5-flare"),
    ("google/nano-banana", "google/nano-banana-2.1"),
    ("google/nano-banana-2", "google/nano-banana-2.1"),
    # Replicate video
    ("bytedance/seedance-2.0", "bytedance/seedance-2.5"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(
                text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"),
            )


def downgrade() -> None:
    # no-op: several previous model choices map to the same replacement
    pass
