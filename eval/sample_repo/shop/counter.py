import threading


class Counter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def increment(self, n=1):
        with self._lock:
            self._value += n
            return self._value

    @property
    def value(self):
        return self._value


class IdGenerator:
    def __init__(self, start=1):
        self._next = start
        self._lock = threading.Lock()

    def next_id(self):
        with self._lock:
            i = self._next
            self._next += 1
            return i
