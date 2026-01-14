import asyncio
import inspect
from typing import Any


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    """Lightweight asyncio support without relying on external plugins."""
    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    if pyfuncitem.get_closest_marker("asyncio") is None:
        return None

    coro = test_function(**pyfuncitem.funcargs)
    asyncio.run(coro)
    return True
