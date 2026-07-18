from logging.config import fileConfig

from alembic import context
from alembic.config import Config as AlembicConfig
from sqlalchemy import engine_from_config, pool

# Base model is used by alembic
from db.model.base import BaseModel

# noinspection PyUnresolvedReferences
from db.model.chat_attachment import ChatAttachmentDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.chat_config import ChatConfigDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.chat_membership import ChatMembershipDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.chat_message import ChatMessageDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.price_alert import PriceAlertDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.purchase_record import PurchaseRecordDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.sponsorship import SponsorshipDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.tools_cache import ToolsCacheDB  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.usage_record import UsageRecordDB  # used by alembic  # noqa: F401

# noinspection PyUnresolvedReferences
from db.model.user import UserDB  # used by alembic  # noqa: F401
from util.config import config as app_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config: AlembicConfig = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = BaseModel.metadata

# Get the database URL from an environment variable
# noinspection PyUnresolvedReferences
config.set_main_option("sqlalchemy.url", app_config.db_url.get_secret_value())


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine, though an Engine is acceptable here as well.
    By skipping the Engine creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the script output.
    """

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url = url,
        target_metadata = target_metadata,
        literal_binds = True,
        dialect_opts = {"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection with the context.
    """

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix = "sqlalchemy.",
        poolclass = pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection = connection,
            target_metadata = target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
