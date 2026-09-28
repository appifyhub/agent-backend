from ast import If, ImportFrom, parse
from collections.abc import Generator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from contextvars import ContextVar
from functools import cache, wraps
from importlib import import_module
from inspect import getsource
from pathlib import Path
from socket import socket
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_openai_client import FakeOpenAIClient
from fakes.fake_s3_client import FakeS3Client
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_uploadcare_client import FakeUploadcareClient
from fakes.fake_url_shortener import FakeUrlShortener
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from langchain_core.language_models import BaseChatModel
from openai import OpenAI
from pyuploadcare import Uploadcare
from sqlalchemy import Integer, MetaData, PrimaryKeyConstraint, UniqueConstraint, create_engine
from sqlalchemy.orm import Session

from db.model.base import BaseModel
from di.di import DI
from di.interception import DependencyRequest, DIInterceptor
from features.chat.attachment.storage.attachment_storage import AttachmentStorage
from features.chat.attachment.storage.local_attachment_storage import LOCAL_ATTACHMENT_STORAGE_ROOT, LocalAttachmentStorage
from features.chat.attachment.storage.s3_client import S3Client
from features.chat.telegram.sdk.telegram_bot_api import TelegramBotAPI
from features.chat.whatsapp.sdk.whatsapp_bot_api import WhatsAppBotAPI
from features.web_browsing.url_shortener import UrlShortener
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError
from util.http_client import HTTPClient

context_local_interceptor: ContextVar[DIInterceptor | None] = ContextVar("test_di_interceptor", default = None)


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

    _factories: dict[type, DIInterceptor]

    def __init__(self):
        self._factories = {}

    def register(self, dependency_type: type, instance: object) -> None:
        self.register_factory(dependency_type, lambda _: instance)

    def register_factory(self, dependency_type: type, factory: DIInterceptor) -> None:
        self._factories[dependency_type] = factory

    def __call__(self, request: DependencyRequest) -> object | None:
        declared = request.factory.__annotations__["return"]
        if isinstance(declared, str):
            name = declared.strip("\"'")
            try:
                declared = eval(name, request.factory.__globals__)
            except NameError:
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


def _sqlite_metadata() -> MetaData:
    """Copy the registered application schema for the SQLite test database.

    SQLite generates identities only on an INTEGER primary key. Adapt Identity
    columns in the copy, preserving the original key as a unique constraint.
    The production metadata and ORM mappings remain unchanged; SQLite itself
    allocates values without callbacks inspecting or modifying application data.
    """
    metadata = MetaData()
    for source in BaseModel.metadata.sorted_tables:
        table = source.to_metadata(metadata)
        identity = next((column for column in table.columns if column.identity is not None), None)
        if identity is None:
            continue
        original_key = list(table.primary_key.columns)
        table.constraints.remove(table.primary_key)
        table.append_constraint(UniqueConstraint(*(column.name for column in original_key)))
        for column in original_key:
            column.primary_key = False
        identity.type = Integer()
        identity.identity = None
        identity.server_default = None
        table.append_constraint(PrimaryKeyConstraint(identity.name))
        table.dialect_options["sqlite"]["autoincrement"] = True
    return metadata


@contextmanager
def _sqlite_session(path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{path}")
    try:
        _sqlite_metadata().create_all(engine)
        with Session(engine, autoflush = False) as session:
            yield session
    finally:
        engine.dispose()


@contextmanager
def di_for_tests(
    interceptor: DIInterceptor | None = None,
    invoker_id: str | None = None,
    invoker_chat_id: str | None = None,
) -> Generator[DI, None, None]:
    """Yield a production DI with an isolated SQLite database and temporary local storage.

    Use with di_for_tests() as di, or self.enterContext(di_for_tests()) in unittest.
    The supplied interceptor runs before shared defaults; None falls back to normal
    construction. HTTP, storage clients, bot APIs, OpenAI audio/embeddings, the base
    chat model, and URL shortening have shared per-environment fakes, configurable
    through normal DI providers. The model's usage decorator, services, repositories, and bot SDKs
    remain real. Network access is blocked for the scope.
    Exit closes the session, disposes the engine, removes files, and restores network
    access. Configuration belongs to the test: assign config properties directly and restore any changed
    values in test cleanup. Opening or closing a DI environment does not reset settings.

    SQLUtil can coexist during migration, but owns a separate database and session.
    This helper leaves db.sql globals untouched; seed and query through this DI's
    repositories rather than SQLUtil when using this environment.
    DI.new_session() and clones open independent sessions on this same database;
    callers close them with a context manager before the environment exits.
    A temporary constructor hook supplies the context-local interceptor to the real
    DI initializer. Fresh instances inherit it in asyncio tasks and asyncio.to_thread
    workers without inheriting a session. Production DI has no ambient interceptor.
    Nested environments restore the enclosing interceptor on exit. Plain threads
    do not inherit this context automatically; finish all background work before exit.
    """
    with ExitStack() as resources:
        # system socket guards prevent accidental live traffic from an unhandled external dependency
        resources.enter_context(patch.object(socket, "connect", new = _block_network))
        resources.enter_context(patch.object(socket, "connect_ex", new = _block_network))
        resources.enter_context(patch("socket.getaddrinfo", new = _block_network))
        root = Path(resources.enter_context(TemporaryDirectory()))
        db = resources.enter_context(_sqlite_session(root / "database.sqlite"))
        storage = LocalAttachmentStorage(root = root / "attachments")
        storage.ensure_ready()
        defaults = FakeInterceptor()
        defaults.register_factory(AbstractContextManager[Session], lambda _: Session(db.get_bind(), autoflush = False))
        defaults.register(S3Client, FakeS3Client())
        defaults.register(Uploadcare, FakeUploadcareClient())
        defaults.register(HTTPClient, FakeHTTPClient())
        defaults.register(TelegramBotAPI, FakeTelegramBotAPI())
        defaults.register(WhatsAppBotAPI, FakeWhatsAppBotAPI())
        defaults.register(BaseChatModel, FakeChatModel())
        defaults.register(OpenAI, FakeOpenAIClient())
        defaults.register(UrlShortener, FakeUrlShortener("https://example.com/short"))
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

        original_init = DI.__init__

        @wraps(original_init)
        def initialize_di(
            di: DI,
            db: Session | None = None,
            invoker_id: str | None = None,
            invoker_chat_id: str | None = None,
            interceptor: DIInterceptor | None = None,
        ) -> None:
            original_init(
                di,
                db = db,
                invoker_id = invoker_id,
                invoker_chat_id = invoker_chat_id,
                interceptor = interceptor if interceptor is not None else context_local_interceptor.get(),
            )

        resources.enter_context(patch.object(DI, "__init__", new = initialize_di))
        resources.callback(context_local_interceptor.reset, context_local_interceptor.set(resolve))
        yield DI(
            db = db,
            invoker_id = invoker_id,
            invoker_chat_id = invoker_chat_id,
        )
