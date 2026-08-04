from dataclasses import asdict

from google.genai.types import GenerateContentConfig, ImageConfig, Part

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, REPLICATE, XAI
from features.images.image_api_utils import UnifiedImageParameters, filter_replicate_params
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError
from util.functions import extract_url_from_replicate_result


# Not tested as it's just a proxy
class SimpleImageGenerator:

    TOOL_TYPE: ToolType = ToolType.images_gen

    error: str | None
    __configured_tool: ConfiguredTool
    __parameters: UnifiedImageParameters
    __input_attachments: list[ChatAttachment]
    __input_image_urls: list[str]
    __input_image_sizes: list[str] | None
    __output_image_sizes: list[str] | None
    __di: DI

    def __init__(
        self,
        configured_tool: ConfiguredTool,
        parameters: UnifiedImageParameters,
        input_attachments: list[ChatAttachment],
        input_image_urls: list[str],
        input_image_sizes: list[str] | None,
        output_image_sizes: list[str] | None,
        di: DI,
    ):
        self.__di = di
        self.__configured_tool = configured_tool
        self.__parameters = parameters
        self.__input_attachments = input_attachments
        self.__input_image_urls = input_image_urls
        self.__input_image_sizes = input_image_sizes
        self.__output_image_sizes = output_image_sizes

    def execute(self) -> str | None:
        log.t(f"Starting simple image generator with {len(self.__input_attachments)} reference image(s)")
        self.error = None

        try:
            if self.__configured_tool.definition.provider == REPLICATE:
                return self.__execute_with_replicate()
            elif self.__configured_tool.definition.provider == GOOGLE_AI:
                return self.__execute_with_google_ai()
            elif self.__configured_tool.definition.provider == XAI:
                return self.__execute_with_x_ai()
            else:
                raise ConfigurationError(f"Unsupported provider: '{self.__configured_tool.definition.provider}'", UNSUPPORTED_PROVIDER)  # noqa: E501
        except Exception as e:
            self.error = f"Failed to generate image: {str(e)}"
            log.e("Failed to generate image", e)
            return None

    def __execute_with_replicate(self) -> str | None:
        dict_params = filter_replicate_params(self.__configured_tool.definition, self.__parameters)
        log.t("Calling Replicate image generator with params", dict_params)

        replicate = self.__di.replicate_client(
            configured_tool = self.__configured_tool,
            timeout_s = config.web_timeout_s * 30,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
        )
        prediction = replicate.predictions.create(
            version = self.__configured_tool.definition.id,
            input = dict_params,
        )

        prediction.wait()
        image_url = extract_url_from_replicate_result(prediction)
        log.t("Image generated successfully with Replicate")

        # store the output image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            remote_url = image_url,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __execute_with_google_ai(self) -> str | None:
        has_reference_images = bool(self.__input_attachments)
        log.t("Calling Google AI image generator API with params", asdict(self.__parameters))

        google_ai = self.__di.google_ai_client(
            configured_tool = self.__configured_tool,
            timeout_s = config.web_timeout_s * 30,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
        )

        # prepare the request data
        image_config = ImageConfig(aspect_ratio = self.__parameters.aspect_ratio, image_size = self.__parameters.size)
        contents = (
            [
                self.__parameters.prompt,
                *[
                    Part.from_uri(file_uri = url, mime_type = attachment.mime_type)
                    for url, attachment in zip(self.__input_image_urls, self.__input_attachments)
                ],
            ]
            if has_reference_images else self.__parameters.prompt
        )
        response = google_ai.models.generate_content(
            model = self.__configured_tool.definition.id,
            contents = contents,
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

        # store the output image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url

    def __execute_with_x_ai(self) -> str | None:
        log.t("Generating image with xAI")
        log.t("Calling xAI image generator with params", self.__parameters)

        x_ai_client = self.__di.x_ai_client(
            configured_tool = self.__configured_tool,
            timeout_s = config.web_timeout_s * 30,
            output_image_sizes = self.__output_image_sizes,
            input_image_sizes = self.__input_image_sizes,
        )

        # prepare the request data (note: request.image vs request.images)
        if not self.__input_image_urls:
            response = x_ai_client.image.sample(
                prompt = self.__parameters.prompt,
                model = self.__configured_tool.definition.id,
                aspect_ratio = self.__parameters.aspect_ratio,
                resolution = self.__parameters.resolution,
                image_format = "base64",
            )
        elif len(self.__input_image_urls) == 1:
            response = x_ai_client.image.sample(
                prompt = self.__parameters.prompt,
                model = self.__configured_tool.definition.id,
                image_url = self.__input_image_urls[0],
                aspect_ratio = self.__parameters.aspect_ratio,
                resolution = self.__parameters.resolution,
                image_format = "base64",
            )
        else:
            response = x_ai_client.image.sample(
                prompt = self.__parameters.prompt,
                model = self.__configured_tool.definition.id,
                image_urls = self.__input_image_urls,
                aspect_ratio = self.__parameters.aspect_ratio,
                resolution = self.__parameters.resolution,
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

        # store the output image as an attachment and return a public URL
        chat = self.__di.require_invoker_chat()
        attachment = self.__di.chat_attachment_service.save(
            attachment = ChatAttachment(chat_id = chat.chat_id, uploader_user_id = self.__di.invoker.id),
            content = image_data,
        )
        return self.__di.chat_attachment_service.create_public_url(attachment).url
