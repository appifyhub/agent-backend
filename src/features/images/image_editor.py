import base64
import contextlib
import os
import tempfile

import requests
from google.genai.types import GenerateContentConfig, ImageConfig
from PIL import Image

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.chat.supported_files import resolve_file_type
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, REPLICATE, XAI
from features.images.image_api_utils import filter_replicate_params, map_to_model_parameters
from features.images.image_size_utils import calculate_image_size_category
from features.web_browsing.web_fetcher import DEFAULT_HEADERS
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, TOO_MANY_INPUT_IMAGES, UNEXPECTED_ERROR, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError, InternalError, ValidationError
from util.functions import extract_url_from_replicate_result

BOOT_AND_RUN_TIMEOUT_S = 120


# Not tested as it's just a proxy
class ImageEditor:

    TOOL_TYPE: ToolType = ToolType.images_edit

    error: str | None
    __prompt: str
    __configured_tool: ConfiguredTool
    __image_urls: list[str]
    __input_mime_types: list[str | None]
    __aspect_ratio: str | None
    __output_size: str | None
    __di: DI

    def __init__(
        self,
        image_urls: list[str],
        configured_tool: ConfiguredTool,
        prompt: str,
        di: DI,
        input_mime_types: list[str | None],
        aspect_ratio: str | None = None,
        output_size: str | None = None,
    ):
        self.__prompt = prompt
        self.__image_urls = image_urls
        self.__configured_tool = configured_tool
        self.__input_mime_types = input_mime_types
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size
        self.__di = di
        self.__validate_inputs()

    def __validate_inputs(self) -> None:
        if len(self.__input_mime_types) != len(self.__image_urls):
            raise InternalError(
                f"image_urls and input_mime_types length mismatch: {len(self.__image_urls)} vs {len(self.__input_mime_types)}",
                UNEXPECTED_ERROR,
            )
        max_images = self.__configured_tool.definition.max_input_images
        if len(self.__image_urls) > max_images:
            raise ValidationError(
                f"Too many input images: {len(self.__image_urls)} provided, max is {max_images} for this model",
                TOO_MANY_INPUT_IMAGES,
            )

    def execute(self) -> str | None:
        log.d(f"Starting photo editing with {len(self.__image_urls)} image(s)")
        self.error = None
        temp_paths: list[str] = []
        try:
            # not using the URL directly because it contains the bot token in its path
            for url, mime_type in zip(self.__image_urls, self.__input_mime_types):
                _, extension = resolve_file_type(mime_type = mime_type, uri = url)
                suffix = f".{extension}" if extension else ""
                temp_file = tempfile.NamedTemporaryFile(delete = False, suffix = suffix)
                response = requests.get(url, headers = DEFAULT_HEADERS)
                temp_file.write(response.content)
                temp_file.flush()
                temp_file.close()
                temp_paths.append(temp_file.name)

            # Calculate input image sizes
            input_image_sizes: list[str | None] = []
            for path in temp_paths:
                try:
                    input_image_sizes.append(calculate_image_size_category(path))
                except Exception as e:
                    log.e(f"Failed to calculate input image size, will proceed without it: {e}")
                    input_image_sizes.append(None)

            if self.__configured_tool.definition.provider == REPLICATE:
                return self.__edit_with_replicate(temp_paths, input_image_sizes)
            elif self.__configured_tool.definition.provider == GOOGLE_AI:
                return self.__edit_with_google_ai(temp_paths, input_image_sizes)
            elif self.__configured_tool.definition.provider == XAI:
                return self.__edit_with_x_ai(temp_paths, input_image_sizes)
            else:
                raise ConfigurationError(f"Unsupported provider: '{self.__configured_tool.definition.provider}'", UNSUPPORTED_PROVIDER)  # noqa: E501
        except Exception as e:
            self.error = f"Error editing image: {str(e)}"
            log.e("Error editing image", e)
            return None
        finally:
            for path in temp_paths:
                try:
                    os.unlink(path)
                except Exception:
                    pass

    def __edit_with_replicate(self, temp_file_paths: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with Replicate")

        with contextlib.ExitStack() as stack:
            files = [stack.enter_context(open(path, "rb")) for path in temp_file_paths]
            unified_params = map_to_model_parameters(
                tool = self.__configured_tool.definition, prompt = self.__prompt,
                aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
                input_files = files,
            )
            dict_params = {
                k: v for k, v in unified_params.__dict__.items() if v is not None
            }
            dict_params = filter_replicate_params(self.__configured_tool.definition, dict_params)
            log.t("Calling Replicate image editing with params", dict_params)

            valid_sizes = [s for s in input_image_sizes if s is not None] or None
            replicate = self.__di.replicate_client(
                configured_tool = self.__configured_tool,
                timeout_s = BOOT_AND_RUN_TIMEOUT_S,
                output_image_sizes = [unified_params.size] if unified_params.size else None,
                input_image_sizes = valid_sizes,
            )
            prediction = replicate.predictions.create(version = self.__configured_tool.definition.id, input = dict_params)
            prediction.wait()

        result = extract_url_from_replicate_result(prediction)
        log.d("Image edit successful")

        # store the edited image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            remote_url = result,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __edit_with_google_ai(self, temp_file_paths: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with Google AI")

        with open(temp_file_paths[0], "rb") as file:
            unified_params = map_to_model_parameters(
                tool = self.__configured_tool.definition, prompt = self.__prompt,
                aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
                input_files = [file],
            )
        log.t("Calling Google AI image editing API with params", unified_params)

        valid_sizes = [s for s in input_image_sizes if s is not None] or None
        google_ai = self.__di.google_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.size] if unified_params.size else None,
            input_image_sizes = valid_sizes,
        )
        pil_images = [Image.open(path) for path in temp_file_paths]
        image_config = ImageConfig(aspect_ratio = unified_params.aspect_ratio, image_size = unified_params.size)
        response = google_ai.models.generate_content(
            model = self.__configured_tool.definition.id,
            contents = [self.__prompt] + pil_images,
            config = GenerateContentConfig(
                response_modalities = ["TEXT", "IMAGE"],
                image_config = image_config,
            ),
        )

        # analyze the response
        if not response or not response.candidates:
            raise ExternalServiceError("No candidates in the response from Google AI", EXTERNAL_EMPTY_RESPONSE)
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            raise ExternalServiceError("No contents in the top candidate from Google AI", EXTERNAL_EMPTY_RESPONSE)

        # locate the image data in the response
        image_data: bytes | None = None
        for part in candidate.content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                break
        if image_data is None:
            raise ExternalServiceError("No image data found in Google AI response", EXTERNAL_EMPTY_RESPONSE)
        log.t("Image edited successfully with Google AI")

        # store the image data as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __edit_with_x_ai(self, temp_file_paths: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with xAI")

        with open(temp_file_paths[0], "rb") as file:
            unified_params = map_to_model_parameters(
                tool = self.__configured_tool.definition, prompt = self.__prompt,
                aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
                input_files = [file],
            )
        log.t("Calling xAI image editing with params", unified_params)

        encoded_images: list[str] = []
        for path, mime_type in zip(temp_file_paths, self.__input_mime_types):
            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            encoded_images.append(f"data:{mime_type or 'image/png'};base64,{image_data}")

        valid_sizes = [s for s in input_image_sizes if s is not None] or None
        x_ai_client = self.__di.x_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.resolution] if unified_params.resolution else None,
            input_image_sizes = valid_sizes,
        )

        # image_url and image_urls map to different proto fields (request.image vs request.images)
        if len(encoded_images) == 1:
            response = x_ai_client.image.sample(
                prompt = self.__prompt,
                model = self.__configured_tool.definition.id,
                image_url = encoded_images[0],
                aspect_ratio = unified_params.aspect_ratio,
                resolution = unified_params.resolution,
                image_format = "base64",
            )
        else:
            response = x_ai_client.image.sample(
                prompt = self.__prompt,
                model = self.__configured_tool.definition.id,
                image_urls = encoded_images,
                aspect_ratio = unified_params.aspect_ratio,
                resolution = unified_params.resolution,
                image_format = "base64",
            )

        log.d("xAI image edit response received")
        if not response:
            raise ExternalServiceError("No response returned from xAI", EXTERNAL_EMPTY_RESPONSE)
        if not response.respect_moderation:
            raise ExternalServiceError("xAI image was filtered by moderation", EXTERNAL_EMPTY_RESPONSE)
        image_data = response.image
        if not image_data:
            raise ExternalServiceError("No image data returned from xAI", EXTERNAL_EMPTY_RESPONSE)
        log.t("Image edited successfully with xAI")

        # store the edited image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url
