from threading import Event
from typing import cast
from unittest import TestCase
from unittest.mock import Mock, patch

from fakes.fake_telegram_bot_api import FakeTelegramBotAPI
from fakes.fake_whatsapp_bot_api import FakeWhatsAppBotAPI
from stubs import domain
from util.di_utils import di_for_tests

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.chat.chat_progress_notifier import MAX_CYCLES, ChatProgressNotifier


class ChatProgressNotifierTest(TestCase):

    di: DI
    notifier: ChatProgressNotifier
    api: FakeTelegramBotAPI
    signal: Event
    thread: Mock
    now: float
    cycles: int
    cycle_limit: int

    def setUp(self):
        self.di = self.enterContext(di_for_tests())
        self.api = cast(FakeTelegramBotAPI, self.di.telegram_bot_api)
        self.di.inject_invoker_chat(domain.chat_config(external_id = "chat"))
        self.signal = Event()
        self.now = 0.0
        self.cycles = 0
        self.cycle_limit = 1
        # control only system scheduling; run the real target supplied to Thread
        self.thread = self.enterContext(patch("features.chat.chat_progress_notifier.Thread"))
        self.thread.return_value.is_alive.return_value = True
        self.enterContext(patch("features.chat.chat_progress_notifier.Event", return_value = self.signal))
        self.enterContext(patch.object(self.signal, "wait", side_effect = self.__advance_time))
        self.enterContext(patch("time.time", side_effect = lambda: self.now))
        self.notifier = self.di.chat_progress_notifier("message")
        self.addCleanup(self.notifier.stop)

    def __advance_time(self, timeout: float) -> bool:
        self.now += timeout
        self.cycles += 1
        if self.cycles >= self.cycle_limit:
            self.signal.set()
        return self.signal.is_set()

    def test_init_does_not_start_notifications(self):
        self.assertEqual(self.api.statuses, {})
        self.assertEqual(self.api.reactions, {})
        self.thread.assert_not_called()

    def test_start_is_idempotent_while_thread_is_running(self):
        self.notifier.start()
        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.thread.assert_called_once()
        self.thread.return_value.start.assert_called_once()
        self.assertEqual(self.api.statuses, {"chat": "typing"})

    def test_stop_clears_reaction_and_signals_thread(self):
        self.notifier.start()
        self.api.reactions[("chat", "message")] = "👀"

        self.notifier.stop()

        self.assertTrue(self.signal.is_set())
        self.thread.return_value.join.assert_called_once_with(timeout = 1)
        self.assertIsNone(self.api.reactions[("chat", "message")])

    def test_no_reactions_when_intervals_not_set(self):
        self.di.inject_invoker_chat(domain.chat_config(external_id = "chat", chat_type = ChatConfigDB.ChatType.background))
        notifier = self.di.chat_progress_notifier("message")
        self.addCleanup(notifier.stop)
        self.cycle_limit = 3

        notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.api.statuses, {})
        self.assertEqual(self.api.reactions, {})

    def test_whatsapp_fires_immediately(self):
        self.di.inject_invoker_chat(domain.chat_config(external_id = "chat", chat_type = ChatConfigDB.ChatType.whatsapp))
        notifier = self.di.chat_progress_notifier("message")
        self.addCleanup(notifier.stop)

        notifier.start()
        self.thread.call_args.kwargs["target"]()

        api = cast(FakeWhatsAppBotAPI, self.di.whatsapp_bot_api)
        self.assertEqual(api.reactions, {("chat", "message"): "👀"})

    def test_telegram_waits_for_initial_delay(self):
        self.cycle_limit = 3

        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.api.statuses, {"chat": "typing"})
        self.assertEqual(self.api.reactions, {})

    def test_telegram_fires_after_initial_delay(self):
        self.cycle_limit = 4

        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.api.reactions, {("chat", "message"): "👀"})

    def test_telegram_waits_full_interval_before_escalating(self):
        self.cycle_limit = 9

        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.api.reactions, {("chat", "message"): "👀"})

    def test_telegram_escalates_after_interval(self):
        self.cycle_limit = 10

        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.api.reactions, {("chat", "message"): "🫡"})

    def test_stops_after_maximum_cycles(self):
        self.cycle_limit = MAX_CYCLES + 1

        self.notifier.start()
        self.thread.call_args.kwargs["target"]()

        self.assertEqual(self.cycles, MAX_CYCLES)
        self.assertFalse(self.signal.is_set())
