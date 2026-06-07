# ruff: noqa: E501

import functools
import inspect
import json
import re
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import tool

from di.di import DI
from features.chat.chat_agent import ChatAgent
from features.chat.chat_attachment_processor import ChatAttachmentProcessor
from features.chat.chat_image_edit_service import ChatImageEditService
from features.chat.dev_announcements_service import DevAnnouncementsService
from features.external_tools.intelligence_presets import default_tool_for
from features.images.smart_image_generator import SmartImageGenerator
from features.integrations.integrations import add_messaging_frequency_warning, resolve_private_chat_id
from features.social_cards.social_card_orchestrator import SocialCardOrchestrator
from features.support.user_support_service import UserSupportService
from features.web_browsing.ai_web_search import AIWebSearch
from util import log
from util.config import config
from util.error_codes import (
    EXTERNAL_EMPTY_RESPONSE,
    IMAGE_EDIT_FAILED,
    IMAGE_GENERATION_FAILED,
    INVALID_ATTACHMENT_OPERATION,
    PROFILE_CONNECT_FAILED,
)
from util.errors import ExternalServiceError, InternalError, ServiceError, ValidationError

TOOL_TRUNCATE_LENGTH = 8192  # to save some tokens

KEYWORD_ATTACHMENT_ANALYZE = "analyze"
KEYWORD_ATTACHMENT_IMAGE_EDIT = "image-edit"
ATTACHMENT_OPERATIONS = [KEYWORD_ATTACHMENT_ANALYZE, KEYWORD_ATTACHMENT_IMAGE_EDIT]


def process_media(
    di: DI,
    operation: str = KEYWORD_ATTACHMENT_ANALYZE,
    attachment_ids: str | None = None,
    urls: str | None = None,
    context: str | None = None,
    aspect_ratio: str | None = None,
    size: str | None = None,
) -> str:
    """
    Processes the contents of the given media sources (chat attachments and/or external URLs). Allowed operations are:
        - 'analyze' (default): Analyzes attachments and returns descriptions — images are analyzed using vision (multiple images can be provided and all will be described), audio is transcribed, documents are searched
        - 'image-edit': Generates a new image using the provided attachments as visual reference or inspiration — use this whenever the partner's images should influence the output (e.g. "use this logo", "generate a variant of this", "apply this style"). Multiple images can be provided for multi-reference generation. To process images individually (one output per image), call this function multiple times with a single image each time.

    Args:
        operation: [mandatory] The action to perform on the attachments
        attachment_ids: [optional] A comma-separated list of verbatim, unique 📎 attachment IDs that need to be processed (located in each message); include any dashes, underscores or other symbols; these IDs are not to be cleaned or truncated
        urls: [optional] A comma-separated list of external media URLs (starting with http:// or https://) to process; at least one of attachment_ids or urls must be provided
        context: [optional] Additional task context or guidance, e.g. the user's message/question/caption, if available
        aspect_ratio: [optional] The desired image's aspect ratio for image editing. Valid options: 1:1, 2:3, 3:2, 3:4, 4:3, 16:9, 9:16, match_input_image. If not explicitly requested, don't send
        size: [optional] The desired image size/resolution for image editing. Valid options: 1K, 2K, 4K. If not explicitly requested, don't send
    """
    try:
        operation = operation.lower().strip()
        attachment_ids_list = [id.strip() for id in attachment_ids.split(",") if id.strip()] if attachment_ids else []
        raw_urls_list = [url.strip() for url in urls.split(",") if url.strip()] if urls else []

        if operation == KEYWORD_ATTACHMENT_ANALYZE:
            # Analyze the attachments and convert contents to text descriptions
            analyzer = di.chat_attachment_processor(context, attachment_ids_list, raw_urls_list or None)
            result = analyzer.execute()
            if result == ChatAttachmentProcessor.Result.failed:
                raise ExternalServiceError("Failed to resolve attachments", EXTERNAL_EMPTY_RESPONSE)
            return json.dumps({"result": result.value, "attachments": analyzer.result})
        elif operation == KEYWORD_ATTACHMENT_IMAGE_EDIT:
            log.d(
                f"LLM requested to process {len(attachment_ids_list)} attachments "
                f"and {len(raw_urls_list)} URLs in aspect ratio {aspect_ratio}, size {size}",
            )
            # Generate images based on the provided context and attachments
            result, details = di.chat_image_edit_service(attachment_ids_list, raw_urls_list, context, aspect_ratio, size).execute()
            if result == ChatImageEditService.Result.failed:
                raise ExternalServiceError("Failed to edit the images! Details: " + str(details), IMAGE_EDIT_FAILED)
            return __success(
                {
                    "status": result.value,
                    "details": details,
                    "description": "Results were already delivered to the partner!",
                    "next_step": "You may deliver any errors to the partner (but no links or 📎 attachment IDs)",
                },
            )
        else:
            raise ValidationError(f"Unknown operation '{operation}'; try one of: [{', '.join(ATTACHMENT_OPERATIONS)}]", INVALID_ATTACHMENT_OPERATION)
    except Exception as e:
        return __error(e)


