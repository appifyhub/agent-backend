import os
from enum import Enum

import requests
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from di.di import DI
from features.external_tools.configured_tool import ConfiguredTool
from features.external_tools.external_tool import ToolType
from features.integrations import prompt_resolvers
from features.integrations.integrations import resolve_external_handle, resolve_user_link
from util import log
from util.config import config
from util.functions import parse_ai_message_content

GITHUB_BASE_URL = "https://api.github.com"


class UserSupportService:

    TOOL_TYPE: ToolType = ToolType.copywriting

    class RequestType(Enum):
        bug = "bug_report"
        request = "request_support"
        feature = "feature_request"

    __user_input: str
    __github_author: str | None
    __include_platform_handle: bool
    __include_full_name: bool
    __request_type: RequestType
    __copywriter: BaseChatModel
    __di: DI

    def __init__(
        self,
        user_input: str,
        github_author: str | None,
        include_platform_handle: bool,
        include_full_name: bool,
        request_type_str: str | None,
        configured_tool: ConfiguredTool,
        di: DI,
    ):
        self.__user_input = user_input
        self.__github_author = github_author
        self.__include_platform_handle = include_platform_handle
        self.__include_full_name = include_full_name
        self.__request_type = self.__resolve_request_type(request_type_str)
        self.__copywriter = di.chat_langchain_model(configured_tool)
        self.__di = di

    def __resolve_request_type(self, request_type_str: str | None) -> RequestType:
        request_type_str = request_type_str.lower() if request_type_str else None
        log.d(f"Resolving support request type: '{request_type_str}'")
        for request_type in self.RequestType:
            if request_type.name == request_type_str:
                return request_type
        default = UserSupportService.RequestType.request
        log.w(f"Request type not found, defaulting to {default}")
        return default

    def __load_template(self) -> str:
        log.t(f"Loading issue template for: {self.__request_type.value}")
        path = os.path.join(config.issue_templates_abs_path, f"{self.__request_type.value}.yaml")
        with open(path, "r") as file:
            return file.read()

    def __generate_issue_description(self) -> str:
        log.t("Generating issue description...")
        # prepare the system prompt
        template_contents = self.__load_template()
        chat_type = self.__di.require_invoker_chat_type()
        system_prompt = prompt_resolvers.copywriting_support_request_description(
            chat_type, self.__request_type.name, template_contents,
        )

        # prepare the report information
        platform_handle = resolve_external_handle(self.__di.invoker, chat_type)
        user_info_parts = []
        if self.__include_platform_handle and platform_handle:
            user_link = resolve_user_link(self.__di.invoker, chat_type)
            if user_link:
                user_info_parts.append(f"Platform user: {chat_type.value}/{user_link}")
            else:
                user_info_parts.append(f"Platform handle: {platform_handle}")
        if self.__github_author:
            user_info_parts.append(f"GitHub author: @{self.__github_author}")
        if self.__include_full_name and self.__di.invoker.full_name:
            user_info_parts.append(f"Full name: {self.__di.invoker.full_name}")
        if not user_info_parts:
            user_info_parts.append(f"User ID: `{self.__di.invoker.id.hex}`")
        user_info = "\n".join(user_info_parts)
        message = f"Reporter:\n{user_info}\n\nRaw reporter input:\n```\n{self.__user_input}\n```\n"

        # generate the issue description
        response = self.__copywriter.invoke([SystemMessage(system_prompt), HumanMessage(message)])
        return parse_ai_message_content(response)

    def __generate_issue_title(self, description: str) -> str:
        log.t("Generating issue title")
        system_prompt = prompt_resolvers.copywriting_support_request_title(self.__di.require_invoker_chat_type())
        message = f"Issue description:\n```\n{description}\n```\n\nIssue type: '{self.__request_type.name}'"
        response = self.__copywriter.invoke([SystemMessage(system_prompt), HumanMessage(message)])
        return parse_ai_message_content(response)

    def execute(self) -> str:
        log.t("Creating user support request / issue")

        issue_description = self.__generate_issue_description()
        issue_title = self.__generate_issue_title(issue_description)
        github_token = config.github_issues_token.get_secret_value()
        response = requests.post(
            f"{GITHUB_BASE_URL}/repos/{config.github_issues_repo}/issues",
            json = {
                "title": issue_title,
                "body": issue_description,
                "labels": [self.__request_type.name.capitalize()],
            },
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout = float(config.web_timeout_s),
        )
        response.raise_for_status()

        issue = response.json()
        issue_url = str(issue["html_url"])
        log.i(f"Issue created successfully. Issue URL: {issue_url}")

        shortener = self.__di.url_shortener(issue_url)
        return shortener.execute()
