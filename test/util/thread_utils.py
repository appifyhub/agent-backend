from collections.abc import Callable
from contextvars import copy_context
from threading import Event, Thread
from typing import Any

from util.error_codes import DI_DEPENDENCY_NOT_MET
from util.errors import InternalError


class BackgroundThreads:
    """Run real workers in the test context and finish them before resource cleanup.

    Workers wait until finish() so tests can inspect the immediate acknowledgement
    independently of delivery. Each worker inherits the test interceptor, never
    the parent DI or its session.
    """

    threads: list[Thread]
    _ready: Event

    def __init__(self):
        self.threads = []
        self._ready = Event()

    def create(self, *, target: Callable, kwargs: dict[str, Any], **options: Any) -> Thread:
        context = copy_context()

        def run() -> None:
            self._ready.wait()
            context.run(target, **kwargs)

        thread = Thread(target = run, **options)
        self.threads.append(thread)
        return thread

    def finish(self) -> None:
        self._ready.set()
        for thread in self.threads:
            if thread.ident is None:
                continue
            thread.join(timeout = 10)
            if thread.is_alive():
                raise InternalError("Background test worker did not finish", DI_DEPENDENCY_NOT_MET)
