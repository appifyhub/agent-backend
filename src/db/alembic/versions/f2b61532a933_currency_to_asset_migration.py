"""currency_to_asset_migration

Revision ID: f2b61532a933
Revises: 5acf7f96c138
Create Date: 2026-07-25 01:50:54.512219

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from alembic.util import CommandError

# revision identifiers, used by Alembic.
revision: str = "f2b61532a933"
down_revision: Union[str, None] = "5acf7f96c138"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("pk_price_alert", "price_alerts", type_ = "primary")
    op.alter_column(
        "price_alerts",
        "base_currency",
        new_column_name = "asset_id",
        existing_type = sa.String(),
        existing_nullable = False,
    )
    op.alter_column(
        "price_alerts",
        "desired_currency",
        new_column_name = "currency",
        existing_type = sa.String(),
        existing_nullable = False,
    )
    op.add_column("price_alerts", sa.Column("asset_type", sa.String(), nullable = True))
    op.execute(sa.text("UPDATE price_alerts SET asset_type = 'crypto'"))
    op.alter_column(
        "price_alerts",
        "asset_type",
        existing_type = sa.String(),
        nullable = False,
    )
    op.create_primary_key(
        "pk_price_alert",
        "price_alerts",
        ["chat_id", "asset_type", "asset_id", "currency"],
    )


def downgrade() -> None:
    unsupported_alerts = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM price_alerts WHERE asset_type != 'crypto'"),
    ).scalar_one()
    if unsupported_alerts:
        raise CommandError("Cannot downgrade while non-crypto price alerts exist")

    op.drop_constraint("pk_price_alert", "price_alerts", type_ = "primary")
    op.drop_column("price_alerts", "asset_type")
    op.alter_column(
        "price_alerts",
        "asset_id",
        new_column_name = "base_currency",
        existing_type = sa.String(),
        existing_nullable = False,
    )
    op.alter_column(
        "price_alerts",
        "currency",
        new_column_name = "desired_currency",
        existing_type = sa.String(),
        existing_nullable = False,
    )
    op.create_primary_key(
        "pk_price_alert",
        "price_alerts",
        ["chat_id", "base_currency", "desired_currency"],
    )
