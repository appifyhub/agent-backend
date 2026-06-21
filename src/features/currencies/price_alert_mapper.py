from db.model.price_alert import PriceAlertDB
from features.currencies.price_alert import PriceAlert


def domain(db_model: PriceAlertDB | None) -> PriceAlert | None:
    if db_model is None:
        return None

    return PriceAlert(
        chat_id = db_model.chat_id,
        owner_id = db_model.owner_id,
        base_currency = db_model.base_currency,
        desired_currency = db_model.desired_currency,
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
        base_currency = domain_model.base_currency,
        desired_currency = domain_model.desired_currency,
        threshold_percent = domain_model.threshold_percent,
        last_price = domain_model.last_price,
        last_price_time = domain_model.last_price_time,
    )
