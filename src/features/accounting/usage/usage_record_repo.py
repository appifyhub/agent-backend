from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, or_
from sqlalchemy.orm import Query, Session

from db.model.usage_record import UsageRecordDB
from features.accounting.usage.usage_aggregates import AggregateStats, ProviderInfo, ToolInfo, UsageAggregates
from features.accounting.usage.usage_record import UsageRecord
from features.accounting.usage.usage_record_mapper import db, domain
from features.external_tools.external_tool import ToolType


class UsageRecordRepository:

    _db: Session

    def __init__(self, db: Session):
        self._db = db

    def get(self, record_id: UUID) -> UsageRecord | None:
        db_model = self._db.query(UsageRecordDB).filter(UsageRecordDB.id == record_id).first()
        return domain(db_model)

    def create(self, record: UsageRecord, commit: bool = True) -> UsageRecord:
        db_model = db(record)
        self._db.add(db_model)

        self._db.flush()
        if commit:
            self._db.commit()

        self._db.refresh(db_model)
        return domain(db_model)

    def create_all(self, records: list[UsageRecord]) -> list[UsageRecord]:
        db_models = [db(record) for record in records]
        for db_model in db_models:
            self._db.add(db_model)
        self._db.commit()
        for db_model in db_models:
            self._db.refresh(db_model)
        return [domain(db_model) for db_model in db_models]

    def get_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        exclude_self: bool = False,
        include_sponsored: bool = False,
        include_transfers: bool = True,
        only_transfers: bool = False,
        tool_id: str | None = None,
        purpose: str | None = None,
        provider_id: str | None = None,
    ) -> list[UsageRecord]:
        base_query = self._build_user_query(
            user_id, start_date, end_date,
            exclude_self, include_sponsored,
            include_transfers, only_transfers,
        )

        # apply optional filters
        if tool_id:
            base_query = base_query.filter(UsageRecordDB.tool_id == tool_id)
        if purpose:
            base_query = base_query.filter(UsageRecordDB.purpose == purpose)
        if provider_id:
            base_query = base_query.filter(UsageRecordDB.provider_id == provider_id)

        db_models = base_query.order_by(UsageRecordDB.timestamp.desc()).offset(skip).limit(limit).all()
        return [domain(db_model) for db_model in db_models]

    def get_aggregates_by_user(
        self,
        user_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        exclude_self: bool = False,
        include_sponsored: bool = False,
        include_transfers: bool = True,
        only_transfers: bool = False,
        tool_id: str | None = None,
        purpose: str | None = None,
        provider_id: str | None = None,
    ) -> UsageAggregates:
        # unfiltered query for all_*_used lists (dropdown options)
        unfiltered_query = self._build_user_query(
            user_id, start_date, end_date,
            exclude_self, include_sponsored,
            include_transfers, only_transfers,
        )
        unfiltered_subquery = unfiltered_query.subquery()

        # filtered query for totals and by_* breakdowns
        filtered_query = self._build_user_query(
            user_id, start_date, end_date,
            exclude_self, include_sponsored,
            include_transfers, only_transfers,
        )
        if tool_id:
            filtered_query = filtered_query.filter(UsageRecordDB.tool_id == tool_id)
        if purpose:
            filtered_query = filtered_query.filter(UsageRecordDB.purpose == purpose)
        if provider_id:
            filtered_query = filtered_query.filter(UsageRecordDB.provider_id == provider_id)
        filtered_subquery = filtered_query.subquery()

        # totals from filtered query
        total_records = int(self._db.query(func.count(filtered_subquery.c.id)).scalar() or 0)
        total_cost = float(self._db.query(func.sum(filtered_subquery.c.total_cost_credits)).scalar() or 0.0)
        total_runtime = float(self._db.query(func.sum(filtered_subquery.c.runtime_seconds)).scalar() or 0.0)

        # per-tool aggregated stats from filtered query (keyed by tool_id)
        by_tool: dict[str, AggregateStats] = {}
        tool_stats = self._db.query(
            filtered_subquery.c.tool_id,
            func.count(filtered_subquery.c.id).label("count"),
            func.sum(filtered_subquery.c.total_cost_credits).label("total_cost"),
        ).group_by(filtered_subquery.c.tool_id).all()
        for tool_id_val, count, total_cost_val in tool_stats:
            by_tool[str(tool_id_val)] = AggregateStats(
                record_count = int(count),
                total_cost = float(total_cost_val or 0),
            )

        # per-purpose aggregated stats from filtered query
        by_purpose: dict[str, AggregateStats] = {}
        purpose_stats = self._db.query(
            filtered_subquery.c.purpose,
            func.count(filtered_subquery.c.id).label("count"),
            func.sum(filtered_subquery.c.total_cost_credits).label("total_cost"),
        ).group_by(filtered_subquery.c.purpose).all()
        for purpose_val, count, total_cost_val in purpose_stats:
            by_purpose[str(purpose_val)] = AggregateStats(
                record_count = int(count),
                total_cost = float(total_cost_val or 0),
            )

        # per-provider aggregated stats from filtered query (keyed by provider_id)
        by_provider: dict[str, AggregateStats] = {}
        provider_stats = self._db.query(
            filtered_subquery.c.provider_id,
            func.count(filtered_subquery.c.id).label("count"),
            func.sum(filtered_subquery.c.total_cost_credits).label("total_cost"),
        ).group_by(filtered_subquery.c.provider_id).all()
        for provider_id_val, count, total_cost_val in provider_stats:
            by_provider[str(provider_id_val)] = AggregateStats(
                record_count = int(count),
                total_cost = float(total_cost_val or 0),
            )

        # all_*_used lists from UNFILTERED query (for dropdown population)
        all_tools_db = self._db.query(
            unfiltered_subquery.c.tool_id,
            unfiltered_subquery.c.tool_name,
        ).distinct().all()
        all_tools_used = sorted(
            [ToolInfo(id = str(row[0]), name = str(row[1])) for row in all_tools_db],
            key = lambda x: x.name,
        )
        all_purposes_db = self._db.query(
            unfiltered_subquery.c.purpose,
        ).distinct().all()
        all_purposes_used = sorted([str(row[0]) for row in all_purposes_db])
        all_providers_db = self._db.query(
            unfiltered_subquery.c.provider_id,
            unfiltered_subquery.c.provider_name,
        ).distinct().all()
        all_providers_used = sorted(
            [ProviderInfo(id = str(row[0]), name = str(row[1])) for row in all_providers_db],
            key = lambda x: x.name,
        )

        return UsageAggregates(
            total_records = total_records,
            total_cost_credits = total_cost,
            total_runtime_seconds = total_runtime,
            by_tool = by_tool,
            by_purpose = by_purpose,
            by_provider = by_provider,
            all_tools_used = all_tools_used,
            all_purposes_used = all_purposes_used,
            all_providers_used = all_providers_used,
        )

    def _build_user_query(
        self,
        user_id: UUID,
        start_date: datetime | None,
        end_date: datetime | None,
        exclude_self: bool,
        include_sponsored: bool,
        include_transfers: bool = True,
        only_transfers: bool = False,
    ) -> Query:
        ownership_filter: ColumnElement[bool]
        if not include_sponsored:
            ownership_filter = UsageRecordDB.user_id == user_id
        elif exclude_self:
            ownership_filter = and_(UsageRecordDB.payer_id == user_id, UsageRecordDB.user_id != user_id)
        else:
            ownership_filter = UsageRecordDB.payer_id == user_id

        transfer_purpose = ToolType.credit_transfer.value
        counterpart_transfer_filter = and_(
            UsageRecordDB.counterpart_id == user_id,
            UsageRecordDB.purpose == transfer_purpose,
        )
        if only_transfers:
            base_query = self._db.query(UsageRecordDB).filter(
                or_(ownership_filter, counterpart_transfer_filter),
                UsageRecordDB.purpose == transfer_purpose,
            )
        elif include_transfers:
            base_query = self._db.query(UsageRecordDB).filter(
                or_(ownership_filter, counterpart_transfer_filter),
            )
        else:
            base_query = self._db.query(UsageRecordDB).filter(
                ownership_filter,
                UsageRecordDB.purpose != transfer_purpose,
            )

        if start_date is not None:
            base_query = base_query.filter(UsageRecordDB.timestamp >= start_date)

        if end_date is not None:
            base_query = base_query.filter(UsageRecordDB.timestamp <= end_date)

        return base_query

    def delete_older_than(self, cutoff: datetime) -> int:
        deleted = self._db.query(UsageRecordDB).filter(
            UsageRecordDB.timestamp < cutoff,
        ).delete(synchronize_session = False)
        self._db.commit()
        return deleted
