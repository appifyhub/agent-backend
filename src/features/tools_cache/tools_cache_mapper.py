from db.model.tools_cache import ToolsCacheDB
from features.tools_cache.tools_cache import ToolsCache


def domain(db_model: ToolsCacheDB | None) -> ToolsCache | None:
    if db_model is None:
        return None

    return ToolsCache(
        key = db_model.key,
        value = db_model.value,
        created_at = db_model.created_at,
        expires_at = db_model.expires_at,
    )


def db(domain_model: ToolsCache | None) -> ToolsCacheDB | None:
    if domain_model is None:
        return None

    return ToolsCacheDB(
        key = domain_model.key,
        value = domain_model.value,
        created_at = domain_model.created_at,
        expires_at = domain_model.expires_at,
    )


def apply_to_db_model(
    domain_model: ToolsCache,
    db_model: ToolsCacheDB,
) -> None:
    db_model.value = domain_model.value
    db_model.created_at = domain_model.created_at
    db_model.expires_at = domain_model.expires_at
