from collections.abc import Iterator

from starlette.responses import StreamingResponse

from api.auth import PublicAttachmentTokenClaims
from di.di import DI
from features.chat.attachment.chat_message_attachment_service import ResolvedAttachmentStream
from util import log

ATTACHMENT_STREAM_CHUNK_SIZE_BYTES = 1024 * 1024


class AttachmentsController:

    __di: DI

    def __init__(self, di: DI):
        self.__di = di

    def stream_private_attachment(self, attachment_id: str) -> StreamingResponse:
        attachment_stream = self.__di.chat_message_attachment_service.stream_attachment(attachment_id)
        return self.__to_response(attachment_stream)

    def stream_public_attachment(self, token_claims: PublicAttachmentTokenClaims) -> StreamingResponse:
        log.t(
            f"Streaming public attachment '{token_claims.attachment_id}' "
            f"for chat '{token_claims.chat_id}' issued by '{token_claims.issuer_user_id}'",
        )
        attachment_stream = self.__di.chat_message_attachment_service.stream_attachment(token_claims.attachment_id)
        return self.__to_response(attachment_stream)

    def __to_response(self, attachment_stream: ResolvedAttachmentStream) -> StreamingResponse:
        return StreamingResponse(self.__attachment_chunks(attachment_stream), media_type = attachment_stream.media_type)

    def __attachment_chunks(self, attachment_stream: ResolvedAttachmentStream) -> Iterator[bytes]:
        with attachment_stream.stream as stream:
            while chunk := stream.read(ATTACHMENT_STREAM_CHUNK_SIZE_BYTES):
                yield chunk
