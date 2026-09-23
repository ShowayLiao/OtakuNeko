"""Validation and HTTP client helpers for user-selected provider endpoints."""

from __future__ import annotations

from dataclasses import dataclass
import socket
from ipaddress import ip_address
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx


_LOCAL_HOSTS = {"localhost", "localhost.localdomain"}


class ProviderEndpointError(ValueError):
    """Safe provider endpoint failure with a non-sensitive error category."""

    def __init__(self, message: str, *, category: str = "ssrf") -> None:
        self.provider_error_code = category
        super().__init__(message)


@dataclass(frozen=True)
class ProviderEndpointPolicy:
    """One immutable policy shared by initial requests and redirects."""

    allow_local: bool = False
    resolve_dns: bool = False
    allowed_hosts: frozenset[str] = frozenset()
    allowed_ports: frozenset[int] = frozenset()
    allowed_schemes: frozenset[str] = frozenset({"http", "https"})


def _canonical_hosts(values: Iterable[str]) -> frozenset[str]:
    return frozenset(
        item.strip().rstrip(".").lower()
        for item in values
        if item and item.strip()
    )


def parse_provider_allowlists(
    allowed_hosts: str,
    allowed_ports: str,
) -> tuple[frozenset[str], frozenset[int]]:
    """Parse server-owned endpoint allowlists without accepting wildcards."""
    hosts = _canonical_hosts(allowed_hosts.split(","))
    try:
        ports = frozenset(
            int(item.strip())
            for item in allowed_ports.split(",")
            if item.strip()
        )
    except ValueError as exc:
        raise ProviderEndpointError(
            "provider port allowlist is invalid", category="config"
        ) from exc
    if any(port < 1 or port > 65535 for port in ports):
        raise ProviderEndpointError(
            "provider port allowlist is invalid", category="config"
        )
    if any("*" in host or "/" in host for host in hosts):
        raise ProviderEndpointError(
            "provider host allowlist is invalid", category="config"
        )
    return hosts, ports


def validate_provider_configuration(
    *,
    deploy_mode: str,
    resolve_dns: bool,
    allowed_hosts: set[str] | frozenset[str],
    allowed_ports: set[int] | frozenset[int],
) -> None:
    """Fail closed for cloud deployments before an endpoint can be requested."""
    if deploy_mode.lower() == "local":
        return
    if not resolve_dns:
        raise ProviderEndpointError(
            "provider DNS resolution must be enabled in cloud mode",
            category="config",
        )
    if not allowed_hosts:
        raise ProviderEndpointError(
            "provider host allowlist is required in cloud mode",
            category="config",
        )
    if not allowed_ports:
        raise ProviderEndpointError(
            "provider port allowlist is required in cloud mode",
            category="config",
        )
    if any(port < 1 or port > 65535 for port in allowed_ports):
        raise ProviderEndpointError(
            "provider port allowlist is invalid",
            category="config",
        )


def make_provider_endpoint_policy(
    *,
    deploy_mode: str,
    resolve_dns: bool,
    allowed_hosts: set[str] | frozenset[str],
    allowed_ports: set[int] | frozenset[int],
) -> ProviderEndpointPolicy:
    validate_provider_configuration(
        deploy_mode=deploy_mode,
        resolve_dns=resolve_dns,
        allowed_hosts=allowed_hosts,
        allowed_ports=allowed_ports,
    )
    return ProviderEndpointPolicy(
        allow_local=deploy_mode.lower() == "local",
        resolve_dns=resolve_dns and deploy_mode.lower() != "local",
        allowed_hosts=_canonical_hosts(allowed_hosts),
        allowed_ports=frozenset(allowed_ports) if deploy_mode.lower() != "local" else frozenset(),
        allowed_schemes=(
            frozenset({"http", "https"})
            if deploy_mode.lower() == "local"
            else frozenset({"https"})
        ),
    )


def _blocked_address(address: str) -> bool:
    parsed = ip_address(address)
    # Reject all mapped forms. They are a common representation bypass for
    # IPv4 loopback/private checks and do not add value for provider egress.
    if parsed.version == 6 and parsed.ipv4_mapped is not None:
        return True
    return any(
        (
            parsed.is_private,
            parsed.is_loopback,
            parsed.is_link_local,
            parsed.is_reserved,
            parsed.is_multicast,
            parsed.is_unspecified,
        )
    )


