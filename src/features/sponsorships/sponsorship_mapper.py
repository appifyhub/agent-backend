from db.model.sponsorship import SponsorshipDB
from features.sponsorships.sponsorship import Sponsorship


def domain(db_model: SponsorshipDB | None) -> Sponsorship | None:
    if db_model is None:
        return None

    return Sponsorship(
        sponsor_id = db_model.sponsor_id,
        receiver_id = db_model.receiver_id,
        sponsored_at = db_model.sponsored_at,
        accepted_at = db_model.accepted_at,
    )


def db(domain_model: Sponsorship | None) -> SponsorshipDB | None:
    if domain_model is None:
        return None

    return SponsorshipDB(
        sponsor_id = domain_model.sponsor_id,
        receiver_id = domain_model.receiver_id,
        sponsored_at = domain_model.sponsored_at,
        accepted_at = domain_model.accepted_at,
    )


def apply_to_db_model(
    domain_model: Sponsorship,
    db_model: SponsorshipDB,
) -> None:
    db_model.sponsored_at = domain_model.sponsored_at
    db_model.accepted_at = domain_model.accepted_at
