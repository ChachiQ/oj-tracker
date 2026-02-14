import time
import threading


class RateLimiter:
    """Thread-safe rate limiter for web scraping."""

    def __init__(self, min_interval: float = 2.0):
        self.min_interval = min_interval
        self._last_request_time = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request_time = time.time()


_platform_limiters = {}
_registry_lock = threading.Lock()


def get_platform_limiter(platform: str, min_interval: float = 2.0) -> RateLimiter:
    """Get or create a shared rate limiter for a platform."""
    with _registry_lock:
        if platform not in _platform_limiters:
            _platform_limiters[platform] = RateLimiter(min_interval)
        return _platform_limiters[platform]
