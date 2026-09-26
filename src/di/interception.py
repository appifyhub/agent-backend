from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from di.di import DI


@dataclass(frozen = True)
class DependencyRequest:

    di: DI
    factory: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    @property
    def arguments(self) -> dict[str, Any]:
        bound = signature(self.factory).bind(self.di, *self.args, **self.kwargs)
        bound.apply_defaults()
        return {name: value for name, value in bound.arguments.items() if name != "self"}


type DIInterceptor = Callable[[DependencyRequest], object | None]


def dependency[T](cache: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Allow an optional DI interceptor to replace a dependency before construction.

    The interceptor receives the current DI, the original factory (including its
    return annotation), and the invocation arguments. `DependencyRequest.arguments`
    binds positional and keyword arguments and fills in parameter defaults.

    Returning `None` means the request is unhandled, so the original factory runs.
    Any other result is used as the replacement. Interceptor exceptions propagate
    without falling back to production construction.

    When cache names a DI attribute, an existing instance is reused and replacements
    are stored in that attribute. Without a cache, each call consults the interceptor.
    Without an interceptor, the original factory runs directly. Type matching and
    fake registration are handled by test support.
    """
    def decorate(factory: Callable[..., T]) -> Callable[..., T]:
        @wraps(factory)
        def resolve(di: DI, *args: Any, **kwargs: Any) -> T:
            if di._interceptor is None:
                return factory(di, *args, **kwargs)
            if cache is not None:
                cached = getattr(di, cache)
                if cached is not None:
                    return cast(T, cached)
            result = di._interceptor(DependencyRequest(di, factory, args, kwargs))
            if result is None:
                return factory(di, *args, **kwargs)
            if cache is not None:
                setattr(di, cache, result)
            return cast(T, result)

        return resolve

    return decorate
