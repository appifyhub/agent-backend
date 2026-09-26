from collections import deque
from typing import BinaryIO

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FakeUploadcareFile:

    def __init__(self, cdn_url: str, filename: str):
        self.__cdn_url = cdn_url
        self.__filename = filename
        self.deleted = False
        self.delete_error: Exception | None = None

    @property
    def cdn_url(self) -> str:
        return self.__cdn_url

    @property
    def filename(self) -> str:
        return self.__filename

    def delete(self) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted = True


class FakeUploadcareClient:

    def __init__(self):
        self.uploads: list[tuple[str, bytes, bool]] = []
        self.upload_streams: list[BinaryIO] = []
        self.upload_results: deque[FakeUploadcareFile | Exception | None] = deque()
        self.files: dict[str, FakeUploadcareFile] = {}
        self.requested_files: list[str] = []

    def upload(self, file_handle: BinaryIO, store: bool = True) -> FakeUploadcareFile | None:
        self.uploads.append((file_handle.name, file_handle.read(), store))
        self.upload_streams.append(file_handle)
        if not self.upload_results:
            raise InternalError("No Uploadcare upload result configured", DI_DEPENDENCY_NOT_MET)
        result = self.upload_results.popleft()
        if isinstance(result, Exception):
            raise result
        if result is not None:
            self.files[f"{result.cdn_url}{result.filename}"] = result
        return result

    def file(self, cdn_url_or_file_id: str) -> FakeUploadcareFile:
        self.requested_files.append(cdn_url_or_file_id)
        if cdn_url_or_file_id not in self.files:
            raise InternalError(f"No Uploadcare file configured for {cdn_url_or_file_id}", DI_DEPENDENCY_NOT_MET)
        return self.files[cdn_url_or_file_id]
