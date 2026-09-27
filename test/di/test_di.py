from pathlib import Path
from socket import create_connection, socket
from tempfile import TemporaryDirectory
from typing import cast
from unittest import TestCase
from uuid import UUID

from botocore.client import BaseClient
from fakes.fake_attachment_storage import RecordingAttachmentStorage
from google.genai import Client as GoogleSDKClient
from pydantic import SecretStr
from replicate.client import Client as ReplicateSDKClient
from sqlalchemy.orm import Session
from stubs import domain
from util.di_utils import FakeInterceptor, di_for_tests

from db import sql
from di.di import DI
from di.interception import DependencyRequest
from features.chat.attachment.storage.attachment_storage import AttachmentStorage
from features.chat.attachment.storage.local_attachment_storage import LOCAL_ATTACHMENT_STORAGE_ROOT, LocalAttachmentStorage
from features.chat.attachment.storage.s3_attachment_storage import S3AttachmentStorage
from features.chat.attachment.storage.uploadcare_attachment_storage import UploadcareAttachmentStorage
from features.chat.telegram.telegram_domain_mapper import TelegramDomainMapper
from features.web_browsing.web_fetcher import WebFetcher
from util.config import config
from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class FalseValuedStorage(RecordingAttachmentStorage):

    def __bool__(self) -> bool:
        return False


