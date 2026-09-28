from collections import deque
from typing import BinaryIO

from openai.types import CreateEmbeddingResponse
from openai.types.audio import Transcription
from stubs import external

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeTranscriptions:

    responses: deque[Transcription | Exception]
    recordings: list[bytes]

    def __init__(self):
        self.responses = deque()
        self.recordings = []

    def create(self, *, model: str, file: BinaryIO, response_format: str) -> Transcription:
        self.recordings.append(file.read())
        if not self.responses:
            raise InternalError("No transcription response configured", DI_DEPENDENCY_NOT_MET)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep = True)


class FakeAudio:

    transcriptions: FakeTranscriptions

    def __init__(self):
        self.transcriptions = FakeTranscriptions()


class FakeEmbeddings:

    vector: list[float] | None
    inputs: list[str]

    def __init__(self):
        self.vector = None
        self.inputs = []

    def create(self, *, model: str, input: str | list[str]) -> CreateEmbeddingResponse:
        texts = [input] if isinstance(input, str) else input
        self.inputs.extend(texts)
        if self.vector is None:
            raise InternalError("No embedding vector configured", DI_DEPENDENCY_NOT_MET)
        return external.openai_embedding_response(
            model = model,
            data = [external.openai_embedding(index = index, embedding = list(self.vector)) for index in range(len(texts))],
        )


class FakeOpenAIClient:

    audio: FakeAudio
    embeddings: FakeEmbeddings

    def __init__(self):
        self.audio = FakeAudio()
        self.embeddings = FakeEmbeddings()
