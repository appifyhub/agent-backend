from db.model.price_alert import PriceAlertDB
from features.currencies.asset_price import AssetType
from features.currencies.price_alert import PriceAlert


def domain(db_model: PriceAlertDB | None) -> PriceAlert | None:
    if db_model is None:
        return None

    return PriceAlert(
        chat_id = db_model.chat_id,
        owner_id = db_model.owner_id,
        asset_type = AssetType(db_model.asset_type),
        asset_id = db_model.asset_id,
        currency = db_model.currency,
        threshold_percent = db_model.threshold_percent,
        last_price = db_model.last_price,
        last_price_time = db_model.last_price_time,
    )


def db(domain_model: PriceAlert | None) -> PriceAlertDB | None:
    if domain_model is None:
        return None

    return PriceAlertDB(
        chat_id = domain_model.chat_id,
        owner_id = domain_model.owner_id,
        asset_type = domain_model.asset_type.value,
        asset_id = domain_model.asset_id,
        currency = domain_model.currency,
        threshold_percent = domain_model.threshold_percent,
        last_price = domain_model.last_price,
        last_price_time = domain_model.last_price_time,
    )


def apply_to_db_model(
    domain_model: PriceAlert,
    db_model: PriceAlertDB,
) -> None:
    db_model.owner_id = domain_model.owner_id
    db_model.threshold_percent = domain_model.threshold_percent
    db_model.last_price = domain_model.last_price
    db_model.last_price_time = domain_model.last_price_time
