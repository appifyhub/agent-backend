from dataclasses import asdict

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.videos.video_api_utils import UnifiedVideoParameters, filter_replicate_params
from util import log
from util.config import config
from util.error_codes import VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ServiceError
from util.functions import extract_url_from_replicate_result


# Not tested as it's just a proxy
class SimpleVideoGenerator:

    TOOL_TYPE: ToolType = ToolType.videos_gen

    __configured_tool: ConfiguredTool
    __parameters: UnifiedVideoParameters
    __di: DI

    def __init__(
        self,
        configured_tool: ConfiguredTool,
        parameters: UnifiedVideoParameters,
        di: DI,
    ):
        self.__configured_tool = configured_tool
        self.__parameters = parameters
        self.__di = di

    def execute(self) -> str:
        log.t("Generating video with Replicate")
        try:
            replicate = self.__di.replicate_client(
                self.__configured_tool,
                config.web_timeout_s * 10,
                output_video_size = self.__parameters.size,
                output_video_duration_seconds = self.__parameters.duration,
            )
            prediction = replicate.predictions.create(
                version = self.__configured_tool.definition.id,
                input = filter_replicate_params(
                    self.__configured_tool.definition,
                    {key: value for key, value in asdict(self.__parameters).items() if value is not None},
                ),
            )
        except ServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Could not create Replicate video prediction", VIDEO_GENERATION_FAILED) from e

        self.__di.rollback_db_session()
        try:
            prediction.wait()
            video_url = extract_url_from_replicate_result(prediction)
            log.t("Video generated successfully with Replicate")
            return video_url
        except ServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Replicate video generation failed", VIDEO_GENERATION_FAILED) from e
