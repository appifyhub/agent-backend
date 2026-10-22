from ast import If, ImportFrom, parse
from collections.abc import Generator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from contextvars import ContextVar
from functools import cache, wraps
from importlib import import_module
from inspect import getsource
from ipaddress import ip_address
from pathlib import Path
from socket import AF_INET, AF_INET6, IPPROTO_TCP, SOCK_STREAM, socket
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from fakes.fake_chat_model import FakeChatModel
from fakes.fake_google_ai_client import FakeGoogleAIClient
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_openai_client import FakeOpenAIClient
from fakes.fake_replicate_client import FakeReplicateClient
from fakes.fake_s3_client import FakeS3Client
from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_uploadcare_client import FakeUploadcareClient
from fakes.fake_url_shortener import FakeUrlShortener
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from fakes.fake_x_ai_client import FakeXAIClient
from google.genai import Client as GoogleSDKClient
from langchain_core.language_models import BaseChatModel
from openai import OpenAI
from pyuploadcare import Uploadcare
from replicate.client import Client as ReplicateSDKClient
from sqlalchemy import Integer, MetaData, PrimaryKeyConstraint, UniqueConstraint, create_engine
from sqlalchemy.orm import Session
from xai_sdk import Client as XAISDKClient

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


# A guarded outbound fetch resolves its destination, so tests need a deterministic answer that still
# passes the production "is this address public?" check. Every documentation range (TEST-NET-1/2/3,
# 2001:db8::) is classified private by `ipaddress`, so the guard would refuse it and no fetch could be
# tested. This is the 6to4 relay anycast prefix, deprecated by RFC 7526: classified global, assigned to
# no host. Nothing ever connects to it - `socket.connect`/`connect_ex` stay blocked and both HTTP
# clients are faked, so resolution is the only step that happens.
_DEPRECATED_GLOBAL_ADDRESS = "192.88.99.1"


def _block_network(*args: Any, **kwargs: Any) -> None:
    raise InternalError("Live network access is disabled in the test DI environment", DI_DEPENDENCY_NOT_MET)


def _offline_resolve(host: Any, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
    """Resolve names offline so production destination guards can run under tests.

    Name resolution is not traffic and this performs none: live access stays blocked by the
    socket connect guards and the HTTP fakes below. IP literals resolve to themselves and
    "localhost" resolves to loopback, so a test can assert a guard refusal; every other name
    resolves to the deprecated global address above so ordinary fetches pass the guard.
    """
    text = str(host)
    if text == "localhost":
        address = "127.0.0.1"
    else:
        try:
            address = str(ip_address(text))
        except ValueError:
            address = _DEPRECATED_GLOBAL_ADDRESS
    resolved_port = int(port) if isinstance(port, int) or str(port).isdigit() else 0
    if ":" in address:
        return [(AF_INET6, SOCK_STREAM, IPPROTO_TCP, "", (address, resolved_port, 0, 0))]
    return [(AF_INET, SOCK_STREAM, IPPROTO_TCP, "", (address, resolved_port))]


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
    construction. HTTP, storage clients, bot APIs, OpenAI, Google, Replicate, xAI,
    the base chat model, and URL shortening have shared per-environment fakes, configurable
    through normal DI providers. The model's usage decorator, services, repositories, and bot SDKs
    remain real. Direct requests.get/post calls use the same default HTTP fake through
    scoped transport replacements. Network access is blocked for the scope.
    Exit closes the session, disposes the engine, removes files, and restores network
    access. Configuration belongs to the test: assign config properties directly and restore any changed
    values in test cleanup. Opening or closing a DI environment does not reset settings.

    Seed and query through this DI's repositories. The helper leaves production
    db.sql globals untouched. DI.new_session() opens an independent session on the
    same database; pass it to clone(db = ...) when a separate scope is needed.
    Close that scope with a context manager before the environment exits.
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
        resources.enter_context(patch("socket.getaddrinfo", new = _offline_resolve))
        root = Path(resources.enter_context(TemporaryDirectory()))
        db = resources.enter_context(_sqlite_session(root / "database.sqlite"))
        storage = LocalAttachmentStorage(root = root / "attachments")
        storage.ensure_ready()
        defaults = FakeInterceptor()
        defaults.register_factory(AbstractContextManager[Session], lambda _: Session(db.get_bind(), autoflush = False))
        defaults.register(S3Client, FakeS3Client())
        defaults.register(Uploadcare, FakeUploadcareClient())
        http = FakeHTTPClient()
        defaults.register(HTTPClient, http)
        resources.enter_context(patch("requests.get", new = http.get))
        resources.enter_context(patch("requests.post", new = http.post))
        defaults.register(TelegramBotAPI, FakeTelegramBotAPI())
        defaults.register(WhatsAppBotAPI, FakeWhatsAppBotAPI())
        defaults.register(BaseChatModel, FakeChatModel())
        defaults.register(OpenAI, FakeOpenAIClient())
        defaults.register(GoogleSDKClient, FakeGoogleAIClient())
        defaults.register(ReplicateSDKClient, FakeReplicateClient())
        defaults.register(XAISDKClient, FakeXAIClient())
        shortener = FakeUrlShortener("https://example.com/short")
        defaults.register_factory(UrlShortener, lambda request: shortener.for_url(request.arguments["long_url"]))
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
