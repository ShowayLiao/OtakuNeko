"""Validation helpers for user-selected model provider endpoints."""

from ipaddress import ip_address
from urllib.parse import urlparse


_LOCAL_HOSTS = {"localhost", "localhost.localdomain"}


def is_local_endpoint(value: str | None) -> bool:
    if not value:
        return False
    host = (urlparse(value).hostname or "").rstrip(".").lower()
    return host in _LOCAL_HOSTS or host.endswith(".local") or host == "127.0.0.1" or host == "::1"


def validate_provider_endpoint(
    value: str | None,
    *,
    allow_local: bool = False,
) -> str | None:
    """Validate an HTTP(S) provider URL before the server makes a request.

    ``allow_local`` is reserved for explicitly configured local development
    mode (for example an Ollama instance).  Production callers must not be
    able to turn the API into a proxy for private or metadata addresses.
    """
    if value is None or not value.strip():
        return None

    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("provider endpoint must be an http(s) URL with a host")
    if parsed.username or parsed.password:
        raise ValueError("provider endpoint must not contain credentials")

    host = parsed.hostname.rstrip(".").lower()
    if host in _LOCAL_HOSTS or host.endswith(".local"):
        if not allow_local:
            raise ValueError("local provider endpoints are disabled")
    else:
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise ValueError("private or link-local provider endpoints are disabled")

    return value.strip().rstrip("/")
