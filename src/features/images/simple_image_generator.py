from dataclasses import asdict

from google.genai.types import GenerateContentConfig, ImageConfig, Part

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, REPLICATE, XAI
from features.images.image_api_utils import filter_replicate_params, map_to_model_parameters
from features.images.image_size_utils import calculate_image_size_category
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError
from util.functions import extract_url_from_replicate_result

BOOT_AND_RUN_TIMEOUT_S = 120


# Not tested as it's just a proxy
class SimpleImageGenerator:

    TOOL_TYPE: ToolType = ToolType.images_gen

    error: str | None
    __prompt: str
    __configured_tool: ConfiguredTool
    __input_attachments: list[ChatAttachment]
    __input_image_urls: list[str]
    __input_image_sizes: list[str | None]
    __aspect_ratio: str | None
    __output_size: str | None
    __di: DI

    def __init__(
        self,
        prompt: str,
        configured_tool: ConfiguredTool,
        di: DI,
        aspect_ratio: str | None = None,
        output_size: str | None = None,
        input_attachments: list[ChatAttachment] | None = None,
    ):
        self.__di = di
        self.__prompt = prompt
        self.__configured_tool = configured_tool
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size
        max_images = self.__configured_tool.definition.max_input_images
        self.__input_attachments = (input_attachments or [])[:max_images]
        self.__input_image_urls = [
            self.__di.chat_attachment_service.create_public_url(attachment).url
            for attachment in self.__input_attachments
        ]
        self.__input_image_sizes = self.__resolve_input_image_sizes()

    def execute(self) -> str | None:
        log.t(f"Starting simple image generator with prompt: '{self.__prompt}'")
        self.error = None
        if self.__input_attachments:
            log.d(f"Starting photo editing with {len(self.__input_attachments)} image(s)")

        try:
            if self.__configured_tool.definition.provider == REPLICATE:
                if self.__input_attachments:
                    return self.__edit_with_replicate(self.__input_image_urls, self.__input_image_sizes)
                return self.__generate_with_replicate()
            elif self.__configured_tool.definition.provider == GOOGLE_AI:
                if self.__input_attachments:
                    return self.__edit_with_google_ai(self.__input_image_urls, self.__input_image_sizes)
                return self.__generate_with_google_ai()
            elif self.__configured_tool.definition.provider == XAI:
                if self.__input_attachments:
                    return self.__edit_with_x_ai(self.__input_image_urls, self.__input_image_sizes)
                return self.__generate_with_x_ai()
            else:
                raise ConfigurationError(f"Unsupported provider: '{self.__configured_tool.definition.provider}'", UNSUPPORTED_PROVIDER)  # noqa: E501
        except Exception as e:
            if self.__input_attachments:
                self.error = f"Error editing image: {str(e)}"
                log.e("Error editing image", e)
            else:
                self.error = f"Failed to generate image: {str(e)}"
                log.e("Failed to generate image", e)
            return None

    def __resolve_input_image_sizes(self) -> list[str | None]:
        input_image_sizes: list[str | None] = []
        for attachment in self.__input_attachments:
            try:
                with self.__di.attachment_storage.open(attachment) as stream:
                    input_image_sizes.append(calculate_image_size_category(file_contents = stream))
            except Exception as e:
                log.e(f"Failed to calculate input image size, will proceed without it: {e}")
                input_image_sizes.append(None)
        return input_image_sizes

    def __generate_with_replicate(self) -> str | None:
        log.t("Generating image with Replicate")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
        )
        dict_params = {
            k: v for k, v in unified_params.__dict__.items() if v is not None
        }
        dict_params = filter_replicate_params(self.__configured_tool.definition, dict_params)
        log.t("Calling Replicate image generator with params", dict_params)

        replicate = self.__di.replicate_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.size] if unified_params.size else None,
            input_image_sizes = None,
        )
        prediction = replicate.predictions.create(
            version = self.__configured_tool.definition.id,
            input = dict_params,
        )

        # we need to release the session before we start waiting
        self.__di.rollback_db_session()

        prediction.wait()
        image_url = extract_url_from_replicate_result(prediction)
        log.t("Image generated successfully with Replicate")

        # store the generated image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            remote_url = image_url,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __generate_with_google_ai(self) -> str | None:
        log.t("Generating image with Google AI")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
        )
        dict_params = asdict(unified_params)
        log.t("Calling Google AI image generator API with params", dict_params)

        google_ai = self.__di.google_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.size] if unified_params.size else None,
            input_image_sizes = None,
        )
        image_config = ImageConfig(aspect_ratio = unified_params.aspect_ratio, image_size = unified_params.size)
        response = google_ai.models.generate_content(
            model = self.__configured_tool.definition.id,
            contents = self.__prompt,
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
        log.t("Image generated successfully with Google AI")

        # store the image data as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __edit_with_replicate(self, input_image_urls: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with Replicate")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
            input_urls = input_image_urls,
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
        self.__di.rollback_db_session()
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

    def __edit_with_google_ai(self, input_image_urls: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with Google AI")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
            input_urls = input_image_urls,
        )
        log.t("Calling Google AI image editing API with params", unified_params)

        valid_sizes = [s for s in input_image_sizes if s is not None] or None
        google_ai = self.__di.google_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.size] if unified_params.size else None,
            input_image_sizes = valid_sizes,
        )
        image_config = ImageConfig(aspect_ratio = unified_params.aspect_ratio, image_size = unified_params.size)
        response = google_ai.models.generate_content(
            model = self.__configured_tool.definition.id,
            contents = [
                self.__prompt,
                *[
                    Part.from_uri(file_uri = url, mime_type = attachment.mime_type)
                    for url, attachment in zip(input_image_urls, self.__input_attachments)
                ],
            ],
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

    def __edit_with_x_ai(self, input_image_urls: list[str], input_image_sizes: list[str | None]) -> str | None:
        log.t("Editing image with xAI")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
            input_urls = input_image_urls,
        )
        log.t("Calling xAI image editing with params", unified_params)

        valid_sizes = [s for s in input_image_sizes if s is not None] or None
        x_ai_client = self.__di.x_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.resolution] if unified_params.resolution else None,
            input_image_sizes = valid_sizes,
        )

        # image_url and image_urls map to different proto fields (request.image vs request.images)
        if len(input_image_urls) == 1:
            response = x_ai_client.image.sample(
                prompt = self.__prompt,
                model = self.__configured_tool.definition.id,
                image_url = input_image_urls[0],
                aspect_ratio = unified_params.aspect_ratio,
                resolution = unified_params.resolution,
                image_format = "base64",
            )
        else:
            response = x_ai_client.image.sample(
                prompt = self.__prompt,
                model = self.__configured_tool.definition.id,
                image_urls = input_image_urls,
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

    def __generate_with_x_ai(self) -> str | None:
        log.t("Generating image with xAI")

        unified_params = map_to_model_parameters(
            tool = self.__configured_tool.definition, prompt = self.__prompt,
            aspect_ratio = self.__aspect_ratio, output_size = self.__output_size,
        )
        log.t("Calling xAI image generator with params", unified_params)

        x_ai_client = self.__di.x_ai_client(
            self.__configured_tool,
            config.web_timeout_s * 10,
            output_image_sizes = [unified_params.resolution] if unified_params.resolution else None,
        )

        response = x_ai_client.image.sample(
            prompt = self.__prompt,
            model = self.__configured_tool.definition.id,
            aspect_ratio = unified_params.aspect_ratio,
            resolution = unified_params.resolution,
            image_format = "base64",
        )

        log.d("xAI image response received")
        if not response:
            raise ExternalServiceError("No response returned from xAI", EXTERNAL_EMPTY_RESPONSE)
        if not response.respect_moderation:
            raise ExternalServiceError("xAI image was filtered by moderation", EXTERNAL_EMPTY_RESPONSE)
        image_data = response.image
        if not image_data:
            raise ExternalServiceError("No image data returned from xAI", EXTERNAL_EMPTY_RESPONSE)
        log.t("Image generated successfully with xAI")

        # store the image data as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url
