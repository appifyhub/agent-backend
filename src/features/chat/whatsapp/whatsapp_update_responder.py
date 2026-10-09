import asyncio
from dataclasses import dataclass, field

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.command_processor import is_known_command
from features.chat.message_burst import ScheduledChatMessageBurst
from features.chat.whatsapp.model.status import MessageStatus
from features.chat.whatsapp.model.update import Update
from features.integrations.integrations import resolve_agent_user, resolve_external_handle
from util import log
from util.config import config


@dataclass(frozen = True, kw_only = True)
class _IngressOutcome:
    scheduled_bursts: list[ScheduledChatMessageBurst] = field(default_factory = list)
    processed: bool = False


async def respond_to_update(update: Update) -> bool:
    outcome = await asyncio.to_thread(_ingest_update, update)
    if not outcome.scheduled_bursts:
        return outcome.processed
    results = await asyncio.gather(*(_process_scheduled_burst(scheduled) for scheduled in outcome.scheduled_bursts))
    return outcome.processed or any(results)


async def _process_scheduled_burst(scheduled: ScheduledChatMessageBurst) -> bool:
    di = DI(invoker_id = scheduled.author_id.hex, invoker_chat_id = scheduled.chat_id.hex)
    return await di.message_burst_service.process_after_quiet_period(scheduled = scheduled)


def _ingest_update(update: Update) -> _IngressOutcome:
    if config.log_whatsapp_update:
        log.t(f"Received a WhatsApp update: `{update}`")

    di = DI()
    with di.new_session() as db:
        di.inject_db_session(db)
        try:
            processed = False

            # delivery cost reconciliation needs to be handled specially, and in front
            for entry in update.entry or []:
                for change in entry.changes or []:
                    for status in change.value.statuses or []:
                        processed = _reconcile_message_delivery(di, status) or processed

            # store and map to domain models (throws in case of error)
            resolved_domain_data_all = di.whatsapp_chat_inbound_service.ingest_update(update)
            if not resolved_domain_data_all:
                log.w("No messages to process in this WhatsApp update (likely a status update or notification)")
                return _IngressOutcome(processed = processed)

            scheduled_bursts: list[ScheduledChatMessageBurst] = []
            for resolved_domain_data in resolved_domain_data_all:
                # filter out messages without authors
                if not resolved_domain_data.author or resolved_domain_data.author.id is None:
                    log.d("Not responding to WhatsApp message without author")
                    continue

                di.inject_invoker(resolved_domain_data.author)
                di.inject_invoker_chat(resolved_domain_data.chat)
                agent_handle = resolve_external_handle(
                    resolve_agent_user(resolved_domain_data.chat.chat_type),
                    resolved_domain_data.chat.chat_type,
                )
                if is_known_command(resolved_domain_data.raw_message_text, agent_handle):
                    processed = (
                        di.message_burst_service.process_message(
                            resolved_domain_data,
                            command_only = True,
                        )
                        or processed
                    )
                    continue

                scheduled_bursts.append(di.message_burst_service.record(
                    message = resolved_domain_data.message,
                    is_addressed = (
                        resolved_domain_data.chat.is_private
                        or di.message_burst_service.is_explicitly_addressed(
                            resolved_domain_data.raw_message_text,
                            resolved_domain_data.chat.chat_type,
                        )
                    ),
                ))
            return _IngressOutcome(scheduled_bursts = scheduled_bursts, processed = processed)
        except Exception as e:
            log.e(f"Failed to ingest: {update}", e)
            return _IngressOutcome()


def _reconcile_message_delivery(di: DI, status: MessageStatus) -> bool:
    if status.status != "sent" or status.pricing is None:
        return False

    if status.pricing.type == "regular":
        is_delivery_free = False
    elif status.pricing.type in {"free_customer_service", "free_entry_point"}:
        is_delivery_free = True
    else:
        return False

    chat = di.chat_config_repo.get_by_external_identifiers(status.recipient_id, ChatConfigDB.ChatType.whatsapp)
    recipient_id = status.recipient_participant_id or status.recipient_id
    recipient = di.user_repo.get_by_whatsapp_user_id(recipient_id)
    if chat is None or recipient is None:
        return False

    return di.spending_service.reconcile_message_delivery(chat, recipient, is_delivery_free = is_delivery_free)
