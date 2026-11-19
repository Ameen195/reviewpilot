import threading
import time


class TTLCache:
    def __init__(self, ttl=60.0, max_items=128):
        self.ttl = ttl
        self.max_items = max_items
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return default
            value, expires = item
            if expires < time.monotonic():
                del self._data[key]
                return default
            return value

    def set(self, key, value):
        with self._lock:
            if len(self._data) >= self.max_items and key not in self._data:
                oldest = min(self._data, key=lambda k: self._data[k][1])
                del self._data[oldest]
            self._data[key] = (value, time.monotonic() + self.ttl)

    def __len__(self):
        with self._lock:
            return len(self._data)
