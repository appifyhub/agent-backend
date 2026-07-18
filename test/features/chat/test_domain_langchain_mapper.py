import unittest
from datetime import date
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage

from db.model.chat_config import ChatConfigDB
from features.chat.config.chat_config import ChatConfig
from features.chat.domain_langchain_mapper import DomainLangchainMapper, _split_preserving_blocks
from features.chat.message.chat_message import ChatMessage
from features.integrations.integrations import resolve_agent_user
from features.prompting.prompt_library import CHAT_MESSAGE_DELIMITER
from features.users.user import User


class DomainLangchainMapperTest(unittest.TestCase):

    agent_user: User
    chat: ChatConfig
    mapper: DomainLangchainMapper

    def setUp(self):
        self.agent_user = resolve_agent_user(ChatConfigDB.ChatType.telegram)
        self.chat = ChatConfig(
            chat_id = UUID(int = 3),
            external_id = "test_chat",
            is_private = True,
            reply_chance_percent = 100,
            chat_type = ChatConfigDB.ChatType.telegram,
            release_notifications = ChatConfigDB.ReleaseNotifications.all,
            media_mode = ChatConfigDB.MediaMode.photo,
        )
        self.mapper = DomainLangchainMapper()

    def test_map_to_langchain_with_author(self):
        author = User(
            id = UUID(int = 1),
            created_at = date.today(),
            telegram_user_id = 12345,
            telegram_username = "john_doe",
            full_name = "John Doe",
        )
        message = ChatMessage(chat_id = UUID(int = 1), message_id = "m1", text = "Hello, how are you?")
        expected_output = HumanMessage("@john_doe [John Doe]:\nHello, how are you?")
        self.assertEqual(self.mapper.map_to_langchain(author, message, ChatConfigDB.ChatType.telegram), expected_output)

    def test_map_to_langchain_with_slim_author(self):
        author = User(id = UUID(int = 1), created_at = date.today(), telegram_user_id = 12345)
        message = ChatMessage(chat_id = UUID(int = 1), message_id = "m1", text = "Test message")
        expected_output = HumanMessage("#UID-12345:\nTest message")
        self.assertEqual(self.mapper.map_to_langchain(author, message, ChatConfigDB.ChatType.telegram), expected_output)

    def test_map_to_langchain_with_ai_author(self):
        ai_author = User(
            id = UUID(int = 2),
            created_at = date.today(),
            telegram_username = self.agent_user.telegram_username,
            telegram_user_id = self.agent_user.telegram_user_id,
            full_name = self.agent_user.full_name,
        )
        message = ChatMessage(chat_id = UUID(int = 2), message_id = "m2", text = "I'm an AI assistant.")
        expected_output = AIMessage("I'm an AI assistant.")
        self.assertEqual(self.mapper.map_to_langchain(ai_author, message, ChatConfigDB.ChatType.telegram), expected_output)

    def test_map_to_langchain_no_author(self):
        message = ChatMessage(chat_id = UUID(int = 1), message_id = "m1", text = "Test message")
        expected_output = AIMessage("Test message")
        self.assertEqual(self.mapper.map_to_langchain(None, message, ChatConfigDB.ChatType.telegram), expected_output)

    def test_map_bot_message_to_storage_single_message(self):
        message = AIMessage(content = "Test message")
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Test message")
        self.assertEqual(result[0].chat_id, self.chat.chat_id)
        self.assertEqual(result[0].author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_multiple_messages(self):
        message = AIMessage(content = f"Message 1{CHAT_MESSAGE_DELIMITER}Message 2{CHAT_MESSAGE_DELIMITER}Message 3")
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].text, "Message 1")
        self.assertEqual(result[1].text, "Message 2")
        self.assertEqual(result[2].text, "Message 3")
        for message in result:
            self.assertEqual(message.chat_id, self.chat.chat_id)
            self.assertEqual(message.author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_empty_message(self):
        message = AIMessage(content = "")
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 0)

    def test_map_bot_message_to_storage_list_of_strings(self):
        message = AIMessage(content = ["Message 1", "Message 2", "Message 3"])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].text, "Message 1")
        self.assertEqual(result[1].text, "Message 2")
        self.assertEqual(result[2].text, "Message 3")
        for message in result:
            self.assertEqual(message.chat_id, self.chat.chat_id)
            self.assertEqual(message.author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_list_of_dicts(self):
        message = AIMessage(content = [{"name": "Mike", "city": "Valencia"}, {"name": "Dirk"}])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "name: Mike\ncity: Valencia")
        self.assertEqual(result[1].text, "name: Dirk")
        for message in result:
            self.assertEqual(message.chat_id, self.chat.chat_id)
            self.assertEqual(message.author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_content_block_format(self):
        # Test Gemini 3.0 format: list of content blocks with 'text' key
        message = AIMessage(content = [{"type": "text", "text": "Hello, world!", "extras": {"signature": "abc123"}}])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Hello, world!")
        self.assertEqual(result[0].chat_id, self.chat.chat_id)
        self.assertEqual(result[0].author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_content_block_format_multiple(self):
        # Test multiple content blocks with 'text' key
        message = AIMessage(
            content = [
                {"type": "text", "text": "First message", "extras": {}},
                {"type": "text", "text": "Second message", "extras": {"signature": "xyz"}},
            ],
        )
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "First message")
        self.assertEqual(result[1].text, "Second message")
        for message in result:
            self.assertEqual(message.chat_id, self.chat.chat_id)
            self.assertEqual(message.author_id, self.agent_user.id)

    def test_map_bot_message_to_storage_message_id_uniqueness(self):
        message = AIMessage(content = "Test message")
        result1 = self.mapper.map_bot_message_to_storage(self.chat, message)
        result2 = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertNotEqual(result1[0].message_id, result2[0].message_id)

    def test_map_bot_message_to_storage_preserves_code_block(self):
        content = (
            f"Here's code:{CHAT_MESSAGE_DELIMITER}```python\n"
            f"x = 1{CHAT_MESSAGE_DELIMITER}y = 2\n"
            f"```{CHAT_MESSAGE_DELIMITER}Done!"
        )
        message = AIMessage(content = content)
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].text, "Here's code:")
        self.assertEqual(result[1].text, f"```python\nx = 1{CHAT_MESSAGE_DELIMITER}y = 2\n```")
        self.assertEqual(result[2].text, "Done!")

    def test_map_bot_message_to_storage_preserves_list(self):
        D = CHAT_MESSAGE_DELIMITER
        content = f"Steps:{D}- First{D}- Second{D}- Third{D}That's it."
        message = AIMessage(content = content)
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].text, "Steps:")
        self.assertEqual(result[1].text, f"- First{CHAT_MESSAGE_DELIMITER}- Second{CHAT_MESSAGE_DELIMITER}- Third")
        self.assertEqual(result[2].text, "That's it.")

    def test_map_bot_message_to_storage_closes_unclosed_code_block(self):
        content = f"Here:{CHAT_MESSAGE_DELIMITER}```python\nprint('hi')"
        message = AIMessage(content = content)
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "Here:")
        self.assertEqual(result[1].text, "```python\nprint('hi')\n```")

    def test_map_bot_message_to_storage_formats_thinking_block(self):
        message = AIMessage(content = [
            {"type": "thinking", "thinking": "some reasoning", "signature": "EqwH..."},
            {"type": "text", "text": "Hello!"},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "💭\n> some reasoning")
        self.assertEqual(result[1].text, "Hello!")

    def test_map_bot_message_to_storage_formats_multiline_thinking_block(self):
        message = AIMessage(content = [
            {"type": "thinking", "thinking": "line one\nline two\nline three", "signature": "EqwH..."},
            {"type": "text", "text": "Answer."},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].text, "💭\n> line one\n> line two\n> line three")
        self.assertEqual(result[1].text, "Answer.")

    def test_map_bot_message_to_storage_skips_empty_thinking_block(self):
        message = AIMessage(content = [
            {"type": "thinking", "thinking": "", "signature": "EqwH..."},
            {"type": "text", "text": "Hello!"},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Hello!")

    def test_map_bot_message_to_storage_only_thinking_block(self):
        message = AIMessage(content = [
            {"type": "thinking", "thinking": "some reasoning", "signature": "EqwH..."},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "💭\n> some reasoning")

    def test_map_bot_message_to_storage_only_empty_thinking_block(self):
        message = AIMessage(content = [
            {"type": "thinking", "thinking": "", "signature": "EqwH..."},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 0)

    def test_map_bot_message_to_storage_skips_redacted_thinking_block(self):
        message = AIMessage(content = [
            {"type": "redacted_thinking", "data": "opaque-data"},
            {"type": "text", "text": "Hello!"},
        ])
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "Hello!")

    def test_map_bot_message_to_storage_closes_unclosed_tilde_fence(self):
        content = "~~~\nsome code"
        message = AIMessage(content = content)
        result = self.mapper.map_bot_message_to_storage(self.chat, message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "~~~\nsome code\n~~~")


class SplitPreservingBlocksTest(unittest.TestCase):

    D = CHAT_MESSAGE_DELIMITER

    def test_plain_split(self):
        result = _split_preserving_blocks(f"A{self.D}B{self.D}C", self.D)
        self.assertEqual(result, ["A", "B", "C"])

    def test_no_delimiter(self):
        result = _split_preserving_blocks("Just one message", self.D)
        self.assertEqual(result, ["Just one message"])

    def test_empty_string(self):
        result = _split_preserving_blocks("", self.D)
        self.assertEqual(result, [""])

    def test_code_block_with_blank_lines(self):
        content = f"Intro{self.D}```\nline1{self.D}line2\n```{self.D}Outro"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Intro", f"```\nline1{self.D}line2\n```", "Outro"])

    def test_code_block_with_language(self):
        content = f"Check this:{self.D}```python\ndef foo():\n    pass{self.D}def bar():\n    pass\n```{self.D}Nice."
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, [
            "Check this:",
            f"```python\ndef foo():\n    pass{self.D}def bar():\n    pass\n```",
            "Nice.",
        ])

    def test_tilde_code_fence(self):
        content = f"Start{self.D}~~~\ncode{self.D}more\n~~~{self.D}End"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Start", f"~~~\ncode{self.D}more\n~~~", "End"])

    def test_unordered_list_dash(self):
        content = f"Items:{self.D}- A{self.D}- B{self.D}- C{self.D}Done"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Items:", f"- A{self.D}- B{self.D}- C", "Done"])

    def test_unordered_list_asterisk(self):
        content = f"Items:{self.D}* A{self.D}* B{self.D}Done"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Items:", f"* A{self.D}* B", "Done"])

    def test_ordered_list(self):
        content = f"Steps:{self.D}1. First{self.D}2. Second{self.D}3. Third{self.D}End"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Steps:", f"1. First{self.D}2. Second{self.D}3. Third", "End"])

    def test_ordered_list_with_paren(self):
        content = f"Steps:{self.D}1) First{self.D}2) Second{self.D}End"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Steps:", f"1) First{self.D}2) Second", "End"])

    def test_multiline_list_items(self):
        content = f"List:{self.D}- Item one\n  with detail{self.D}- Item two{self.D}End"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["List:", f"- Item one\n  with detail{self.D}- Item two", "End"])

    def test_list_not_merged_with_intro(self):
        content = f"Here's the plan:{self.D}- Step one{self.D}- Step two"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Here's the plan:", f"- Step one{self.D}- Step two"])

    def test_code_block_then_list(self):
        content = f"Code:{self.D}```\na{self.D}b\n```{self.D}List:{self.D}- X{self.D}- Y{self.D}Bye"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, [
            "Code:",
            f"```\na{self.D}b\n```",
            "List:",
            f"- X{self.D}- Y",
            "Bye",
        ])

    def test_unclosed_code_block_keeps_rest_together(self):
        content = f"Oops:{self.D}```\ncode{self.D}more code{self.D}still going"
        result = _split_preserving_blocks(content, self.D)
        self.assertEqual(result, ["Oops:", f"```\ncode{self.D}more code{self.D}still going"])
