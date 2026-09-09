# -*- coding: utf-8 -*-
"""workers/worker.py

This module implements the base class for all worker threads in the system.
"""
from contextlib import contextmanager
from threading import Thread
from threading import Event as ThreadEvent


class BaseWorker(Thread):
    r"""
    Base class for all worker threads.

    It extends `threading.Thread` and provides a standardized mechanism for stopping the thread
    using a `threading.Event`.
    """

    def  __init__(self):

        super(BaseWorker, self).__init__()

        self.stop_event = ThreadEvent()

    def get_stop_event(self):
        r"""
        Returns the stop event object.

        **Returns:**

        * **threading.Event**: The event used to signal the thread to stop.
        """
        return self.stop_event

    def stop(self):
        r"""
        Signals the worker thread to stop execution.
        """
        self.stop_event.set()

    def release_historian_socket(self):
        r"""
        Returns this worker's greenlet-local historian socket to the server.

        Peewee keeps the libpq socket in greenlet-local storage. A worker that
        exits without calling this leaves an `idle` backend that only the
        registry reaper or PostgreSQL can end, and every restart adds one more.
        Call it on the way out of `run()`.
        """
        try:
            from .. import PyAutomation
            from ..utils.db_connections import close_current_greenlet_connection

            close_current_greenlet_connection(getattr(PyAutomation(), "_db", None))
        except Exception:
            import logging

            logging.getLogger("pyautomation").debug(
                "worker historian socket release skipped name=%s",
                getattr(self, "name", "?"),
                exc_info=True,
            )

    @contextmanager
    def historian_cycle(self):
        r"""
        Wraps one worker cycle so the historian socket goes back when it ends.

        Only the resident roles (`RESIDENT_SOCKET_ROLES`) may hold a socket
        between cycles, because they touch the server every few seconds. A
        worker that idles minutes between ticks and keeps its socket costs a
        permanent `idle` backend and, worse, PostgreSQL's `idle_session_timeout`
        closes it underneath: the next tick then runs on a dead handle. Wrap the
        body of `run()`'s loop in this and the socket lives exactly as long as
        the work does.
        """
        try:
            yield
        finally:
            if not self._historian_socket_is_resident():
                self.release_historian_socket()

    @staticmethod
    def _historian_socket_is_resident():
        try:
            from ..utils.db_connections import keep_historian_socket

            return keep_historian_socket()
        except Exception:
            return False

    def __getstate__(self):

        state = self.__dict__.copy()
        del state['stop_event']
        return state

    def __setstate__(self, state):
        
        self.__dict__.update(state)
        self.stop_event = ThreadEvent()