class DITest(TestCase):

    root: Path

    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def test_s3_client_uses_configured_credentials_and_path_style_endpoint(self):
        for name, value in {
            "s3_base_url": "http://s3.invalid",
            "s3_region": "eu-central-1",
            "s3_access_key": SecretStr("access"),
            "s3_secret_key": SecretStr("secret"),
        }.items():
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)
        self.enterContext(di_for_tests())
        client = cast(BaseClient, DI().s3_client())
        self.addCleanup(client.close)

        self.assertEqual(client.meta.endpoint_url, "http://s3.invalid")
        self.assertEqual(client.meta.region_name, "eu-central-1")
        self.assertEqual(client.meta.config.s3["addressing_style"], "path")
        self.assertEqual(client._request_signer._credentials.access_key, "access")
        self.assertEqual(client._request_signer._credentials.secret_key, "secret")

    def test_uploadcare_client_uses_configured_credentials_and_cdn(self):
        for name, value in {
            "uploadcare_public_key": "public",
            "uploadcare_private_key": SecretStr("private"),
            "uploadcare_cdn_id": "cdn-id",
        }.items():
            self.addCleanup(setattr, config, name, getattr(config, name))
            setattr(config, name, value)
        self.enterContext(di_for_tests())

        client = DI().uploadcare_client()

        self.assertEqual(client.public_key, "public")
        self.assertEqual(client.secret_key, "private")
        self.assertEqual(client.cdn_base, "https://cdn-id.ucarecd.net/")

    def test_without_interceptor_constructs_and_caches_real_dependency(self):
        di = DI()

        self.assertIsInstance(di.telegram_domain_mapper, TelegramDomainMapper)
        self.assertIs(di.telegram_domain_mapper, di.telegram_domain_mapper)

    def test_unhandled_dependency_uses_and_caches_production_construction(self):
        requests: list[DependencyRequest] = []

        def unhandled(request: DependencyRequest) -> None:
            requests.append(request)

        di = DI(interceptor = unhandled)

        self.assertIsInstance(di.telegram_domain_mapper, TelegramDomainMapper)
        self.assertIs(di.telegram_domain_mapper, di.telegram_domain_mapper)
        self.assertEqual(len(requests), 1)

    def test_forward_reference_replacement_is_cached_without_running_original_factory(self):
        storage = RecordingAttachmentStorage(self.root / "replacement")
        requests: list[DependencyRequest] = []

        def create(request: DependencyRequest) -> AttachmentStorage:
            requests.append(request)
            return storage

        interceptor = FakeInterceptor()
        interceptor.register_factory(AttachmentStorage, create)
        di = self.enterContext(di_for_tests(interceptor = interceptor))

        self.assertIs(di.attachment_storage, storage)
        self.assertIs(di.attachment_storage, storage)
        self.assertEqual(len(requests), 1)
        self.assertIs(requests[0].di, di)
        self.assertEqual(storage.ready_calls, 0)

    def test_false_valued_replacement_is_handled(self):
        storage = FalseValuedStorage(self.root)
        interceptor = FakeInterceptor()
        interceptor.register(AttachmentStorage, storage)
        di = self.enterContext(di_for_tests(interceptor = interceptor))

        self.assertIs(di.attachment_storage, storage)
        self.assertIs(di.attachment_storage, storage)

    def test_interceptor_exception_does_not_fall_back(self):
        error = InternalError("replacement failed", DI_DEPENDENCY_NOT_MET)

        def fail(_: DependencyRequest) -> None:
            raise error

        di = self.enterContext(di_for_tests(interceptor = fail))

        with self.assertRaises(InternalError) as raised:
            di.attachment_storage

        self.assertIs(raised.exception, error)

    def test_transient_factory_receives_context_and_bound_arguments_for_each_call(self):
        requests: list[DependencyRequest] = []

        def create(request: DependencyRequest) -> WebFetcher:
            requests.append(request)
            return WebFetcher(di = request.di, **request.arguments)

        interceptor = FakeInterceptor()
        interceptor.register_factory(WebFetcher, create)
        di = self.enterContext(di_for_tests(interceptor = interceptor))

        first = di.web_fetcher("https://first.invalid", {"Accept": "text/plain"})
        second = di.web_fetcher(url = "https://second.invalid", params = {"page": 2})

        self.assertIsNot(first, second)
        self.assertEqual(first.url, "https://first.invalid")
        self.assertEqual(second.url, "https://second.invalid")
        self.assertEqual(len(requests), 2)
        self.assertIs(requests[0].di, di)
        self.assertIs(requests[1].di, di)
        self.assertEqual(requests[0].arguments["headers"], {"Accept": "text/plain"})
        self.assertEqual(requests[1].arguments["params"], {"page": 2})
        self.assertFalse(requests[0].arguments["auto_fetch_html"])

    def test_aliased_types_with_same_short_name_resolve_independently(self):
        di = self.enterContext(di_for_tests())
        google = GoogleSDKClient(api_key = "test-google-key")
        self.addCleanup(google.close)
        replicate = ReplicateSDKClient(api_token = "test-replicate-key")
        interceptor = FakeInterceptor()
        interceptor.register(GoogleSDKClient, google)
        interceptor.register(ReplicateSDKClient, replicate)
        di = DI(db = di.db, interceptor = interceptor)

        self.assertEqual(GoogleSDKClient.__name__, ReplicateSDKClient.__name__)
        self.assertIs(di.base_google_ai_client("unused-google-key"), google)
        self.assertIs(di.base_replicate_client("unused-replicate-key"), replicate)

    def test_registration_for_one_client_does_not_handle_another_client_type(self):
        replicate = ReplicateSDKClient(api_token = "test-replicate-key")
        interceptor = FakeInterceptor()
        interceptor.register(ReplicateSDKClient, replicate)
        di = self.enterContext(di_for_tests(interceptor = interceptor))

        google = di.base_google_ai_client("test-google-key")
        self.addCleanup(google.close)

        self.assertIsInstance(google, GoogleSDKClient)
        self.assertIsNot(google, replicate)

    def test_context_operations_are_not_intercepted(self):
        def fail(_: DependencyRequest) -> None:
            raise InternalError("context was intercepted", DI_DEPENDENCY_NOT_MET)

        di = DI(interceptor = fail)
        user = domain.user()
        chat = domain.chat_config()

        self.assertIsNone(di.invoker_chat)
        di.inject_invoker(user)
        di.inject_invoker_chat(chat)

        self.assertIs(di.invoker, user)
        self.assertIs(di.require_invoker_chat(), chat)
        self.assertEqual(di.invoker_id, user.id.hex)
        self.assertEqual(di.require_invoker_chat_type(), chat.chat_type)

    def test_clone_rebuilds_services_and_repositories_and_retains_shared_storage(self):
        di = self.enterContext(di_for_tests())
        user = di.user_repo.save(domain.user())
        service = di.chat_attachment_service
        storage = di.attachment_storage

        with Session(di.db.get_bind()) as session:
            clone = di.clone(db = session, invoker_id = user.id.hex)

            self.assertIs(clone.db, session)
            self.assertIsNot(clone.user_repo, di.user_repo)
            self.assertIsNot(clone.chat_attachment_service, service)
            self.assertEqual(clone.user_repo.get(user.id).id, user.id)
            self.assertIs(clone.attachment_storage, storage)

    def test_clone_uses_its_own_invoker_context(self):
        first = domain.user()
        second = domain.user(
            id = UUID("22222222-2222-4222-8222-a22222222222"),
            telegram_user_id = 2,
            whatsapp_user_id = "second-user",
            connect_key = "SECOND-USER",
        )
        di = self.enterContext(di_for_tests(invoker_id = first.id.hex))
        di.user_repo.save(first)
        di.user_repo.save(second)

        self.assertEqual(di.invoker.id, first.id)
        clone = di.clone(invoker_id = second.id.hex)

        self.assertEqual(clone.invoker.id, second.id)
        self.assertEqual(di.invoker.id, first.id)

    def test_clone_replacement_factory_receives_clone(self):
        requests: list[DependencyRequest] = []

        def create(request: DependencyRequest) -> TelegramDomainMapper:
            requests.append(request)
            return TelegramDomainMapper()

        interceptor = FakeInterceptor()
        interceptor.register_factory(TelegramDomainMapper, create)
        di = self.enterContext(di_for_tests(interceptor = interceptor))
        parent_mapper = di.telegram_domain_mapper
        clone = di.clone()

        self.assertIsNot(clone.telegram_domain_mapper, parent_mapper)
        self.assertEqual([request.di for request in requests], [di, clone])

    def test_helper_returns_production_di_with_real_local_dependencies(self):
        di = self.enterContext(di_for_tests())

        self.assertIs(type(di), DI)
        self.assertIsInstance(di.attachment_storage, LocalAttachmentStorage)
        self.assertIs(di.attachment_storage, di.local_attachment_storage())
        self.assertEqual(di.user_repo.count(), 0)

    def test_external_clients_are_shared_with_clones_but_isolated_between_environments(self):
        with di_for_tests() as first, di_for_tests() as second:
            clone = first.clone()
            for factory in ("s3_client", "uploadcare_client", "http_client"):
                with self.subTest(factory = factory):
                    client = getattr(first, factory)()
                    self.assertIs(client, getattr(clone, factory)())
                    self.assertIsNot(client, getattr(second, factory)())

    def test_local_storage_factory_preserves_default_root(self):
        storage = DI().local_attachment_storage()

        self.assertTrue(storage.owns_uri(f"file://{LOCAL_ATTACHMENT_STORAGE_ROOT}/attachment.txt"))

    def test_local_storage_factory_honors_explicit_root_in_production_and_test_di(self):
        test_di = self.enterContext(di_for_tests())
        attachment = domain.chat_attachment()

        for name, di in (("production", DI()), ("test", test_di)):
            with self.subTest(di = name):
                root = self.root / name
                storage = di.local_attachment_storage(root = root)
                locator = storage.put(attachment, b"custom root")

                self.assertEqual(locator, f"file://{root}/{attachment.uri}")
                self.assertEqual((root / attachment.uri).read_bytes(), b"custom root")

    def test_real_service_persists_attachment_and_bytes(self):
        di = self.enterContext(di_for_tests())
        user = di.user_repo.save(domain.user())
        chat = di.chat_config_repo.save(domain.chat_config())
        attachment = domain.chat_attachment(
            chat_id = chat.chat_id,
            uploader_user_id = user.id,
            mime_type = "text/plain",
            extension = "txt",
        )

        saved = di.chat_attachment_service.save(attachment, content = b"stored text")

        self.assertEqual(di.chat_attachment_repo.get(saved.id).last_url, saved.last_url)
        with di.attachment_storage.open(saved) as stream:
            self.assertEqual(stream.read(), b"stored text")

    def test_environments_do_not_share_database_or_storage(self):
        with di_for_tests() as first:
            user = first.user_repo.save(domain.user())
            attachment = domain.chat_attachment()
            locator = first.attachment_storage.put(attachment, b"first only")

            with di_for_tests() as second:
                self.assertIsNone(second.user_repo.get(user.id))
                self.assertIsNot(second.attachment_storage, first.attachment_storage)
                with self.assertRaises(FileNotFoundError):
                    second.attachment_storage.open(attachment)

            with first.attachment_storage.open(attachment) as stream:
                self.assertEqual(stream.read(), b"first only")

        self.assertFalse(Path(locator.removeprefix("file://")).exists())

    def test_helper_leaves_production_database_globals_unchanged(self):
        before = {name: getattr(sql, name, None) for name in ("engine", "LocalSession")}

        with di_for_tests() as di:
            di.user_repo.save(domain.user())

        for name, value in before.items():
            self.assertIs(getattr(sql, name, None), value)

    def test_di_environments_preserve_test_configuration(self):
        self.addCleanup(setattr, config, "user_agent", config.user_agent)
        config.user_agent = "test setting before DI"
        with di_for_tests():
            self.assertEqual(config.user_agent, "test setting before DI")
            with di_for_tests():
                self.assertEqual(config.user_agent, "test setting before DI")
                config.user_agent = "updated test setting"
            self.assertEqual(config.user_agent, "updated test setting")

        self.assertEqual(config.user_agent, "updated test setting")

    def test_network_guard_blocks_connections_and_name_resolution_and_is_restored(self):
        connect = socket.connect

        with di_for_tests():
            with socket() as connection:
                with self.assertRaisesRegex(InternalError, "Live network access is disabled"):
                    connection.connect(("127.0.0.1", 9))
            with self.assertRaisesRegex(InternalError, "Live network access is disabled"):
                create_connection(("must-not-resolve.invalid", 443))

        self.assertIs(socket.connect, connect)

    def test_failure_cleans_up_storage_and_database_without_resetting_configuration(self):
        self.addCleanup(setattr, config, "user_agent", config.user_agent)
        database_path: Path | None = None
        storage_path: Path | None = None

        with self.assertRaisesRegex(InternalError, "consumer failed"):
            with di_for_tests() as di:
                database_path = Path(di.db.get_bind().url.database)
                locator = di.attachment_storage.put(domain.chat_attachment(), b"temporary")
                storage_path = Path(locator.removeprefix("file://"))
                config.user_agent = "temporary setting"
                raise InternalError("consumer failed", DI_DEPENDENCY_NOT_MET)

        self.assertIsNotNone(database_path)
        self.assertIsNotNone(storage_path)
        self.assertFalse(database_path.exists())
        self.assertFalse(storage_path.exists())
        self.assertEqual(config.user_agent, "temporary setting")


