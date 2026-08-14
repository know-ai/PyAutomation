import threading
from collections import deque


class Buffer:
    r"""
    Circular buffer with O(1) push.

    Backed by ``collections.deque(maxlen=size)``. ``forward`` inserts at the
    left (newest at index 0); ``backward`` appends (newest at the end).
    Thread-safe for concurrent DAS writers. Sequence-compatible for Plotly/Dash.
    """

    def __init__(self, size: int = 10, roll: str = "forward"):
        self._roll_type_allowed = ["forward", "backward"]
        self._size = size
        self._lock = threading.Lock()
        self.roll_type = "forward"
        self.roll = roll
        maxlen = max(int(size), 2) if size else 2
        self._data = deque(maxlen=maxlen)

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, value: int):
        if not isinstance(value, int):
            raise TypeError("Only integers are allowed")
        if value <= 1:
            raise ValueError(f"{value} must be greater than one (1)")
        with self._lock:
            self._size = value
            self._data = deque(self._data, maxlen=value)

    def last(self):
        with self._lock:
            if not self._data:
                return None
            if self.roll == "forward":
                return self._data[-1]
            return self._data[0]

    def current(self):
        with self._lock:
            if not self._data:
                return None
            if self.roll == "forward":
                return self._data[0]
            return self._data[-1]

    def previous_current(self):
        with self._lock:
            if len(self._data) < 2:
                return None
            if self.roll == "forward":
                return self._data[1]
            return self._data[-2]

    @property
    def roll(self):
        return self.roll_type

    @roll.setter
    def roll(self, value: str):
        if not isinstance(value, str):
            raise TypeError("Only strings are allowed")
        if value not in self._roll_type_allowed:
            raise ValueError(
                f"{value} is not allowed, you can only use: {self._roll_type_allowed}"
            )
        self.roll_type = value

    def __call__(self, value):
        with self._lock:
            if self.roll.lower() == "forward":
                self._data.appendleft(value)
            else:
                self._data.append(value)
        return self

    def __len__(self):
        return len(self._data)

    def count(self, value):
        """Compatibilidad con ``list.count`` (p. ej. pre-alarma ``count(True)``)."""
        with self._lock:
            return self._data.count(value)

    def __bool__(self):
        return bool(self._data)

    def __iter__(self):
        with self._lock:
            return iter(list(self._data))

    def __getitem__(self, index):
        with self._lock:
            if isinstance(index, slice):
                return list(self._data)[index]
            return self._data[index]

    def __array__(self, dtype=None):
        with self._lock:
            data = list(self._data)
        try:
            import numpy as np
            return np.asarray(data, dtype=dtype)
        except ImportError:
            return data

    def __repr__(self):
        return repr(list(self._data))