def generate_image(
    di: DI,
    prompt: str,
    aspect_ratio: str | None = None,
    size: str | None = None,
) -> str:
    """
    Generates (draws) a new image from text only, with no reference images. Use this when creating something entirely new from a description. If the partner has provided image attachments that should influence the output (e.g. "use this logo", "based on this photo"), use process_media with 'image-edit' instead.

    Args:
        prompt: [mandatory] The user's description or prompt for the generated image
        aspect_ratio: [optional] The desired image's aspect ratio. Valid options: 1:1, 2:3, 3:2, 3:4, 4:3, 16:9, 9:16. If not explicitly requested, don't send
        size: [optional] The desired image size/resolution. Valid options: 1K, 2K, 4K. If not explicitly requested, don't send
    """
    try:
        log.d(f"LLM requested to generate an image in aspect ratio {aspect_ratio}")
        copywriter_tool = di.tool_choice_resolver.require_tool(
            SmartImageGenerator.COPYWRITER_TOOL_TYPE,
            default_tool_for(SmartImageGenerator.COPYWRITER_TOOL_TYPE),
        )
        image_gen_tool = di.tool_choice_resolver.require_tool(
            SmartImageGenerator.IMAGE_GEN_TOOL_TYPE,
            default_tool_for(SmartImageGenerator.IMAGE_GEN_TOOL_TYPE),
        )
        generator = di.smart_image_generator(prompt, copywriter_tool, image_gen_tool, aspect_ratio, size)
        result = generator.execute()
        if result == SmartImageGenerator.Result.failed:
            raise ExternalServiceError(f"Failed to generate the image! Reason: {str(generator.error)}", IMAGE_GENERATION_FAILED)
        return __success({"next_step": "Confirm to partner that the image has been sent"})
    except Exception as e:
        return __error(e)


def fetch_web_content(di: DI, url: str, offset: str | None = None) -> str:
    """
    Fetches the text content from the given web page URL, including Twitter / X posts.
    For long pages, use the 'offset' parameter to paginate through the content.

    Args:
        url: [mandatory] A valid URL of the web page, starting with 'http://' or 'https://' provided in the text
        offset: [optional] Character offset to start reading from (for paginating long content); returned in previous responses as 'next_offset'
    """
    try:
        fetcher = di.web_fetcher(url, auto_fetch_html = True)
        html = str(fetcher.html)
        text = di.html_content_cleaner(html).clean_up()
        start = int(offset) if offset else 0
        chunk = text[start:start + TOOL_TRUNCATE_LENGTH]
        has_more = start + TOOL_TRUNCATE_LENGTH < len(text)
        response: dict[str, Any] = {"content": chunk}
        if has_more:
            response["next_offset"] = str(start + TOOL_TRUNCATE_LENGTH)
            response["total_length"] = len(text)
        if re.search(r"!\[.*?]\(https?://", text):
            response["next_step"] = "Media URLs found on this page can be passed to other tools that accept URLs for further processing"
        return __success(response)
    except Exception as e:
        return __error(e)


