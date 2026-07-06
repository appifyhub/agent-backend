import requests
from requests import RequestException, Response

from features.chat.whatsapp.model.media_info import MediaInfo
from features.chat.whatsapp.model.response import MarkAsReadResponse, MessageResponse
from util import log
from util.config import config

API_VERSION = "v23.0"


class WhatsAppBotAPI:
    """https://developers.facebook.com/docs/whatsapp/cloud-api"""
    __bot_api_url: str

    def __init__(self):
        self.__bot_api_url = f"https://graph.facebook.com/{API_VERSION}/{config.whatsapp_phone_number_id}/messages"

    def send_text_message(
        self,
        recipient_id: str,
        text: str,
    ) -> MessageResponse:
        log.t(f"Sending message to recipient #{recipient_id}")
        payload = self.__create_payload(
            recipient_id = recipient_id,
            message_type = "text",
            content = {"text": {"body": text}},
        )
        response = self.__post_request(payload)
        return MessageResponse(**response)

    def send_image(
        self,
        recipient_id: str,
        image_url: str,
        caption: str | None = None,
    ) -> MessageResponse:
        log.t(f"Sending image to recipient #{recipient_id}")
        image_payload = {"link": image_url}
        if caption:
            image_payload["caption"] = caption
        payload = self.__create_payload(
            recipient_id = recipient_id,
            message_type = "image",
            content = {"image": image_payload},
        )
        response = self.__post_request(payload)
        return MessageResponse(**response)

    def send_document(
        self,
        recipient_id: str,
        document_url: str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> MessageResponse:
        log.t(f"Sending document to recipient #{recipient_id}")
        document_payload = {"link": document_url}
        if caption:
            document_payload["caption"] = caption
        if filename:
            document_payload["filename"] = filename
        payload = self.__create_payload(
            recipient_id = recipient_id,
            message_type = "document",
            content = {"document": document_payload},
        )
        response = self.__post_request(payload)
        return MessageResponse(**response)

    def send_reaction(
        self,
        recipient_id: str,
        message_id: str,
        emoji: str,
    ) -> MessageResponse:
        log.t(f"Sending reaction to message #{message_id}")
        payload = self.__create_payload(
            recipient_id = recipient_id,
            message_type = "reaction",
            content = {"reaction": {"message_id": message_id, "emoji": emoji}},
        )
        response = self.__post_request(payload)
        return MessageResponse(**response)

    def mark_as_read(
        self,
        message_id: str,
    ) -> MarkAsReadResponse:
        log.t(f"Marking message #{message_id} as read")
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        response = self.__post_request(payload)
        return MarkAsReadResponse(**response)

    def get_media_info(
        self,
        media_id: str,
    ) -> MediaInfo | None:
        log.t(f"Getting media info for #{media_id}")
        media_url = f"https://graph.facebook.com/{API_VERSION}/{media_id}"
        headers = {"Authorization": f"Bearer {config.whatsapp_bot_token.get_secret_value()}"}
        response = requests.get(media_url, headers = headers, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        media_data = response.json()
        if "url" not in media_data:
            log.e(f"No URL found in media response: {media_data}")
            return None
        return MediaInfo.model_validate(media_data)

    def download_media_bytes(
        self,
        media_url: str,
    ) -> bytes | None:
        log.t("Downloading media bytes from URL")
        headers = {"Authorization": f"Bearer {config.whatsapp_bot_token.get_secret_value()}"}
        file_response = requests.get(media_url, headers = headers, timeout = config.web_timeout_s)
        content_length = len(file_response.content or b"")
        if file_response.status_code != 200 or content_length == 0:
            log.w(f"Could not download WhatsApp media: status={file_response.status_code}, bytes={content_length}")
        self.__raise_for_status(file_response)
        if content_length == 0:
            return None
        log.t(f"Media downloaded successfully ({content_length} bytes)")
        return file_response.content

    def __create_payload(
        self,
        recipient_id: str | None = None,
        message_type: str | None = None,
        content: dict | None = None,
    ) -> dict:
        payload = {"messaging_product": "whatsapp"}
        if recipient_id:
            payload.update({
                "recipient_type": "individual",
                "to": recipient_id,
            })
        if message_type:
            payload["type"] = message_type
        if content:
            payload.update(content)
        return payload

    def __post_request(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {config.whatsapp_bot_token.get_secret_value()}",
            "Content-Type": "application/json",
        }
        response = requests.post(self.__bot_api_url, json = payload, headers = headers, timeout = config.web_timeout_s)
        self.__raise_for_status(response)
        return response.json()

    def __raise_for_status(self, response: Response | None):
        if response is None:
            raise RequestException(log.e("No API response received"))
        if response.status_code < 200 or response.status_code > 299:
            log.e(f"  Status is not '200': HTTP_{response.status_code}!", response.json())
            response.raise_for_status()
