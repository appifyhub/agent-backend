import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, mock_open, patch
from uuid import UUID

import requests
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from db.model.chat_config import ChatConfigDB
from db.model.user import UserDB
from di.di import DI
from features.external_tools.external_tool import ExternalTool, ToolType
from features.external_tools.external_tool_library import CLAUDE_4_6_SONNET
from features.support.user_support_service import UserSupportService
from features.users.user import User


class UserSupportServiceTest(unittest.TestCase):

    user: User
    mock_di: DI
    mock_configured_tool: tuple[ExternalTool, SecretStr, ToolType]
    service: UserSupportService

    def setUp(self):
        self.user = User(
            id = UUID(int = 1),
            full_name = "Test User",
            telegram_username = "test_username",
            telegram_chat_id = "test_chat_id",
            telegram_user_id = 1,
            open_ai_key = SecretStr("test_api_key"),
            anthropic_key = SecretStr("test_anthropic_key"),
            group = UserDB.Group.standard,
            created_at = datetime.now().date(),
        )
        self.mock_di = Mock(spec = DI)
        self.mock_di.invoker.return_value = self.user
        self.mock_di.invoker_chat_type = ChatConfigDB.ChatType.telegram
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)
        self.mock_di.chat_langchain_model = Mock()

        # Mock URL shortener to return same URL
        def mock_url_shortener(long_url, **kwargs):
            mock_shortener = MagicMock()
            mock_shortener.execute.return_value = long_url
            return mock_shortener
        self.mock_di.url_shortener = MagicMock(side_effect = mock_url_shortener)
        self.mock_configured_tool = (CLAUDE_4_6_SONNET, SecretStr("test_key"), ToolType.copywriting)
        self.service = UserSupportService(
            user_input = "Test input",
            github_author = "test_github",
            include_platform_handle = True,
            include_full_name = True,
            request_type_str = "bug",
            configured_tool = self.mock_configured_tool,
            di = self.mock_di,
        )

    def test_resolve_request_type(self):
        # noinspection PyUnresolvedReferences
        self.assertEqual(self.service._UserSupportService__request_type, UserSupportService.RequestType.bug)

        service = UserSupportService(
            user_input = "Test input",
            github_author = "test_github",
            include_platform_handle = True,
            include_full_name = True,
            request_type_str = "invalid_type",
            configured_tool = self.mock_configured_tool,
            di = self.mock_di,
        )
        # noinspection PyUnresolvedReferences
        self.assertEqual(service._UserSupportService__request_type, UserSupportService.RequestType.request)

    @patch("builtins.open", new_callable = mock_open, read_data = "test template")
    def test_load_template(self, mock_open_template):
        # noinspection PyUnresolvedReferences
        template = self.service._UserSupportService__load_template()
        self.assertEqual(template, "test template")
        mock_open_template.assert_called_once()

    @patch("features.support.user_support_service.UserSupportService._UserSupportService__load_template")
    @patch("features.integrations.prompt_resolvers.copywriting_support_request_description")
    def test_generate_issue_description(self, mock_prompt_generator, mock_load_template):
        mock_load_template.return_value = "test template"
        mock_prompt_generator.return_value = "test prompt"

        with patch.object(self.service, "_UserSupportService__copywriter") as mock_llm:
            mock_llm.invoke.return_value = AIMessage(content = [
                {"type": "thinking", "thinking": "Hidden reasoning"},
                {"type": "text", "text": "Generated description"},
            ])
            # noinspection PyUnresolvedReferences
            description = self.service._UserSupportService__generate_issue_description()

        self.assertEqual(description, "Generated description")
        mock_load_template.assert_called_once()
        mock_prompt_generator.assert_called_once()
        mock_llm.invoke.assert_called_once()

    @patch("features.integrations.prompt_resolvers")
    def test_generate_issue_title(self, mock_prompt_resolvers):
        mock_prompt_resolvers.copywriting_support_request_title.return_value = "test prompt"

        with patch.object(self.service, "_UserSupportService__copywriter") as mock_llm:
            mock_llm.invoke.return_value = AIMessage(content = [
                {"type": "thinking", "thinking": "Hidden reasoning"},
                {"type": "text", "text": "Generated title"},
            ])
            # noinspection PyUnresolvedReferences
            title = self.service._UserSupportService__generate_issue_title("Test description")

        self.assertEqual(title, "Generated title")
        mock_llm.invoke.assert_called_once()

    @patch("features.support.user_support_service.UserSupportService._UserSupportService__generate_issue_description")
    @patch("features.support.user_support_service.UserSupportService._UserSupportService__generate_issue_title")
    @patch("requests.post")
    def test_execute_success(self, mock_post, mock_generate_title, mock_generate_description):
        mock_generate_description.return_value = "Test description"
        mock_generate_title.return_value = "Test title"
        mock_post.return_value.json.return_value = {"html_url": "https://example.com/issue/1"}
        mock_post.return_value.raise_for_status = Mock(spec = requests.Response)

        result = self.service.execute()

        self.assertEqual(result, "https://example.com/issue/1")
        mock_generate_description.assert_called_once()
        mock_generate_title.assert_called_once()
        mock_post.assert_called_once()

    @patch("features.support.user_support_service.UserSupportService._UserSupportService__generate_issue_description")
    @patch("features.support.user_support_service.UserSupportService._UserSupportService__generate_issue_title")
    @patch("requests.post")
    def test_execute_failure(self, mock_post, mock_generate_title, mock_generate_description):
        mock_generate_description.return_value = "Test description"
        mock_generate_title.return_value = "Test title"
        mock_post.return_value.raise_for_status.side_effect = Exception("API Error")

        with self.assertRaises(Exception):
            self.service.execute()

        mock_generate_description.assert_called_once()
        mock_generate_title.assert_called_once()
        mock_post.assert_called_once()