class DIAttachmentStorageTest(TestCase):

    def setUp(self):
        for name in (
            "s3_base_url", "s3_access_key", "s3_secret_key",
            "uploadcare_public_key", "uploadcare_private_key", "uploadcare_cdn_id",
        ):
            self.addCleanup(setattr, config, name, getattr(config, name))
        root = Path(self.enterContext(TemporaryDirectory()))
        self.storages = {
            "s3": RecordingAttachmentStorage(root / "s3"),
            "uploadcare": RecordingAttachmentStorage(root / "uploadcare"),
            "local": RecordingAttachmentStorage(root / "local"),
        }
        interceptor = FakeInterceptor()
        interceptor.register_factory(AttachmentStorage, lambda request: request.factory(request.di))
        interceptor.register(S3AttachmentStorage, self.storages["s3"])
        interceptor.register(UploadcareAttachmentStorage, self.storages["uploadcare"])
        interceptor.register(LocalAttachmentStorage, self.storages["local"])
        self.di = self.enterContext(di_for_tests(interceptor = interceptor))

    def test_selects_s3_when_full_s3_config_present(self):
        self.__configure(s3 = True, uploadcare = True)
        self.__assert_selected("s3")

    def test_selects_uploadcare_when_s3_incomplete_but_uploadcare_full(self):
        self.__configure(s3 = False, uploadcare = True)
        self.__assert_selected("uploadcare")

    def test_falls_back_to_local_when_s3_only_has_base_url(self):
        self.__configure(s3 = False, uploadcare = False)
        config.s3_base_url = "http://s3.invalid"
        self.__assert_selected("local")

    def test_falls_back_to_local_when_uploadcare_config_partial(self):
        self.__configure(s3 = False, uploadcare = False)
        config.uploadcare_public_key = "public-only"
        self.__assert_selected("local")

    def test_falls_back_to_local_when_nothing_configured(self):
        self.__configure(s3 = False, uploadcare = False)
        self.__assert_selected("local")

    def __assert_selected(self, expected: str) -> None:
        self.assertIs(self.di.attachment_storage, self.storages[expected])
        self.assertIs(self.di.attachment_storage, self.storages[expected])
        for name, storage in self.storages.items():
            self.assertEqual(storage.ready_calls, 1 if name == expected else 0)

    def __configure(self, s3: bool, uploadcare: bool) -> None:
        config.s3_base_url = "http://s3.invalid" if s3 else ""
        config.s3_access_key = SecretStr("access" if s3 else "")
        config.s3_secret_key = SecretStr("secret" if s3 else "")
        config.uploadcare_public_key = "public" if uploadcare else ""
        config.uploadcare_private_key = SecretStr("private" if uploadcare else "")
        config.uploadcare_cdn_id = "cdn-id" if uploadcare else ""