def get_exchange_rate(di: DI, base_currency: str, desired_currency: str, amount: str | None = None) -> str:
    """
    Fetches the exchange rate between two (crypto or fiat) currencies.

    Args:
        base_currency: [mandatory] The currency code of the base currency, e.g. 'USD' or 'BTC'
        desired_currency: [mandatory] The currency code of the desired currency, e.g. 'EUR' or 'ADA'
        amount: [optional] The amount of the base currency to convert; not sending this will assume value of 1.0
    """
    try:
        result = di.exchange_rate_fetcher.execute(base_currency, desired_currency, float(amount) if amount else 1.0)
        return __success({"exchange_rate": result})
    except Exception as e:
        return __error(e)


def set_up_currency_price_alert(
    di: DI,
    base_currency: str,
    desired_currency: str,
    threshold_percent: int,
) -> str:
    """
    Sets up a price alert at the given threshold for the given currency pair.

    Args:
        base_currency: [mandatory] The currency code of the base currency, e.g. 'USD' or 'BTC'
        desired_currency: [mandatory] The currency code of the desired currency, e.g. 'EUR' or 'ADA'
        threshold_percent: [mandatory] The trigger threshold, in percent [0-100], that triggers the price alert
    """
    try:
        service = di.currency_alert_service(di.invoker_chat_id)
        alert = service.create_alert(base_currency, desired_currency, threshold_percent)
        response_data: dict[str, Any] = {"created_alert_data": alert.model_dump(mode = "json")}
        add_messaging_frequency_warning(response_data, di.invoker_chat_type)
        return __success(response_data)
    except Exception as e:
        return __error(e)


def remove_currency_price_alerts(di: DI, base_currency: str, desired_currency: str) -> str:
    """
    Deletes the oldest price alert for the given currency pair.

    Args:
        base_currency: [mandatory] The currency code of the base currency, e.g. 'USD' or 'BTC'
        desired_currency: [mandatory] The currency code of the desired currency, e.g. 'EUR' or 'ADA'
    """
    try:
        service = di.currency_alert_service(di.invoker_chat_id)
        alert = service.delete_alert(base_currency, desired_currency)
        deleted_alert_data = alert.model_dump(mode = "json") if alert else None
        return __success({"deleted_alert_data": deleted_alert_data})
    except Exception as e:
        return __error(e)


def list_currency_price_alerts(di: DI) -> str:
    """
    Lists all price alerts.

    Args:
        None.
    """
    try:
        service = di.currency_alert_service(di.invoker_chat_id)
        alerts = service.get_active_alerts()
        return __success({"alerts": [alert.model_dump(mode = "json") for alert in alerts]})
    except Exception as e:
        return __error(e)


def ai_web_search(di: DI, search_query: str) -> str:
    """
    Searches the web for the given query, and responds using AI. To be used any time there's missing information or upon user request.

    Args:
        search_query: [mandatory] The user's search query, in English
    """
    try:
        configured_tool = di.tool_choice_resolver.require_tool(AIWebSearch.TOOL_TYPE, default_tool_for(AIWebSearch.TOOL_TYPE))
        search = di.ai_web_search(search_query, configured_tool)
        result = search.execute()
        if not result.content:
            raise ExternalServiceError("Answer not received", EXTERNAL_EMPTY_RESPONSE)
        return __success({"content": result.content})
    except Exception as e:
        return __error(e)


def announce_maintenance_or_news(di: DI, raw_announcement: str) -> str:
    """
    [Developers-only] Announces a maintenance or news message from developers to all chats.

    Args:
        raw_announcement: [mandatory] The raw announcement message to send to all chats
    """
    try:
        configured_tool = di.tool_choice_resolver.require_tool(
            DevAnnouncementsService.TOOL_TYPE,
            default_tool_for(DevAnnouncementsService.TOOL_TYPE),
        )
        results = di.dev_announcements_service(raw_announcement, None, configured_tool).execute()
        return __success(
            {
                "summary": results,
                "next_step": "Report these summary numbers back to the developer-user",
            },
        )
    except Exception as e:
        return __error(e)


