from pathlib import Path
from typing import cast
from unittest import TestCase

import stubs
from fakes.fake_chat_model import FakeChatModel
from fakes.fake_http_client import FakeHTTPClient
from fakes.fake_url_shortener import FakeUrlShortener
from requests import HTTPError
from util.di_utils import di_for_tests

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.external_tools.intelligence_presets import default_tool_for
from features.support.user_support_service import UserSupportService
from util.config import config


class UserSupportServiceTest(TestCase):

    di: DI
    service: UserSupportService
    tool: ConfiguredTool
    model: FakeChatModel
    shortener: FakeUrlShortener
    http: FakeHTTPClient
    github_url: str

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.di.inject_invoker(self.di.user_repo.save(stubs.domain.user()))
        self.di.inject_invoker_chat(self.di.chat_config_repo.save(stubs.domain.chat_config()))
        self.tool = self.di.tool_choice_resolver.require_tool(ToolType.copywriting, default_tool_for(ToolType.copywriting))
        self.model = cast(FakeChatModel, self.di.base_chat_langchain_model(self.tool))
        self.service = self.di.user_support_service(
            user_input = "Test input",
            github_author = "test_github",
            include_platform_handle = True,
            include_full_name = True,
            request_type_str = "bug",
            configured_tool = self.tool,
        )
        issue = stubs.external.github_issue_response()
        self.shortener = cast(FakeUrlShortener, self.di.url_shortener(issue["html_url"]))
        self.shortener.short_url = "https://example.com/short-issue"
        self.github_url = f"https://api.github.com/repos/{config.github_issues_repo}/issues"
        self.http = cast(FakeHTTPClient, self.di.http_client())
        self.http.post_responses[self.github_url].append(stubs.external.http_json_response(issue, status_code = 201))

    def test_resolve_request_type(self):
        self.http.post_responses[self.github_url].append(stubs.external.http_json_response(
            stubs.external.github_issue_response(), status_code = 201,
        ))
        for request_type, label in (("bug", "Bug"), ("invalid_type", "Request")):
            with self.subTest(request_type = request_type):
                self.model.responses.extend([
                    stubs.external.ai_message(content = "Test description"),
                    stubs.external.ai_message(content = "Test title"),
                ])
                service = self.di.user_support_service(
                    user_input = "Test input",
                    github_author = "test_github",
                    include_platform_handle = True,
                    include_full_name = True,
                    request_type_str = request_type,
                    configured_tool = self.tool,
                )

                service.execute()

                self.assertEqual(self.http.post_requests[-1][1]["json"]["labels"], [label])

    def test_load_template(self):
        self.model.responses.extend([
            stubs.external.ai_message(content = "Test description"),
            stubs.external.ai_message(content = "Test title"),
        ])
        template = Path(config.issue_templates_abs_path, "bug_report.yaml").read_text()

        self.service.execute()

        self.assertIn(template, self.model.prompts[0][0].content)

    def test_generate_issue_description(self):
        self.model.responses.extend([
            stubs.external.ai_message(content = [
                {"type": "thinking", "thinking": "Hidden reasoning"},
                {"type": "text", "text": "Generated description"},
            ]),
            stubs.external.ai_message(content = "Test title"),
        ])

        self.service.execute()

        self.assertEqual(self.http.post_requests[-1][1]["json"]["body"], "Generated description")
        reporter = self.model.prompts[0][-1].content
        self.assertIn("Test input", reporter)
        self.assertIn("GitHub author: @test_github", reporter)
        self.assertIn("Full name: Mark Johnson", reporter)
        self.assertIn("Platform user: telegram/", reporter)
        self.assertIn("mark_johnson", reporter)
        self.assertIn("Generated description", self.model.prompts[1][-1].content)
        self.assertNotIn("Hidden reasoning", self.model.prompts[1][-1].content)

    def test_generate_issue_title(self):
        self.model.responses.extend([
            stubs.external.ai_message(content = "Test description"),
            stubs.external.ai_message(content = [
                {"type": "thinking", "thinking": "Hidden reasoning"},
                {"type": "text", "text": "Generated title"},
            ]),
        ])

        self.service.execute()

        self.assertEqual(self.http.post_requests[-1][1]["json"]["title"], "Generated title")
        self.assertIn("Test description", self.model.prompts[1][-1].content)
        self.assertIn("Issue type: 'bug'", self.model.prompts[1][-1].content)

    def test_execute_success(self):
        self.model.responses.extend([
            stubs.external.ai_message(content = "Test description"),
            stubs.external.ai_message(content = "Test title"),
        ])

        result = self.service.execute()

        self.assertEqual(result, "https://example.com/short-issue")
        self.assertEqual(self.http.post_requests[-1][1]["json"], {
            "title": "Test title",
            "body": "Test description",
            "labels": ["Bug"],
        })
        self.assertEqual(len(self.http.post_requests), 1)
        self.assertEqual(self.http.post_requests[0][0], self.github_url)
        self.assertEqual(self.shortener.executions, 1)

    def test_execute_failure(self):
        self.model.responses.extend([
            stubs.external.ai_message(content = "Test description"),
            stubs.external.ai_message(content = "Test title"),
        ])
        self.http.post_responses[self.github_url].clear()
        self.http.post_responses[self.github_url].append(stubs.external.http_response(status_code = 503))

        with self.assertRaises(HTTPError) as raised:
            self.service.execute()

        self.assertEqual(raised.exception.response.status_code, 503)
        self.assertEqual(self.shortener.executions, 0)
