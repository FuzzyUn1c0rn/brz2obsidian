"""Validated local origin and finite operational bounds, without credentials."""

import ipaddress
import math
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID


@dataclass(frozen=True)
class LocalApiSourceRef:
    brain_id: str

    def __post_init__(self):
        try:
            valid = (
                isinstance(self.brain_id, str)
                and str(UUID(self.brain_id)) == self.brain_id
                and UUID(self.brain_id).int != 0
            )
        except ValueError, TypeError, AttributeError:
            valid = False
        if not valid:
            raise ValueError("A canonical nonzero Brain UUID is required") from None


@dataclass(frozen=True)
class LocalApiConfig:
    api_url: str = "http://127.0.0.1:11522/api"
    search_initial_results: int = 5000
    search_timeout: float = 300
    search_max_response_bytes: int = 128000000
    search_max_results: int | None = None
    request_timeout: float = 30
    max_response_bytes: int = 16000000
    max_requests: int = 100000
    max_traversal_items: int = 100000
    max_total_capture_bytes: int = 1000000000
    max_payload_bytes: int = 256000000
    include_pins: bool = False

    def __post_init__(self):
        try:
            if not isinstance(self.api_url, str) or any(
                ord(c) < 33 or ord(c) > 126 for c in self.api_url
            ):
                raise ValueError
            url = urlsplit(self.api_url)
            host = url.hostname
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback
            if (
                not local
                or url.scheme not in {"http", "https"}
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or url.path not in {"/api", "/api/"}
                or (url.port is not None and not 1 <= url.port <= 65535)
            ):
                raise ValueError
        except ValueError, TypeError, AttributeError:
            raise ValueError(
                "The API address must be a credential-free local HTTP origin ending in /api"
            ) from None
        for name in [
            "search_initial_results",
            "search_max_response_bytes",
            "max_response_bytes",
            "max_requests",
            "max_traversal_items",
            "max_total_capture_bytes",
            "max_payload_bytes",
        ]:
            value = getattr(self, name)
            if type(value) is not int or value <= 0 or value > 9223372036854775807:
                raise ValueError("Acquisition limits must be positive bounded integers")
        if self.search_initial_results > 2147483647:
            raise ValueError("Search result limits must fit the API integer range")
        if self.search_max_results is not None and (
            type(self.search_max_results) is not int
            or not 1 <= self.search_max_results <= 2147483647
        ):
            raise ValueError(
                "Optional search result ceiling must fit the API integer range"
            )
        for name in ["search_timeout", "request_timeout"]:
            value = getattr(self, name)
            if (
                type(value) not in {int, float}
                or not math.isfinite(value)
                or value < 0.001
                or value > 86400
                or Decimal(str(value)) * 1000
                != (Decimal(str(value)) * 1000).to_integral_value()
            ):
                raise ValueError(
                    "Acquisition timeouts require positive finite milliseconds, at most one day"
                )
        if type(self.include_pins) is not bool:
            raise ValueError("Optional seed selection must be boolean")

    def audit_limits(self):
        return {
            "initial_search_results": self.search_initial_results,
            "search_budget_ms": int(Decimal(str(self.search_timeout)) * 1000),
            "search_max_response_bytes": self.search_max_response_bytes,
            "max_search_results": self.search_max_results,
            "request_timeout_ms": int(Decimal(str(self.request_timeout)) * 1000),
            "max_response_bytes": self.max_response_bytes,
            "max_total_capture_bytes": self.max_total_capture_bytes,
            "max_requests": self.max_requests,
            "max_traversal_items": self.max_traversal_items,
            "max_payload_bytes": self.max_payload_bytes,
        }
