import unittest
from types import SimpleNamespace
from unittest.mock import patch

from di.di import DI
from features.chat.attachment.storage.local_attachment_storage import LocalAttachmentStorage
from features.chat.attachment.storage.s3_attachment_storage import S3AttachmentStorage
from features.chat.attachment.storage.uploadcare_attachment_storage import UploadcareAttachmentStorage


class FakeSecret:

    __value: str

    def __init__(self, value: str):
        self.__value = value

    def get_secret_value(self) -> str:
        return self.__value


class DIAttachmentStorageTest(unittest.TestCase):

    def test_selects_s3_when_full_s3_config_present(self):
        self.__assert_selected(self.__config(s3 = True, uploadcare = True), expected = "s3")

    def test_selects_uploadcare_when_s3_incomplete_but_uploadcare_full(self):
        self.__assert_selected(self.__config(s3 = False, uploadcare = True), expected = "uploadcare")

    def test_falls_back_to_local_when_s3_only_has_base_url(self):
        config = self.__config(s3 = False, uploadcare = False)
        config.s3_base_url = "http://s3.local"
        self.__assert_selected(config, expected = "local")

    def test_falls_back_to_local_when_uploadcare_config_partial(self):
        config = self.__config(s3 = False, uploadcare = False)
        config.uploadcare_public_key = "public-only"
        self.__assert_selected(config, expected = "local")

    def test_falls_back_to_local_when_nothing_configured(self):
        self.__assert_selected(self.__config(s3 = False, uploadcare = False), expected = "local")

    def __assert_selected(self, config: SimpleNamespace, expected: str) -> None:
        with patch("features.chat.attachment.storage.s3_attachment_storage.config", config), \
             patch("features.chat.attachment.storage.uploadcare_attachment_storage.config", config), \
             patch("features.chat.attachment.storage.s3_attachment_storage.S3AttachmentStorage") as s3_class, \
             patch("features.chat.attachment.storage.uploadcare_attachment_storage.UploadcareAttachmentStorage") as uploadcare_class, \
             patch("features.chat.attachment.storage.local_attachment_storage.LocalAttachmentStorage") as local_class:
            s3_class.can_be_used.side_effect = S3AttachmentStorage.can_be_used
            uploadcare_class.can_be_used.side_effect = UploadcareAttachmentStorage.can_be_used
            local_class.can_be_used.side_effect = LocalAttachmentStorage.can_be_used
            classes = {"s3": s3_class, "uploadcare": uploadcare_class, "local": local_class}

            result = DI().attachment_storage

            selected = classes[expected]
            self.assertIs(result, selected.return_value)
            selected.assert_called_once_with()
            selected.return_value.ensure_ready.assert_called_once_with()
            for name, storage_class in classes.items():
                if name != expected:
                    storage_class.assert_not_called()

    def __config(self, s3: bool, uploadcare: bool) -> SimpleNamespace:
        return SimpleNamespace(
            s3_base_url = "http://s3.local" if s3 else "",
            s3_region = "eu-central-1",
            s3_bucket = "the-agent",
            s3_access_key = FakeSecret("access" if s3 else ""),
            s3_secret_key = FakeSecret("secret" if s3 else ""),
            uploadcare_public_key = "public" if uploadcare else "",
            uploadcare_private_key = FakeSecret("private" if uploadcare else ""),
            uploadcare_cdn_id = "cdn-id" if uploadcare else "",
        )
