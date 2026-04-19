"""Thin requests wrapper with retry + exponential backoff for flaky sources."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def request(
    method: str,
    url: str,
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> requests.Response:
    """Issue an HTTP request with retry on transient errors.

    Retries on: connection errors, timeouts, and status codes in _RETRY_STATUSES.
    Backoff: exponential with jitter (base_delay * 2^(n-1) + uniform(0, base_delay)).
    Raises the final exception after max_attempts.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(method, url, **kwargs)
            if resp.status_code in _RETRY_STATUSES and attempt < max_attempts:
                logger.debug(
                    "HTTP %s from %s (attempt %d/%d) — retrying",
                    resp.status_code, url[:80], attempt, max_attempts,
                )
                last_exc = requests.HTTPError(f"status {resp.status_code}")
            else:
                return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            logger.debug(
                "%s on %s (attempt %d/%d) — retrying",
                type(exc).__name__, url[:80], attempt, max_attempts,
            )

        sleep_for = base_delay * (2 ** (attempt - 1)) + random.uniform(0, base_delay)
        time.sleep(sleep_for)

    assert last_exc is not None
    raise last_exc


def get(url: str, **kwargs: Any) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    return request("POST", url, **kwargs)
