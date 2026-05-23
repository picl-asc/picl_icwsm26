"""Single-worker-thread dispatcher for Jupyter / IPython compatibility.

Playwright's sync API refuses to start inside an asyncio event loop, which
is exactly the situation Jupyter and IPython kernels create. 

To fix the issue, it used a single dedicated worker thread that owns all Playwright objects.

When the public facade function is called from inside an asyncio loop, it
gets routed onto the worker. Because the worker thread has no running
asyncio loop, Playwright sync works there. Subsequent calls reuse the same
worker so the browser session is persistent.

Outside Jupyter (no running event loop), the dispatcher is transparent —
calls go through directly with no extra threading.
"""
from __future__ import annotations

import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_EXECUTOR: ThreadPoolExecutor | None = None
_LOCK = threading.Lock()
# Cached decision: "jupyter" if the FIRST @jupyter_safe call detected a
# running asyncio loop (route to worker), "plain" otherwise (call directly).
# We cache because once Playwright sync starts, IT creates an asyncio loop
# that asyncio.get_running_loop() can see, and re-checking would flip us to
# "jupyter" mid-session, dispatching subsequent calls to a different thread
# than the one that owns the Playwright page → greenlet error.
_MODE: str | None = None


def _detect_mode() -> str:
    """Return 'jupyter' if we're called from inside an asyncio loop, else 'plain'."""
    try:
        asyncio.get_running_loop()
        return "jupyter"
    except RuntimeError:
        return "plain"


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        with _LOCK:
            if _EXECUTOR is None:
                _EXECUTOR = ThreadPoolExecutor(max_workers=1,
                                               thread_name_prefix="pyktok_2026")
    return _EXECUTOR


def shutdown() -> None:
    """Cleanly shut down the worker thread, if one was spawned."""
    global _EXECUTOR, _MODE
    with _LOCK:
        if _EXECUTOR is not None:
            _EXECUTOR.shutdown(wait=False)
            _EXECUTOR = None
        _MODE = None  # next session re-detects


def jupyter_safe(fn: Callable) -> Callable:
    """Decorator: when called from inside an asyncio loop, run the body on a
    persistent worker thread with no running loop. Otherwise, call directly.

    The mode is decided on the FIRST call and reused for the rest of the
    session. Re-detecting per call breaks under Playwright.
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        global _MODE
        if _MODE is None:
            with _LOCK:
                if _MODE is None:
                    _MODE = _detect_mode()
        if _MODE == "jupyter":
            return _get_executor().submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)
    return wrapper
