"""Circuit breaker pattern for API calls."""

import threading
from datetime import datetime
from typing import Optional


class CircuitBreaker:
    """Circuit breaker pattern for API calls"""

    def __init__(self, failure_threshold: int = 5, recovery_time: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        self.lock = threading.Lock()

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.state = "closed"

    def record_failure(self) -> None:
        with self.lock:
            self.failures += 1
            self.last_failure = datetime.now()
            if self.failures >= self.failure_threshold:
                self.state = "open"

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                if self.last_failure and (datetime.now() - self.last_failure).total_seconds() > self.recovery_time:
                    self.state = "half-open"
                    return True
            return False
