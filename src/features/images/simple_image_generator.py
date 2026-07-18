from dataclasses import asdict

from google.genai.types import GenerateContentConfig, ImageConfig

from di.di import DI
from features.chat.attachment.chat_attachment import ChatAttachment
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.external_tool_provider_library import GOOGLE_AI, REPLICATE, XAI
from features.images.image_api_utils import filter_replicate_params, map_to_model_parameters
from util import log
from util.config import config
from util.error_codes import EXTERNAL_EMPTY_RESPONSE, UNSUPPORTED_PROVIDER
from util.errors import ConfigurationError, ExternalServiceError
from util.functions import extract_url_from_replicate_result


# Not tested as it's just a proxy
class SimpleImageGenerator:

    TOOL_TYPE: ToolType = ToolType.images_gen

    error: str | None
    __prompt: str
    __configured_tool: ConfiguredTool
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
    ):
        self.__di = di
        self.__prompt = prompt
        self.__configured_tool = configured_tool
        self.__aspect_ratio = aspect_ratio
        self.__output_size = output_size

    def execute(self) -> str | None:
        log.t(f"Starting simple image generator with prompt: '{self.__prompt}'")
        self.error = None
        try:
            if self.__configured_tool.definition.provider == REPLICATE:
                return self.__generate_with_replicate()
            elif self.__configured_tool.definition.provider == GOOGLE_AI:
                return self.__generate_with_google_ai()
            elif self.__configured_tool.definition.provider == XAI:
                return self.__generate_with_x_ai()
            else:
                raise ConfigurationError(f"Unsupported provider: '{self.__configured_tool.definition.provider}'", UNSUPPORTED_PROVIDER)  # noqa: E501
        except Exception as e:
            self.error = f"Failed to generate image: {str(e)}"
            log.e("Failed to generate image", e)
            return None

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
