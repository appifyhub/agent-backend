import random
import time
from threading import Event, Lock, Thread
from typing import Literal

from db.model.chat_config import ChatConfigDB
from di.di import DI
from features.integrations.integration_config import TELEGRAM_REACTIONS, WHATSAPP_REACTIONS
from features.integrations.integrations import resolve_reaction_timing
from util import log

DEFAULT_REACTION_INTERVAL_S = 60
TYPING_STATUS_INTERVAL_S = 5  # set by Telegram API for auto-clearing
MAX_CYCLES = 10

# subset of features.integrations.integration_config reactions
# sorted by intensity (later ones emote more about the delay)
ESCALATING_REACTIONS = [
    "👀", "🫡", "👨‍💻", "😴", "🔥", "🤔", "🤨",
    "😐", "🥱", "🥴", "😨", "😱", "🤯", "😢",
    "😭", "🙈", "💩", "💅", "⚡",
]


class ChatProgressNotifier:

    __message_id: str
    __initial_delay_s: int | None
    __reaction_interval_s: int | None
    __start_time: float | None
    __last_reaction_time: float | None
    __next_reaction_index: int
    __total_cycles: int
    __lock: Lock
    __thread: Thread | None
    __signal: Event
    __di: DI

    def __init__(
        self,
        message_id: str,
        di: DI,
        auto_start: bool = False,
    ):
        self.__di = di
        self.__message_id = message_id
        self.__start_time = None
        self.__last_reaction_time = None
        self.__next_reaction_index = 0
        self.__total_cycles = 0
        self.__thread = None
        self.__lock = Lock()
        self.__signal = Event()
        resolved_timing = resolve_reaction_timing(self.__di.require_invoker_chat_type())
        if resolved_timing is None:
            self.__initial_delay_s = None
            self.__reaction_interval_s = None
        else:
            # both are always set together or both are None
            self.__initial_delay_s, self.__reaction_interval_s = resolved_timing
        if auto_start:
            self.start()

    def start(self):
        log.t("Acquiring start lock...")
        if self.__thread and self.__thread.is_alive():
            log.d(f"  Thread {self.__thread.name} is already running (before lock)")
            return
        with self.__lock:
            log.t("  Acquired")
            if self.__thread and self.__thread.is_alive():
                log.d(f"  Thread {self.__thread.name} is already running (after lock)")
                return
            log.t("  Starting a new thread...")
            self.__signal.clear()
            thread_name = f"chat-progress-notifier-{random.randint(1000, 9999)}"
            self.__thread = Thread(name = thread_name, target = self.__run, daemon = True)
            self.__thread.start()  # fire and forget
            log.t(f"  Started thread {thread_name}")

    def stop(self):
        log.t("Acquiring stop lock...")
        if not self.__thread:
            log.t("  No thread running (before lock)")
            return
        with self.__lock:
            log.t("  Acquired")
            log.t(f"  Stopping thread {self.__thread.name}...")
            self.__signal.set()
            if not self.__thread:
                log.t("  No thread running (after lock)")
                return
            self.__thread.join(timeout = 1)  # wait for up to 1 second and proceed anyway
            if self.__thread.is_alive():
                log.t("  Thread did not stop in time, proceeding...")
                self.__total_cycles = MAX_CYCLES
            log.t(f"  Stopped thread {self.__thread.name}")
        # noinspection TryExceptPass
        # remove the stale reaction (sometimes fails due to API race condition but doesn't matter)
        try:
            platform_sdk = self.__di.platform_bot_sdk()
            platform_sdk.set_reaction(str(self.__di.require_invoker_chat().external_id), self.__message_id, None)
        except:  # noqa: E722
            pass

    def __run(self):
        # both interval and delay are always set together, or both are None
        are_intervals_set = self.__reaction_interval_s is not None and self.__initial_delay_s is not None

        while not self.__signal.is_set() and self.__total_cycles < MAX_CYCLES:
            current_time_s = time.time()
            if self.__start_time is None:
                self.__start_time = current_time_s

            # let's try to notify with a reaction
            if are_intervals_set:
                assert self.__reaction_interval_s is not None  # linter is stupid
                assert self.__initial_delay_s is not None  # linter is stupid

                if self.__last_reaction_time is None:
                    # we haven't reacted yet, so check initial delay
                    elapsed_time_s = current_time_s - self.__start_time
                    if elapsed_time_s >= self.__initial_delay_s:
                        self.__send_reaction()
                        self.__last_reaction_time = current_time_s
                else:
                    # we have reacted before, so check interval
                    elapsed_time_s = current_time_s - self.__last_reaction_time
                    if elapsed_time_s >= self.__reaction_interval_s:
                        self.__send_reaction()
                        self.__last_reaction_time = current_time_s

            # always notify the typing status because it resets automatically, and wait
            self.__set_chat_action("typing")
            self.__total_cycles += 1
            self.__signal.wait(TYPING_STATUS_INTERVAL_S)

    def __set_chat_action(self, action: Literal["typing", "upload_photo"]):
        log.t(f"Setting \"{action}\" action")
        try:
            invoker_chat = self.__di.require_invoker_chat()
            platform_sdk = self.__di.platform_bot_sdk()
            platform_sdk.set_chat_action(str(invoker_chat.external_id), action)
        except Exception as e:
            log.w(f"Failed to set \"{action}\" action", e)

    def __send_reaction(self):
        log.t("Time for a reaction update")
        try:
            invoker_chat = self.__di.require_invoker_chat()
            # use platform-appropriate reactions
            available_reactions = self.__get_available_reactions()
            next_reaction = available_reactions[self.__next_reaction_index]
            self.__next_reaction_index = (self.__next_reaction_index + 1) % len(available_reactions)
            platform_sdk = self.__di.platform_bot_sdk()
            platform_sdk.set_reaction(str(invoker_chat.external_id), self.__message_id, next_reaction)
        except Exception as e:
            log.w(f"Failed to send reaction: {e}")

    def __get_available_reactions(self) -> list[str]:
        match self.__di.require_invoker_chat_type():
            case ChatConfigDB.ChatType.telegram:
                reactions = TELEGRAM_REACTIONS
            case ChatConfigDB.ChatType.whatsapp:
                reactions = WHATSAPP_REACTIONS
            case _:
                reactions = ESCALATING_REACTIONS
        # filter to only include escalating reactions that exist in the platform's reactions
        return [r for r in ESCALATING_REACTIONS if r in reactions]
