from pathlib import Path

import requests
from pydantic import TypeAdapter
from requests import RequestException, Response

from features.chat.telegram.model.attachment.file import File
from features.chat.telegram.model.chat_member import ChatMember
from features.chat.telegram.telegram_markdown_utils import escape_markdown
from features.videos.video_file_utils import VideoMetadata
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE
from util.errors import ExternalServiceError


class TelegramBotAPI:
    """https://core.telegram.org/bots/api"""
    __bot_api_url: str

    def __init__(self):
        bot_token = config.telegram_bot_token.get_secret_value()
        self.__bot_api_url = f"{config.telegram_api_base_url}/bot{bot_token}"

    def send_text_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
        link_preview_options: dict | None = None,
    ) -> dict:
        log.t(f"Sending message to chat #{chat_id}")
        url = f"{self.__bot_api_url}/sendMessage"
        cleaned_text = escape_markdown(text)
        if link_preview_options is None:
            link_preview_options = {
                "is_disabled": False,
                "prefer_small_media": True,
                "show_above_text": True,
            }
        payload = {
            "chat_id": chat_id,
            "text": cleaned_text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
            "link_preview_options": link_preview_options,
        }
        response = requests.post(url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def send_photo(
        self,
        chat_id: int | str,
        photo_url: str,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> dict:
        log.t(f"Sending photo to chat #{chat_id}")
        url = f"{self.__bot_api_url}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "disable_notification": disable_notification,
        }
        if caption:
            payload["caption"] = escape_markdown(caption)
            payload["parse_mode"] = parse_mode
        response = requests.post(url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def send_document(
        self,
        chat_id: int | str,
        document_url: str | None = None,
        document_path: str | None = None,
        filename: str | None = None,
        parse_mode: str = "markdown",
        thumbnail: str | None = None,
        caption: str | None = None,
        disable_notification: bool = False,
    ) -> dict:
        log.t(f"Sending document to chat #{chat_id}")
        url = f"{self.__bot_api_url}/sendDocument"
        payload = {"chat_id": chat_id, "disable_notification": disable_notification}

        if thumbnail and not document_path:
            payload["thumbnail"] = thumbnail
        if caption:
            payload["caption"] = escape_markdown(caption)
            payload["parse_mode"] = parse_mode
        if document_path:
            payload["disable_content_type_detection"] = True
            with open(document_path, "rb") as document_file:
                response = requests.post(
                    url = url,
                    data = payload,
                    files = {
                        "document": (
                            filename or Path(document_path).name,
                            document_file,
                            "application/octet-stream",
                        ),
                    },
                    timeout = config.web_timeout_s,
                )
        else:
            payload["document"] = document_url
            response = requests.post(url = url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return self.__validate_message_response(response)

    def send_video(
        self,
        chat_id: int | str,
        video_path: str,
        metadata: VideoMetadata,
        caption: str | None = None,
        parse_mode: str = "markdown",
        disable_notification: bool = False,
    ) -> dict:
        log.t(f"Sending video to chat #{chat_id}")
        url = f"{self.__bot_api_url}/sendVideo"
        payload = {
            "chat_id": chat_id,
            "disable_notification": disable_notification,
            "supports_streaming": True,
            "width": metadata.width,
            "height": metadata.height,
            "duration": round(metadata.duration_seconds),
        }
        if caption:
            payload["caption"] = escape_markdown(caption)
            payload["parse_mode"] = parse_mode
        with open(video_path, "rb") as video_file:
            response = requests.post(
                url,
                data = payload,
                files = {"video": (Path(video_path).name, video_file, "video/mp4")},
                timeout = config.web_timeout_s,
            )
        self.__raise_for_status(response)
        return self.__validate_message_response(response)

    def download_file(self, file_id: str) -> bytes | None:
        log.t(f"Getting file info for file_id: {file_id}")
        info_url = f"{self.__bot_api_url}/getFile"
        info_response = requests.get(info_url, params = {"file_id": file_id}, timeout = config.web_timeout_s)
        self.__raise_for_status(info_response)
        file_info = File(**info_response.json()["result"])
        if not file_info.file_path:
            return None

        log.t("Downloading Telegram file bytes")
        bot_token = config.telegram_bot_token.get_secret_value()
        file_url = f"{config.telegram_api_base_url}/file/bot{bot_token}/{file_info.file_path}"
        file_response = requests.get(file_url, timeout = config.web_timeout_s)
        content_length = len(file_response.content or b"")
        file_name = file_info.file_path.rsplit("/", 1)[-1]
        if file_response.status_code != 200 or content_length == 0:
            log.w(f"Could not download Telegram file '{file_name}': status={file_response.status_code}, bytes={content_length}")
        self.__raise_for_status(file_response)
        if content_length == 0:
            log.w(f"Telegram file contents are empty, for file '{file_name}'")
            return None
        log.t(f"Telegram file downloaded successfully ({content_length} bytes)")
        return file_response.content

    def set_status_typing(self, chat_id: int | str) -> dict:
        url = f"{self.__bot_api_url}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "typing",
        }
        response = requests.post(url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def set_status_uploading_image(self, chat_id: int | str) -> dict:
        url = f"{self.__bot_api_url}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "upload_photo",
        }
        response = requests.post(url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def set_reaction(self, chat_id: int | str, message_id: int | str, reaction: str | None) -> dict:
        url = f"{self.__bot_api_url}/setMessageReaction"
        reactions_list = [{"type": "emoji", "emoji": reaction}] if reaction else []
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": reactions_list,
        }
        response = requests.post(url, json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def send_button_link(self, chat_id: int | str, link_url: str, button_text: str = "⚙️") -> dict:
        payload = {
            "chat_id": chat_id,
            "text": "👇",
            "reply_markup": {
                "inline_keyboard": [[
                    {
                        "text": button_text,
                        "url": link_url,
                    },
                ]],
            },
        }
        response = requests.post(f"{self.__bot_api_url}/sendMessage", json = payload, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def get_chat_member(self, chat_id: int | str, user_id: int | str) -> ChatMember:
        url = f"{self.__bot_api_url}/getChatMember"
        response = requests.get(url, params = {"chat_id": chat_id, "user_id": user_id}, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        member_info = response.json()["result"]
        return TypeAdapter(ChatMember).validate_python(member_info)

    def get_chat_administrators(self, chat_id: int | str) -> list[ChatMember]:
        url = f"{self.__bot_api_url}/getChatAdministrators"
        response = requests.get(url, params = {"chat_id": chat_id}, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        admins_info = response.json()["result"]
        return TypeAdapter(list[ChatMember]).validate_python(admins_info)

    def __raise_for_status(self, response: Response | None):
        if response is None:
            raise RequestException(log.e("No API response received"))
        if response.status_code < 200 or response.status_code > 299:
            log.e(f"  Status is not '200': HTTP_{response.status_code}!", response.json())
            response.raise_for_status()

    # noinspection PyMethodMayBeStatic
    def __validate_message_response(self, response: Response) -> dict:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True or not isinstance(payload.get("result"), dict):
            raise ExternalServiceError("Telegram returned an invalid message response", EXTERNAL_EMPTY_RESPONSE)
        return payload