def deliver_message(di: DI, message: str, target_handle: str) -> str:
    """
    [Developers-only] Delivers a personalized message from developers to a specific user.

    Args:
        message: [mandatory] The message to deliver to the target user
        target_handle: [mandatory] The full social handle (e.g. username, phone, email) of the target user to send the message to, without '@' or '+'
    """
    try:
        configured_tool = di.tool_choice_resolver.require_tool(
            DevAnnouncementsService.TOOL_TYPE,
            default_tool_for(DevAnnouncementsService.TOOL_TYPE),
        )
        results = di.dev_announcements_service(message, target_handle, configured_tool).execute()
        return __success(
            {
                "summary": results,
                "next_step": "Report these summary numbers back to the developer-user",
            },
        )
    except Exception as e:
        return __error(e)


def request_feature_bug_or_support(
    di: DI,
    user_request_details: str,
    request_type: str | None = None,
    include_full_name: bool = False,
    include_platform_handle: bool = False,
    author_github_username: str | None = None,
) -> str:
    """
    Allows the user to request a feature, report a bug, or ask for support. As a result, a GitHub issue is created.
    Conversing with the user helps gather more details (based on this function's arguments).
    This function must be explicitly called once the user is ready to submit the request.

    Args:
        user_request_details: [mandatory] The raw text of the user's request, bug report, or support question
        include_full_name: [mandatory] Whether to include the user's full name in the GitHub issue
        include_platform_handle: [mandatory] Whether to include the current platform's handle in the GitHub issue (username, phone, email)
        request_type: [optional] The type of the request: [ 'feature', 'bug', 'request' ]
        author_github_username: [optional] The GitHub username of the author, if available and shared
    """
    try:
        configured_tool = di.tool_choice_resolver.require_tool(
            UserSupportService.TOOL_TYPE,
            default_tool_for(UserSupportService.TOOL_TYPE),
        )
        service = di.user_support_service(
            user_request_details, author_github_username,
            include_platform_handle, include_full_name,
            request_type, configured_tool,
        )
        issue_url = service.execute()
        return __success(
            {
                "github_issue_url": issue_url,
                "next_step": "Report this link back to the partner",
            },
        )
    except Exception as e:
        return __error(e)


def configure_settings(
    di: DI,
    raw_settings_type: str,
) -> str:
    """
    Launches the configuration screen with various profile and payment settings, credits, API tokens/keys, chat's settings,
    language, response rate, release notifications, model options, etc. Intelligence settings should be the default page.
    The user will probably not know which settings page they need, so they must either be chosen for, or asked.

    Args:
        raw_settings_type: [mandatory] The type of settings the user wants: [ 'intelligence', 'user', 'chat' ]
    """
    try:
        settings_link = di.settings_controller.create_settings_link(raw_settings_type).settings_link
        platform_private_chat_id = resolve_private_chat_id(di.invoker, di.require_invoker_chat_type())
        if not platform_private_chat_id:
            return __error("Author has no private chat with the agent; cannot send settings link")
        di.platform_bot_sdk().send_button_link(platform_private_chat_id, settings_link)
        if di.require_invoker_chat().is_private:
            return __success({"next_step": "Notify the user to click on the settings link above"})
        else:
            return __success({"next_step": "Notify the user that the link was sent to their private chat"})
    except Exception as e:
        return __error(e)


def read_help_and_features(
    di: DI,
) -> str:
    """
    Launches the help screen. This allows the user to understand more about the service, how to use it,
    look for help or FAQ, as well as check the details of the many features available in the service.
    This does not allow the user to request support or report issues - use another tool for that.

    Args:
        None.
    """
    try:
        help_link = di.settings_controller.create_help_link()
        platform_private_chat_id = resolve_private_chat_id(di.invoker, di.require_invoker_chat_type())
        if not platform_private_chat_id:
            return __error("Author has no private chat with the agent; cannot send settings link")
        di.platform_bot_sdk().send_button_link(platform_private_chat_id, help_link)
        return __success({"next_step": "Notify the user that the link was sent to their private chat"})
    except Exception as e:
        return __error(e)


