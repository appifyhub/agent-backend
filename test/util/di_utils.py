from ast import If, ImportFrom, parse
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from functools import cache
from importlib import import_module
from inspect import getsource
from pathlib import Path
from socket import socket
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fakes.http_client import FakeHTTPClient
from fakes.s3_client import FakeS3Client
from fakes.uploadcare_client import FakeUploadcareClient
from pyuploadcare import Uploadcare
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.model.base import BaseModel
from db.model.chat_attachment import ChatAttachmentDB
from db.model.chat_config import ChatConfigDB
from db.model.chat_membership import ChatMembershipDB
from db.model.chat_message import ChatMessageDB
from db.model.chat_message_burst import ChatMessageBurstDB
from db.model.price_alert import PriceAlertDB
from db.model.purchase_record import PurchaseRecordDB
from db.model.sponsorship import SponsorshipDB
from db.model.tools_cache import ToolsCacheDB
from db.model.usage_record import UsageRecordDB
from db.model.user import UserDB
from di.di import DI
from di.interception import DependencyRequest, DIInterceptor
from features.chat.attachment.storage.attachment_storage import AttachmentStorage
from features.chat.attachment.storage.local_attachment_storage import LOCAL_ATTACHMENT_STORAGE_ROOT, LocalAttachmentStorage
from features.chat.attachment.storage.s3_client import S3Client
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError
from util.http_client import HTTPClient

_MODELS = (
    UserDB, ChatConfigDB, ChatMembershipDB, ChatMessageDB, ChatMessageBurstDB,
    ChatAttachmentDB, PriceAlertDB, PurchaseRecordDB, SponsorshipDB, ToolsCacheDB, UsageRecordDB,
)


@cache
def _imported_types(module_name: str) -> dict[str, tuple[str, str]]:
    body = list(parse(getsource(import_module(module_name))).body)
    imports: dict[str, tuple[str, str]] = {}
    for node in body:
        if isinstance(node, If):
            body.extend(node.body)
        elif isinstance(node, ImportFrom) and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return imports


class FakeInterceptor:

    def __init__(self):
        self._factories: dict[type, DIInterceptor] = {}

    def register(self, dependency_type: type, instance: object) -> None:
        self.register_factory(dependency_type, lambda _: instance)

    def register_factory(self, dependency_type: type, factory: DIInterceptor) -> None:
        self._factories[dependency_type] = factory

    def __call__(self, request: DependencyRequest) -> object | None:
        declared = request.factory.__annotations__["return"]
        if isinstance(declared, str):
            name = declared.strip("\"'")
            declared = request.factory.__globals__.get(name)
            if declared is None:
                imported = _imported_types(request.factory.__module__).get(name)
                if imported is None:
                    return None
                module_name, class_name = imported
                if not any(cls.__name__ == class_name for cls in self._factories):
                    return None
                declared = getattr(import_module(module_name), class_name)
        factory = self._factories.get(declared)
        return factory(request) if factory is not None else None


def _block_network(*args: Any, **kwargs: Any) -> None:
    raise InternalError("Live network access is disabled in the test DI environment", DI_DEPENDENCY_NOT_MET)


@contextmanager
def di_for_tests(
    interceptor: DIInterceptor | None = None,
    invoker_id: str | None = None,
    invoker_chat_id: str | None = None,
) -> Generator[DI, None, None]:
    """Yield a production DI with an isolated SQLite database and temporary local storage.

    Use with di_for_tests() as di, or self.enterContext(di_for_tests()) in unittest.
    The supplied interceptor runs before shared defaults; None falls back to normal
    construction. Network access is blocked for the scope. Exit closes the session,
    disposes the engine, removes files, and restores network access. Configuration
    belongs to the test: assign config properties directly and restore any changed
    values in test cleanup. Opening or closing a DI environment does not reset settings.

    SQLUtil can coexist during migration, but owns a separate database and session.
    This helper leaves db.sql globals untouched; seed and query through this DI's
    repositories rather than SQLUtil when using this environment.
    """
    with ExitStack() as resources:
        # system socket guards prevent accidental live traffic from an unhandled external dependency
        resources.enter_context(patch.object(socket, "connect", new = _block_network))
        resources.enter_context(patch.object(socket, "connect_ex", new = _block_network))
        resources.enter_context(patch("socket.getaddrinfo", new = _block_network))
        root = Path(resources.enter_context(TemporaryDirectory()))
        database_path = root / "database.sqlite"
        engine = create_engine(f"sqlite:///{database_path}")
        resources.callback(engine.dispose)
        BaseModel.metadata.create_all(engine, tables = [model.__table__ for model in _MODELS])
        db = resources.enter_context(Session(engine, autoflush = False))
        storage = LocalAttachmentStorage(root = root / "attachments")
        storage.ensure_ready()
        defaults = FakeInterceptor()
        defaults.register(S3Client, FakeS3Client())
        defaults.register(Uploadcare, FakeUploadcareClient())
        defaults.register(HTTPClient, FakeHTTPClient())
        defaults.register(AttachmentStorage, storage)
        defaults.register_factory(
            LocalAttachmentStorage,
            lambda request: storage if request.arguments["root"] == LOCAL_ATTACHMENT_STORAGE_ROOT else None,
        )

        def resolve(request: DependencyRequest) -> object | None:
            if interceptor is not None:
                result = interceptor(request)
                if result is not None:
                    return result
            return defaults(request)

        yield DI(
            db = db,
            invoker_id = invoker_id,
            invoker_chat_id = invoker_chat_id,
            interceptor = resolve,
        )
