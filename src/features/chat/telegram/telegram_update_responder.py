import asyncio
from dataclasses import dataclass

from db.sql import get_detached_session
from di.di import DI
from features.chat.command_processor import is_known_command
from features.chat.message_burst import ScheduledChatMessageBurst
from features.chat.telegram.model.update import Update
from features.integrations.integrations import resolve_agent_user, resolve_external_handle
from util import log
from util.config import config


@dataclass(frozen = True, kw_only = True)
class _IngressOutcome:
    scheduled_burst: ScheduledChatMessageBurst | None = None
    processed: bool = False


async def respond_to_update(update: Update) -> bool:
    outcome = await asyncio.to_thread(_ingest_update, update)
    if outcome.scheduled_burst is None:
        return outcome.processed
    return await _process_scheduled_burst(outcome.scheduled_burst)


async def _process_scheduled_burst(
    scheduled: ScheduledChatMessageBurst,
) -> bool:
    di = DI(
        invoker_id = scheduled.author_id.hex,
        invoker_chat_id = scheduled.chat_id.hex,
    )
    return await di.message_burst_service.process_after_quiet_period(
        scheduled = scheduled,
    )


def _ingest_update(update: Update) -> _IngressOutcome:
    if config.log_telegram_update:
        log.t(f"Received a Telegram update: `{update}`")

    with get_detached_session() as db:
        di = DI(db)
        try:
            # store and map to domain models (throws in case of error)
            resolved_domain_data = di.telegram_chat_inbound_service.ingest_update(update)
            if not resolved_domain_data:
                log.d("No Telegram response needed (update ignored)")
                return _IngressOutcome()
            # filter out messages without authors
            if not resolved_domain_data.author or resolved_domain_data.author.id is None:
                log.d("Not responding to messages without author")
                return _IngressOutcome()

            di.inject_invoker(resolved_domain_data.author)
            di.inject_invoker_chat(resolved_domain_data.chat)
            agent_handle = resolve_external_handle(
                resolve_agent_user(resolved_domain_data.chat.chat_type),
                resolved_domain_data.chat.chat_type,
            )
            if is_known_command(resolved_domain_data.raw_message_text, agent_handle):
                return _IngressOutcome(
                    processed = di.message_burst_service.process_message(
                        resolved_domain_data,
                        command_only = True,
                    ),
                )

            scheduled_burst = di.message_burst_service.record(
                message = resolved_domain_data.message,
                is_addressed = (
                    resolved_domain_data.chat.is_private
                    or di.message_burst_service.is_explicitly_addressed(
                        resolved_domain_data.raw_message_text,
                        resolved_domain_data.chat.chat_type,
                    )
                ),
            )
            return _IngressOutcome(scheduled_burst = scheduled_burst)
        except Exception as e:
            log.e(f"Failed to ingest: {update}", e)
            return _IngressOutcome()