def get_version(di: DI) -> str:
    """
    Checks the current version of the agent (the latest version available to the users).
    """
    try:
        log.t(f"Getting version for chat '{di.invoker_chat_id}'")
        configured_tool = di.tool_choice_resolver.require_tool(ChatAgent.TOOL_TYPE, default_tool_for(ChatAgent.TOOL_TYPE))
        return __success(
            {
                "service_version": f"v{config.version}",
                "chat_agent_version": f"{configured_tool.definition.name} from {configured_tool.definition.provider.name}",
                "next_step": "Notify the user of the current (latest) version",
            },
        )
    except Exception as e:
        return __error(e)


def connect_profiles(di: DI, connect_key: str) -> str:
    """
    Connects the current user profile with another profile using a connect key. This allows users to
    (for example) merge their Telegram and WhatsApp accounts into a single unified profile, or merge
    any other two profiles together — provided they have the other profile's connect key. The connect
    key is usually a 12-character code in the format XXXX-XXXX-XXXX that can be obtained from the
    settings page of any profile. The user must provide this key to connect their profiles together.

    Args:
        connect_key: [mandatory] The connect key from the other profile that you want to connect with
    """
    try:
        result, message = di.profile_connect_service.connect_profiles(di.invoker, connect_key)
        if result == di.profile_connect_service.Result.failure:
            raise InternalError(message, PROFILE_CONNECT_FAILED)
        return __success({"status": "success", "message": message})
    except Exception as e:
        return __error(e)


def check_usage_and_balance(di: DI) -> str:
    """
    Checks the user's usage model, credit balance, and the last 5 usage records.

    Args:
        None.
    """
    try:
        if di.invoker.has_any_api_key() and di.invoker.credit_balance > 0:
            usage_model = "API keys and credits"
        elif di.invoker.has_any_api_key():
            usage_model = "API keys only"
        else:
            usage_model = "Credits only"
        records = di.usage_record_repo.get_by_user(di.invoker.id, limit = 5)
        recent_usage = [
            {
                "tool": record.tool.name,
                "purpose": record.tool_purpose.value,
                "cost_credits": record.total_cost_credits,
                "timestamp": record.timestamp.isoformat(),
            }
            for record in records
        ]
        return __success({
            "usage_model": usage_model,
            "credit_balance": di.invoker.credit_balance,
            "recent_usage": recent_usage,
            "next_step": "Offer to the user to open settings and inspect usage in detail",
        })
    except Exception as e:
        return __error(e)


def transfer_credits_to_user(
    di: DI,
    recipient_handle: str,
    amount: str,
    note: str | None = None,
) -> str:
    """
    Transfers credits from the current user to another user on the same platform.

    Args:
        recipient_handle: [mandatory] The recipient's platform handle (username or phone number), without '@' or '+'
        amount: [mandatory] The amount of credits to transfer (minimum 1.0)
        note: [optional] An optional note or reason for the transfer
    """
    try:
        chat_type = di.require_invoker_chat_type()
        di.credit_transfer_service.transfer_credits(
            sender_id = di.invoker.id,
            recipient_handle = recipient_handle,
            chat_type = chat_type,
            amount = float(amount),
            note = note,
        )
        return __success({
            "next_step": "Offer to the user to open settings and inspect usage in detail",
        })
    except Exception as e:
        return __error(e)


