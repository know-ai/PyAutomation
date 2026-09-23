"""OS thread and queue primitives that survive a gevent monkey patch."""

from __future__ import annotations


def _original(module: str, name: str):
    try:
        from gevent.monkey import get_original

        return get_original(module, name)
    except Exception:
        import importlib

        return getattr(importlib.import_module(module), name)


Thread = _original("threading", "Thread")
Event = _original("threading", "Event")
Lock = _original("threading", "Lock")
Queue = _original("queue", "Queue")
Empty = _original("queue", "Empty")


_LOOP_BY_THREAD: dict[int, object] = {}


def _thread_ident() -> int:
    """Ident that differs per OS thread after gevent's patch.

    ``gevent.monkey.get_original('threading', 'get_ident')`` returns the hub
    ident from every thread, so it cannot key this map. Complexity: O(1).
    """
    import threading

    return threading.get_ident()


def _thread_get_running_loop():
    """Per-OS-thread running loop. Complexity: O(1)."""
    return _LOOP_BY_THREAD.get(_thread_ident())


def _thread_set_running_loop(loop) -> None:
    """Complexity: O(1)."""
    ident = _thread_ident()
    if loop is None:
        _LOOP_BY_THREAD.pop(ident, None)
    else:
        _LOOP_BY_THREAD[ident] = loop


def _thread_get_running_loop_or_raise():
    loop = _thread_get_running_loop()
    if loop is None:
        raise RuntimeError("no running event loop")
    return loop


def _thread_current_task(loop=None):
    """Current task for this OS thread. Complexity: O(1).

    The C ``current_task`` reads the process-wide running-loop slot. That slot
    stays empty because ``_set_running_loop`` is the per-thread map above, so
    ``asyncio.wait_for`` raised ``no running event loop`` inside a live loop.
    """
    import asyncio.tasks as tasks

    if loop is None:
        loop = _thread_get_running_loop_or_raise()
    return tasks._current_tasks.get(loop)


def install_asyncio_thread_local() -> None:
    """Give each OS thread its own asyncio running-loop pointer.

    Under gevent the C ``_get_running_loop`` is one slot for the whole process.
    The embedded server and the field client then cannot each call ``asyncio.run``.
    These wrappers key the loop by the native thread id. Complexity: O(1).
    """
    import asyncio
    import asyncio.events as events
    import asyncio.tasks as tasks

    if getattr(events, "_pyautomation_thread_loop", False):
        return
    events._get_running_loop = _thread_get_running_loop
    events._set_running_loop = _thread_set_running_loop
    events.get_running_loop = _thread_get_running_loop_or_raise
    asyncio._get_running_loop = _thread_get_running_loop
    asyncio._set_running_loop = _thread_set_running_loop
    asyncio.get_running_loop = _thread_get_running_loop_or_raise
    tasks.current_task = _thread_current_task
    asyncio.current_task = _thread_current_task
    events._pyautomation_thread_loop = True


install_asyncio_thread_local()
