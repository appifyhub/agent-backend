import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from db.model.chat_config import ChatConfigDB
from features.chat.chat_progress_notifier import ChatProgressNotifier
from features.chat.config.chat_config import ChatConfig
from features.integrations.platform_bot_sdk import PlatformBotSDK


class ChatProgressNotifierTest(unittest.TestCase):

    chat_config: ChatConfig
    message_id: str
    mock_di: Mock
    notifier: ChatProgressNotifier

    def setUp(self):
        self.chat_config = ChatConfig(
            chat_id = UUID(int = 1),
            external_id = "test_chat_id",
            language_iso_code = "en",
            language_name = "English",
            title = "Test Chat",
            is_private = True,
            reply_chance_percent = 100,
            chat_type = ChatConfigDB.ChatType.telegram,
        )
        self.message_id = "test_message_id"

        # Create mock DI with all necessary dependencies
        self.mock_di = Mock()
        # noinspection PyPropertyAccess
        self.mock_di.invoker_chat = self.chat_config
        self.mock_di.require_invoker_chat = MagicMock(return_value = self.chat_config)
        # noinspection PyPropertyAccess
        self.mock_di.platform_bot_sdk = Mock(return_value = Mock(spec = PlatformBotSDK))
        self.mock_di.require_invoker_chat_type = MagicMock(return_value = ChatConfigDB.ChatType.telegram)

        self.notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

    # noinspection PyUnresolvedReferences
    def test_init(self):
        self.assertEqual(self.notifier._ChatProgressNotifier__message_id, self.message_id)
        self.assertEqual(self.notifier._ChatProgressNotifier__di, self.mock_di)

    @patch("features.chat.chat_progress_notifier.Thread")
    def test_start(self, mock_thread):
        self.notifier.start()
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("features.chat.chat_progress_notifier.Thread")
    def test_stop(self, mock_thread):
        self.notifier.start()
        self.notifier.stop()
        mock_thread.return_value.join.assert_called_once_with(timeout = 1)

    @patch("features.chat.chat_progress_notifier.time.time")
    def test_send_reaction(self, mock_time):
        mock_time.return_value = 100
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk
        # noinspection PyUnresolvedReferences
        self.notifier._ChatProgressNotifier__send_reaction()
        mock_platform_sdk.set_reaction.assert_called_once()

    @patch("features.chat.chat_progress_notifier.resolve_reaction_timing")
    @patch("features.chat.chat_progress_notifier.time.time")
    def test_no_reactions_when_intervals_not_set(self, mock_time, mock_resolve_timing):
        mock_resolve_timing.return_value = None
        mock_time.return_value = 0.0
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk

        notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

        # Simulate a few cycles
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal = Mock()
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.is_set.side_effect = [False, False, False, True]
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.wait = Mock()

        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__run()

        # Should only set typing action, never send reactions
        mock_platform_sdk.set_chat_action.assert_called()
        mock_platform_sdk.set_reaction.assert_not_called()

    @patch("features.chat.chat_progress_notifier.resolve_reaction_timing")
    @patch("features.chat.chat_progress_notifier.time.time")
    def test_fires_immediately_when_initial_delay_zero(self, mock_time, mock_resolve_timing):
        mock_resolve_timing.return_value = (0, 15)  # WhatsApp-like: 0s initial, 15s interval
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk

        # Time progression: start at 0, then advance by small increments
        mock_time.side_effect = [0.0, 0.0, 0.1, 0.2]

        notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

        # Simulate one cycle
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal = Mock()
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.is_set.side_effect = [False, True]
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.wait = Mock()

        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__run()

        # Should fire reaction immediately (elapsed = 7 at start due to offset)
        mock_platform_sdk.set_reaction.assert_called()

    @patch("features.chat.chat_progress_notifier.resolve_reaction_timing")
    @patch("features.chat.chat_progress_notifier.time.time")
    def test_fires_after_initial_delay(self, mock_time, mock_resolve_timing):
        mock_resolve_timing.return_value = (15, 30)  # Telegram-like: 15s initial, 30s interval
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk

        # Time progression: loop iterations
        # 5.0: first cycle, initializes to 5, elapsed=0, should NOT fire
        # 11.0: second cycle, elapsed=6, should NOT fire (need 15s)
        # 16.0: third cycle, elapsed=11, should NOT fire (need 15s)
        # 21.0: fourth cycle, elapsed=16, should fire
        mock_time.side_effect = [5.0, 11.0, 16.0, 21.0]

        notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

        # Simulate four cycles
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal = Mock()
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.is_set.side_effect = [False, False, False, False, True]
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.wait = Mock()

        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__run()

        # First cycle at t=5: init to 5, elapsed=0, should NOT fire
        # Second cycle at t=11: elapsed=6, should NOT fire (need 15s)
        # Third cycle at t=16: elapsed=11, should NOT fire (need 15s)
        # Fourth cycle at t=21: elapsed=16, should fire
        self.assertEqual(mock_platform_sdk.set_reaction.call_count, 1)

    @patch("features.chat.chat_progress_notifier.resolve_reaction_timing")
    @patch("features.chat.chat_progress_notifier.time.time")
    def test_fires_when_initial_delay_greater_than_interval(self, mock_time, mock_resolve_timing):
        mock_resolve_timing.return_value = (15, 7)  # delay=15s, interval=7s
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk

        # Time progression:
        # 0: start, elapsed=0, should NOT fire (need 15s)
        # 10: elapsed=10, should NOT fire (need 15s)
        # 15: elapsed=15, should fire (first reaction)
        # 20: elapsed=5 from last, should NOT fire (need 7s)
        # 22: elapsed=7 from last, should fire (second reaction)
        mock_time.side_effect = [0.0, 10.0, 15.0, 20.0, 22.0]

        notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

        # Simulate five cycles
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal = Mock()
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.is_set.side_effect = [False, False, False, False, False, True]
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.wait = Mock()

        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__run()

        # Should fire twice: once at t=15 (initial), once at t=22 (interval)
        self.assertEqual(mock_platform_sdk.set_reaction.call_count, 2)

    @patch("features.chat.chat_progress_notifier.resolve_reaction_timing")
    @patch("features.chat.chat_progress_notifier.time.time")
    def test_fires_when_initial_delay_less_than_interval(self, mock_time, mock_resolve_timing):
        mock_resolve_timing.return_value = (3, 7)  # delay=3s, interval=7s
        mock_platform_sdk = Mock(spec = PlatformBotSDK)
        self.mock_di.platform_bot_sdk.return_value = mock_platform_sdk

        # Time progression:
        # 0: start, elapsed=0, should NOT fire (need 3s)
        # 3: elapsed=3, should fire (first reaction)
        # 8: elapsed=5 from last, should NOT fire (need 7s)
        # 10: elapsed=7 from last, should fire (second reaction)
        mock_time.side_effect = [0.0, 3.0, 8.0, 10.0]

        notifier = ChatProgressNotifier(
            message_id = self.message_id,
            di = self.mock_di,
            auto_start = False,
        )

        # Simulate four cycles
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal = Mock()
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.is_set.side_effect = [False, False, False, False, True]
        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__signal.wait = Mock()

        # noinspection PyUnresolvedReferences
        notifier._ChatProgressNotifier__run()

        # Should fire twice: once at t=3 (initial), once at t=10 (interval)
        self.assertEqual(mock_platform_sdk.set_reaction.call_count, 2)