def render_social_post(di: DI, url: str) -> str:
    """
    Used for extracting and persisting the agent's screenshot/render of a social post.
    Renders a social network post into a styled, shareable card image.
    Supports only X/Twitter links for now.

    Args:
        url: [mandatory] The URL of the social media post to render, starting with 'http://' or 'https://'
    """
    try:
        x_api_tool = di.tool_choice_resolver.require_tool(SocialCardOrchestrator.TOOL_TYPE, default_tool_for(SocialCardOrchestrator.TOOL_TYPE))
        vision_tool = di.tool_choice_resolver.require_tool(SocialCardOrchestrator.VISION_TOOL_TYPE, default_tool_for(SocialCardOrchestrator.VISION_TOOL_TYPE))
        image_url = di.social_card_orchestrator(x_api_tool, vision_tool).execute(url)
        invoker_chat = di.require_invoker_chat()
        di.platform_bot_sdk().smart_send_photo(
            media_mode = invoker_chat.media_mode,
            chat_id = int(invoker_chat.external_id or "-1"),
            photo_url = image_url,
            thumbnail = image_url,
        )
        return __success({"next_step": "Confirm to the user that the card has been rendered and sent"})
    except Exception as e:
        return __error(e)


# === Helper functions ===


def __success(content: dict[str, Any] | str) -> str:
    if isinstance(content, str):
        log.t(f"Tool call succeeded: {content}")
        return json.dumps({"result": "Success", "information": content})
    else:
        log.t(f"Tool call succeeded: {str(content)}")
        return json.dumps({"result": "Success", **content})


def __error(message: str | Exception) -> str:
    if isinstance(message, ServiceError):
        log.e(message.to_log_string())
        return json.dumps(message.to_llm_dict())
    if isinstance(message, str):
        log.e(f"Tool call failed: {message}")
        return json.dumps({"result": "Error", "information": f"Tool call failed: {message}"})
    log.e("Tool call failed", message)
    return json.dumps({"result": "Error", "information": f"Tool call failed: {message}"})


# === Tool Bindings ===


ALL_LLM_TOOLS: dict[str, Callable[..., str]] = {
    "fetch_web_content": fetch_web_content,
    "process_media": process_media,
    "get_exchange_rate": get_exchange_rate,
    "set_up_currency_price_alert": set_up_currency_price_alert,
    "remove_currency_price_alerts": remove_currency_price_alerts,
    "list_currency_price_alerts": list_currency_price_alerts,
    "generate_image": generate_image,
    "ai_web_search": ai_web_search,
    "announce_maintenance_or_news": announce_maintenance_or_news,
    "deliver_message": deliver_message,
    "request_feature_bug_or_support": request_feature_bug_or_support,
    "configure_settings": configure_settings,
    "read_help_and_features": read_help_and_features,
    "get_version": get_version,
    "connect_profiles": connect_profiles,
    "check_usage_and_balance": check_usage_and_balance,
    "transfer_credits_to_user": transfer_credits_to_user,
    "render_social_post": render_social_post,
}


class LLMToolLibrary:

    _di: DI
    _impls: dict[str, Callable[..., str]]
    _wrapped_tools: dict[str, Any]

    def __init__(self, di: DI):
        self._di = di
        self._impls = {}
        self._wrapped_tools = {}
        for name, func in ALL_LLM_TOOLS.items():
            wrapped = self._wrap_with_di(func)
            self._impls[name] = wrapped
            self._wrapped_tools[name] = tool(wrapped)

    def _wrap_with_di(self, func: Callable[..., str]) -> Callable[..., str]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(self._di, *args, **kwargs)

        # Clean the signature so DI is hidden from the LLM
        orig_sig = inspect.signature(func)
        params = list(orig_sig.parameters.values())[1:]
        cleaned_sig = orig_sig.replace(parameters = params)
        try:
            wrapper.__signature__ = cleaned_sig  # type: ignore[attr-defined]
        except Exception:
            pass
        return wrapper

    def bind_tools(self, llm_base: BaseChatModel) -> Runnable[LanguageModelInput, BaseMessage]:
        return llm_base.bind_tools(list(self._wrapped_tools.values()))

    def invoke(self, tool_name: str, args: object) -> str | None:
        impl = self._impls.get(tool_name)
        if impl is None:
            log.w(f"Tool {tool_name} not found for invocation")
            return None
        if isinstance(args, dict):
            return impl(**args)
        return impl(args)

    @property
    def tool_names(self) -> list[str]:
        return list(self._wrapped_tools.keys())