def _validate_resolved_addresses(host: str, port: int) -> None:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, TimeoutError) as exc:
        raise ProviderEndpointError(
            "provider hostname could not be resolved", category="dns"
        ) from exc
    addresses = {str(record[4][0]).rstrip(".") for record in records if record[4]}
    if not addresses:
        raise ProviderEndpointError(
            "provider hostname resolved to no addresses", category="dns"
        )
    for address in addresses:
        try:
            blocked = _blocked_address(address)
        except ValueError:
            blocked = True
        if blocked:
            raise ProviderEndpointError(
                "provider endpoint resolved address is not public",
                category="ssrf",
            )


def is_local_endpoint(value: str | None) -> bool:
    if not value:
        return False
    host = (urlparse(value).hostname or "").rstrip(".").lower()
    return host in _LOCAL_HOSTS or host.endswith(".local") or host in {"127.0.0.1", "::1"}


def validate_provider_endpoint(
    value: str | None,
    *,
    allow_local: bool = False,
    resolve_dns: bool = False,
    allowed_hosts: set[str] | frozenset[str] | None = None,
    allowed_ports: set[int] | frozenset[int] | None = None,
    allowed_schemes: set[str] | frozenset[str] | None = None,
) -> str | None:
    """Validate an HTTP(S) provider URL before the server makes a request."""
    if value is None or not value.strip():
        return None

    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderEndpointError(
            "provider endpoint must be an http(s) URL with a host"
        )
    if allowed_schemes and parsed.scheme not in {
        scheme.lower() for scheme in allowed_schemes
    }:
        raise ProviderEndpointError("provider endpoint scheme is not allowlisted")
    if parsed.username or parsed.password:
        raise ProviderEndpointError("provider endpoint must not contain credentials")

    host = parsed.hostname.rstrip(".").lower()
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ProviderEndpointError(
            "provider endpoint has an invalid port", category="config"
        ) from exc
    normalized_allowed_hosts = _canonical_hosts(allowed_hosts or ())
    if normalized_allowed_hosts and host not in normalized_allowed_hosts:
        raise ProviderEndpointError("provider endpoint host is not allowlisted")
    if allowed_ports and port not in allowed_ports:
        raise ProviderEndpointError("provider endpoint port is not allowlisted")

    local_endpoint = is_local_endpoint(value)
    if local_endpoint and not allow_local:
        raise ProviderEndpointError("local provider endpoints are disabled")

    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if _blocked_address(host) and not (allow_local and local_endpoint):
            raise ProviderEndpointError("private or link-local provider endpoints are disabled")
    elif resolve_dns and not (allow_local and local_endpoint):
        _validate_resolved_addresses(host, port)

    return value.strip().rstrip("/")


def validate_provider_redirect(
    value: str | None,
    *,
    allow_local: bool = False,
    allowed_hosts: set[str] | frozenset[str] | None = None,
    allowed_ports: set[int] | frozenset[int] | None = None,
    allowed_schemes: set[str] | frozenset[str] | None = None,
) -> str | None:
    """Validate every redirect with DNS resolution and the same allowlist."""
    return validate_provider_endpoint(
        value,
        allow_local=allow_local,
        resolve_dns=True,
        allowed_hosts=allowed_hosts,
        allowed_ports=allowed_ports,
        allowed_schemes=allowed_schemes,
    )


def create_provider_http_client(
    policy: ProviderEndpointPolicy,
    *,
    timeout: float | httpx.Timeout = 90,
) -> httpx.AsyncClient:
    """Create the only HTTP client shape allowed for provider requests."""
    async def validate_redirect(response: httpx.Response) -> None:
        if not 300 <= response.status_code < 400:
            return
        location = response.headers.get("location")
        if not location:
            raise ProviderEndpointError("provider redirect has no destination")
        target = urljoin(str(response.request.url), location)
        validate_provider_redirect(
            target,
            allow_local=policy.allow_local,
            allowed_hosts=policy.allowed_hosts,
            allowed_ports=policy.allowed_ports,
            allowed_schemes=policy.allowed_schemes,
        )

    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        event_hooks={"response": [validate_redirect]},
    )
