"""
Rate limiter for Binance API requests.
Implements token bucket algorithm with per-endpoint limits.
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, Tuple


class RateLimiter:
    """
    Simple token bucket rate limiter.
    Limits: 20 requests per second overall, 2400 per minute.
    """

    def __init__(self, max_requests_per_second: int = 10):
        self.max_requests_per_sec = max_requests_per_second
        self.tokens = max_requests_per_second
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            now = time.time()
            # Refill tokens based on time elapsed
            elapsed = now - self.last_refill
            new_tokens = elapsed * self.max_requests_per_sec
            if new_tokens > 0:
                self.tokens = min(self.max_requests_per_sec, self.tokens + new_tokens)
                self.last_refill = now

            if self.tokens >= 1:
                self.tokens -= 1
                return

            # Wait for next token
            wait_time = (1.0 / self.max_requests_per_sec)
            await asyncio.sleep(wait_time)
            await self.acquire()
