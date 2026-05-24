"""model_updates_may_2026

Revision ID: 0ab60975e593
Revises: 233cbdadb4b6
Create Date: 2026-05-24 14:22:43.581764

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0ab60975e593"
down_revision: Union[str, None] = "233cbdadb4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Snapshot of supported model IDs as of 2026-05-24. Hardcoded on purpose:
# the migration must remain stable even if future code changes the model list.
SUPPORTED_MODEL_IDS: tuple[str, ...] = (
    # OpenAI
    "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "gpt-4o-transcribe", "gpt-4o-mini-transcribe",
    "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.5",
    "whisper-1", "text-embedding-3-small", "text-embedding-3-large",
    # Anthropic
    "claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-5",
    "claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-7",
    # Google AI
    "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest",
    "gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview",
    # xAI
    "grok-4.20-non-reasoning", "grok-4.20-reasoning", "grok-4.3",
    "grok-imagine-image", "grok-imagine-image-quality",
    # Perplexity
    "sonar", "sonar-pro", "sonar-reasoning-pro", "sonar-deep-research",
    # Replicate
    "black-forest-labs/flux-1.1-pro", "black-forest-labs/flux-kontext-pro",
    "black-forest-labs/flux-2-pro", "black-forest-labs/flux-2-max",
    "openai/gpt-image-1.5", "openai/gpt-image-2",
    "bytedance/seedream-4", "bytedance/seedream-4.5",
    "google/nano-banana", "google/nano-banana-pro", "google/nano-banana-2",
    # API Integrations
    "currency-converter5.p.rapidapi.com", "x.api-v2-post.read", "v1.cryptocurrency.quotes.latest",
    # Internal
    "credit_transfer",
)

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
    # grok-4-1-fast-* are now aliases of grok-4.3
    ("grok-4-1-fast-non-reasoning", "grok-4.3"),
    ("grok-4-1-fast-reasoning", "grok-4.3"),
    # grok-imagine-image-pro was renamed to grok-imagine-image-quality
    ("grok-imagine-image-pro", "grok-imagine-image-quality"),
    # gemini-3-flash-preview was the preview name for gemini-2.5-flash-image
    ("gemini-3-flash-preview", "gemini-2.5-flash-image"),
)


def upgrade() -> None:
    for old_id, new_id in RENAMES:
        for column in TOOL_CHOICE_COLUMNS:
            op.execute(
                text(f"UPDATE simulants SET {column} = '{new_id}' WHERE {column} = '{old_id}'"),
            )

    quoted_ids = ", ".join(f"'{id_}'" for id_ in SUPPORTED_MODEL_IDS)
    for column in TOOL_CHOICE_COLUMNS:
        op.execute(
            text(
                f"UPDATE simulants SET {column} = NULL "
                f"WHERE {column} IS NOT NULL AND {column} NOT IN ({quoted_ids})",
            ),
        )


def downgrade() -> None:
    # No-op: renamed model IDs cannot be losslessly restored.
    pass
