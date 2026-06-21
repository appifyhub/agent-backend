import json

from di.di import DI
from features.announcements.sys_announcements_service import SysAnnouncementsService
from features.external_tools.intelligence_presets import default_tool_for
from util import log
from util.config import config
from util.error_codes import ANNOUNCEMENT_NOT_RECEIVED, CHAT_CONFIG_NOT_FOUND
from util.errors import ExternalServiceError, NotFoundError
from util.translations_cache import TranslationsCache


def respond_with_currency_alerts(di: DI) -> dict:
    chats_notified: int = 0
    announcements_created: int = 0
    service = di.currency_alert_service(target_chat_id = None)
    triggered_alerts = service.get_triggered_alerts()
    translation_caches_all: dict[str, TranslationsCache] = {}
    for triggered_alert in triggered_alerts:
        scoped_di: DI
        # try to summarize the announcement first
        try:
            chat_config = di.chat_config_repo.get(triggered_alert.chat_id)
            if not chat_config:
                raise NotFoundError(f"Chat config not found for chat {triggered_alert.chat_id}", CHAT_CONFIG_NOT_FOUND)
            scoped_di = di.clone(invoker_id = triggered_alert.owner_id.hex, invoker_chat_id = chat_config.chat_id.hex)

            # find the correct translations cache for this alert
            base_currency = triggered_alert.base_currency
            desired_currency = triggered_alert.desired_currency
            alert_threshold = triggered_alert.threshold_percent
            translations_cache_key = f"{base_currency}-{desired_currency}-{alert_threshold}"

            # get or create cache instance for this alert type
            if translations_cache_key not in translation_caches_all:
                translation_caches_all[translations_cache_key] = scoped_di.translations_cache
            translations = translation_caches_all[translations_cache_key]

            language_name = chat_config.language_name or config.main_language_name
            language_iso_code = chat_config.language_iso_code or config.main_language_iso_code
            announcement_text = translations.get(language_name, language_iso_code)
            if announcement_text:
                log.t(
                    f"Announcement already cached for alert type {translations_cache_key} "
                    f"in chat {triggered_alert.chat_id}",
                )
            else:
                log.t(
                    f"No cached announcement available for alert type {translations_cache_key} "
                    f"in chat {triggered_alert.chat_id}",
                )
                raw_information = json.dumps(triggered_alert.model_dump(mode = "json"))
                configured_tool = scoped_di.tool_choice_resolver.require_tool(
                    SysAnnouncementsService.TOOL_TYPE,
                    default_tool_for(SysAnnouncementsService.TOOL_TYPE),
                )
                _, answer = scoped_di.sys_announcements_service(raw_information, chat_config, configured_tool).execute()
                if not answer.content:
                    raise ExternalServiceError("LLM Answer not received", ANNOUNCEMENT_NOT_RECEIVED)
                announcement_text = translations.save(str(answer.content), language_name, language_iso_code)
                announcements_created += 1
        except Exception as e:
            log.e("Price alert announcement failed", e)
            continue

        # now let's send the announcement to each chat
        try:
            scoped_di.platform_bot_sdk().send_text_message(str(chat_config.external_id), announcement_text)
            chats_notified += 1
        except Exception as e:
            log.w(f"Chat notification failed for chat #{triggered_alert.chat_id}", e)

    # we're done, report back
    all_chat_ids = set([alert.chat_id for alert in triggered_alerts])
    log.i(
        f"Alerts: {len(triggered_alerts)}, "
        f"chats: {len(all_chat_ids)}, "
        f"announcements created: {announcements_created}, "
        f"notified: {chats_notified}",
    )
    return {
        "alerts_triggered": len(triggered_alerts),
        "announcements_created": announcements_created,
        "chats_affected": len(all_chat_ids),
        "chats_notified": chats_notified,
    }
