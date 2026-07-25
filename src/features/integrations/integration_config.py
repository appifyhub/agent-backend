import uuid

from pydantic import SecretStr

from db.model.user import UserDB
from features.users.user import User
from util.config import config

# === Core Agent (chat and core operations) ===

THE_AGENT = User(
    id = uuid.uuid5(uuid.NAMESPACE_DNS, "the-agent"),
    full_name = config.agent_bot_name,
    group = UserDB.Group.standard,
    telegram_username = config.telegram_bot_username,
    telegram_chat_id = str(config.telegram_bot_id),
    telegram_user_id = config.telegram_bot_id,
    whatsapp_user_id = config.whatsapp_phone_number_id,
    whatsapp_phone_number = SecretStr(config.whatsapp_bot_phone_number),
)

# === Background Agent (runs scheduled/background tasks) ===

BACKGROUND_AGENT = User(
    id = uuid.uuid5(uuid.NAMESPACE_DNS, "the-agent-background"),
    full_name = config.background_bot_name,
    group = UserDB.Group.standard,
)

# === Publicly Known Agents ===

SYSTEM_AGENTS: list[User] = [THE_AGENT, BACKGROUND_AGENT]

# === Platform Reactions ===

TELEGRAM_REACTIONS: list[str] = [
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩",
    "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆", "💔",
    "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇",
    "😨", "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿", "🆒", "💘", "🙉", "🦄", "😘",
    "💊", "🙊", "😎", "👾", "🤷‍♂️", "😡",
]

WHATSAPP_REACTIONS: list[str] = [
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩",
    "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆",
    "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈",
    "😇", "😨", "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿", "🆒", "💘", "🙉", "🦄",
    "😘", "💊", "🙊", "😎", "👾", "🤷‍♂️", "😡",
]

# === Platform Notification Intervals (in seconds) ===

TELEGRAM_REACTION_INTERVAL_S = 30
TELEGRAM_REACTION_INITIAL_DELAY_S = 15

WHATSAPP_REACTION_INTERVAL_S = 15
WHATSAPP_REACTION_INITIAL_DELAY_S = 0

# === Platform Photo Size Limits (in bytes, when sending via HTTP URL) ===

TELEGRAM_MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB (10 MB for multipart upload, but we use URLs)
WHATSAPP_MAX_PHOTO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
