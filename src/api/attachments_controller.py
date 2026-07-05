from collections.abc import Iterator

from starlette.responses import StreamingResponse

from api.auth import PublicResourceTokenClaims
from di.di import DI
from features.chat.attachment.attachment_service import ResolvedAttachmentStream

ATTACHMENT_STREAM_CHUNK_SIZE_BYTES = 1024 * 1024


class AttachmentsController:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def stream_private_attachment(self, attachment_id: str) -> StreamingResponse:
        attachment_stream = self.__di.attachment_service.open_attachment(attachment_id)
        return self.__to_response(attachment_stream)

    def stream_public_attachment(self, token_claims: PublicResourceTokenClaims) -> StreamingResponse:
        self.__di.attachment_service.validate_public_read_claims(token_claims)
        attachment_stream = self.__di.attachment_service.open_attachment(token_claims.resource_id)
        return self.__to_response(attachment_stream)

    def __to_response(self, attachment_stream: ResolvedAttachmentStream) -> StreamingResponse:
        return StreamingResponse(self.__attachment_chunks(attachment_stream), media_type = attachment_stream.media_type)

    def __attachment_chunks(self, attachment_stream: ResolvedAttachmentStream) -> Iterator[bytes]:
        with attachment_stream.stream as stream:
            while chunk := stream.read(ATTACHMENT_STREAM_CHUNK_SIZE_BYTES):
                yield chunk
