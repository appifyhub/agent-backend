from dataclasses import asdict
from uuid import UUID

from db.sql import get_detached_session
from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.videos.video_api_utils import UnifiedVideoParameters, filter_replicate_params
from util.config import config
from util.error_codes import VIDEO_GENERATION_FAILED
from util.errors import ExternalServiceError, ServiceError
from util.functions import extract_url_from_replicate_result


def run_replicate_video(
    configured_tool: ConfiguredTool,
    parameters: UnifiedVideoParameters,
    invoker_id: UUID,
    invoker_chat_id: UUID,
) -> str:
    with get_detached_session() as db:
        di = DI(db, invoker_id.hex, invoker_chat_id.hex)
        try:
            replicate = di.replicate_client(
                configured_tool,
                config.web_timeout_s * 10,
                output_video_size = parameters.size,
                output_video_duration_seconds = parameters.duration,
            )
            prediction = replicate.predictions.create(
                version = configured_tool.definition.id,
                input = filter_replicate_params(
                    configured_tool.definition,
                    {key: value for key, value in asdict(parameters).items() if value is not None},
                ),
            )
        except ServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Could not create Replicate video prediction", VIDEO_GENERATION_FAILED) from e

        di.rollback_db_session()
        try:
            prediction.wait()
            return extract_url_from_replicate_result(prediction)
        except ServiceError:
            raise
        except Exception as e:
            raise ExternalServiceError("Replicate video generation failed", VIDEO_GENERATION_FAILED) from e
